# ADR 003: Estratégia de Tiers de Lojas
> Última revisão: 2026-07-06 02:38 UTC

**Status**: Aceito
**Data**: 27/06/2026
**Contexto**: Lojas possuem diferentes formas de disponibilizar preços (PDF, Site, API, Manual), exigindo abordagens de coleta distintas.

## Decisão
Classificação de lojas em 4 Tiers:

- **Tier 1 (PDF Direto)**: Redes atacadistas com encartes semanais em PDF. Coleta via `pdfplumber` + OCR.
- **Tier 2 (E-commerce/API)**: Lojas com API VTEX ou catálogos web. Coleta via `httpx` / `selectolax`. Subdividido em 2a (Automático) e 2b (Físico/Manual).
- **Tier 3 (Agregadores)**: Sites como Tiendeo/Kimbino. Coleta via Playwright (SSR) como fallback.
- **Tier 4 (Manual)**: Lojas sem presença digital. Coleta via importação de planilhas `.xlsx` preenchidas manualmente.

## Rationale
- Permite a aplicação de frequências de coleta diferentes (ex: Diária para Tier 2a, Semanal para Tier 1).
- Otimiza o uso de recursos do GitHub Actions (evita rodar Playwright pesado para lojas que possuem API).
- Garante a inclusão de lojas locais (Tier 4) que não possuem site.

## Consequências
- **Positivas**: Cobertura máxima de fontes de preços.
- **Negativas**: Necessidade de manter múltiplos tipos de scrapers e lidar com a fragilidade de seletores HTML.
