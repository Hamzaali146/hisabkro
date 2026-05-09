"""
Frontend (Streamlit) — Distributed AI Receipt Splitter.

A thin orchestrator. It holds NO business logic; it only translates user
actions into HTTP calls against the three backend services. State that
must survive a page rerun (e.g. bill_id) lives in st.session_state — not
on the server.
"""

import os

import httpx
import streamlit as st

OCR_URL = os.environ["OCR_URL"].rstrip("/")
SPLIT_URL = os.environ["SPLIT_URL"].rstrip("/")
SETTLE_URL = os.environ["SETTLE_URL"].rstrip("/")

TIMEOUT = httpx.Timeout(60.0)


# --- Service clients (one function per remote endpoint) --------------------

def api_scan(file_bytes: bytes, filename: str, title: str, payer: str) -> dict:
    r = httpx.post(
        f"{OCR_URL}/scan",
        files={"file": (filename, file_bytes)},
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
    httpx.post(
        f"{SPLIT_URL}/bills/{bill_id}/payer",
        json={"name": name}, timeout=TIMEOUT,
    ).raise_for_status()


def api_claim(item_id: str, participant_id: str) -> None:
    httpx.post(
        f"{SPLIT_URL}/claims",
        json={"item_id": item_id, "participant_id": participant_id},
        timeout=TIMEOUT,
    ).raise_for_status()


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


# --- Page setup ------------------------------------------------------------

st.set_page_config(
    page_title="Receipt Splitter",
    page_icon="🧾",
    layout="centered",
)

st.title("🧾 Distributed AI Receipt Splitter")
st.caption("CS-432 Distributed Computing — Complex Engineering Activity")

# Session state — Streamlit reruns the script on every interaction, so we
# stash the active bill_id here to keep it across reruns.
if "bill_id" not in st.session_state:
    st.session_state.bill_id = ""

# --- Sidebar: bill_id resume + service health ------------------------------

with st.sidebar:
    st.header("Active bill")
    st.session_state.bill_id = st.text_input(
        "Bill ID",
        value=st.session_state.bill_id,
        help="Auto-filled after scanning. Paste an old ID to resume that bill.",
    )

    st.divider()
    st.header("Backends")
    st.code(f"OCR     → {OCR_URL}\nSPLIT   → {SPLIT_URL}\nSETTLE  → {SETTLE_URL}")

    if st.button("🔄 Refresh bill"):
        st.rerun()


# --- Tabs ------------------------------------------------------------------

tab_scan, tab_split, tab_settle = st.tabs(["1. Scan", "2. Split", "3. Settle"])

# === Tab 1: Scan ===========================================================
with tab_scan:
    st.subheader("Upload a receipt")
    uploaded = st.file_uploader(
        "Receipt photo",
        type=["png", "jpg", "jpeg", "webp"],
    )
    title = st.text_input("Bill title", placeholder="Dinner at Kolachi")
    payer = st.text_input(
        "Payer name",
        placeholder="The friend who fronted the bill",
        help="They'll be auto-added as a participant and marked as the payer.",
    )

    if st.button("Scan receipt", type="primary", disabled=uploaded is None):
        with st.spinner("OCR is working… first call can take ~30s if the Space was asleep."):
            try:
                out = api_scan(uploaded.getvalue(), uploaded.name,
                               title or "Untitled bill", payer or "")
                st.session_state.bill_id = out["bill_id"]
                # Auto-add payer as participant + mark them as payer.
                if payer:
                    try:
                        api_add_participant(out["bill_id"], payer)
                        api_set_payer(out["bill_id"], payer)
                    except Exception:
                        pass
                st.success(f"Bill created. ID: `{out['bill_id']}`")
                with st.expander("Raw OCR text (for debugging)"):
                    st.text(out.get("raw_text", ""))
            except httpx.HTTPStatusError as e:
                st.error(f"OCR failed: {e.response.text}")
            except Exception as e:
                st.error(f"Network error: {e}")

# === Tab 2: Split ==========================================================
with tab_split:
    if not st.session_state.bill_id:
        st.info("Scan a receipt first, or paste a Bill ID in the sidebar.")
    else:
        try:
            snap = api_get_bill(st.session_state.bill_id)
        except Exception as e:
            st.error(f"Couldn't load bill: {e}")
            st.stop()

        bill, items, parts, claims = (
            snap["bill"], snap["items"], snap["participants"], snap["claims"],
        )
        name_of = {p["id"]: p["name"] for p in parts}
        # Map item -> list of participant_ids that claimed it.
        claim_map: dict[str, list[str]] = {}
        for c in claims:
            claim_map.setdefault(c["item_id"], []).append(c["participant_id"])

        # --- Bill summary card --------------------------------------------
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Subtotal", f"Rs {bill['subtotal']}")
        col2.metric("Tax", f"Rs {bill['tax']}")
        col3.metric("Tip", f"Rs {bill['tip']}")
        col4.metric("Total", f"Rs {bill['total']}")
        st.caption(
            f"**{bill['title']}** · payer: "
            f"{bill.get('payer_name') or '_(not set)_'} · status: {bill['status']}"
        )

        # --- Add participant ----------------------------------------------
        st.subheader("Participants")
        with st.form("add_participant", clear_on_submit=True):
            cols = st.columns([3, 1])
            new_name = cols[0].text_input("Name", placeholder="Add a friend")
            submitted = cols[1].form_submit_button("➕ Add")
            if submitted and new_name.strip():
                try:
                    api_add_participant(st.session_state.bill_id, new_name.strip())
                    st.rerun()
                except httpx.HTTPStatusError as e:
                    st.error(e.response.text)

        if parts:
            st.write(" · ".join(f"**{p['name']}**" for p in parts))
        else:
            st.caption("_No participants yet — add a few above._")

        # --- Items + claims ------------------------------------------------
        st.subheader("Items")
        if not parts:
            st.caption("_Add at least one participant before claiming items._")
        else:
            for item in items:
                with st.container(border=True):
                    head = st.columns([3, 1])
                    head[0].markdown(f"**{item['name']}**")
                    head[1].markdown(f"**Rs {item['price']}**")

                    # Multiselect = the source of truth for who claimed this item.
                    # We diff against the existing claim_map and call POST/DELETE
                    # for the changes, so the user just picks names.
                    current = claim_map.get(item["id"], [])
                    selected_ids = st.multiselect(
                        "Claimed by",
                        options=[p["id"] for p in parts],
                        default=current,
                        format_func=lambda pid: name_of[pid],
                        key=f"claim_{item['id']}",
                        label_visibility="collapsed",
                        placeholder="Tap names to claim",
                    )

                    n = len(selected_ids)
                    if n > 0:
                        st.caption(
                            f"split {n} way{'s' if n > 1 else ''} · "
                            f"Rs {round(float(item['price']) / n, 2)} each"
                        )

                    # Sync the diff to the backend.
                    to_add = set(selected_ids) - set(current)
                    to_remove = set(current) - set(selected_ids)
                    if to_add or to_remove:
                        try:
                            for pid in to_add:
                                api_claim(item["id"], pid)
                            for pid in to_remove:
                                api_unclaim(item["id"], pid)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Claim sync failed: {e}")

# === Tab 3: Settle =========================================================
with tab_settle:
    if not st.session_state.bill_id:
        st.info("Scan a receipt first, or paste a Bill ID in the sidebar.")
    elif st.button("💸 Compute settlement", type="primary"):
        with st.spinner("Computing…"):
            try:
                res = api_settle(st.session_state.bill_id)
            except httpx.HTTPStatusError as e:
                st.error(e.response.text)
                st.stop()
            except Exception as e:
                st.error(f"Network error: {e}")
                st.stop()

        st.success(f"Payer: **{res['payer']}**")

        st.subheader("Each person owes")
        st.dataframe(
            [
                {
                    "Participant": b["participant"],
                    "Items total": b["items_total"],
                    "Owes total":  b["owes_total"],
                }
                for b in res["breakdown"]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Transfers")
        if not res["transfers"]:
            st.info("Payer ate alone — no transfers.")
        else:
            for t in res["transfers"]:
                st.markdown(
                    f"- **{t['from']}** → **{t['to']}**: Rs {t['amount']}"
                )
            # WhatsApp-friendly summary the user can copy.
            summary = "\n".join(
                f"{t['from']} → {t['to']}: Rs {t['amount']}"
                for t in res["transfers"]
            )
            st.code(summary, language="text")
            st.caption("Copy the block above and paste into your group chat.")
