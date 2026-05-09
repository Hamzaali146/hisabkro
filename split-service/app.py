"""
Split Service — Distributed AI Receipt Splitter.

Responsibility (single):
    Manage participants on a bill, and record claims (who-ordered-what).
    Stateless API; all state lives in Supabase.

Why separate from OCR:
    Different lifecycle. OCR runs once per bill (heavy, slow).
    Splitting runs many times concurrently as friends tap their items
    (light, latency-sensitive). Putting them in the same Space would mean
    OCR's slow cold start delays every claim request.
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Split Service", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ParticipantIn(BaseModel):
    name: str


class ClaimIn(BaseModel):
    item_id: str
    participant_id: str


@app.get("/")
def health():
    return {"service": "split", "status": "ok"}


@app.get("/bills/{bill_id}")
def get_bill(bill_id: str):
    """Full snapshot of a bill — items, participants, current claims."""
    bill = supabase.table("bills").select("*").eq("id", bill_id).execute().data
    if not bill:
        raise HTTPException(404, "bill not found")
    items = supabase.table("items").select("*").eq("bill_id", bill_id).execute().data
    parts = supabase.table("participants").select("*").eq("bill_id", bill_id).execute().data
    item_ids = [i["id"] for i in items]
    claims = (
        supabase.table("claims").select("*").in_("item_id", item_ids).execute().data
        if item_ids else []
    )
    return {"bill": bill[0], "items": items, "participants": parts, "claims": claims}


@app.post("/bills/{bill_id}/participants")
def add_participant(bill_id: str, body: ParticipantIn):
    try:
        row = supabase.table("participants").insert(
            {"bill_id": bill_id, "name": body.name.strip()}
        ).execute().data[0]
        return row
    except Exception as e:
        # Most likely the unique(bill_id, name) constraint.
        raise HTTPException(409, f"could not add participant: {e}")


@app.post("/claims")
def add_claim(body: ClaimIn):
    """Toggle-style: if (item, participant) already exists, do nothing.

    Re-balancing of `share` happens server-side: when an item has N claimers,
    each claim's share becomes 1/N. This is the standard 'split equally among
    claimers' UX and removes the need for the client to compute fractions.
    """
    existing = (
        supabase.table("claims")
        .select("id")
        .eq("item_id", body.item_id)
        .eq("participant_id", body.participant_id)
        .execute().data
    )
    if not existing:
        supabase.table("claims").insert({
            "item_id": body.item_id,
            "participant_id": body.participant_id,
            "share": 1.0,                # placeholder, rebalanced below
        }).execute()
    _rebalance_item(body.item_id)
    return {"ok": True}


@app.delete("/claims")
def remove_claim(item_id: str, participant_id: str):
    supabase.table("claims").delete().eq(
        "item_id", item_id
    ).eq("participant_id", participant_id).execute()
    _rebalance_item(item_id)
    return {"ok": True}


def _rebalance_item(item_id: str) -> None:
    """Set every claim on this item to share = 1/N where N = number of claims."""
    claims = supabase.table("claims").select("id").eq("item_id", item_id).execute().data
    n = len(claims)
    if n == 0:
        return
    share = round(1.0 / n, 4)
    for c in claims:
        supabase.table("claims").update({"share": share}).eq("id", c["id"]).execute()


@app.post("/bills/{bill_id}/payer")
def set_payer(bill_id: str, body: ParticipantIn):
    """Mark who fronted the cash (used by Settlement Service)."""
    supabase.table("bills").update({"payer_name": body.name}).eq("id", bill_id).execute()
    return {"ok": True}
