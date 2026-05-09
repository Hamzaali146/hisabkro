---
title: Receipt Splitter — OCR Service
emoji: 🧾
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# OCR Service

Part of the **Distributed AI Receipt Splitter** (CS-432 CEP).

Accepts a receipt photo, extracts items and totals via Tesseract, persists to Supabase, returns `bill_id`.

## Required Space secrets
Set these in your HF Space → Settings → Variables and secrets:

- `SUPABASE_URL` — e.g. `https://abcd1234.supabase.co`
- `SUPABASE_SERVICE_KEY` — service_role key (Project Settings → API)

## Endpoints
- `GET /` — health check
- `POST /scan` — multipart form: `file` (image), `title`, `payer_name`
- `POST /manual` — JSON fallback for testing without an image
