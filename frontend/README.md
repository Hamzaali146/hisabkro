---
title: Receipt Splitter — Frontend
emoji: 🧾
colorFrom: pink
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
---

# Frontend

Gradio UI that orchestrates the OCR, Split, and Settlement services.

## Required Space variables (NOT secrets — these are URLs)
Set these in your HF Space → Settings → Variables and secrets:

- `OCR_URL` — e.g. `https://your-username-receipt-splitter-ocr.hf.space`
- `SPLIT_URL` — e.g. `https://your-username-receipt-splitter-split.hf.space`
- `SETTLE_URL` — e.g. `https://your-username-receipt-splitter-settle.hf.space`

## How it flows
1. **Scan tab** — uploads photo to OCR service, gets back `bill_id` + items.
2. **Split tab** — calls Split service to add participants and claim items.
3. **Settle tab** — calls Settlement service to compute who-pays-whom.

The frontend holds zero business logic — it's a dumb HTTP client. That's the whole point of a microservices architecture.
