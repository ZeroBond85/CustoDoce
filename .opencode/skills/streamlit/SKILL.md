---
name: streamlit
description: "extends streamlit patterns for CustoDoce dashboard conventions."
---

# streamlit — CustoDoce overlay

Universal Streamlit patterns (execution model, caching, session_state, multipage, layout, connections, antipatterns) live in `~/.config/opencode/skills/streamlit/SKILL.md`. This overlay documents CustoDoce's specific 18-page admin dashboard structure.

## Dashboard architecture

- Entry: `admin/app.py` (107 lines) — imports 18 pages + sidebar + login gate
- Login: `dashboard/login_page.py` — simple password gate
- Pages: `dashboard/pages/*.py` — each exposes a `render_<name>()` function
- Components: `dashboard/components/ui.py`, `layout.py` — shared widgets, KPI cards, table helpers
- Queries: `services/dashboard_queries.py` — cached Supabase queries, single-source `extract_ppk/pun`

> **Streamlit version**: 1.58.0 (May 2026) — `st.navigation`, `st.pagination`, `st.fragment(parallel=True)`, `st.dialog` all available.

## Page map (19 pages total — 18 registered + 1 orphan)

| Page module | Registered in PAGES | Menu group (target for Sprint 7) | Notes |
|-------------|---------------------|----------------------------------|-------|
| `visao_geral.py` | ✅ | 📊 Painel | Default landing page |
| `precos.py` | ✅ | 📊 Painel | |
| `historico.py` | ✅ | 📊 Painel | |
| `promocoes.py` | ✅ (registered) | 📊 Painel | Integrated in Sprint 7 (18 pages active) |
| `insights.py` | ✅ | 📈 Análises | Has bug: `pivot_table` on numeric `store_count` (Sprint 8) |
| `fontes.py` | ✅ | 📈 Análises | |
| `ranking.py` | ✅ | 📈 Análises | |
| `calculadora.py` | ✅ | 📈 Análises | Cart optimizer (monofonte/multifonte) |
| `revisao.py` | ✅ | 📈 Análises | Review queue |
| `lojas.py` | ✅ | 📦 Cadastros | |
| `ingredientes.py` | ✅ | 📦 Cadastros | |
| `alertas.py` | ✅ | 🔧 Operações | 54 rules, no pagination yet |
| `scrapers.py` | ✅ | 🔧 Operações | |
| `scraper_health.py` | ✅ | 🔧 Operações | |
| `relatorios.py` | ✅ | 🔧 Operações | |
| `flyers.py` | ✅ | 🔧 Operações | Delete without confirmation (Sprint 7 fix) |
| `config.py` | ✅ | ⚙️ Ferramentas | Per-flag save (batch form in Sprint 7) |
| `diagnostico.py` | ✅ | ⚙️ Ferramentas | |
| `capacity_planning.py` | ❌ (orphan) | ⚙️ Ferramentas | Exists on disk, never imported |
| | | | |
| **Total registered** | **18** | 5 groups | Sprint 7 integrated promocoes |
| **Total on disk** | **19** | | sprint 8+9: capacity_planning stays as future |

> **Orphan**: `capacity_planning.py` exists on disk but is NOT imported in `admin/app.py::PAGE_FUNCTIONS` nor `layout.py::PAGES`. Deferred — needs `scraping_logs` aggregation fix first.

## CustoDoce-specific patterns

### Login gate (always at top of `admin/app.py`)
```python
def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        render_login()
        return
    # ... sidebar + page rendering (legacy) or st.navigation (Sprint 7+)
```

### KPI card component (use instead of raw `st.metric`)
```python
from dashboard.components.ui import kpi_card
kpi_card(label="Preço médio/kg", value="R$ 9.04", delta="-3.2%", delta_color="inverse")
```

### Data table with column_config (single source of truth)
```python
from services.dashboard_queries import get_prices_df
df = get_prices_df()
st.dataframe(
    df,
    column_config={
        "price_per_kg": st.column_config.NumberColumn("R$/kg", format="R$ %.2f"),
        "price_per_un": st.column_config.NumberColumn("R$/un", format="R$ %.2f"),
        "collected_at": st.column_config.DateColumn("Coletado"),
    },
    hide_index=True,
    use_container_width=True,
)
```

### `st.navigation()` sidebar grouping (target for Sprint 7)
Replace layout.py's manual sidebar button loop with Streamlit 1.36+ native navigation:

```python
# admin/app.py
import streamlit as st

PAINEL = [
    st.Page(render_visao_geral, title="Visão Geral", icon="📊", url_path="visao_geral"),
    st.Page(render_precos,     title="Preços",      icon="🔍", url_path="precos"),
    st.Page(render_historico,  title="Histórico",    icon="📈", url_path="historico"),
    st.Page(render_promocoes,  title="Promoções",    icon="🏷️", url_path="promocoes"),
]
ANALISES = [
    st.Page(render_insights,     title="Insights",           icon="💡"),
    st.Page(render_fontes,       title="Fontes & Ofertas",   icon="📡"),
    st.Page(render_ranking,      title="Ranking",            icon="🏆"),
    st.Page(render_calculadora,  title="Calculadora",        icon="🧮"),
    st.Page(render_revisao,      title="Revisão",            icon="⚠️"),
]
CADASTROS = [
    st.Page(render_lojas,        title="Lojas",              icon="🏪"),
    st.Page(render_ingredientes,  title="Ingredientes",       icon="🛒"),
]
OPERACOES = [
    st.Page(render_alertas,       title="Alertas",            icon="🔔"),
    st.Page(render_scrapers,      title="Scrapers & Logs",    icon="🤖"),
    st.Page(render_scraper_health, title="Scraper Health",    icon="🏥"),
    st.Page(render_relatorios,    title="Relatórios",         icon="📬"),
    st.Page(render_flyers,        title="Flyers",             icon="📄"),
]
FERRAMENTAS = [
    st.Page(render_config,       title="Configuração",       icon="⚙️"),
    st.Page(render_diagnostico,   title="Diagnóstico",        icon="🔬"),
]

pg = st.navigation({
    "📊 Painel": PAINEL,
    "📈 Análises": ANALISES,
    "📦 Cadastros": CADASTROS,
    "🤖 Operações": OPERACOES,
    "🔧 Ferramentas": FERRAMENTAS,
})

if not st.session_state.get("authenticated"):
    render_login()
    if not st.session_state.get("authenticated"):
        st.stop()

pg.run()
```

### `st.dialog()` confirmations (Sprint 7)
Use native dialogs for destructive actions instead of `st.warning` + inline buttons:

```python
@st.dialog("Confirmar exclusão")
def confirm_delete(flyer_id):
    st.warning("Esta ação é irreversível.")
    if st.button("🗑️ Confirmar Exclusão", type="primary"):
        delete_flyer(flyer_id)
        st.rerun()
```

Pattern applies to: `flyers.py` (delete), `relatorios.py` (send report), `ingredientes.py` (YAML overwrite).

### `st.pagination()` for alert rules (Sprint 8)
54 alert rules rendered on one page — paginate 25/page:

```python
rules = cached_get_all_alert_rules()
PAGE_SIZE = 25
total_pages = max(1, (len(rules) + PAGE_SIZE - 1) // PAGE_SIZE)
page = st.pagination(num_pages=total_pages, default=1, bind="query-params")
start = (page - 1) * PAGE_SIZE
end = start + PAGE_SIZE
```

### Async-safe Supabase calls (port 443 via RPC)
```python
# services/dashboard_queries.py uses supabase_client.py singleton
# which internally uses RPC `exec_sql_query` on port 443
# Never open psycopg2 pool in Streamlit process
```

## Antipatterns specific to CustoDoce
- ❌ Running `st.cache_data(ttl=300)` on raw Supabase `select()` (use RPC wrapper)
- ❌ Calling `st.rerun()` after button click inside a fragment — use `st.fragment(parallel=False)` (1.32+)
- ❌ Embedding SQL strings in page modules — always delegate to `dashboard_queries.py`
- ❌ Using `st.experimental_*` APIs — deprecated, use stable counterparts
- ❌ Orphan pages (`capacity_planning.py`) exist but not imported — must be registered in `admin/app.py::PAGE_FUNCTIONS` AND `layout.py::PAGES` (or st.Page group)
- ❌ `st.fragment(parallel=True)` with `lru_cache` — thread-unsafe; validate with `threading.Lock` before enabling parallel
- ❌ `httpx.post()` without error handling (`services/email_service.py:508`) — wrap in try/except
- ❌ `import smtplib` inside functions in hot path (`services/email_service.py:368,422`) — move to top-level
- ❌ `label_visibility="collapsed"` on input fields — use visible label + `st.caption` helper text instead (a11y)

## Required for new page additions
1. Create `dashboard/pages/nova_pagina.py` with `def render_nova_pagina():`
2. Add entry to `dashboard/components/layout.py::PAGES` dict
3. Run `python scripts/sync_docs.py` (updates AGENTS.md page list automatically)
4. Test locally: `streamlit run admin/app.py`

## Performance baseline
- Target: <3s first paint, <1s page switch (caching hits)
- `dashboard_queries.py` uses `@st.cache_data(ttl=300)` for all read paths
- `dashboard_queries.py` uses `@st.cache_resource` for Supabase client singleton