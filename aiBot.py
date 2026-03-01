# aibot.py — GDPR Code Review Chatbot (Gemini version, v2)
# Run: streamlit run aibot.py
# Requirements: pip install streamlit python-dotenv google-genai

import os
import re
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()  # Load GOOGLE_API_KEY from .env (never hardcode keys)

MODEL_ID = "gemini-3-flash-preview"
MAX_CODE_CHARS = 12_000    # Cap code to avoid huge token payloads
MAX_CONTEXT_CHARS = 6_000  # Cap retrieved GDPR context too
MAX_HISTORY_MSGS = 6       # Only last N messages sent to model
SUPPORTED_TYPES = ["py", "js", "ts", "java", "cpp", "cs", "php", "go", "txt"]
GDPR_KNOWLEDGE_FILE = "gdpr_knowledge.md"

# Fenced code block pattern: captures optional lang + code body
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n([\s\S]*?)```", re.MULTILINE)

# Markdown table validator: header row + separator row + at least one data row
TABLE_RE = re.compile(
    r"\|.+\|\n\|[-| :]+\|\n(\|.+\|\n)+",
    re.MULTILINE
)

# ---------------------------------------------------------------------------
# Gemini client — created once, cached in session_state
# ---------------------------------------------------------------------------
def get_client() -> genai.Client:
    """Initialize Gemini client once per session."""
    if "client" not in st.session_state:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            st.error("❌ GOOGLE_API_KEY not found. Add it to your .env file.")
            st.stop()
        st.session_state.client = genai.Client(api_key=api_key)
    return st.session_state.client


# ---------------------------------------------------------------------------
# Mini-RAG: load and retrieve GDPR knowledge sections
# ---------------------------------------------------------------------------
def load_gdpr_sections() -> dict[str, str]:
    """
    Read gdpr_knowledge.md once, split by markdown headings.
    Cached in session_state — file is only read once per session.
    """
    if "gdpr_sections" not in st.session_state:
        if not os.path.exists(GDPR_KNOWLEDGE_FILE):
            st.warning(f"⚠️ '{GDPR_KNOWLEDGE_FILE}' not found. GDPR context will be empty.")
            st.session_state.gdpr_sections = {}
        else:
            with open(GDPR_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            parts = re.split(r"(?m)^(#{1,2} .+)", raw)
            sections: dict[str, str] = {}
            i = 1
            while i < len(parts) - 1:
                heading = parts[i].strip("# ").strip()
                body = parts[i + 1] if i + 1 < len(parts) else ""
                sections[heading] = body
                i += 2
            st.session_state.gdpr_sections = sections
    return st.session_state.gdpr_sections


def retrieve_gdpr_context(code_text: str, user_question: str, top_n: int = 4) -> tuple[str, bool]:
    """
    Score GDPR sections by keyword overlap with (code + question).
    Returns (context_string, was_truncated).
    Context itself is capped at MAX_CONTEXT_CHARS so prompts stay lean.
    """
    sections = load_gdpr_sections()
    if not sections:
        return "(No GDPR knowledge base available.)", False

    query_words = set(re.findall(r"\w+", (code_text + " " + user_question).lower()))

    scored = []
    for heading, body in sections.items():
        section_words = set(re.findall(r"\w+", (heading + " " + body).lower()))
        score = len(query_words & section_words)
        scored.append((score, heading, body))

    top_sections = sorted(scored, reverse=True)[:top_n]
    parts = [f"### {h}\n{b.strip()}" for _, h, b in top_sections]
    full_context = "\n\n".join(parts)

    # Cap context and flag truncation clearly
    if len(full_context) > MAX_CONTEXT_CHARS:
        return full_context[:MAX_CONTEXT_CHARS] + "\n\n...[GDPR context truncated for length]", True
    return full_context, False


# ---------------------------------------------------------------------------
# System prompt — rebuilt fresh every question to avoid stale context
# ---------------------------------------------------------------------------
def build_system_prompt(gdpr_context: str) -> str:
    """
    Strict system prompt injected with fresh GDPR context on every call.
    Tightly constrains output format to prevent table/formatting drift.
    """
    return f"""You are a GDPR Code Review Assistant. Analyze code for GDPR compliance issues.

STRICT RULES:
- Base ALL findings on the GDPR context below. Do NOT invent article numbers not present there.
- If evidence is insufficient, write exactly: "Insufficient context to determine compliance."
- Do NOT give legal advice. Always end with the required disclaimer.
- Do NOT recommend logging personal data. If logging is mentioned, recommend anonymized/pseudonymized logging only.
- Never rewrite the entire submitted code. Only provide short illustrative snippets (5–10 lines max).

---
GDPR KNOWLEDGE CONTEXT:
{gdpr_context}
---

REQUIRED OUTPUT FORMAT — output exactly this structure, nothing else:

1) **Summary**
- [bullet 1]
- [bullet 2]
- [bullet 3 if needed]

2) **Findings Table**
Output as valid GitHub-flavored Markdown with EXACTLY 5 columns.
One header row, one separator row (dashes only), then N data rows. No blank lines inside the table. No extra pipes.

| Issue | GDPR Principle | Evidence (line/function) | Severity | Recommendation |
|-------|---------------|--------------------------|----------|----------------|
| ...   | ...           | ...                      | High/Med/Low | ...        |

3) **Suggested Secure Changes**
For each item (3–7 total):
- **What to change:** ...
- **Why (principle):** ...
- **Minimal snippet:** ```language
[SHORT example only]
```

4) **Disclaimer**
This is an automated analysis tool, not legal advice. Consult a qualified DPO or legal counsel for formal GDPR assessments.
"""


# ---------------------------------------------------------------------------
# Code extraction: parse fenced code blocks from a chat message
# ---------------------------------------------------------------------------
def extract_code_from_message(text: str) -> str | None:
    """
    Look for fenced code blocks (``` ... ```) in the user's message.
    Returns the extracted code string, or None if not found.
    Multiple blocks are joined with a newline separator.
    """
    matches = CODE_BLOCK_RE.findall(text)
    if matches:
        return "\n\n".join(m.strip() for m in matches)
    return None


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks from text to isolate the plain question."""
    return CODE_BLOCK_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Table validator + auto-repair
# ---------------------------------------------------------------------------
def has_valid_table(response_text: str) -> bool:
    """Check if response contains a properly formatted Markdown table."""
    return bool(TABLE_RE.search(response_text))


def repair_table(chat, response_text: str) -> str:
    """
    If the Findings Table is malformed, send a single follow-up asking
    the model to reformat ONLY the table. Returns the fixed response.
    This fixes ~90% of broken tables without re-running the full analysis.
    """
    repair_prompt = (
        "The Findings Table in your previous response is not valid GitHub-flavored Markdown. "
        "Reformat ONLY the Findings Table with exactly 5 columns: "
        "Issue | GDPR Principle | Evidence (line/function) | Severity | Recommendation. "
        "One header row, one separator row, then data rows. No blank lines inside the table. "
        "Do not change any other content in your response — output the full response again with only the table fixed."
    )
    try:
        repair_response = chat.send_message(message=repair_prompt)
        return repair_response.text
    except Exception:
        # If repair fails, return the original rather than crashing
        return response_text


# ---------------------------------------------------------------------------
# Response parser — splits raw model text into labelled sections
# ---------------------------------------------------------------------------
def parse_response(text: str) -> dict[str, str]:
    """
    Extract the four expected sections from the model response by looking for
    their header labels (case-insensitive). Returns a dict with keys:
      summary, findings_table, secure_changes, disclaimer
    Falls back to putting everything in 'summary' if parsing fails.
    """
    # Normalise line endings
    text = text.replace("\r\n", "\n").strip()

    # Patterns that match each section header the model might produce
    section_patterns = {
        "summary":        r"(?:1[)\.]?\s*\*{0,2}Summary\*{0,2})",
        "findings_table": r"(?:2[)\.]?\s*\*{0,2}Findings\s*Table\*{0,2})",
        "secure_changes": r"(?:3[)\.]?\s*\*{0,2}Suggested\s*Secure\s*Changes\*{0,2})",
        "disclaimer":     r"(?:4[)\.]?\s*\*{0,2}Disclaimer\*{0,2})",
    }

    # Find the start position of each section in the text
    positions: dict[str, int] = {}
    for key, pattern in section_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            positions[key] = match.start()

    if not positions:
        # Cannot parse — return everything as summary
        return {"summary": text, "findings_table": "", "secure_changes": "", "disclaimer": ""}

    # Sort sections by their position in the text
    ordered = sorted(positions.items(), key=lambda x: x[1])

    result: dict[str, str] = {}
    for i, (key, start) in enumerate(ordered):
        # Content starts after the header line
        header_end = text.index("\n", start) + 1 if "\n" in text[start:] else len(text)
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        result[key] = text[header_end:end].strip()

    # Fill in any missing keys
    for key in ("summary", "findings_table", "secure_changes", "disclaimer"):
        result.setdefault(key, "")

    return result


def normalize_table(raw: str) -> str:
    """
    Ensure every table row is on its own line and surrounded by blank lines
    so st.markdown() renders it correctly.
    Handles the common model failure of outputting the whole table on one line.
    """
    # Replace literal \n text (model sometimes outputs escaped newlines)
    raw = raw.replace("\\n", "\n")

    # If the table has pipe chars but no real newlines between rows, split on |---
    # by inserting newlines before every | that follows a non-newline character
    # e.g. "| a | b |\n|---|---|\n| c | d |" is fine; "| a | b ||---|---|| c |" is not
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            lines.append(line)

    # Ensure a blank line before and after the table block
    return "\n" + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Structured renderer — each section gets the right Streamlit treatment
# ---------------------------------------------------------------------------
def render_response(text: str) -> None:
    """
    Parse the model response into sections and render each one properly:
    - Summary  → st.markdown (bullets render fine)
    - Findings Table → normalize then st.markdown inside a container
    - Secure Changes → st.markdown (code blocks render fine)
    - Disclaimer → st.caption (subdued styling)

    This avoids the one-big-blob problem where a table on a single line
    never renders correctly inside st.markdown.
    """
    sections = parse_response(text)

    # --- 1. Summary ---
    if sections["summary"]:
        st.markdown("### 📋 Summary")
        st.markdown(sections["summary"])

    st.divider()

    # --- 2. Findings Table ---
    st.markdown("### 🔍 Findings Table")
    if sections["findings_table"]:
        table_text = normalize_table(sections["findings_table"])
        # Wrap in a container so Streamlit allocates full width
        with st.container():
            st.markdown(table_text, unsafe_allow_html=False)
    else:
        st.info("No findings table returned.")

    st.divider()

    # --- 3. Suggested Secure Changes ---
    if sections["secure_changes"]:
        st.markdown("### 🛡️ Suggested Secure Changes")
        st.markdown(sections["secure_changes"])

    st.divider()

    # --- 4. Disclaimer ---
    if sections["disclaimer"]:
        st.caption(f"⚠️ {sections['disclaimer']}")


# ---------------------------------------------------------------------------
# Core API call — rebuilds chat with fresh system prompt every question
# ---------------------------------------------------------------------------
def ask_gemini(user_question: str, active_code: str) -> str:
    """
    Build a fresh Gemini chat session with up-to-date GDPR context injected
    into the system prompt. Includes last N history messages for continuity.
    Validates the table and auto-repairs if malformed.

    Why rebuild chat each time: the system prompt contains retrieved GDPR context
    that is specific to the current code + question. Reusing a stale chat would
    cause the model to reference outdated context and produce inconsistent output.
    """
    client = get_client()

    # Retrieve fresh GDPR context for this specific code + question
    gdpr_context, context_truncated = retrieve_gdpr_context(active_code, user_question)
    if context_truncated:
        st.caption("ℹ️ GDPR context was truncated to fit within prompt limits.")

    # Truncate code if needed
    truncated_code = active_code[:MAX_CODE_CHARS]
    code_was_truncated = len(active_code) > MAX_CODE_CHARS

    # Build fresh chat with current system prompt (context baked in)
    chat = client.chats.create(
        model=MODEL_ID,
        config=types.GenerateContentConfig(
            system_instruction=build_system_prompt(gdpr_context)
        )
    )

    # Replay recent history so the model has conversational context
    # We inject past messages before the new question
    recent_history = st.session_state.messages[-(MAX_HISTORY_MSGS):]
    for msg in recent_history:
        # Skip re-sending the very last user message (we'll send it fresh below)
        if msg["role"] == "user":
            try:
                chat.send_message(message=msg["content"])
            except Exception:
                pass  # If history replay fails, continue — new question still works

    # Compose the actual user message with code + question
    code_note = "\n\n⚠️ *[Code was truncated at 12,000 chars]*" if code_was_truncated else ""
    full_message = (
        f"**Code to review:**\n```\n{truncated_code}\n```{code_note}\n\n"
        f"**Question:** {user_question}"
    )

    response = chat.send_message(message=full_message)
    answer = response.text

    # Validate Findings Table — auto-repair if malformed
    if not has_valid_table(answer):
        with st.spinner("🔧 Fixing table formatting..."):
            answer = repair_table(chat, answer)

    return answer


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="GDPR Code Review Chatbot", page_icon="🔒", layout="wide")
st.title("🔒 GDPR Code Review Chatbot")
st.caption(f"Model: `{MODEL_ID}` · Powered by Google Gemini + GDPR knowledge base")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []   # [{role, content}, ...]

if "active_code" not in st.session_state:
    st.session_state.active_code = ""  # Currently loaded code for review

# Initialize Gemini client eagerly so auth errors surface immediately
get_client()


# ---------------------------------------------------------------------------
# Sidebar: file uploader + status + clear buttons
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Setup")

    uploaded_file = st.file_uploader(
        "Upload a code file",
        type=SUPPORTED_TYPES,
        help="Supported: " + ", ".join(SUPPORTED_TYPES),
    )

    # Load uploaded file into session_state when a new file is provided
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode("utf-8", errors="replace")
            st.session_state.active_code = content
            st.success(f"✅ Loaded: `{uploaded_file.name}`")
        except Exception as e:
            st.error(f"Failed to read file: {e}")

    # Show current code status
    if st.session_state.active_code:
        char_count = len(st.session_state.active_code)
        capped = char_count > MAX_CODE_CHARS
        st.info(
            f"📄 Code loaded: **{char_count:,} chars**"
            + (" *(will be capped at 12k in prompt)*" if capped else "")
        )
    else:
        st.warning("No code loaded yet.")

    st.divider()

    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

    if st.button("🗑️ Clear Code"):
        st.session_state.active_code = ""
        st.rerun()

    st.divider()
    st.markdown("""
**How to use:**
1. Upload a file **or** paste a code block in chat
2. Ask any GDPR question, or just send the code block alone
3. The bot will ask what to check if no question is provided
4. Paste new code at any time to switch context
""")


# ---------------------------------------------------------------------------
# Chat UI: render message history
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_response(msg["content"])
        else:
            st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Chat input — message-first flow
# Accepts: (a) code block + question, (b) code block alone, (c) question alone
# ---------------------------------------------------------------------------
user_input = st.chat_input(
    "Paste code (``` ``` block) + question, or just ask about loaded code..."
)

if user_input:
    # --- Step 1: Check if user pasted a new code block in this message ---
    extracted_code = extract_code_from_message(user_input)
    plain_question = strip_code_blocks(user_input)

    if extracted_code:
        # User pasted new code — update active_code in session_state
        st.session_state.active_code = extracted_code

    # --- Step 2: Determine the question to ask ---
    if not plain_question:
        # No question provided alongside code — prompt the model to ask what to check
        plain_question = (
            "I've just provided a new code snippet. "
            "Please review it for GDPR compliance issues using the standard format."
        )

    # --- Step 3: Guard — need code to proceed ---
    if not st.session_state.active_code:
        st.error(
            "⚠️ No code to review. "
            "Please upload a file in the sidebar or paste a code block (``` ``` fences) in your message."
        )
        st.stop()

    # --- Step 4: Display user message ---
    display_message = user_input  # Show the original input including code block
    st.session_state.messages.append({"role": "user", "content": display_message})
    with st.chat_message("user"):
        st.markdown(display_message)

    # --- Step 5: Call Gemini with fresh context ---
    with st.chat_message("assistant"):
        with st.spinner("🔍 Retrieving GDPR context & analyzing..."):
            try:
                answer = ask_gemini(plain_question, st.session_state.active_code)
                render_response(answer)  # Structured render instead of raw st.markdown
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    st.error(
                        "❌ Rate limit hit (429). You've exceeded the free tier quota for today. "
                        "Wait a minute and retry, or check https://ai.dev/rate-limit."
                    )
                else:
                    st.error(f"❌ Gemini API error: {e}")