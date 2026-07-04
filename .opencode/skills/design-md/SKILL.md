---
name: design-md
description: "Creates and manages DESIGN.md files for documenting design decisions before implementation."
---

# design-md

Design document creation and management following Google's Stitch methodology.

## When to Use

- Before implementing new features
- When redesigning existing pages
- For complex UI changes
- For team alignment on design decisions

## DESIGN.md Template

```markdown
# Feature: [Nome]

## 1. Concept & Vision

[O que é, por que existe, como deve sentir]

## 2. Design Language

### Aesthetic Direction
[Brief description: minimal, playful, professional...]

### Color Palette
```
Primary:    #XXXXXX
Secondary:  #XXXXXX
Background: #XXXXXX
Text:       #XXXXXX
Accent:     #XXXXXX
```

### Typography
- Headings: [Font, weight]
- Body: [Font, weight]
- Mono: [Font]

### Motion
[Animation principles, timing, easing]

## 3. Layout & Structure

### Page Structure
[Header, content areas, footer]

### Responsive Strategy
[Breakpoints, mobile-first approach]

## 4. Features & Interactions

### Core Features
| Feature | Behavior | States |

### Interaction Details
[Hover, click, focus states]

### Edge Cases
[Empty, error, loading]

## 5. Component Inventory

| Component | Appearance | States |

## 6. Technical Approach

[Streamlit components, data flow, API]

## 7. Open Questions

[Items to decide]
```

## Workflow

```
1. Create DESIGN.md (this skill)
2. Review with team/stakeholder
3. Implement based on spec
4. Update DESIGN.md if changes needed
5. Link in PR description
```

## Example: CustoDoce Ranking Page

```markdown
# Ranking de Preços

## 1. Concept & Vision
Página para comparar preços entre lojas.
Visual limpo, focado em dados.

## 2. Design Language
- Aesthetic: Data-focused, minimal
- Colors: CustoDoce palette
- Motion: Subtle, 200ms transitions

## 3. Layout
- Filtros no topo
- Tabela com ordenação
- Cards de insight abaixo

## 4. Features
- Sort by price, store, ingredient
- Filter by region
- Highlight lowest price

## 5. Components
- st.dataframe com column_config
- st.pills para filtros
- kpi_card para summary
```

## Antipatterns

- ❌ Writing DESIGN.md after implementation
- ❌ Leaving "Open Questions" empty
- ❌ Vague descriptions ("looks good")
- ❌ No technical approach section
- ❌ Not linking to relevant specs (AGENTS.md)

## Integration

- Links from: PR description, issue, ticket
- Updates: After implementation review
- Archival: Move to `docs/archive/` when deprecated

## Reference

- Source: [Google Labs Stitch](https://github.com/google-labs-code/stitch)
- Design.md spec: https://google.github.com/stitch