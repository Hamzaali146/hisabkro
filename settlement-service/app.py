"""
Settlement Service — Distributed AI Receipt Splitter.

Responsibility (single):
    Read claims from Supabase, allocate tax + tip proportionally to each
    person's items_total, and emit "who pays whom" rows.

Why separate from Split:
    Settlement is a *computational* read-only step run once at the end of a
    meal. Split is a write-heavy interactive step run continuously while
    people tap items. Splitting the workloads keeps each service focused
    and individually scalable. It also lets us swap settlement algorithms
    (single-payer ↔ multi-payer min-cash-flow) without touching Split.

Algorithm — single-payer model (matches the 'one friend Venmo'd everyone' UX):
    1. items_total[p]  = sum of (item.price * claim.share) for participant p
    2. fee_share[p]    = (tax + tip) * items_total[p] / sum(items_total)
    3. owed[p]         = items_total[p] + fee_share[p]
    4. settlement      = for each non-payer p: (p → payer, owed[p])

This is intentionally simple and explainable; defensible in viva. A
multi-payer min-cash-flow extension is sketched at the bottom of the file.
"""

import os
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Settlement Service", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def health():
    return {"service": "settlement", "status": "ok"}


@app.post("/bills/{bill_id}/settle")
def settle(bill_id: str):
    bill_rows = supabase.table("bills").select("*").eq("id", bill_id).execute().data
    if not bill_rows:
        raise HTTPException(404, "bill not found")
    bill = bill_rows[0]

    if not bill.get("payer_name"):
        raise HTTPException(400, "set a payer first (POST /bills/{id}/payer on Split Service)")

    parts = supabase.table("participants").select("*").eq("bill_id", bill_id).execute().data
    items = supabase.table("items").select("*").eq("bill_id", bill_id).execute().data
    if not parts or not items:
        raise HTTPException(400, "need at least one participant and one item")

    item_ids = [i["id"] for i in items]
    item_price = {i["id"]: float(i["price"]) for i in items}
    claims = supabase.table("claims").select("*").in_("item_id", item_ids).execute().data

    # Per-participant items_total.
    items_total: Dict[str, float] = {p["id"]: 0.0 for p in parts}
    for c in claims:
        items_total[c["participant_id"]] += item_price[c["item_id"]] * float(c["share"])

    grand_items = sum(items_total.values())
    if grand_items == 0:
        raise HTTPException(400, "no claims yet — nobody owes anything")

    fees = float(bill["tax"] or 0) + float(bill["tip"] or 0)

    # Allocate fees proportionally.
    owed: Dict[str, float] = {}
    for pid, base in items_total.items():
        owed[pid] = round(base + fees * (base / grand_items), 2)

    payer = next((p for p in parts if p["name"].lower() == bill["payer_name"].lower()), None)
    if not payer:
        raise HTTPException(400, f"payer '{bill['payer_name']}' is not a participant on this bill")

    # Wipe previous settlement rows so re-running is idempotent.
    supabase.table("settlements").delete().eq("bill_id", bill_id).execute()

    transfers: List[dict] = []
    for p in parts:
        if p["id"] == payer["id"]:
            continue
        amt = owed[p["id"]]
        if amt <= 0:
            continue
        transfers.append({
            "bill_id": bill_id,
            "from_participant": p["id"],
            "to_participant": payer["id"],
            "amount": amt,
        })

    if transfers:
        supabase.table("settlements").insert(transfers).execute()
    supabase.table("bills").update({"status": "settled"}).eq("id", bill_id).execute()

    name_of = {p["id"]: p["name"] for p in parts}
    return {
        "bill_id": bill_id,
        "payer": payer["name"],
        "breakdown": [
            {"participant": name_of[pid], "items_total": round(items_total[pid], 2),
             "owes_total": owed[pid]}
            for pid in items_total
        ],
        "transfers": [
            {"from": name_of[t["from_participant"]],
             "to": name_of[t["to_participant"]],
             "amount": t["amount"]}
            for t in transfers
        ],
    }


@app.get("/bills/{bill_id}/settlement")
def get_settlement(bill_id: str):
    rows = supabase.table("settlements").select("*").eq("bill_id", bill_id).execute().data
    parts = supabase.table("participants").select("id,name").eq("bill_id", bill_id).execute().data
    name_of = {p["id"]: p["name"] for p in parts}
    return {
        "transfers": [
            {"from": name_of.get(r["from_participant"]),
             "to":   name_of.get(r["to_participant"]),
             "amount": float(r["amount"])}
            for r in rows
        ]
    }


# --------------------------------------------------------------------------
# Multi-payer extension (kept here for the viva, not wired up):
# If bills could have multiple payers, replace the single-payer block above
# with a balance vector: balance[p] = paid[p] - owed[p]. Then run a greedy
# min-cash-flow:
#     while any(balance[p] != 0):
#         creditor = argmax(balance); debtor = argmin(balance)
#         x = min(balance[creditor], -balance[debtor])
#         emit (debtor → creditor, x)
#         balance[creditor] -= x; balance[debtor] += x
# This produces O(n) transfers and is the standard Splitwise approach.
# --------------------------------------------------------------------------
