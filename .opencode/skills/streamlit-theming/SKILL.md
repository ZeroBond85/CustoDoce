---
name: streamlit-theming
description: "Custom theming para CustoDoce Streamlit dashboard: cores, fonts, layout, visual identity"
---

# streamlit-theming

Custom theme e visual identity para CustoDoce dashboard.

## CustoDoce Color Palette

```python
# .streamlit/config.toml
[theme]
primaryColor = "#E8B4B8"      # Rosa CustoDoce
secondaryColor = "#67597A"     # Roxo suave
backgroundColor = "#FAF9F6"    # Off-white
textColor = "#2D2D2D"          # Cinza escuro
font = "sans serif"

[theme].fontFace = "Inter"
```

## Paleta de Cores

| Uso | Cor | Hex |
|-----|-----|-----|
| Primary (botões, destaques) | Rosa | `#E8B4B8` |
| Secondary (cards, containers) | Roxo | `#67597A` |
| Background | Off-white | `#FAF9F6` |
| Text | Cinza escuro | `#2D2D2D` |
| Success | Verde | `#4CAF50` |
| Warning | Amarelo | `#FFC107` |
| Error | Vermelho | `#F44336` |
| Info | Azul | `#2196F3` |

## Fontes

```toml
# .streamlit/config.toml
[theme]
font = "sans serif"
```

| Opção | Uso |
|-------|-----|
| Inter | Default (recomendado) |
| Roboto | Alternative |
| sans-serif | Sistema |

## Custom CSS

```python
def add_custom_css():
    st.markdown("""
    <style>
        /* Main background */
        .stApp {
            background-color: #FAF9F6;
        }
        
        /* Cards */
        .stCard {
            background-color: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        /* KPI values */
        .metric-value {
            color: #67597A;
            font-weight: 700;
        }
        
        /* Headers */
        h1, h2, h3 {
            color: #2D2D2D;
        }
    </style>
    """, unsafe_allow_html=True)
```

## Theme Factory (10 Presets)

Se precisar de tema diferente:

1. **Minimal** — branco + cinza + serif
2. **Dark Tech** — fundo escuro + azul neon
3. **Warm** — tons terrosos + fonte serif
4. **Corporate** — azul institucional + sem serifa
5. **Vibrant** — cores saturadas + bold

## Aplicar Tema

```python
# admin/app.py
import streamlit as st

st.set_page_config(
    page_title="CustoDoce",
    page_icon="🍬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
add_custom_css()
```

## Antipatterns

- ❌ Cores harsh para accessibility (contraste <4.5:1)
- ❌ Font excessivamente decorativa
- ❌ Background muito escuro ou brilhante
- ❌ Animations excessivas (performance)

## Responsivo (breakpoints)

```css
/* Mobile */
@media (max-width: 768px) {
    .stApp { padding: 10px; }
}

/* Tablet */
@media (min-width: 769px) and (max-width: 1024px) {
    .stApp { padding: 20px; }
}

/* Desktop */
@media (min-width: 1025px) {
    .stApp { padding: 32px; max-width: 1400px; }
}
```

## Atualização 2026

Streamlit 1.58+ suporta:
- `st.color_picker` nativo
- Tema automático (dark/light)
- Cores por página