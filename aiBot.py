# aibot.py — GDPR Code Review Chatbot (Gemini, v3)
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
load_dotenv()

MODEL_ID = "gemini-3-flash-preview"
MAX_CODE_CHARS = 12_000
MAX_CONTEXT_CHARS = 6_000
MAX_HISTORY_MSGS = 6
SUPPORTED_TYPES = ["py", "js", "ts", "java", "cpp", "cs", "php", "go", "txt"]
GDPR_KNOWLEDGE_FILE = "gdpr_knowledge.md"

# Lenient fenced code block pattern — handles optional lang, spaces, any line ending
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?[ \t]*[\r\n]*([\s\S]*?)```", re.MULTILINE)

# Markdown table validator
TABLE_RE = re.compile(r"\|.+\|\n\|[-| :]+\|\n(\|.+\|\n)+", re.MULTILINE)

# Keywords that indicate a line is code syntax, not natural language
CODE_INDICATORS = (
    "def ", "class ", "import ", "from ", "return ", "if __",
    "function ", "const ", "let ", "var ", "=>", "public ", "private ",
    "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE",
    "<?php", "#include", "package ", "using ", "};", "();",
    "@app.", "console.log", "print(", "System.out", "cout <<",
)


# ---------------------------------------------------------------------------
# Gemini client — created once, cached in session_state
# ---------------------------------------------------------------------------
def get_client() -> genai.Client:
    """Initialize Gemini client once per session."""
    if "client" not in st.session_state:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            st.error("GOOGLE_API_KEY not found. Add it to your .env file.")
            st.stop()
        st.session_state.client = genai.Client(api_key=api_key)
    return st.session_state.client


# ---------------------------------------------------------------------------
# Mini-RAG: load and retrieve GDPR knowledge sections
# ---------------------------------------------------------------------------
def load_gdpr_sections() -> dict:
    """Read gdpr_knowledge.md once, split by headings. Cached in session_state."""
    if "gdpr_sections" not in st.session_state:
        if not os.path.exists(GDPR_KNOWLEDGE_FILE):
            st.warning(f"'{GDPR_KNOWLEDGE_FILE}' not found. GDPR context will be empty.")
            st.session_state.gdpr_sections = {}
        else:
            with open(GDPR_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            parts = re.split(r"(?m)^(#{1,2} .+)", raw)
            sections = {}
            i = 1
            while i < len(parts) - 1:
                heading = parts[i].strip("# ").strip()
                body = parts[i + 1] if i + 1 < len(parts) else ""
                sections[heading] = body
                i += 2
            st.session_state.gdpr_sections = sections
    return st.session_state.gdpr_sections


def retrieve_gdpr_context(code_text: str, user_question: str, top_n: int = 4):
    """
    Score GDPR sections by keyword overlap. Returns (context_string, was_truncated).
    Context is capped at MAX_CONTEXT_CHARS to keep prompts lean.
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

    if len(full_context) > MAX_CONTEXT_CHARS:
        return full_context[:MAX_CONTEXT_CHARS] + "\n\n...[GDPR context truncated]", True
    return full_context, False


# ---------------------------------------------------------------------------
# System prompt — rebuilt fresh every question with current GDPR context
# ---------------------------------------------------------------------------
def build_system_prompt(gdpr_context: str) -> str:
    return f"""You are a GDPR Code Review Assistant. Analyze code for GDPR compliance issues.

STRICT RULES:
- Base ALL findings on the GDPR context below. Do NOT invent article numbers not present there.
- If evidence is insufficient, write: "Insufficient context to determine compliance."
- Do NOT give legal advice. Always end with the required disclaimer.
- Do NOT recommend logging personal data. If logging is needed, recommend anonymized/pseudonymized logging only.
- Never rewrite the entire submitted code. Only short illustrative snippets (5-10 lines max).

---
GDPR KNOWLEDGE CONTEXT:
{gdpr_context}
---

REQUIRED OUTPUT FORMAT — output exactly this structure:

1) **Summary**
- [bullet 1]
- [bullet 2]
- [bullet 3 if needed]

2) **Findings Table**
Output as valid GitHub-flavored Markdown with EXACTLY 5 columns.
One header row, one separator row, then data rows. No blank lines inside the table.

| Issue | GDPR Principle | Evidence (line/function) | Severity | Recommendation |
|-------|---------------|--------------------------|----------|----------------|
| ...   | ...           | ...                      | High/Med/Low | ...        |

3) **Suggested Secure Changes**
For each item (3-7 total):
- **What to change:** ...
- **Why (principle):** ...
- **Minimal snippet:** (short example only)

4) **Disclaimer**
This is an automated analysis tool, not legal advice. Consult a qualified DPO or legal counsel for formal GDPR assessments.
"""


# ---------------------------------------------------------------------------
# Code extraction — fenced blocks first, raw code heuristic as fallback
# ---------------------------------------------------------------------------
def looks_like_code(text: str) -> bool:
    """
    Heuristic: checks if a plain-text message is actually raw pasted code.
    Returns True if more than 30% of non-empty lines contain code syntax.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 3:
        return False
    code_line_count = sum(
        1 for line in lines
        if any(kw in line for kw in CODE_INDICATORS)
    )
    return (code_line_count / len(lines)) > 0.30


def extract_code_from_message(text: str):
    """
    Two-stage extraction:
    1. Fenced code blocks (``` ... ```) — explicit, always preferred
    2. Raw code heuristic — whole message treated as code if it looks like it
    Returns code string or None.
    """
    # Stage 1: fenced blocks
    matches = CODE_BLOCK_RE.findall(text)
    if matches:
        return "\n\n".join(m.strip() for m in matches)

    # Stage 2: raw code fallback
    if looks_like_code(text):
        return text.strip()

    return None


def strip_code_blocks(text: str) -> str:
    """
    Remove fenced code blocks to isolate the plain question.
    Returns empty string if the whole message was raw code (no separate question).
    """
    cleaned = CODE_BLOCK_RE.sub("", text).strip()
    if looks_like_code(cleaned):
        return ""
    return cleaned


# ---------------------------------------------------------------------------
# Table validator + auto-repair
# ---------------------------------------------------------------------------
def has_valid_table(response_text: str) -> bool:
    return bool(TABLE_RE.search(response_text))


def repair_table(chat, response_text: str) -> str:
    """Send a targeted follow-up to fix a malformed table. Fixes ~90% of cases."""
    repair_prompt = (
        "The Findings Table in your previous response is not valid GitHub-flavored Markdown. "
        "Reformat ONLY the Findings Table with exactly 5 columns: "
        "Issue | GDPR Principle | Evidence (line/function) | Severity | Recommendation. "
        "One header row, one separator row, then data rows. No blank lines inside the table. "
        "Output the full response again with only the table fixed."
    )
    try:
        return chat.send_message(message=repair_prompt).text
    except Exception:
        return response_text


# ---------------------------------------------------------------------------
# Response parser — splits raw model text into labelled sections
# ---------------------------------------------------------------------------
def parse_response(text: str) -> dict:
    """
    Extract the four expected sections from the model response.
    Falls back to putting everything in 'summary' if parsing fails.
    """
    text = text.replace("\r\n", "\n").strip()

    section_patterns = {
        "summary":        r"(?:1[)\.]?\s*\*{0,2}Summary\*{0,2})",
        "findings_table": r"(?:2[)\.]?\s*\*{0,2}Findings\s*Table\*{0,2})",
        "secure_changes": r"(?:3[)\.]?\s*\*{0,2}Suggested\s*Secure\s*Changes\*{0,2})",
        "disclaimer":     r"(?:4[)\.]?\s*\*{0,2}Disclaimer\*{0,2})",
    }

    positions = {}
    for key, pattern in section_patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            positions[key] = match.start()

    if not positions:
        return {"summary": text, "findings_table": "", "secure_changes": "", "disclaimer": ""}

    ordered = sorted(positions.items(), key=lambda x: x[1])
    result = {}
    for i, (key, start) in enumerate(ordered):
        header_end = text.index("\n", start) + 1 if "\n" in text[start:] else len(text)
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        result[key] = text[header_end:end].strip()

    for key in ("summary", "findings_table", "secure_changes", "disclaimer"):
        result.setdefault(key, "")

    return result


def normalize_table(raw: str) -> str:
    """Ensure every table row is on its own line so st.markdown renders it correctly."""
    raw = raw.replace("\\n", "\n")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n" + "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Structured renderer — each section gets the right Streamlit widget
# ---------------------------------------------------------------------------
def render_response(text: str) -> None:
    sections = parse_response(text)

    if sections["summary"]:
        st.markdown("### 📋 Summary")
        st.markdown(sections["summary"])

    st.divider()

    st.markdown("### 🔍 Findings Table")
    if sections["findings_table"]:
        with st.container():
            st.markdown(normalize_table(sections["findings_table"]))
    else:
        st.info("No findings table returned.")

    st.divider()

    if sections["secure_changes"]:
        st.markdown("### 🛡️ Suggested Secure Changes")
        st.markdown(sections["secure_changes"])

    st.divider()

    if sections["disclaimer"]:
        st.caption(f"⚠️ {sections['disclaimer']}")


# ---------------------------------------------------------------------------
# Core API call
# ---------------------------------------------------------------------------
def ask_gemini(user_question: str, active_code: str) -> str:
    """
    Build a fresh Gemini chat session with up-to-date GDPR context in the system
    prompt. Rebuilds every call so context is never stale. Validates and
    auto-repairs the Findings Table if malformed.
    """
    client = get_client()

    gdpr_context, context_truncated = retrieve_gdpr_context(active_code, user_question)
    if context_truncated:
        st.caption("ℹ️ GDPR context was truncated to fit within prompt limits.")

    truncated_code = active_code[:MAX_CODE_CHARS]
    code_was_truncated = len(active_code) > MAX_CODE_CHARS

    chat = client.chats.create(
        model=MODEL_ID,
        config=types.GenerateContentConfig(
            system_instruction=build_system_prompt(gdpr_context)
        )
    )

    # Replay recent history for conversational continuity
    recent_history = st.session_state.messages[-MAX_HISTORY_MSGS:]
    for msg in recent_history:
        if msg["role"] == "user":
            try:
                chat.send_message(message=msg["content"])
            except Exception:
                pass

    code_note = "\n\n[Code truncated at 12,000 chars]" if code_was_truncated else ""
    full_message = (
        f"**Code to review:**\n```\n{truncated_code}\n```{code_note}\n\n"
        f"**Question:** {user_question}"
    )

    response = chat.send_message(message=full_message)
    answer = response.text

    if not has_valid_table(answer):
        with st.spinner("Fixing table formatting..."):
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
    st.session_state.messages = []

if "active_code" not in st.session_state:
    st.session_state.active_code = ""

get_client()  # Fail fast on missing API key


# ---------------------------------------------------------------------------
# Sidebar — code status, paste box, file uploader, clear buttons
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Setup")

    # Always show what code is currently loaded
    if st.session_state.active_code:
        char_count = len(st.session_state.active_code)
        capped = char_count > MAX_CODE_CHARS
        label = f"✅ Code ready: **{char_count:,} chars**"
        if capped:
            label += " *(capped at 12k)*"
        st.success(label)
        with st.expander("👁️ Preview", expanded=False):
            preview = st.session_state.active_code[:800]
            if len(st.session_state.active_code) > 800:
                preview += "\n... [truncated]"
            st.code(preview)
    else:
        st.warning("⚠️ No code loaded yet — paste or upload below.")

    st.divider()

    # Option 1: paste box (most common use case)
    st.markdown("**Option 1 — Paste code**")
    pasted_code = st.text_area(
        "code_paste",
        height=180,
        placeholder="Paste your code here...",
        label_visibility="collapsed",
    )
    if st.button("⬆️ Load this code", use_container_width=True):
        if pasted_code.strip():
            st.session_state.active_code = pasted_code.strip()
            st.rerun()
        else:
            st.error("Paste box is empty.")

    st.divider()

    # Option 2: file upload
    st.markdown("**Option 2 — Upload a file**")
    uploaded_file = st.file_uploader(
        "file_upload",
        type=SUPPORTED_TYPES,
        help="Supported: " + ", ".join(SUPPORTED_TYPES),
        label_visibility="collapsed",
    )
    if uploaded_file is not None:
        try:
            file_content = uploaded_file.read().decode("utf-8", errors="replace")
            if file_content != st.session_state.active_code:
                st.session_state.active_code = file_content
                st.rerun()
        except Exception as e:
            st.error(f"Failed to read file: {e}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Clear Code", use_container_width=True):
            st.session_state.active_code = ""
            st.rerun()
    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ---------------------------------------------------------------------------
# Chat UI — render message history
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            render_response(msg["content"])
        else:
            st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Chat input — accepts questions, fenced code, or raw pasted code
# ---------------------------------------------------------------------------
user_input = st.chat_input("Ask a GDPR question, or paste code here...")

if user_input:
    # Check if the message itself contains new code
    extracted_code = extract_code_from_message(user_input)
    plain_question = strip_code_blocks(user_input)

    if extracted_code:
        st.session_state.active_code = extracted_code

    if not plain_question:
        plain_question = (
            "Please review the provided code for GDPR compliance issues "
            "using the standard format."
        )

    # Guard: code must be loaded by now
    if not st.session_state.active_code:
        st.error("⚠️ No code loaded yet — use the **sidebar** to paste or upload your code first.")
        st.stop()

    # Show user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Call Gemini and render structured response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing for GDPR compliance..."):
            try:
                answer = ask_gemini(plain_question, st.session_state.active_code)
                render_response(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    st.error(
                        "Rate limit hit (429). Free tier quota exceeded. "
                        "Wait a minute and retry, or check https://ai.dev/rate-limit."
                    )
                else:
                    st.error(f"Gemini API error: {e}")