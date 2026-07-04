---
name: streamlit-responsive
description: "Responsive design, accessibility (a11y), mobile-first para CustoDoce dashboard"
---

# streamlit-responsive

Responsive design e accessibility patterns para Streamlit.

## Breakpoints

```css
/* Mobile first */
@media (min-width: 640px)  { /* sm */ }
@media (min-width: 768px)  { /* md */ }
@media (min-width: 1024px) { /* lg */ }
@media (min-width: 1280px) { /* xl */ }
```

## Column Layouts

```python
import streamlit as st

# Mobile: 1 coluna, Desktop: 3 colunas
def get_columns(n=3):
    return st.columns([1] * n) if st.session_state.get("is_mobile", False) else st.columns(n)

cols = get_columns(3)
with cols[0]:
    st.metric("Preço", "R$ 9.04")
with cols[1]:
    st.metric("Qtd", "12")
with cols[2]:
    st.metric("Store", "Extra")
```

## Mobile Detection

```python
def is_mobile():
    if "is_mobile" not in st.session_state:
        st.session_state["is_mobile"] = (
            st.context.headers.get("User-Agent", "").lower().find("mobile") >= 0
            or st.query_params.get("mobile", False)
        )
    return st.session_state["is_mobile"]
```

## Accessibility (WCAG 2.1)

### Skip Link

```python
st.markdown("""
<a href="#main-content" style="
    position: absolute;
    top: -40px;
    left: 0;
    background: #67597A;
    color: white;
    padding: 8px;
    z-index: 100;
">Pular para conteúdo</a>
""", unsafe_allow_html=True)
```

### Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
    * {
        animation: none !important;
        transition: none !important;
    }
}
```

### Focus Indicators

```css
*:focus {
    outline: 3px solid #E8B4B8;
    outline-offset: 2px;
}
```

## Keyboard Navigation

```python
# Botão com hint de atalho
st.button("Salvar", help="Ctrl+Enter para salvar")
st.markdown("*Keyboard: Ctrl+Enter para salvar*")
```

## Form Labels

```python
# ❌ NÃO usar
st.text_input("Name", label_visibility="collapsed")

# ✅ CORRETO
st.text_input(
    "Digite seu nome",
    help="Seu nome completo conforme documento"
)
st.caption("Seu nome completo conforme documento de identidade")
```

## Color Contrast

| combinação | Ratio | WCAG |
|------------|-------|------|
| #2D2D2D on #FAF9F6 | 14.5:1 | ✅ AAA |
| #67597A on #FAF9F6 | 5.2:1 | ✅ AA |
| #E8B4B8 on #FFFFFF | 2.8:1 | ❌ Fail |

## Screen Reader Support

```python
# Descrições para elementos complexos
st.dataframe(df, help="Tabela com preços por ingrediente e loja")

# Status announcements
st.status("Processando...", expanded=True, state="running")
```

## Responsive Tables

```python
# Overflow horizontal para mobile
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={...}
)
```

## Performance (Core Web Vitals)

| Métrica | Target |
|---------|--------|
| LCP | <2.5s |
| FID | <100ms |
| CLS | <0.1 |

### Otimizações

```python
# Cache pesado
@st.cache_data(ttl=300)
def heavy_query():
    ...

# Lazy loading
if expand_section:
    st.dataframe(large_data)
```

## Testes de Responsividade

```python
# tests/
- test_streamlit_mobile.py
- test_streamlit_a11y.py
```

## Antipatterns

- ❌ `label_visibility="collapsed"` sem caption
- ❌ Cores com contraste <4.5:1
- ❌ Imagens sem alt text
- ❌ Tables sem overflow horizontal
- ❌ modais sem close button
- ❌ Click handlers sem feedback visual