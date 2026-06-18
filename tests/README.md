# CustoDoce — Plano de Testes

## Checklist por Fase

A cada fase, rodar este checklist completo antes de avançar:

```
[ ] ruff check .                    — lint (zero erros)
[ ] bandit -r admin/ dashboard/ services/ -x tests/ — segurança
[ ] pip-audit                       — CVEs conhecidas
[ ] python -m pytest tests/ -v      — 100% pass
[ ] Responsivo 320/768/1024         — CSS media queries
[ ] XSS review                      — unsafe_allow_html=True
[ ] Secrets vazados                 — git diff + grep credenciais
[ ] pip list --outdated             — deprecações revisadas
[ ] python scripts/deploy_check.py  — deploy health check
```

## Ferramentas

```bash
# Instalar ferramentas de qualidade
pip install -r requirements-dev.txt

# Lint
ruff check . --fix

# Type hints
mypy admin/ dashboard/ services/ --ignore-missing-imports

# Segurança
bandit -r admin/ dashboard/ services/ -x tests/

# Dependências vulneráveis
pip-audit

# Complexidade
radon cc admin/ dashboard/ -a

# Código morto
vulture admin/ dashboard/ services/

# Testes
python -m pytest tests/ -v

# Deprecações
pip list --outdated
```

## Cobertura por Fase

### Fase 1-2 — Base (22 testes)
auth, rate_limiter, imports, UI components, login, YAML, estrutura, CSS, navegação

### Fase 3 — Flyers & History (12+ testes)
- `_flyer_status_color()` / `_flyer_status_label()` / `_format_kg()`
- `flyer_service.py` (upsert, mark_processed, get_recent, get_pending)
- CSS breakpoints flyer (640px, 768px, 1024px)
- Home KPIs flyer
- History chart types

### Fase 4 — CRUD Console (8+ testes)
- Editor lojas (YAML load/save)
- Editor ingredientes (aliases, canonical)
- Normalizer tester (cx 12x395g → 4.74kg)
- Matcher tester (fuzzy threshold 80%)
- CRUD sync (YAML ↔ DB)

### Fase 5 — Control & Reports (6+ testes)
- Email builder
- SMTP tester
- Telegram tester
- Schedule cron validator
- Scraper dispatch payload

### Fase 6 — System Config & Diagnostics (7 testes)
- Health check componentes
- Secrets editor (mask + save + grupos)
- SMTP/Telegram testers inline
- Schedule editor

### Fase 7 — Polish, Config & Deploy (8 testes)
- `config/features.yaml` loading + schema
- `services/config.py` get() + reload()
- `:focus-visible` rings CSS
- `aria-label` sidebar
- Export CSV (st.download_button)
- Config guards (telegram/email/alerts/export)
- `scripts/deploy_check.py` estrutura

### Fase 8 — Dedup, Cleanup & Segurança (6 testes)
- `cleanup_old_prices()` — RPC call + default 90 dias
- `cleanup_old_logs()` — RPC call + default 30 dias
- `cleanup_old_flyers()` — RPC call + default 60 dias
- `insert_review_item()` dedup sem filtro status
- `_sanitize()` escapa XSS (None, texto, número, script, aspas, &)
- `cleanup_imports()` — imports + assinaturas

### Fase 9 — Dashboard Insights (2 testes)
- `test_all_imports` — 17 páginas + handlers callable
- `test_cleanup_imports` — imports + default values

## Regras

1. **Nunca secrets no código** — usar env vars ou Streamlit Cloud Secrets
2. **Testes sem dependência externa** — mockar Supabase, APIs, etc.
3. **Responsivo validado** — 320px, 768px, 1024px
4. **Últimas versões estáveis** se não quebrar funcionalidades
