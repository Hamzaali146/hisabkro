---
title: Receipt Splitter — Settlement Service
emoji: 💸
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Settlement Service

Computes who-owes-whom for a finalized bill (single-payer model + proportional tax/tip allocation).

## Required Space secrets
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

## Endpoints
- `POST /bills/{bill_id}/settle` — compute and persist the settlement; returns full breakdown.
- `GET /bills/{bill_id}/settlement` — fetch a previously computed settlement.
