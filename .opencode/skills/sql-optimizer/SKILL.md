---
name: sql-optimizer
description: "extends global sql-optimizer with CustoDoce schema, RPCs, and indexes reality."
---

# sql-optimizer — CustoDoce overlay

Universal SQL patterns (index design, RLS optimization, migration safety, partitioning) live in `~/.config/opencode/skills/sql-optimizer/SKILL.md`. This overlay focuses on CustoDoce-specific schema and RPCs.

## Core tables (live snapshot)
| Table | Purpose | Cardinality estimate |
|-------|---------|----------------------|
| `prices` | Time-series price records | 50k/year → 1M over 5 years |
| `ingredients` | Canonical ingredient master (23 rows) | static |
| `stores` | 51 stores (Tier 1-4) | static |
| `review_queue` | Low-confidence matches awaiting human review | 100-500 rows |
| `scrape_runs` | Audit trail per store per run | 365 × 51 = 18k rows/year |

## Critical indexes (do not remove)
```sql
-- prices lookups by (ingredient, store, date) — most common query
CREATE INDEX idx_prices_ingredient_store_date
  ON prices (ingredient_id, store_id, collected_at DESC);

-- prevent duplicate upserts
CREATE UNIQUE INDEX uq_prices_ingredient_store_date
  ON prices (ingredient_id, store_id, collected_at);

-- review_queue scans pending items
CREATE INDEX idx_review_pending
  ON review_queue (created_at)
  WHERE status = 'pending';
```

## RPCs (server-side, must be used for writes)
| RPC | Replaces | Why |
|-----|----------|-----|
| `upsert_price_rpc(...)` | Client-side `.upsert()` | Avoid 42P10 constraint missing errors |
| `search_prices_rpc(text)` | Direct SELECT with ILIKE | Server-side fingerprint normalization |
| `exec_sql_query(text)` | psycopg2/SSH tunnel | Runs on port 443 from any network |

**Rule of thumb**: if you're tempted to write raw SQL from the Python client, wrap it in an RPC first.

## Migration workflow (CRITICAL for this project)
1. Append to a `supabase/00N_*.sql` file (incremental, idempotent).
2. Run `python scripts/deploy_database.py --dry-run` first.
3. Apply with `python scripts/deploy_database.py --execute`.
4. **Behavioral verification via REST API** (per project `AGENTS.md` rule 5): go beyond schema validation, do an insert + assert against the live RPC.
5. **Never** trust "migration applied" log lines; psycopg2 hidden commits are flaky and the rest of the team relies on REST tests.

## RLS posture
- `prices`, `review_queue`, `scrape_runs` — read-only to `anon`, write only via service role (RPCs).
- `ingredients`, `stores` — public read.
- No row-level user-id filters yet (single-tenant data). Don't add them speculatively.
