---
title: Receipt Splitter — Frontend (Streamlit)
emoji: 🧾
colorFrom: pink
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
---

# Frontend (Streamlit)

Streamlit version of the orchestrator UI. Same job as the Gradio frontend — translates user actions into HTTP calls against the OCR, Split, and Settlement services.

## Required Space variables (NOT secrets — these are URLs)
Set these in your HF Space → Settings → Variables and secrets:

- `OCR_URL` — e.g. `https://your-username-receipt-splitter-ocr.hf.space`
- `SPLIT_URL` — e.g. `https://your-username-receipt-splitter-split.hf.space`
- `SETTLE_URL` — e.g. `https://your-username-receipt-splitter-settle.hf.space`

## Local run
```powershell
$env:OCR_URL="http://localhost:7861"
$env:SPLIT_URL="http://localhost:7862"
$env:SETTLE_URL="http://localhost:7863"
pip install -r requirements.txt
streamlit run app.py
```

## How it flows
1. **Scan tab** — upload photo → calls OCR Service → stores `bill_id` in `st.session_state`.
2. **Split tab** — add participants, then per-item `st.multiselect` of who claimed it; the app diffs against the existing claims and POST/DELETEs the changes.
3. **Settle tab** — calls Settlement Service, displays a breakdown table + a copy-to-WhatsApp transfer summary.

The frontend holds zero business logic.
