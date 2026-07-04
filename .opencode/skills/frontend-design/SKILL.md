---
name: frontend-design
description: "Build frontend interfaces with intentional aesthetic direction. Forces distinct visual tone before coding."
---

# frontend-design

Anthropic official skill for building frontend interfaces with intentional aesthetic direction.

## When to Use

- Building landing pages that avoid generic gradient-hero templates
- Styling dashboards with brutalist or editorial aesthetic
- Generating HTML/CSS with custom typography and motion
- Prototyping web components with scroll-triggered animations
- Converting plain UI mockups into visually distinct pages

## Philosophy

Push past generic patterns by committing to a specific visual tone **before** writing code. Instead of producing purple-gradient-on-white output, this skill forces:

1. **Distinct aesthetic commitment** upfront
2. **Specific font choices**
3. **Spatial composition**
4. **Motion** rather than generic patterns

## Workflow

### 1. Define Aesthetic Direction

Ask or determine:
- What emotion/tone? (Professional, playful, minimal, bold)
- What constraints? (Brand colors, existing design system)
- What makes this different from generic AI output?

### 2. Font Selection

```css
/* Example: Editorial */
font-family: 'Playfair Display', Georgia, serif;
font-weight: 400-700;

/* Example: Modern Sans */
font-family: 'Inter', -apple-system, sans-serif;
font-weight: 300-600;
```

### 3. Color System

```css
:root {
    --primary: #E8B4B8;      /* CustoDoce pink */
    --secondary: #67597A;    /* Muted purple */
    --background: #FAF9F6;   /* Warm white */
    --text: #2D2D2D;         /* Near black */
    --accent: #4A4A4A;       /* Neutral accent */
}
```

### 4. Motion Principles

```css
/* Purposeful, not decorative */
transition: all 0.2s ease-out;    /* Fast, responsive */
animation: fadeIn 0.3s ease-out;   /* Subtle entrances */

/* Respect reduced-motion */
@media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
}
```

## Output

Production-ready HTML/CSS with:
- Semantic HTML structure
- CSS custom properties for theming
- Responsive breakpoints
- Accessibility considerations
- No generic AI-slop patterns

## Antipatterns

- ❌ Purple gradient on white backgrounds
- ❌ Inter font as default (use distinctive choices)
- ❌ Centered everything, max-width containers
- ❌ Hover animations that feel gimmicky
- ❌ Drop shadows without purpose

## Reference

- Source: [Anthropic/skills](https://github.com/anthropics/skills)
- Skill ID: `anthropics/frontend-design`
- Last Updated: 2024