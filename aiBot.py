# aibot.py — GDPR Code Review Chatbot
# Run: streamlit run aibot.py
# Requirements: pip install streamlit python-dotenv openai

import os
import re
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()  # Load OPENAI_API_KEY from .env file (never hardcode keys)

MODEL_ID = "gpt-4.1-mini"
MAX_CODE_CHARS = 12_000   # Cap code payload to avoid huge prompts
MAX_HISTORY_MSGS = 6      # Only send last N messages to keep context manageable
SUPPORTED_TYPES = ["py", "js", "ts", "java", "cpp", "cs", "php", "go", "txt"]
GDPR_KNOWLEDGE_FILE = "gdpr_knowledge.md"

# ---------------------------------------------------------------------------
# OpenAI client — initialized once and stored in session_state
# ---------------------------------------------------------------------------
def get_openai_client() -> OpenAI:
    """Create and cache the OpenAI client in session_state to avoid reinit on reruns."""
    if "openai_client" not in st.session_state:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            st.error("OPENAI_API_KEY not found. Please add it to your .env file.")
            st.stop()
        st.session_state.openai_client = OpenAI(api_key=api_key)
    return st.session_state.openai_client


# ---------------------------------------------------------------------------
# Mini-RAG: Load GDPR knowledge file and retrieve relevant sections
# ---------------------------------------------------------------------------
def load_gdpr_sections() -> dict[str, str]:
    """
    Read gdpr_knowledge.md once and split into sections by markdown headings (## or #).
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
# OpenAI API call
# ---------------------------------------------------------------------------
def call_openai(system_prompt: str, code_text: str, user_question: str) -> str:
    """
    Send the system prompt, recent chat history, code snippet, and user question
    to OpenAI. Returns the assistant's response text.
    """
    client = get_openai_client()

    # Build message list: system + last N history messages + new user message
    messages = [{"role": "system", "content": system_prompt}]

    # Include only the last MAX_HISTORY_MSGS messages to keep token usage reasonable
    recent_history = st.session_state.messages[-MAX_HISTORY_MSGS:]
    for msg in recent_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Compose the user turn: question + code (capped)
    truncated_code = code_text[:MAX_CODE_CHARS]
    if len(code_text) > MAX_CODE_CHARS:
        truncated_code += "\n\n... [code truncated for length] ..."

    user_content = f"**Code to review:**\n```\n{truncated_code}\n```\n\n**Question:** {user_question}"
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=messages,
        temperature=0.2,  # Lower temperature for consistent, factual output
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="GDPR Code Review Chatbot", page_icon="🔒")
st.title("🔒 GDPR Code Review Chatbot")

# Initialize chat message history in session_state (persists across reruns)
if "messages" not in st.session_state:
    st.session_state.messages = []


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

    # Clear chat history
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.success("Chat history cleared.")

    # Clear uploaded code
    if st.button("🗑️ Clear Uploaded Code"):
        st.session_state.pop("uploaded_code", None)
        st.success("Uploaded code cleared.")

    st.divider()
    st.caption(f"Model: `{MODEL_ID}`")
    st.caption("Powered by OpenAI + GDPR knowledge base")


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

    # Build system prompt with injected GDPR context
    system_prompt = build_system_prompt(gdpr_context)

    # Call OpenAI and stream response
    with st.chat_message("assistant"):
        with st.spinner("🤖 Analyzing code for GDPR compliance..."):
            try:
                answer = call_openai(system_prompt, active_code, user_question)
                st.markdown(answer)
                # Append assistant response to history
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                error_msg = f"❌ OpenAI API error: {e}"
                st.error(error_msg)