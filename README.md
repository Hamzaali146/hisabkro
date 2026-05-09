# Distributed AI Receipt Splitter - HISAB KRO

Friends eat out, photograph the receipt, each diner taps the items they ordered, and the system computes who-pays-whom (with proportional tax + tip allocation).

## Architecture (4 distributed components + Supabase)

```
Frontend (Gradio)  ──► OCR Service  ──┐
                   ──► Split Service ──┼──► Supabase Postgres
                   ──► Settlement     ──┘
```

Full design rationale, alternatives considered, and sustainability analysis: [docs/design-document.md](docs/design-document.md).

## Repo layout

| Path | What it is |
|---|---|
| [supabase/schema.sql](supabase/schema.sql) | Database schema — paste into Supabase SQL editor |
| [ocr-service/](ocr-service/) | Tesseract + FastAPI, deployed as a Docker HF Space |
| [split-service/](split-service/) | FastAPI, manages participants and claims |
| [settlement-service/](settlement-service/) | FastAPI, computes who-owes-whom |
| [frontend/](frontend/) | Gradio UI (the only thing users see) |
| [docker-compose.yml](docker-compose.yml) | Run all 4 locally for testing |
| [docs/design-document.md](docs/design-document.md) | The deliverable design doc |

---

## Deployment — full step-by-step

### Step 1 — Set up Supabase (5 min, free)

1. Go to [supabase.com](https://supabase.com) → New Project. Pick a region close to you (Singapore works well from Pakistan).
2. Wait for the project to provision.
3. Open **SQL Editor → New Query**, paste the entire contents of [supabase/schema.sql](supabase/schema.sql), and click **Run**.
4. Open **Project Settings → API**. Copy two values — you'll need them for every Space:
   - `Project URL` → this is your `SUPABASE_URL`
   - `service_role` secret key → this is your `SUPABASE_SERVICE_KEY`
   - ⚠️ The `service_role` key bypasses Row-Level Security. Never put it in the frontend or commit it to a public repo. We only ever set it as an HF Space *secret*.

### Step 2 — Deploy the three backend services to Hugging Face Spaces

For **each** of `ocr-service/`, `split-service/`, `settlement-service/`:

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. **Owner:** your username. **Space name:** e.g. `receipt-splitter-ocr` (then `-split`, then `-settle`).
3. **Space SDK:** `Docker` → blank template.
4. **Visibility:** Public is fine; the service-role key stays in secrets, not in code.
5. Create the Space, then `git clone` it locally OR upload via the web UI.
6. Copy the contents of the matching folder (`ocr-service/*`, etc.) into the Space repo. The `Dockerfile`, `app.py`, `requirements.txt`, and the `README.md` (with the YAML frontmatter — HF needs it) all go at the **root** of the Space repo.
7. Push (or upload). HF will auto-build the container; first build takes ~3-5 min.
8. Open the Space → **Settings → Variables and secrets → New secret**:
   - `SUPABASE_URL` (the project URL from Step 1)
   - `SUPABASE_SERVICE_KEY` (the service-role key from Step 1)
9. Restart the Space. Confirm by visiting `https://YOUR-USERNAME-SPACENAME.hf.space/` — you should see `{"service":"...","status":"ok"}`.

Note the three URLs once they're live — you'll need them next.

### Step 3 — Deploy the Frontend Space

1. New Space → **SDK: Gradio** → blank template, name `receipt-splitter-frontend`.
2. Upload contents of `frontend/` (`app.py`, `requirements.txt`, `README.md`) to the Space root.
3. **Settings → Variables and secrets → New variable** (these are URLs, can be variables not secrets):
   - `OCR_URL` → e.g. `https://your-username-receipt-splitter-ocr.hf.space`
   - `SPLIT_URL` → e.g. `https://your-username-receipt-splitter-split.hf.space`
   - `SETTLE_URL` → e.g. `https://your-username-receipt-splitter-settle.hf.space`
4. Restart. Open the Space — you should see the 3-tab Gradio UI.

### Step 4 — Try it end-to-end

1. **Scan tab** — upload a receipt photo. Set a payer name (e.g. "Hamza"). Click *Scan receipt*. The OCR Space wakes up (~30s on first call), extracts items, and returns a `bill_id`.
2. **Split tab** — type each diner's name → *Add*. Pick an item, pick a person → *Claim*. If two people share an item, claim it for both — the system auto-splits 50/50.
3. **Settle tab** — *Compute settlement*. You get a breakdown and the list of transfers (e.g. "Ali → Hamza: 1240 PKR").

---

## Local development (optional, but useful before deploying)

```powershell
# Windows PowerShell
copy .env.example .env
# edit .env with your Supabase credentials
docker compose up --build
# Open http://localhost:7860
```

---

## What to defend in viva

The CEP rubric will mark you down if you can't explain your code/architecture. Things you should be ready to say in your own words:

| Question they will ask | Where the answer is |
|---|---|
| Why microservices and not monolith? | [docs/design-document.md §2.2](docs/design-document.md) — alternatives considered |
| Why REST and not gRPC / Kafka? | [docs/design-document.md §2.2](docs/design-document.md) |
| How do services share state? | Shared Supabase Postgres with logical separation (each service primarily writes to its own tables). [docs/design-document.md §3](docs/design-document.md) — service-to-table table |
| What happens if OCR misreads a price? | Manual fallback endpoint (`POST /manual` on OCR Service) lets the user enter items by hand. |
| How do you split a shared appetizer? | `_rebalance_item` in [split-service/app.py](split-service/app.py) — when N people claim an item, each claim's `share` becomes 1/N. |
| How does tax/tip get allocated? | Proportional to each person's items_total. See [settlement-service/app.py](settlement-service/app.py) — single-payer block. |
| Why is this sustainable? | [docs/design-document.md §4](docs/design-document.md) — sleep-on-idle, multitenancy, paper waste, Tesseract vs. vision-LLM. |

---

## Suggested team split (4 members)

| Member | Owns |
|---|---|
| 1 | OCR Service + Tesseract tuning + receipt parser regex |
| 2 | Split Service + claims rebalancing logic |
| 3 | Settlement Service + algorithm extension to multi-payer (bonus) |
| 4 | Frontend + design doc + sustainability section + deployment runbook |

Cross-pair on Supabase schema design — every member must understand the data model.
