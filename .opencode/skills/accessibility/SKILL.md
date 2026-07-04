---
name: accessibility
description: "Audits and improves web accessibility against WCAG 2.1 standards. Dashboard a11y compliance."
---

# accessibility

WCAG 2.1 accessibility auditing and implementation.

## When to Use

- Before releasing new dashboard pages
- When adding interactive elements (forms, buttons, modals)
- After UI changes
- For WCAG compliance verification

## WCAG 2.1 Principles (POUR)

| Principle | Description | CustoDoce Target |
|-----------|-------------|------------------|
| **Perceivable** | Info visible to all senses | AA |
| **Operable** | Navigation works for everyone | AA |
| **Understandable** | Clear, predictable UI | AA |
| **Robust** | Works with assistive tech | A |

## Perceivable

### Color Contrast

```css
/* Minimum 4.5:1 for normal text */
/* Minimum 3:1 for large text */

/* Good - CustoDoce palette */
--text: #2D2D2D on --background: #FAF9F6  /* 14.5:1 ✓ */
--primary: #E8B4B8 on white             /* 2.8:1 ✗ */
```

### Images

```html
<!-- Always provide alt text -->
<img src="chart.png" alt="Gráfico de preços do leite condensado">
```

## Operable

### Keyboard Navigation

```css
/* Visible focus indicators */
*:focus {
    outline: 3px solid var(--primary);
    outline-offset: 2px;
}

/* Skip link */
.skip-link {
    position: absolute;
    top: -40px;
    left: 0;
    background: var(--primary);
    color: white;
    padding: 8px 16px;
    z-index: 100;
}
.skip-link:focus { top: 0; }
```

### Form Labels

```python
# ❌ BAD
st.text_input("", label_visibility="collapsed")

# ✅ GOOD
st.text_input(
    "Digite o ingrediente",
    help="Buscar por nome do ingrediente"
)
st.caption("Ex: Leite Condensado, Chocolate 50%")
```

## Understandable

### Error Messages

```python
# ❌ BAD
st.error("Erro")

# ✅ GOOD
st.error("❌ Preço inválido: deve ser número positivo. Ex: 12.50")
```

### Page Titles

```python
st.set_page_config(
    page_title="Preços - CustoDoce",  # Descriptive
    page_icon="🍬"
)
```

## Robust

### HTML Semantics

```html
<!-- ❌ Non-semantic -->
<div class="button" onclick="submit()">Enviar</div>

<!-- ✅ Semantic -->
<button type="submit">Enviar</button>
```

## Streamlit-Specific

```python
# Use native Streamlit a11y features
st.caption()          # Helper text
st.help()             # Tooltips
st.write()            # Announces to screen readers

# Dialog with close button
@st.dialog("Confirmar")
def confirm():
    if st.button("Fechar"):
        st.rerun()
```

## Audit Checklist

```
[] Color contrast ≥4.5:1
[] All images have alt text
[] Keyboard navigation works
[] Focus visible on all elements
[] Skip link present
[] Form labels associated
[] Error messages are descriptive
[] Page titles descriptive
[] No autoplay media
[] Reduced motion respected
```

## Testing

```bash
# Manual test
Tab through page → verify focus order
Check contrast with browser DevTools
Screen reader test (NVDA/VoiceOver)

# Automated
pip install axe-selenium
python -m pytest tests/a11y/
```

## Reference

- WCAG 2.1: https://www.w3.org/TR/WCAG21/
-axe-core: https://github.com/dequelabs/axe-core