# Skills do CustoDoce

> Gerado por `python scripts/sync_docs.py --sync`. **Não editar à mão.**
> Última atualização: 2026-07-16 01:58 UTC
> Total: 34 skills instaladas

| Categoria | Skill | Descrição |
|---|---|---|
| CustoDoce Core | brand-extractor | Extrai brand de produto: 3 níveis (word-boundary exact > substring boundaries > fuzzy RapidFuzz ≥80%). Funções reais: extract_brand() → str, extract_brand_from_all() → str | None. |
| CustoDoce Core | llm-integration | LLMClassifier com multi-provider (Groq → OpenRouter → HuggingFace), semantic matching (sentence-transformers), cache SQLite e circuit breaker |
| CustoDoce Core | price-normalizer | Normaliza raw_price + raw_unit → qty, unit_kg, total_kg, price_per_kg, price_per_un via NormalizedPrice class |
| CustoDoce Core | self-healing | Scraper self-healing: record_failure/success(), attempt_heal(), classify_error_for_alert — regra obrigatória AGENTS.md lição #15 |
| CustoDoce Core | web-scraper | CustoDoce 3-tier scraping: PDF (9 atacadistas), VTEX API (e-commerce), agregadores (Tiendeo/Guiato). Self-healing via services/scraper_health.py |
| Externas (não adotadas) | frontend-design | Build frontend interfaces with intentional aesthetic direction. Forces distinct visual tone before coding. |
| Externas (não adotadas) | theme-factory | Provides 10 pre-built color and font themes for styling artifacts. Pick or generate custom themes. |
| Ops | skills-maintenance | Script para manter skills atualizadas: check, update, backup, e validação |
| Overlay Global | api-design | extends global api-design with CustoDoce Supabase REST + RPC conventions. |
| Overlay Global | docs-writer | extends global docs-writer with CustoDoce documentation conventions. |
| Overlay Global | github-actions | extends global github-actions with the 7 CustoDoce workflows + free-tier budget. |
| Overlay Global | project-doc-sync | extends docs/sync_docs behavior for CustoDoce doc set conventions. |
| Overlay Global | sql-optimizer | extends global sql-optimizer with CustoDoce schema, RPCs, and indexes reality. |
| Overlay Global | telegram-bot | extends global telegram-bot with CustoDoce-specific handlers, commands, and dedup wiring. |
| Overlay Global | test-total-runner | Run CustoDoce end-to-end test pipeline (lint + mypy + 11 phases) and produce JSON report |
| Sem categoria | supabase-pentest | Audita RLS, RPC, buckets e auth config do Supabase via exec_sql_query. db_security_lint.py com --quick (CI) e --full modes. |
| Streamlit UI | accessibility | Audits and improves web accessibility against WCAG 2.1 standards. Dashboard a11y compliance. |
| Streamlit UI | design-md | Creates and manages DESIGN.md files for documenting design decisions before implementation. |
| Streamlit UI | streamlit | extends streamlit patterns for CustoDoce dashboard conventions. |
| Streamlit UI | streamlit-components | Componentes reutilizáveis Streamlit: kpi_card, data_table, dialog, pagination |
| Streamlit UI | streamlit-responsive | Responsive design, accessibility (a11y), mobile-first para CustoDoce dashboard |
| Streamlit UI | streamlit-theming | Custom theming para CustoDoce Streamlit dashboard: cores, fonts, layout, visual identity |
| Vibe Coding | architecture-review | Before committing to an implementation plan, run this skill to stress-test the proposed architecture. Catches over-engineering, circular dependencies, missing failure modes, security gaps, and scalability cliffs — before any code is written. Acts as a "second eye" on the plan. |
| Vibe Coding | brainstorming | Refina ideias usando método socrático. Agent faz perguntas para clarificar escopo. |
| Vibe Coding | code-review | Systematic code review skill covering both requesting a review (pre-commit checklist) and receiving and responding to review feedback. Checks code quality, security, test coverage, architectural alignment, and documentation before any code is committed. |
| Vibe Coding | dependency-audit | Periodically scan project dependencies for security vulnerabilities, outdated packages, and unused dependencies. Produces a prioritized action report. Run before every major release and at least once per month. |
| Vibe Coding | documentation-sync | After any significant code change — new feature, API modification, config change, or architectural refactor — run this skill to identify which documentation files are now stale and update them. Keeps docs and code from drifting apart. |
| Vibe Coding | github | Manages all git operations (commit, push, branch management, PR creation) in a standardized, safe, and consistent way. Automatically runs the code-review skill before any commit. Enforces Conventional Commits standard. Handles the full lifecycle: branch → review → commit → push → PR. |
| Vibe Coding | incident-response | When something breaks in production: triage the severity, gather evidence, identify root cause, deploy a fix or mitigation, and write a post-mortem. Provides a calm, structured process for high-stress moments. |
| Vibe Coding | knowledge-base-update | Use this skill whenever you learn something important during a conversation: a key architectural decision, a project-specific convention, a bug root-cause, a 3rd-party API quirk, or any fact that would help a future agent avoid re-doing the same research. Writes structured entries to the project's knowledge base so that context persists across conversations and agents. |
| Vibe Coding | project-context-primer | Run this skill at the very start of any new conversation or agent session before writing a single line of code. It loads the project's architectural decisions, conventions, known gotchas, and current task status so the agent operates with full context — not as a blank slate. |
| Vibe Coding | prompt-enhancer | Transforma requisições vagas em prompts claros e acionáveis. |
| Vibe Coding | test-driven-execution | Before writing any implementation code, define the acceptance criteria and test cases that the code must satisfy. Agents then write code to pass these tests — not to match a vague description. Eliminates "it works on my machine" and "I think this is what you wanted" outcomes. |
| Vibe Coding | writing-plans | Gera plano de implementação detalhado a partir de scope aprovado. |

## Sub-themes (theme-factory)

arctic-frost, botanical-garden, desert-rose, forest-canopy, golden-hour, midnight-galaxy, modern-minimalist, ocean-depths, sunset-boulevard, tech-innovation.

Ver `.opencode/skills/theme-factory/themes/*.md` para detalhes de cada paleta.

## Skills externas (instaladas mas não adotadas)

Estas skills existem no disco mas não estão integradas ao fluxo principal:
- `frontend-design`: Build frontend interfaces with intentional aesthetic direction. Forces distinct visual tone before coding.
- `theme-factory`: Provides 10 pre-built color and font themes for styling artifacts. Pick or generate custom themes.
