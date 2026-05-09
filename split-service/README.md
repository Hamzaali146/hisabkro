---
title: Receipt Splitter — Split Service
emoji: 🍽️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Split Service

Manages participants and claims (who-ordered-what) for a bill.

## Required Space secrets
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

## Endpoints
- `GET /bills/{bill_id}` — full bill snapshot
- `POST /bills/{bill_id}/participants` — add a person
- `POST /bills/{bill_id}/payer` — mark who fronted the cash
- `POST /claims` — claim an item for a participant
- `DELETE /claims?item_id=&participant_id=` — un-claim
