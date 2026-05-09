-- =====================================================================
-- Distributed AI Receipt Splitter — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
-- =====================================================================

-- A "bill" represents one restaurant visit / one receipt being split.
create table if not exists bills (
    id           uuid primary key default gen_random_uuid(),
    title        text not null,
    image_url    text,
    payer_name   text,                          -- who fronted the cash
    subtotal     numeric(10,2) default 0,
    tax          numeric(10,2) default 0,
    tip          numeric(10,2) default 0,
    total        numeric(10,2) default 0,
    status       text default 'pending',        -- pending → claiming → settled
    created_at   timestamptz default now()
);

-- People involved in splitting this bill.
create table if not exists participants (
    id          uuid primary key default gen_random_uuid(),
    bill_id     uuid not null references bills(id) on delete cascade,
    name        text not null,
    created_at  timestamptz default now(),
    unique(bill_id, name)
);

-- Line items extracted from the receipt (by OCR Service).
create table if not exists items (
    id          uuid primary key default gen_random_uuid(),
    bill_id     uuid not null references bills(id) on delete cascade,
    name        text not null,
    price       numeric(10,2) not null,
    qty         integer default 1,
    created_at  timestamptz default now()
);

-- A claim = "this person ate (a fraction of) this item".
-- For a solo item: 1 claim with share=1.0
-- For a shared item between N people: N claims, share=1/N each (or custom).
create table if not exists claims (
    id              uuid primary key default gen_random_uuid(),
    item_id         uuid not null references items(id) on delete cascade,
    participant_id  uuid not null references participants(id) on delete cascade,
    share           numeric(6,4) default 1.0,
    created_at      timestamptz default now(),
    unique(item_id, participant_id)
);

-- Final output: who pays whom.
create table if not exists settlements (
    id                 uuid primary key default gen_random_uuid(),
    bill_id            uuid not null references bills(id) on delete cascade,
    from_participant   uuid not null references participants(id),
    to_participant     uuid not null references participants(id),
    amount             numeric(10,2) not null,
    created_at         timestamptz default now()
);

create index if not exists idx_items_bill        on items(bill_id);
create index if not exists idx_claims_item       on claims(item_id);
create index if not exists idx_participants_bill on participants(bill_id);
create index if not exists idx_settlements_bill  on settlements(bill_id);

-- Optional: a view that materializes "what each person owes" before settlement.
-- Useful for the Settlement Service algorithm.
create or replace view participant_totals as
select
    p.id            as participant_id,
    p.bill_id,
    p.name,
    coalesce(sum(i.price * c.share), 0)::numeric(10,2) as items_total
from participants p
left join claims c       on c.participant_id = p.id
left join items i        on i.id = c.item_id
group by p.id, p.bill_id, p.name;
