# 🔒 GDPR Code Review Chatbot

An AI-powered chatbot that reviews your code for GDPR compliance issues. Built with [Streamlit](https://streamlit.io/) and [Google Gemini](https://ai.google.dev/), it uses a lightweight mini-RAG system to ground findings in a local GDPR knowledge base — no vector databases, no external services.

---

## ✨ Features

- **Chat-first code input** — paste a fenced code block directly into the chat, or upload a file from the sidebar
- **Structured output** — every response is parsed and rendered in four clean sections: Summary, Findings Table, Suggested Secure Changes, and Disclaimer
- **Mini-RAG retrieval** — relevant GDPR principles are retrieved from `gdpr_knowledge.md` using simple keyword scoring before every API call
- **Fresh context per question** — system prompt is rebuilt with up-to-date GDPR context on every question to prevent stale instructions
- **Auto table repair** — if the model returns a malformed Markdown table, a targeted follow-up fixes it automatically
- **Session-safe** — Gemini client, GDPR sections, and chat history are all cached in `st.session_state` so nothing reinitializes on reruns
- **Rate limit handling** — 429 errors are caught and shown as a clear, actionable message

---

## 📁 Project Structure

```
.
├── aibot.py              # Main application — single file, all logic here
├── gdpr_knowledge.md     # Your GDPR knowledge base (headings = sections)
├── requirements.txt      # Python dependencies
├── .env                  # API key (never commit this)
└── .gitignore            # Must include .env
```

---

## 🚀 Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/your-username/gdpr-code-review-chatbot.git
cd gdpr-code-review-chatbot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up your API key

Create a `.env` file in the project root:

```
GOOGLE_API_KEY=your_gemini_api_key_here
```

Get a free API key at [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).

### 4. Run the app

```bash
streamlit run aibot.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🧑‍💻 How to Use

**Option A — Upload a file**
1. Use the sidebar file uploader to load a code file
2. Type your question in the chat input (e.g. *"Is this GDPR compliant?"*)
3. Press Enter

**Option B — Load the code**
1. Use the sidebar code textbox to load the code
2. Type your question in the chat input (e.g. *"Is this GDPR compliant?"*)
3. Press Enter

**Switching code**
Paste a new code block at any time to replace the current code under review. The GDPR context refreshes automatically.

**Clearing history**
Use the **Clear Chat History** and **Clear Code** buttons in the sidebar to start fresh.

---

## 📋 Output Format

Every response is structured into four sections:

| Section | Description |
|---------|-------------|
| 📋 **Summary** | 2–3 bullets describing what the code does from a privacy perspective |
| 🔍 **Findings Table** | Issue · GDPR Principle · Evidence · Severity (High/Med/Low) · Recommendation |
| 🛡️ **Suggested Secure Changes** | 3–7 actionable items, each with what to change, why, and a short code snippet |
| ⚠️ **Disclaimer** | Reminder that this is not legal advice |

---

## ⚙️ Configuration

All constants are at the top of `aibot.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `MODEL_ID` | `gemini-3-flash-preview` | Gemini model to use |
| `MAX_CODE_CHARS` | `12000` | Code is truncated at this length before being sent |
| `MAX_CONTEXT_CHARS` | `6000` | Retrieved GDPR context is capped at this length |
| `MAX_HISTORY_MSGS` | `6` | Number of past messages replayed to the model |
| `SUPPORTED_TYPES` | `py js ts java cpp cs php go txt` | File types accepted by the uploader |
| `GDPR_KNOWLEDGE_FILE` | `gdpr_knowledge.md` | Path to the knowledge base file |

---

## 🔒 Security Notes

- Your `GOOGLE_API_KEY` is loaded from `.env` via `python-dotenv` — it is never hardcoded or printed
- Ensure `.env` is listed in your `.gitignore`
- Code submitted for review is only sent to the Gemini API — it is not stored anywhere by this app
- The chatbot does not recommend logging personal data; it always suggests anonymized or pseudonymized alternatives

---

## 📦 Requirements

```
streamlit
python-dotenv
google-genai
```

Install with:

```bash
pip install -r requirements.txt
```

---

## 🐛 Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `GOOGLE_API_KEY not found` | Missing or misnamed `.env` entry | Check `.env` has `GOOGLE_API_KEY=...` |
| `429 RESOURCE_EXHAUSTED` | Free tier quota exceeded | Wait ~1 minute or until tomorrow; quota resets daily |
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -r requirements.txt` |

---

## 📄 License

MIT — free to use, modify, and distribute.

---

## 📄 Responsible AI Reflection

This project demonstrates applied AI integration in a compliance-aware context. While large language models can assist in identifying potential GDPR risks in source code, they do not replace legal expertise or certified compliance audits. The model’s analysis is limited to the provided knowledge base and code context, which means conclusions may be incomplete or overly cautious. To reduce hallucination risk, the system restricts responses to a structured format and grounds findings strictly in the provided GDPR knowledge file. Additionally, the chatbot avoids generating legal advice and includes a disclaimer in every response. Responsible AI use in this project emphasizes transparency, limitation awareness, and human oversight. Developers should treat AI output as decision support, not authoritative compliance certification.

---

## ⚠️ Disclaimer

This tool is for developer assistance only. It does not constitute legal advice. Always consult a qualified Data Protection Officer (DPO) or legal counsel for formal GDPR compliance assessments.
