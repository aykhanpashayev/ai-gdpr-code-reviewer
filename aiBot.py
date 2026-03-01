# aibot.py — GDPR Code Review Chatbot (Gemini version)
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
load_dotenv()  # Load GOOGLE_API_KEY from .env file (never hardcode keys)

MODEL_ID = "gemini-2.0-flash"
MAX_CODE_CHARS = 12_000   # Cap code payload to avoid huge prompts
MAX_HISTORY_MSGS = 6      # Only send last N messages to keep context manageable
SUPPORTED_TYPES = ["py", "js", "ts", "java", "cpp", "cs", "php", "go", "txt"]
GDPR_KNOWLEDGE_FILE = "gdpr_knowledge.md"

# ---------------------------------------------------------------------------
# Gemini client — initialized once and stored in session_state
# ---------------------------------------------------------------------------
def get_gemini_client() -> genai.Client:
    """Create and cache the Gemini client in session_state to avoid reinit on reruns."""
    if "client" not in st.session_state:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            st.error("GOOGLE_API_KEY not found. Please add it to your .env file.")
            st.stop()
        st.session_state.client = genai.Client(api_key=api_key)
    return st.session_state.client


# ---------------------------------------------------------------------------
# Mini-RAG: Load GDPR knowledge file and retrieve relevant sections
# ---------------------------------------------------------------------------
def load_gdpr_sections() -> dict[str, str]:
    """
    Read gdpr_knowledge.md once and split into sections by markdown headings.
    Returns a dict of {heading: content_text}.
    Cached in session_state so we only read the file once per session.
    """
    if "gdpr_sections" not in st.session_state:
        if not os.path.exists(GDPR_KNOWLEDGE_FILE):
            st.warning(f"'{GDPR_KNOWLEDGE_FILE}' not found. GDPR context will be empty.")
            st.session_state.gdpr_sections = {}
        else:
            with open(GDPR_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            # Split on lines starting with # or ## headings
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


def retrieve_relevant_gdpr_context(code_text: str, user_question: str, top_n: int = 4) -> str:
    """
    Simple keyword scoring: score each GDPR section by how many of its words
    appear in (code_text + user_question). Return the top_n sections as a string.
    No embeddings, no vector DB — just plain word overlap.
    """
    sections = load_gdpr_sections()
    if not sections:
        return "(No GDPR knowledge base available.)"

    query_words = set(re.findall(r"\w+", (code_text + " " + user_question).lower()))

    scored = []
    for heading, body in sections.items():
        section_words = set(re.findall(r"\w+", (heading + " " + body).lower()))
        score = len(query_words & section_words)
        scored.append((score, heading, body))

    # Sort descending by score, take top_n
    top_sections = sorted(scored, reverse=True)[:top_n]
    context_parts = []
    for _, heading, body in top_sections:
        context_parts.append(f"### {heading}\n{body.strip()}")

    return "\n\n".join(context_parts)


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------
def build_system_prompt(gdpr_context: str) -> str:
    """
    Build a strict system prompt that enforces evidence-based GDPR review output.
    Injects only the retrieved GDPR context — not the full knowledge base.
    """
    return f"""You are a GDPR Code Review Assistant. Your job is to analyze code for GDPR compliance issues.

RULES:
- Base ALL findings strictly on the GDPR context provided below. Do not invent GDPR article numbers unless they appear in the context.
- If you cannot find sufficient evidence, state "Insufficient context to determine compliance."
- Do NOT give legal advice. Always include a disclaimer.
- Do NOT recommend logging personal data. If logging is needed, recommend anonymized or pseudonymized logging only.
- Be consistent and structured. Always respond in the exact format below.

---
GDPR KNOWLEDGE CONTEXT (use this as your reference):
{gdpr_context}
---

REQUIRED RESPONSE FORMAT — follow exactly, no deviations:

1) **Summary** (2–3 bullets)
   - Brief overview of what the code does (privacy-relevant perspective)

2) **Findings Table**
   | Issue | GDPR Principle | Evidence (line/function) | Severity (High/Med/Low) | Recommendation |
   |-------|---------------|--------------------------|------------------------|----------------|
   | ...   | ...           | ...                      | ...                    | ...            |

3) **Suggested Secure Changes** (3–7 items)
   For each item:
   - **What to change:** ...
   - **Why (principle):** ...
   - **Minimal example snippet:** (SHORT snippet only — do NOT rewrite the whole file)

4) **Disclaimer**
   This is an automated analysis tool, not legal advice. Consult a qualified Data Protection Officer or legal counsel for formal GDPR compliance assessments.
"""


# ---------------------------------------------------------------------------
# Gemini chat session — created once per code review session
# ---------------------------------------------------------------------------
def get_or_create_chat(gdpr_context: str):
    """
    Create a Gemini chat session with the system prompt baked in.
    Stored in session_state so it persists across reruns and retains history.
    Recreated only when code or context changes significantly.
    """
    if "chat" not in st.session_state:
        client = get_gemini_client()
        st.session_state.chat = client.chats.create(
            model=MODEL_ID,
            config=types.GenerateContentConfig(
                system_instruction=build_system_prompt(gdpr_context)
            )
        )
    return st.session_state.chat


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="GDPR Code Review Chatbot", page_icon="🔒")
st.title("🔒 GDPR Code Review Chatbot")

# Initialize chat message history in session_state (persists across reruns)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize the Gemini client eagerly so errors surface immediately
get_gemini_client()


# ---------------------------------------------------------------------------
# Sidebar: file uploader + clear buttons
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Setup")

    uploaded_file = st.file_uploader(
        "Upload a code file to review",
        type=SUPPORTED_TYPES,
        help="Supported: " + ", ".join(SUPPORTED_TYPES),
    )

    # Store uploaded file content in session_state so it survives reruns
    if uploaded_file is not None:
        try:
            file_bytes = uploaded_file.read()
            st.session_state.uploaded_code = file_bytes.decode("utf-8", errors="replace")
            st.success(f"✅ Loaded: {uploaded_file.name}")
        except Exception as e:
            st.error(f"Failed to read file: {e}")

    st.divider()

    # Clear chat history and chat session so next question starts fresh
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.session_state.pop("chat", None)  # Force new chat session on next question
        st.success("Chat history cleared.")

    # Clear uploaded code and reset chat session
    if st.button("🗑️ Clear Uploaded Code"):
        st.session_state.pop("uploaded_code", None)
        st.session_state.pop("chat", None)
        st.success("Uploaded code cleared.")

    st.divider()
    st.caption(f"Model: `{MODEL_ID}`")
    st.caption("Powered by Google Gemini + GDPR knowledge base")


# ---------------------------------------------------------------------------
# Main panel: paste box + preview
# ---------------------------------------------------------------------------
st.subheader("📋 Code Input")

pasted_code = st.text_area(
    "Paste your code here (overrides uploaded file if non-empty):",
    height=200,
    placeholder="Paste code to review, or upload a file in the sidebar...",
)

# Determine active code: paste takes priority over uploaded file
if pasted_code.strip():
    active_code = pasted_code.strip()
    st.info("Using **pasted code** for review.")
elif "uploaded_code" in st.session_state:
    active_code = st.session_state.uploaded_code
    st.info("Using **uploaded file** for review.")
else:
    active_code = ""

# Show a collapsible preview of the active code
if active_code:
    with st.expander("👁️ Code Preview", expanded=False):
        preview = active_code[:2000] + ("\n... [truncated]" if len(active_code) > 2000 else "")
        st.code(preview)


# ---------------------------------------------------------------------------
# Chat UI: display existing message history
# ---------------------------------------------------------------------------
st.subheader("💬 Chat")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Chat input: handle new user question
# ---------------------------------------------------------------------------
user_question = st.chat_input("Ask a GDPR compliance question about your code...")

if user_question:
    # Guard: require code to be present
    if not active_code:
        st.error("⚠️ Please upload a code file or paste code before asking a question.")
        st.stop()

    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    # Retrieve relevant GDPR context using mini-RAG keyword scoring
    with st.spinner("🔍 Retrieving GDPR context..."):
        gdpr_context = retrieve_relevant_gdpr_context(active_code, user_question)

    # Get or create the Gemini chat session (system prompt includes GDPR context)
    chat = get_or_create_chat(gdpr_context)

    # Build the user message: include truncated code + question
    truncated_code = active_code[:MAX_CODE_CHARS]
    if len(active_code) > MAX_CODE_CHARS:
        truncated_code += "\n\n... [code truncated for length] ..."

    message_to_send = (
        f"**Code to review:**\n```\n{truncated_code}\n```\n\n"
        f"**Question:** {user_question}"
    )

    # Call Gemini and display the response
    with st.chat_message("assistant"):
        with st.spinner("🤖 Analyzing code for GDPR compliance..."):
            try:
                response = chat.send_message(message=message_to_send)
                answer = response.text
                st.markdown(answer)
                # Append assistant response to display history
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"❌ Gemini API error: {e}")