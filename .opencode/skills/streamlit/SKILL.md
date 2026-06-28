---
name: streamlit
description: "extends streamlit patterns for CustoDoce dashboard conventions."
---

# streamlit — CustoDoce overlay

Universal Streamlit patterns (execution model, caching, session_state, multipage, layout, connections, antipatterns) live in `~/.config/opencode/skills/streamlit/SKILL.md`. This overlay documents CustoDoce's specific 17-page admin dashboard structure.

## Dashboard architecture

- Entry: `admin/app.py` (107 lines) — imports 17 pages + sidebar + login gate
- Login: `dashboard/login_page.py` — simple password gate (no OAuth yet)
- Pages: `dashboard/pages/*.py` — each exposes a `render_<name>()` function
- Components: `dashboard/components/ui.py`, `layout.py` — shared widgets, KPI cards, table helpers
- Queries: `services/dashboard_queries.py` — cached Supabase queries, single-source `extract_ppk/pun`

## Page map (auto-synced by `scripts/sync_docs.py`)

| Page module | Route / sidebar label | Primary data source |
|-------------|----------------------|---------------------|
| `visao_geral.py` | 📊 Visão Geral | `dashboard_queries.get_overview()` |
| `precos.py` | 💰 Preços | `get_prices_df()` |
| `historico.py` | 📈 Histórico | `get_price_history()` |
| `comparativo.py` | ⚖️ Comparativo | `get_store_comparison()` |
| `alertas.py` | 🚨 Alertas | `get_active_alerts()` |
| `ingredientes.py` | 🧂 Ingredientes | `get_ingredient_catalog()` |
| `lojas.py` | 🏪 Lojas | `get_store_catalog()` |
| `tendencias.py` | 📊 Tendências | `get_trend_analysis()` |
| `otimizador.py` | 🛒 Otimizador | `optimize_shopping_cart()` |
| `anomalias.py` | 🔍 Anomalias | `detect_anomalies()` |
| `capacidade.py` | 📦 Capacidade | `get_capacity_plan()` |
| `qualidade.py` | ✅ Qualidade | `get_quality_report()` |
| `logs.py` | 📋 Logs | `get_audit_logs()` |
| `config.py` | ⚙️ Config | `get_config_state()` |
| `backup.py` | 💾 Backup | `get_backup_status()` |
| `relatorios.py` | 📄 Relatórios | `generate_report()` |
| `debug.py` | 🐛 Debug | `get_debug_info()` |

## CustoDoce-specific patterns

### Login gate (always at top of `admin/app.py`)
```python
def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        render_login()
        return
    # ... sidebar + page rendering
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

### Async-safe Supabase calls (port 443 via RPC)
```python
# services/dashboard_queries.py uses supabase_client.py singleton
# which internally uses RPC `exec_sql_query` on port 443
# Never open psycopg2 pool in Streamlit process
```

## Antipatterns specific to CustoDoce
- ❌ Running `st.cache_data(ttl=300)` on raw Supabase `select()` (use RPC wrapper)
- ❌ Calling `st.rerun()` after button click inside a fragment (use `st.fragment` in 1.32+)
- ❌ Embedding SQL strings in page modules (always delegate to `dashboard_queries.py`)
- ❌ Using `st.experimental_*` APIs (deprecated, use stable counterparts)

## Required for new page additions
1. Create `dashboard/pages/nova_pagina.py` with `def render_nova_pagina():`
2. Add entry to `dashboard/components/layout.py::PAGES` dict
3. Run `python scripts/sync_docs.py` (updates AGENTS.md page list automatically)
4. Test locally: `streamlit run admin/app.py`

## Performance baseline
- Target: <3s first paint, <1s page switch (caching hits)
- `dashboard_queries.py` uses `@st.cache_data(ttl=300)` for all read paths
- `dashboard_queries.py` uses `@st.cache_resource` for Supabase client singleton