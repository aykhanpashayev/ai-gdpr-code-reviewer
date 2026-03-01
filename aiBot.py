import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# ---------------------------------------------------
# Configuration Section
# ---------------------------------------------------

# This is the model we selected from Hugging Face
MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"

# Path to your GDPR knowledge base file
KNOWLEDGE_FILE = "gdpr_knowledge.md"


# ---------------------------------------------------
# Load Environment Variables (.env file)
# ---------------------------------------------------

# Loads values from .env into environment variables
load_dotenv()

# Reads your Hugging Face API token
API_KEY = os.getenv("HUGGING_FACE_API")

if not API_KEY:
    st.error("API_KEY not found in .env file")
    st.stop()


# ---------------------------------------------------
# Initialize Hugging Face Client (Once per Session)
# ---------------------------------------------------

# Streamlit reruns script on every interaction.
# We store the client in session_state so it is not recreated every time.
if "client" not in st.session_state:
    st.session_state.client = InferenceClient(token=API_KEY)


# ---------------------------------------------------
# Load GDPR Knowledge Base (Mini RAG Source)
# ---------------------------------------------------

def load_gdpr_knowledge():
    """
    Reads the GDPR knowledge markdown file.
    Returns entire text content.
    """
    if Path(KNOWLEDGE_FILE).exists():
        return Path(KNOWLEDGE_FILE).read_text(encoding="utf-8")
    return ""


def split_sections(markdown_text):
    """
    Splits markdown file into sections based on headings (#).
    Returns list of tuples: (section_title, section_content)
    """
    sections = []
    current_title = ""
    current_content = []

    for line in markdown_text.splitlines():
        if line.startswith("#"):
            # If we hit a new heading, save previous section
            if current_content:
                sections.append((current_title, "\n".join(current_content)))
                current_content = []
            current_title = line.strip()
        else:
            current_content.append(line)

    # Add final section
    if current_content:
        sections.append((current_title, "\n".join(current_content)))

    return sections


# Load GDPR sections once per session
if "gdpr_sections" not in st.session_state:
    gdpr_text = load_gdpr_knowledge()
    st.session_state.gdpr_sections = split_sections(gdpr_text)


# ---------------------------------------------------
# Mini Retrieval Function (Simple RAG)
# ---------------------------------------------------

def retrieve_relevant_sections(sections, code_text, user_question):
    """
    Simple keyword matching to retrieve only relevant GDPR sections.
    This makes the model more accurate and grounded.
    """
    text_blob = (code_text + " " + user_question).lower()

    keywords = [
        "email", "phone", "password", "token", "api_key",
        "secret", "log", "delete", "retention",
        "http://", "encrypt", "ssn", "address"
    ]

    matched = []

    for title, content in sections:
        score = 0
        for kw in keywords:
            # If keyword appears both in code/question AND section content,
            # increase relevance score
            if kw in text_blob and kw in content.lower():
                score += 1
        if score > 0:
            matched.append((score, title, content))

    # Sort by highest relevance
    matched.sort(reverse=True, key=lambda x: x[0])

    # Select top 5–6 most relevant sections
    selected = [f"{t}\n{c}" for _, t, c in matched[:6]]

    # If nothing matched, fallback to first section
    if not selected and sections:
        selected = [f"{sections[0][0]}\n{sections[0][1]}"]

    return "\n\n".join(selected)


# ---------------------------------------------------
# Prompt Builder
# ---------------------------------------------------

def build_prompt(context, code_text, chat_history, question):
    """
    Builds structured prompt in Mistral Instruct format.
    Includes:
    - GDPR context
    - Code
    - Recent chat history
    - User question
    """

    # Keep only recent 6 messages to prevent context overflow
    recent_history = chat_history[-6:]

    history_text = "\n".join(
        [f"{m['role']}: {m['content']}" for m in recent_history]
    )

    return f"""<s>[INST]
You are a GDPR-aware cybersecurity code reviewer.

Rules:
- Use ONLY the provided GDPR context.
- Be evidence-based.
- If unsure, say "Insufficient context".
- Do not provide legal advice.

Return:
1) Summary
2) Findings Table (Issue | GDPR Principle | Evidence | Severity | Recommendation)
3) Suggested Secure Changes
4) Disclaimer

GDPR CONTEXT:
{context}

CODE:
{code_text[:10000]}

CHAT HISTORY:
{history_text}

QUESTION:
{question}
[/INST]"""


# ---------------------------------------------------
# Streamlit UI
# ---------------------------------------------------

st.title("GDPR Code Review Chatbot")

# Store conversation messages
if "messages" not in st.session_state:
    st.session_state.messages = []

# Store uploaded or pasted code
if "code_text" not in st.session_state:
    st.session_state.code_text = ""


# Sidebar for file upload
with st.sidebar:
    st.header("Setup")

    uploaded_file = st.file_uploader(
        "Upload code file",
        type=["py", "js", "java", "cpp", "cs", "php", "go", "txt"]
    )

    # If file uploaded, decode and store text
    if uploaded_file is not None:
        st.session_state.code_text = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        st.success("File loaded successfully")

    if st.button("Clear Chat"):
        st.session_state.messages = []

    if st.button("Clear Code"):
        st.session_state.code_text = ""


# Main code paste area
st.subheader("Paste Code (Optional)")
paste_input = st.text_area("Paste your code here:", height=250)

# If user pasted something, override file content
if paste_input.strip():
    st.session_state.code_text = paste_input


# Show preview of code
if st.session_state.code_text:
    with st.expander("Code Preview"):
        st.code(st.session_state.code_text)
else:
    st.info("Upload or paste code to begin.")


# ---------------------------------------------------
# Chat Section
# ---------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


user_input = st.chat_input("Ask about GDPR compliance...")

if user_input:
    if not st.session_state.code_text:
        st.error("Please upload or paste code first.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Retrieve relevant GDPR knowledge
    relevant_context = retrieve_relevant_sections(
        st.session_state.gdpr_sections,
        st.session_state.code_text,
        user_input
    )

    # Build prompt
    prompt = build_prompt(
        relevant_context,
        st.session_state.code_text,
        st.session_state.messages,
        user_input
    )

    # Call Hugging Face model
    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            response = st.session_state.client.text_generation(
                model=MODEL_ID,
                prompt=prompt,
                max_new_tokens=700,
                temperature=0.2
            )

            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})