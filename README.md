# SmartStudy AI — AI-Based Smart Student Learning & Holistic Development System

An intelligent academic, holistic skill, and college management platform built with **Streamlit**, **SQLite**, **Plotly**, **Scikit-learn**, and **Google Gemini (`google-genai`)** with full offline Demo Mode support.

## Quick Start (Local)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Free Permanent Cloud Deployment (Streamlit Community Cloud)

Because Streamlit Community Cloud resets local container files on sleep/redeploy, SmartStudy AI automatically stores uploaded PDFs/certificates inside `smartstudy.db` (`file_blobs`) and syncs `smartstudy.db` to a **private GitHub data repository** (100% free):

1. Push this project folder to a GitHub repo (e.g. `yourname/smartstudy-ai`).
2. Create a second **private** GitHub repo (e.g. `yourname/smartstudy-data`) and generate a GitHub Personal Access Token (`repo` scope / Contents Read & Write).
3. Deploy `app.py` on **https://share.streamlit.io** and under **App Settings → Secrets**, add:
   ```toml
   # Optional Gemini AI key (omit for Demo mode)
   GEMINI_API_KEY = "your_gemini_key"

   # Free permanent cloud persistence
   GITHUB_TOKEN = "ghp_your_token"
   GITHUB_DATA_REPO = "yourname/smartstudy-data"
   ```
4. Every create/edit/upload automatically syncs `smartstudy.db` to your private data repo and pulls it back on cold start.

## Demo Portal Credentials (1-Click Sign-In Included)

| Role | Username | Password |
| :--- | :--- | :--- |
| 🎓 Student | `aarav` | `student123` |
| 👩‍🏫 Teacher | `priya` | `teacher123` |
| 👨‍👩‍👧 Parent / Guardian | `parent_sharma` | `parent123` |
| 🛡️ Administrator | `admin` | `admin123` |
