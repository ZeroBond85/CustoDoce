# CONCURRENCY.md — Regras de Concorrência para Workflows

## Objetivo
Evitar que múltiplos jobs concorrentes tentem fazer push em `prices_latest.json` ou executem scraping simultaneamente, causando conflitos ou duplicação de trabalho.

## Regras

### 1. Grupo de Concorrência por Job
Todos os jobs longos devem definir um `concurrency` group único para evitar execuções paralelas destrutivas.

```yaml
jobs:
  scrape:
    concurrency:
      group: scrape-${{ github.ref }}
      cancel-in-progress: false
```

### 2. Lock Distribuído via Git Refs
Para garantir que apenas um scraping ocorra por vez, usar `scripts/scrape_lock.py` que cria/remove refs Git:

```yaml
- name: Acquire scrape lock
  run: python scripts/scrape_lock.py acquire ${{ github.run_id }}

- name: Release scrape lock
  if: always()
  run: python scripts/scrape_lock.py release ${{ github.run_id }}
```

### 3. Jobs Proibidos de Rodar em Paralelo
- `scrape` (cron/on-demand/heal)
- `backup`
- `restore-test`
- `e2e-full`

### 4. Exceções
- Jobs de lint/typecheck/unit/schema podem rodar em paralelo.
- Jobs de documentação (`docs-sync`) podem rodar em paralelo.

## Referências
- [GitHub Docs: Concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency)
- `scripts/scrape_lock.py` (a ser criado)

---
Última atualização: $(date +%Y-%m-%d)