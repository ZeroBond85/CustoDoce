---
name: telegram-bot
description: "extends global telegram-bot with CustoDoce-specific handlers, commands, and dedup wiring."
---

# telegram-bot — CustoDoce overlay

This overlay extends the global `telegram-bot` skill with concrete CustoDoce details. The universal patterns (Application, ConversationHandler, async handlers, error handling) still live in `~/.config/opencode/skills/telegram-bot/SKILL.md` — this file only adds project-specific shortcuts.

## Active commands
| Command | Handler | Backed by |
|---------|---------|-----------|
| `/start` | `telegram_bot/handlers.py::start` | Static welcome |
| `/preco <ingredient>` | `cmd_preco()` | Supabase RPC `search_prices_rpc` (full-text + fuzzy match) |
| `/lista` | `cmd_lista()` | `ingredients.yaml` (23 canonical ingredients) |
| `/status` | `cmd_status()` | Last successful `scrape.yml` run + recent errors |
| `/help` | `cmd_help()` | Static help text |

## Architecture (CustoDoce-specific)
- **Polling**, not webhook (bot is in private repo, no public domain).
- **Cron-triggered dispatch**: GitHub Actions runs `scrape.yml` 2×/day, posts summary through bot at end. **Always wire `TelegramDedup`** (from global skill) before sending in cron-triggered paths — same payload across overlapping runs = spam.
- **Database access via REST** (`supabase-py` over portal 443, NOT psycopg2 direct). Reason: GitHub Actions runners cannot reach Supabase pooler port; REST works from any egress.
- **Secrets**: `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` come from GitHub Actions repository secrets.

## Key files in this project
| Path | Purpose |
|------|---------|
| `telegram_bot/handlers.py` | All command handlers |
| `telegram_bot/dispatch.py` | Cron-derived alert sender (uses `TelegramDedup`) |
| `config/telegram.yaml` | Allowed chat IDs, admin IDs, message templates |
| `tests/integration/telegram_bot/` | Integration tests with `python-telegram-bot` mock |

## Constraints & antipatterns (CustoDoce)
- ❌ Don't add a new `telegram_bot/` subpackage — keep monolith in `handlers.py` (93 lines max).
- ❌ Don't reach Postgres directly — everything goes through Supabase REST.
- ❌ Don't disable `TelegramDedup` even for "one-off" bursts; 5min dedup window matters.
