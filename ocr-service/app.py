"""
OCR Service — Distributed AI Receipt Splitter.

Responsibility (single):
    Accept a receipt image, extract line items + totals, persist to Supabase,
    return the bill_id so other services can take over.

Why this is a separate service:
    OCR is the heaviest component (loads Tesseract, image processing). Isolating
    it means the Split / Settlement services stay tiny and fast, and we can
    scale or swap OCR backends (Tesseract → cloud vision API) without touching
    the rest of the system.
"""

import io
import os
import re
from typing import Optional

import pytesseract
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from supabase import Client, create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]  # service_role key — server-side only

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="OCR Service", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # demo: allow any caller; tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Receipt parsing -------------------------------------------------------
# Receipts are messy: variable layouts, OCR errors, currency symbols, etc.
# Heuristic: every line that ends with a "money-like" token is either an item
# (when preceded by text) or a total (when the preceding text matches a known
# keyword like "TOTAL"/"TAX"/"SUBTOTAL"). This is brittle by design — receipts
# are an unsolved problem; in viva, justify it as "good enough for the demo
# and trivially swappable for a vision-LLM backend."

PRICE_RE = re.compile(r"(?P<price>\d{1,5}(?:[.,]\d{2}))\s*$")
TOTAL_KEYWORDS = ("total", "amount due", "grand total", "balance")
TAX_KEYWORDS = ("tax", "gst", "vat", "sales tax")
TIP_KEYWORDS = ("tip", "gratuity", "service")
SKIP_KEYWORDS = ("subtotal", "change", "cash", "card", "visa", "mastercard")


def _money(s: str) -> float:
    return float(s.replace(",", "."))


def parse_receipt(text: str) -> dict:
    """Turn raw OCR text into structured items + totals.

    Returns: {"items": [{"name", "price"}], "tax": float, "tip": float, "total": float}
    """
    items, tax, tip, total = [], 0.0, 0.0, 0.0

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = PRICE_RE.search(line)
        if not m:
            continue
        price = _money(m.group("price"))
        label = line[: m.start()].strip(" .:-\t")
        low = label.lower()

        if any(k in low for k in TOTAL_KEYWORDS):
            total = max(total, price)        # take the largest "total"-ish line
        elif any(k in low for k in TAX_KEYWORDS):
            tax += price
        elif any(k in low for k in TIP_KEYWORDS):
            tip += price
        elif any(k in low for k in SKIP_KEYWORDS):
            continue
        elif label and len(label) >= 2:
            items.append({"name": label, "price": price})

    subtotal = sum(i["price"] for i in items)
    if total == 0:
        total = subtotal + tax + tip
    return {"items": items, "subtotal": subtotal, "tax": tax, "tip": tip, "total": total}


# --- Endpoints -------------------------------------------------------------

@app.get("/")
def health():
    return {"service": "ocr", "status": "ok"}


@app.post("/scan")
async def scan_receipt(
    file: UploadFile = File(...),
    title: str = Form("Untitled bill"),
    payer_name: Optional[str] = Form(None),
):
    """Upload a receipt photo → returns bill_id with items pre-populated."""
    try:
        img = Image.open(io.BytesIO(await file.read()))
    except Exception as e:
        raise HTTPException(400, f"Invalid image: {e}")

    text = pytesseract.image_to_string(img)
    parsed = parse_receipt(text)

    if not parsed["items"]:
        raise HTTPException(422, "No line items detected. Try a clearer photo.")

    bill = supabase.table("bills").insert({
        "title": title,
        "payer_name": payer_name,
        "subtotal": parsed["subtotal"],
        "tax": parsed["tax"],
        "tip": parsed["tip"],
        "total": parsed["total"],
        "status": "claiming",
    }).execute().data[0]

    rows = [{"bill_id": bill["id"], **it} for it in parsed["items"]]
    supabase.table("items").insert(rows).execute()

    return {"bill_id": bill["id"], "parsed": parsed, "raw_text": text}


@app.post("/manual")
def manual_bill(payload: dict):
    """Fallback when OCR fails or for testing — create a bill from JSON."""
    items = payload.get("items", [])
    if not items:
        raise HTTPException(400, "items[] required")
    subtotal = sum(i["price"] for i in items)
    tax = float(payload.get("tax", 0))
    tip = float(payload.get("tip", 0))
    bill = supabase.table("bills").insert({
        "title": payload.get("title", "Manual bill"),
        "payer_name": payload.get("payer_name"),
        "subtotal": subtotal, "tax": tax, "tip": tip,
        "total": subtotal + tax + tip,
        "status": "claiming",
    }).execute().data[0]
    supabase.table("items").insert(
        [{"bill_id": bill["id"], **i} for i in items]
    ).execute()
    return {"bill_id": bill["id"]}
