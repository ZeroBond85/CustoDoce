-- Migration 001: Config tables for CustoDoce
-- Run this in Supabase SQL Editor

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ============================================================
-- INGREDIENTS (replace config/ingredients.yaml)
-- ============================================================
create table if not exists ingredients (
    id uuid primary key default gen_random_uuid(),
    canonical_name text unique not null,
    category text,
    aliases text[] default '{}',
    unit_target text default 'kg',
    active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_ingredients_active on ingredients(active);
create index if not exists idx_ingredients_category on ingredients(category);

-- Trigger for updated_at
create or replace function update_updated_at_column()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end; $$;

drop trigger if exists trg_ingredients_updated_at on ingredients;
create trigger trg_ingredients_updated_at
    before update on ingredients
    for each row execute function update_updated_at_column();

-- ============================================================
-- STORES (replace config/stores.yaml)
-- ============================================================
create table if not exists stores (
    id uuid primary key default gen_random_uuid(),
    name text unique not null,
    tier int check (tier between 1 and 4),
    type text,
    logistics text,
    city text[],
    zone text,
    url_pattern text,
    base_url text,
    api_endpoint text,
    search_url text,
    selectors jsonb default '{}',
    publish_day text,
    collection_method text,
    visit_frequency text,
    scraper text,
    contact text,
    coverage text,
    priority int default 99,
    active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_stores_active on stores(active);
create index if not exists idx_stores_tier on stores(tier);
create index if not exists idx_stores_type on stores(type);
create index if not exists idx_stores_scraper on stores(scraper);

drop trigger if exists trg_stores_updated_at on stores;
create trigger trg_stores_updated_at
    before update on stores
    for each row execute function update_updated_at_column();

-- ============================================================
-- SCHEDULES (replace GitHub Actions cron)
-- ============================================================
create table if not exists schedules (
    id uuid primary key default gen_random_uuid(),
    name text unique not null,
    cron_expression text not null,
    timezone text default 'America/Sao_Paulo',
    payload jsonb default '{}',
    enabled boolean default true,
    last_run timestamptz,
    next_run timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_schedules_enabled on schedules(enabled);

drop trigger if exists trg_schedules_updated_at on schedules;
create trigger trg_schedules_updated_at
    before update on schedules
    for each row execute function update_updated_at_column();

-- ============================================================
-- SCRAPE FREQUENCIES (per store/tier config)
-- ============================================================
create table if not exists scrape_frequencies (
    id uuid primary key default gen_random_uuid(),
    store_id TEXT references stores(id) on delete cascade,
    tier int,
    frequency_minutes int default 1440,
    max_retries int default 2,
    timeout_seconds int default 30,
    rate_limit_per_minute int default 10,
    enabled boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_scrape_freq_store on scrape_frequencies(store_id);
create index if not exists idx_scrape_freq_tier on scrape_frequencies(tier);
create index if not exists idx_scrape_freq_enabled on scrape_frequencies(enabled);

drop trigger if exists trg_scrape_freq_updated_at on scrape_frequencies;
create trigger trg_scrape_freq_updated_at
    before update on scrape_frequencies
    for each row execute function update_updated_at_column();

-- ============================================================
-- ALERT RECIPIENTS (email, telegram, whatsapp)
-- ============================================================
create table if not exists alert_recipients (
    id uuid primary key default gen_random_uuid(),
    channel text not null check (channel in ('email','telegram','whatsapp')),
    target text not null,
    name text,
    active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_alert_recipients_channel on alert_recipients(channel);
create index if not exists idx_alert_recipients_active on alert_recipients(active);

drop trigger if exists trg_alert_recipients_updated_at on alert_recipients;
create trigger trg_alert_recipients_updated_at
    before update on alert_recipients
    for each row execute function update_updated_at_column();

-- ============================================================
-- ALERT RULES (when to notify)
-- ============================================================
create table if not exists alert_rules (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    channel text not null check (channel in ('email','telegram','whatsapp')),
    trigger text not null check (trigger in (
        'price_drop',
        'new_low_price',
        'daily_report',
        'scrape_failure',
        'review_queue_threshold'
    )),
    condition jsonb default '{}',
    frequency_minutes int default 1440,
    recipients uuid[] not null default '{}',
    template text,
    enabled boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

create index if not exists idx_alert_rules_trigger on alert_rules(trigger);
create index if not exists idx_alert_rules_enabled on alert_rules(enabled);

drop trigger if exists trg_alert_rules_updated_at on alert_rules;
create trigger trg_alert_rules_updated_at
    before update on alert_rules
    for each row execute function update_updated_at_column();

-- ============================================================
-- FEATURE FLAGS (replace config/features.yaml)
-- ============================================================
create table if not exists feature_flags (
    key text primary key,
    enabled boolean default false,
    description text,
    updated_at timestamptz default now()
);

create index if not exists idx_feature_flags_enabled on feature_flags(enabled);

drop trigger if exists trg_feature_flags_updated_at on feature_flags;
create trigger trg_feature_flags_updated_at
    before update on feature_flags
    for each row execute function update_updated_at_column();

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================
alter table ingredients enable row level security;
alter table stores enable row level security;
alter table schedules enable row level security;
alter table scrape_frequencies enable row level security;
alter table alert_recipients enable row level security;
alter table alert_rules enable row level security;
alter table feature_flags enable row level security;

-- Admin policies (service role has full access via service_client)
create policy "service_role_all" on ingredients for all using (auth.role() = 'service_role');
create policy "service_role_all" on stores for all using (auth.role() = 'service_role');
create policy "service_role_all" on schedules for all using (auth.role() = 'service_role');
create policy "service_role_all" on scrape_frequencies for all using (auth.role() = 'service_role');
create policy "service_role_all" on alert_recipients for all using (auth.role() = 'service_role');
create policy "service_role_all" on alert_rules for all using (auth.role() = 'service_role');
create policy "service_role_all" on feature_flags for all using (auth.role() = 'service_role');

-- Anon read-only for dashboard (adjust as needed)
create policy "anon_read" on ingredients for select using (true);
create policy "anon_read" on stores for select using (true);
create policy "anon_read" on schedules for select using (true);
create policy "anon_read" on scrape_frequencies for select using (true);
create policy "anon_read" on alert_recipients for select using (true);
create policy "anon_read" on alert_rules for select using (true);
create policy "anon_read" on feature_flags for select using (true);