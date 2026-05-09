"""
Frontend — Distributed AI Receipt Splitter.

A thin Gradio orchestrator. It holds NO business logic; it only translates
user actions into HTTP calls against the three backend services. This keeps
the frontend independently replaceable (e.g., a future React Native mobile
app could speak the same APIs).
"""

import os
from typing import Tuple

import gradio as gr
import httpx

OCR_URL = os.environ["OCR_URL"].rstrip("/")
SPLIT_URL = os.environ["SPLIT_URL"].rstrip("/")
SETTLE_URL = os.environ["SETTLE_URL"].rstrip("/")

TIMEOUT = httpx.Timeout(60.0)


# --- Service clients (one function per remote endpoint, easy to read) ------

def api_scan(image_path: str, title: str, payer: str) -> dict:
    with open(image_path, "rb") as f:
        r = httpx.post(
            f"{OCR_URL}/scan",
            files={"file": f},
            data={"title": title, "payer_name": payer},
            timeout=TIMEOUT,
        )
    r.raise_for_status()
    return r.json()


def api_get_bill(bill_id: str) -> dict:
    r = httpx.get(f"{SPLIT_URL}/bills/{bill_id}", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def api_add_participant(bill_id: str, name: str) -> dict:
    r = httpx.post(
        f"{SPLIT_URL}/bills/{bill_id}/participants",
        json={"name": name}, timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def api_set_payer(bill_id: str, name: str) -> None:
    httpx.post(f"{SPLIT_URL}/bills/{bill_id}/payer",
               json={"name": name}, timeout=TIMEOUT).raise_for_status()


def api_claim(item_id: str, participant_id: str) -> None:
    httpx.post(f"{SPLIT_URL}/claims",
               json={"item_id": item_id, "participant_id": participant_id},
               timeout=TIMEOUT).raise_for_status()


def api_unclaim(item_id: str, participant_id: str) -> None:
    httpx.delete(
        f"{SPLIT_URL}/claims",
        params={"item_id": item_id, "participant_id": participant_id},
        timeout=TIMEOUT,
    ).raise_for_status()


def api_settle(bill_id: str) -> dict:
    r = httpx.post(f"{SETTLE_URL}/bills/{bill_id}/settle", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# --- View helpers ----------------------------------------------------------

def render_bill(bill_id: str) -> Tuple[str, list, list]:
    """Returns (markdown summary, items table rows, participants list)."""
    snap = api_get_bill(bill_id)
    bill, items, parts, claims = snap["bill"], snap["items"], snap["participants"], snap["claims"]
    name_of = {p["id"]: p["name"] for p in parts}

    # Build items table: [name, price, current claimers]
    claims_by_item: dict[str, list[str]] = {}
    for c in claims:
        claims_by_item.setdefault(c["item_id"], []).append(name_of.get(c["participant_id"], "?"))
    items_rows = [
        [it["name"], float(it["price"]), ", ".join(claims_by_item.get(it["id"], [])) or "—"]
        for it in items
    ]

    summary = (
        f"### {bill['title']}\n"
        f"- **Subtotal:** {bill['subtotal']}\n"
        f"- **Tax:** {bill['tax']}\n"
        f"- **Tip:** {bill['tip']}\n"
        f"- **Total:** {bill['total']}\n"
        f"- **Payer:** {bill.get('payer_name') or '_(not set)_'}\n"
        f"- **Status:** {bill['status']}"
    )
    return summary, items_rows, [p["name"] for p in parts]


# --- Gradio handlers -------------------------------------------------------

def handle_scan(image, title, payer):
    if image is None:
        return "Upload a receipt image first.", "", [], gr.update(choices=[]), gr.update(choices=[])
    try:
        out = api_scan(image, title or "Untitled bill", payer or "")
    except httpx.HTTPStatusError as e:
        return f"OCR failed: {e.response.text}", "", [], gr.update(choices=[]), gr.update(choices=[])
    bill_id = out["bill_id"]
    summary, items_rows, _ = render_bill(bill_id)
    # Auto-add the payer as a participant (common case).
    if payer:
        try:
            api_add_participant(bill_id, payer)
            api_set_payer(bill_id, payer)
        except Exception:
            pass
    snap = api_get_bill(bill_id)
    item_choices = [(f"{i['name']} — {i['price']}", i["id"]) for i in snap["items"]]
    part_choices = [(p["name"], p["id"]) for p in snap["participants"]]
    return bill_id, summary, items_rows, gr.update(choices=item_choices, value=None), gr.update(choices=part_choices, value=None)


def handle_add_participant(bill_id, name):
    if not bill_id or not name:
        return "Provide a bill_id and a name.", [], gr.update(), gr.update()
    api_add_participant(bill_id, name.strip())
    summary, items_rows, _ = render_bill(bill_id)
    snap = api_get_bill(bill_id)
    item_choices = [(f"{i['name']} — {i['price']}", i["id"]) for i in snap["items"]]
    part_choices = [(p["name"], p["id"]) for p in snap["participants"]]
    return summary, items_rows, gr.update(choices=item_choices), gr.update(choices=part_choices)


def handle_claim(bill_id, item_id, participant_id):
    if not (bill_id and item_id and participant_id):
        return "Pick an item and a participant.", []
    api_claim(item_id, participant_id)
    summary, items_rows, _ = render_bill(bill_id)
    return summary, items_rows


def handle_unclaim(bill_id, item_id, participant_id):
    if not (bill_id and item_id and participant_id):
        return "Pick an item and a participant.", []
    api_unclaim(item_id, participant_id)
    summary, items_rows, _ = render_bill(bill_id)
    return summary, items_rows


def handle_settle(bill_id):
    if not bill_id:
        return "Provide a bill_id."
    res = api_settle(bill_id)
    lines = [f"**Payer:** {res['payer']}", "", "### Each person owes:"]
    for b in res["breakdown"]:
        lines.append(f"- {b['participant']}: items {b['items_total']} → owes **{b['owes_total']}**")
    lines += ["", "### Transfers"]
    if not res["transfers"]:
        lines.append("_(payer ate alone, no transfers)_")
    for t in res["transfers"]:
        lines.append(f"- {t['from']} → {t['to']}: **{t['amount']}**")
    return "\n".join(lines)


# --- UI --------------------------------------------------------------------

with gr.Blocks(title="Receipt Splitter") as demo:
    gr.Markdown("# 🧾 Distributed AI Receipt Splitter\n_CS-432 Distributed Computing CEP_")
    bill_id_state = gr.Textbox(label="Bill ID", interactive=True,
                               info="Auto-filled after scan; paste here to resume an old bill.")

    with gr.Tab("1. Scan"):
        with gr.Row():
            img = gr.Image(type="filepath", label="Receipt photo")
            with gr.Column():
                title = gr.Textbox(label="Bill title", placeholder="Dinner at Kolachi")
                payer = gr.Textbox(label="Payer name", placeholder="The friend who paid the bill")
                scan_btn = gr.Button("Scan receipt", variant="primary")
        scan_summary = gr.Markdown()

    with gr.Tab("2. Split"):
        with gr.Row():
            new_part = gr.Textbox(label="Add participant")
            add_part_btn = gr.Button("Add")
        items_table = gr.Dataframe(
            headers=["Item", "Price", "Claimed by"],
            datatype=["str", "number", "str"],
            interactive=False,
        )
        with gr.Row():
            item_picker = gr.Dropdown(label="Item", choices=[])
            part_picker = gr.Dropdown(label="Participant", choices=[])
        with gr.Row():
            claim_btn = gr.Button("✅ Claim", variant="primary")
            unclaim_btn = gr.Button("❌ Un-claim")
        split_summary = gr.Markdown()

    with gr.Tab("3. Settle"):
        settle_btn = gr.Button("Compute settlement", variant="primary")
        settle_out = gr.Markdown()

    # Wire events.
    scan_btn.click(
        handle_scan, [img, title, payer],
        [bill_id_state, scan_summary, items_table, item_picker, part_picker],
    )
    add_part_btn.click(
        handle_add_participant, [bill_id_state, new_part],
        [split_summary, items_table, item_picker, part_picker],
    )
    claim_btn.click(
        handle_claim, [bill_id_state, item_picker, part_picker],
        [split_summary, items_table],
    )
    unclaim_btn.click(
        handle_unclaim, [bill_id_state, item_picker, part_picker],
        [split_summary, items_table],
    )
    settle_btn.click(handle_settle, [bill_id_state], [settle_out])


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
