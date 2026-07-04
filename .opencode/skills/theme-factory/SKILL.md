---
name: theme-factory
description: "Provides 10 pre-built color and font themes for styling artifacts. Pick or generate custom themes."
---

# theme-factory

Anthropic official skill for applying consistent color and font themes.

## When to Use

- Applying consistent color scheme to reports/slides
- Restyling generated HTML to match brand
- Switching from corporate gray to warm earth tones
- Generating custom theme from description
- Browsing 10 named themes before selection

## 10 Pre-Built Themes

| Theme | Palette | Best For |
|-------|---------|----------|
| **Minimal** | White + Gray + Serif | Docs, reports |
| **Dark Tech** | Dark + Blue neon | SaaS, developer tools |
| **Warm Earth** | Browns + Oranges | Food, lifestyle |
| **Corporate** | Blue + White + Sans | Enterprise |
| **Vibrant** | Saturated + Bold | Creative, marketing |
| **Pastel** | Soft + Light | Feminine, kids |
| **Monochrome** | Black + Gray only | Editorial, art |
| **Neon** | Black + Neon colors | Gaming, nightlife |
| **Nature** | Greens + Browns | Organic, eco |
| **Luxury** | Gold + Black + Serif | Premium brands |

## Usage

### 1. Select Theme

```css
/* Apply theme variables */
:root {
    --primary: #E8B4B8;
    --secondary: #67597A;
    --background: #FAF9F6;
    --text: #2D2D2D;
}
```

### 2. Generate Custom

Describe what you want:
```
"Dark tech with blue accents, monospace fonts, subtle glow effects"
```

The skill generates:
```css
:root {
    --bg-primary: #0D1117;
    --bg-secondary: #161B22;
    --accent: #58A6FF;
    --text-primary: #E6EDF3;
    --text-secondary: #8B949E;
    --font-mono: 'JetBrains Mono', monospace;
    --glow: 0 0 20px rgba(88, 166, 255, 0.3);
}
```

## Typography Pairings

| Theme | Headings | Body |
|-------|----------|------|
| Minimal | Playfair Display | Inter |
| Dark Tech | Space Grotesk | JetBrains Mono |
| Warm Earth | Merriweather | Open Sans |
| Corporate | Montserrat | Source Sans Pro |
| Vibrant | Poppins | Raleway |

## CustoDoce Theme (Custom)

Based on the project's identity (confectionery/bolos):

```css
:root {
    --primary: #E8B4B8;      /* Rosa Doce */
    --secondary: #67597A;   /* Roxo Chantily */
    --background: #FAF9F6;  /* Açúcar */
    --text: #2D2D2D;        /* Chocolate amargo */
    --success: #7CB342;     /* Menta */
    --warning: #FFB74D;     /* Caramelo */
    --font-heading: 'Playfair Display', serif;
    --font-body: 'Inter', sans-serif;
}
```

## Reference

- Source: [Anthropic/skills](https://github.com/anthropics/skills)
- Skill ID: `anthropics/theme-factory`
- Last Updated: 2024