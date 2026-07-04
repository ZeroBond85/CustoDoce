---
name: streamlit-components
description: "Componentes reutilizáveis Streamlit: kpi_card, data_table, dialog, pagination"
---

# streamlit-components

Componentes Streamlit reutilizáveis do CustoDoce.

## KPI Card

```python
from dashboard.components.ui import kpi_card

kpi_card(
    label="Preço médio/kg",
    value="R$ 9.04",
    delta="-3.2%",
    delta_color="inverse"  # verde = bom, vermelho = ruim
)
```

### Alternativa Inline

```python
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Preço médio", "R$ 9.04", "-3.2%")
```

## Data Table (column_config)

```python
from services.dashboard_queries import get_prices_df

df = get_prices_df()
st.dataframe(
    df,
    column_config={
        "price_per_kg": st.column_config.NumberColumn(
            "R$/kg",
            format="R$ %.2f"
        ),
        "price_per_un": st.column_config.NumberColumn(
            "R$/un",
            format="R$ %.2f"
        ),
        "collected_at": st.column_config.DateColumn(
            "Coletado",
            format="DD/MM/YYYY"
        ),
    },
    hide_index=True,
    use_container_width=True
)
```

## Dialog Confirmation (Sprint 7+)

```python
@st.dialog("Confirmar exclusão")
def confirm_delete(item_id):
    st.warning("Esta ação é irreversível.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirmar", type="primary"):
            delete_item(item_id)
            st.rerun()
    with col2:
        if st.button("❌ Cancelar"):
            st.rerun()
```

## Pagination

```python
from services.dashboard_queries import get_all_alert_rules

rules = get_all_alert_rules()
PAGE_SIZE = 25

total_pages = max(1, (len(rules) + PAGE_SIZE - 1) // PAGE_SIZE)
page = st.pagination(
    num_pages=total_pages,
    default=1,
    bind="query-params"
)
start = (page - 1) * PAGE_SIZE
end = start + PAGE_SIZE

for rule in rules[start:end]:
    st.write(rule)
```

## Sidebar Navigation

```python
import streamlit as st

PAINEL = [
    st.Page(visao_geral, title="Visão Geral", icon="📊"),
    st.Page(precos, title="Preços", icon="🔍"),
]

st.navigation({"📊 Painel": PAINEL})
```

## Form (batch operations)

```python
with st.form("batch_form"):
    st.write("批量操作")
    selected = st.multiselect("Selecionar", options)
    action = st.selectbox("Ação", ["enable", "disable", "delete"])
    submitted = st.form_submit_button("Aplicar")
    
    if submitted:
        batch_operation(selected, action)
```

## Antipatterns

- ❌ `st.rerun()` dentro de fragment → usar `st.fragment(parallel=False)`
- ❌ `st.cache_data` em query RPC (já cacheado em dashboard_queries)
- ❌ SQL no page module (sempre via dashboard_queries.py)
- ❌ `label_visibility="collapsed"` em inputs

## Loading States

```python
with st.spinner("Carregando..."):
    data = fetch_data()
    
# ou

placeholder = st.empty()
with placeholder.container():
    placeholder.info("Loading...")
    data = fetch_data()
    placeholder.empty()
```

## Placeholder Patterns

```python
# Update in place
placeholder = st.empty()
for i in range(10):
    placeholder.write(f"Progress: {i*10}%")
    time.sleep(0.5)
```