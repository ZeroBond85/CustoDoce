---
name: api-design
description: "extends global api-design with CustoDoce Supabase REST + RPC conventions."
---

# api-design — CustoDoce overlay

Universal API design patterns (REST resource naming, status codes, RFC 7807, OpenAPI, versioning, rate limiting) are in `~/.config/opencode/skills/api-design/SKILL.md`. This overlay adds CustoDoce specifics.

## Reality of the CustoDoce "API"
CustoDoce does **not** run a custom REST server. The "API" surface is:
1. **Supabase REST** (auto-generated from tables) — used by the Telegram bot and Streamlit dashboard.
2. **Supabase RPCs** — server-side functions for any non-trivial write or read (see `docs-writer` overlay).
3. **Telegram Bot commands** — user-input endpoints.

That changes some design defaults:

| Concern | Default REST convention | CustoDoce reality |
|---------|------------------------|-------------------|
| Auth | OAuth2 / Bearer + RBAC | Supabase JWT for service-role, anon-key for public reads |
| Versioning | URL prefix `/v1/` | Implicit via RPC naming (`upsert_price_rpc_v1`) |
| Rate limit | Headers + middleware | Free tier (500MB egress) — don't implement custom rate limits |
| Error format | RFC 7807 | Supabase PostgREST error codes (`PGRST116`, `23505`, etc.) |

## Auth boundaries
- **Anon key**: read-only on `ingredients`, `stores`, filtered views on `prices`. NEVER on writes.
- **Service-role key**: full DB access but ONLY inside trusted contexts: GitHub Actions cron, RPC functions, admin Streamlit pages. Never ship it to client code.
- **Telegram chat ID**: hard-allow in `config/telegram.yaml`; reject unknown chat IDs silently.

## RPC design rules (CustoDoce)
- **Single responsibility per RPC**: one action per function. Don't merge `upsert+audit` into a single RPC.
- **Naming**: `<action>_<entity>_rpc` suffix (`upsert_price_rpc`, `search_prices_rpc`).
- **Parameters**: use `p_` prefix for params (`p_ingredient_id`). Snake_case throughout.
- **Return**: return the affected row when the caller needs it; return void for fire-and-forget.
- **Errors**: raise SQLSTATE codes (`P0001` for app-specific, `22P02` for invalid input). Client maps codes to UX messages.

## OpenAPI for the future
If we ever expose a public REST API (e.g. third-party developers asking for price feeds), the global skill has a full OpenAPI 3.0.3 template. Keep it in `docs/api/openapi.yaml` and reference it from `README.md`.
