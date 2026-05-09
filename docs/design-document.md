# Distributed AI Receipt Splitter — Design & Analysis Document

**Course:** CS-432 Distributed Computing — Complex Engineering Activity
**Batch:** BE 2022, Spring 2026

---

## 1. Problem Statement

When friends eat out together, splitting the bill is the most awkward moment of the meal. The common methods all fail:

- **Equal split** — unfair when someone ordered a steak and another ordered just water.
- **Manual itemization on paper** — slow, error-prone, gets the math wrong on tax/tip allocation.
- **Splitwise / Venmo Groups** — exist, but Venmo is unavailable in Pakistan and Splitwise still requires every person to manually type every item they ordered.

A **distributed** solution is needed because the problem is *inherently distributed*:

1. The receipt is captured by **one** person (the photographer).
2. Each diner needs to claim **their** items independently and concurrently from **their own phone**.
3. A neutral computation must produce a settlement everyone can verify.

A monolithic single-process app would force all diners to crowd around one phone — defeating the purpose. We therefore split the system into independently-addressable services that communicate over the network and share state through a central database.

This also satisfies the **sustainability** angle (Section 4): a digital-first workflow eliminates the printed-and-discarded paper most diners use today to scribble splits.

---

## 2. Architectural Style

### 2.1 Chosen style: **Microservices over REST/HTTP**, with a **shared-database** persistence pattern

The system is decomposed into four independently-deployable components:

| Service | Responsibility | Deployment |
|---|---|---|
| OCR Service | Image → structured items | HF Space (Docker, Tesseract) |
| Split Service | Manage participants and item-claims | HF Space (Docker, FastAPI) |
| Settlement Service | Compute who-owes-whom | HF Space (Docker, FastAPI) |
| Frontend | UI orchestrator | HF Space (Gradio) |
| Supabase Postgres | Shared state | Supabase managed Postgres |

Each service owns a *bounded context* (a subset of the database tables it primarily writes), and all services communicate via versioned HTTP/JSON.

### 2.2 Alternatives considered and rejected

| Alternative | Why rejected |
|---|---|
| **Monolith** (single Flask app) | Explicitly forbidden by CEP rubric ("No monolithic single-process systems"). Also misses the distributed-by-nature reality of the use case. |
| **Event-driven / message broker (Kafka, RabbitMQ)** | Overkill for a request/response workflow with seconds-scale latency tolerance. Would add infrastructure burden (broker hosting) that the free HF Spaces tier doesn't support well. We *do* keep an event-style audit trail in the `claims` table. |
| **Peer-to-peer (gossip / WebRTC)** | Tempting (no central server) but loses durability — if a phone dies mid-meal the bill is gone. Also impossible to demo via a public URL during the practical viva. |
| **Serverless functions (AWS Lambda)** | Cold-start latency comparable to HF Spaces but requires a paid AWS account. CEP guidance favors free deployment. |
| **gRPC instead of REST** | More efficient on the wire, but harder to demo (no human-readable URLs to paste into a viva), and Gradio frontend would need extra plumbing. |
| **Database-per-service** (strict bounded contexts) | Considered — would mean three Supabase projects. Rejected for cost and operational complexity at this scale; we use *logical separation* (separate tables, each service writes only its own subset) which the CEP rubric explicitly accepts ("Separate databases (or logical separation)"). |

### 2.3 Communication patterns

- **Synchronous request/response** between Frontend and each backend service (REST + JSON).
- **Stateless services** — every request carries the `bill_id` it operates on; no session affinity needed, so any service instance can handle any request (horizontal-scale ready).
- **Database as integration backbone** — services do not call each other directly; they coordinate via Supabase. This is the *Database per Service avoidance trade-off* discussed in Section 2.2.

### 2.4 Failure modes and resilience

| Failure | Behavior | Mitigation |
|---|---|---|
| OCR Space asleep (cold start) | First request takes ~30s | Frontend shows a "warming up" hint; subsequent users hit a warm container. |
| Supabase momentary outage | All services return 5xx | Each service surfaces the error verbatim to the frontend; user retries. No silent data loss. |
| Mis-OCR'd item / price | Wrong split | `POST /manual` fallback on OCR Service lets the user enter items by hand. |
| Two users claim the same item simultaneously | Both succeed (we *want* shared items) | `_rebalance_item` re-divides the share. The `(item_id, participant_id)` UNIQUE constraint prevents duplicate identical claims. |

---

## 3. System Architecture Diagram

```
                          ┌────────────────────────┐
                          │      Browser           │
                          │ (each diner's phone)   │
                          └───────────┬────────────┘
                                      │ HTTPS
                                      ▼
                       ┌───────────────────────────────┐
                       │   Frontend Space (Gradio)     │
                       │   - thin HTTP orchestrator    │
                       └─┬──────────────┬───────────┬──┘
                         │              │           │
            ┌────────────┘              │           └────────────┐
            │ POST /scan                │ POST /claims           │ POST /settle
            ▼                           ▼                        ▼
   ┌─────────────────┐         ┌─────────────────┐      ┌─────────────────┐
   │  OCR Service    │         │  Split Service  │      │   Settlement    │
   │  (FastAPI +     │         │  (FastAPI)      │      │   Service       │
   │   Tesseract)    │         │                 │      │   (FastAPI)     │
   │  HF Docker Space│         │  HF Docker Space│      │   HF Docker     │
   └────────┬────────┘         └────────┬────────┘      └────────┬────────┘
            │                           │                        │
            └───────────┬───────────────┴──────────┬─────────────┘
                        │                          │
                        ▼  Postgres wire protocol  ▼
               ┌─────────────────────────────────────────┐
               │       Supabase Postgres                 │
               │  bills · items · participants ·         │
               │  claims · settlements                   │
               └─────────────────────────────────────────┘
```

Service-to-table ownership (logical separation):

| Table | Primary writer | Readers |
|---|---|---|
| `bills` | OCR (insert), Split (update payer), Settlement (status) | All |
| `items` | OCR | Split, Settlement |
| `participants` | Split | OCR-frontend init, Settlement |
| `claims` | Split | Settlement |
| `settlements` | Settlement | Frontend |

---

## 4. Sustainability & Environmental Analysis

### 4.1 Direct environmental impact reductions

- **Paper:** Eliminates the napkin/scribble that diners typically use to track splits. A typical group meal in Pakistan generates ~1 sheet of waste paper per session for splits — at scale, non-trivial.
- **Mental + temporal energy:** Faster split → less idle time at the restaurant → less HVAC consumption per cover. Marginal but real for high-throughput restaurants.

### 4.2 Compute energy footprint

The free Hugging Face Spaces tier is an *intentionally* sustainable choice:

- **Sleep-on-idle:** Spaces auto-suspend after ~48h of inactivity, drawing **zero compute power** when nobody is splitting a bill. A traditional always-on VPS would burn ~5W continuously per service × 4 services × 24h = ~480 Wh/day even when unused.
- **Multitenant infrastructure:** HF and Supabase pack many users onto shared hardware, achieving server utilization rates (~60-80%) far above a single-tenant VPS (~5-15%). Higher utilization → less hardware per user → less embodied carbon.
- **Edge-cache via CDN:** HF Spaces fronts assets through a global CDN, reducing repeat-request bandwidth and origin-server load.

### 4.3 Algorithmic efficiency

- **Stateless services** mean we can scale to zero — no idle worker threads.
- **Tesseract over a vision-LLM** for OCR: a 100MB CPU-only Tesseract install per request costs roughly **0.001 kWh**, vs. an estimated **~0.01 kWh** for a single GPT-4-class vision model call. At classroom scale this is negligible, but at country scale it would 10× our footprint.
- **Single-payer settlement (O(n))** vs. a full min-cash-flow optimization (O(n²) and graph-based). For 4-8 friends the simple algorithm suffices and uses < 1ms of CPU per settlement.

### 4.4 Lifecycle considerations

- **No mobile app to install** — works in any browser. Avoids forcing users to download yet another app (each app install is ~50MB of storage and the energy to download it).
- **No vendor lock-in** — Supabase is just Postgres; the OCR/Split/Settle services are plain Python. The team or future adopters can move off the free tiers without rewriting the system.

### 4.5 Honest limitations

- HF Spaces *cold starts* burn extra compute for the first user. We accept this trade for the much larger savings of sleep-on-idle.
- We could not measure exact watt-hours from the free tier — these numbers are estimates from public Hugging Face / Supabase sustainability reports.

---

## 5. Mapping to Course Learning Outcomes

| CLO | How this project addresses it |
|---|---|
| **CLO-1** Examine techniques | We compared REST, gRPC, message brokers, and P2P (Section 2.2). We use REST/JSON for justified reasons. |
| **CLO-2** Pros & cons analysis | Section 2.2 (alternatives) and Section 2.4 (failure modes) explicitly weigh trade-offs. The "shared DB vs. DB per service" trade-off is documented in Section 2.1. |
| **CLO-3** Sustainability | Section 4 covers paper waste, idle compute, multitenancy, algorithmic efficiency, and honest limitations. |

---

## 6. Mandatory Requirements Checklist

| Requirement | Status |
|---|---|
| Network communication | ✅ HTTPS REST between Frontend and 3 backend services; Postgres wire protocol to Supabase. |
| No monolith | ✅ Four independently-deployable Spaces. |
| ≥ 3 distributed components | ✅ OCR, Split, Settlement (frontend is a 4th). |
| Sustainability analysis | ✅ Section 4. |
| All members contribute | Suggested split: OCR (member 1), Split (member 2), Settlement (member 3), Frontend + design doc (member 4). |
