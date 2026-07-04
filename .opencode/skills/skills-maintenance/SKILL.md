---
name: skills-maintenance
description: "Script para manter skills atualizadas: check, update, backup, e validação"
---

# skills-maintenance

Script de manutenção para manter skills do CustoDoce atualizadas.

## Comandos

```bash
# Verificar status de todas as skills
python scripts/skills_maintenance.py --check

# Atualizar skills do repositório
python scripts/skills_maintenance.py --update

# Backup antes de update
python scripts/skills_maintenance.py --backup

# Validar estrutura
python scripts/skills_maintenance.py --validate

# Full (backup + check + update)
python scripts/skills_maintenance.py --full
```

## Check Status

Verifica:
- Skills faltando na lista approved
- Skills desatualizadas (>30 dias sem update)
- SKILL.md com frontmatter inválido
- Datas de última modificação

```bash
python scripts/skills_maintenance.py --check
```

Output:
```
=== Skills Status ===
SKILLS_DIR: .opencode/skills/
TOTAL: 33 skills

[OK] project-context-primer (03/07/2026)
[WARN] streamlit (30/06/2026) - 3 days old
[OK] frontend-design (03/07/2026)
...
```

## Update Flow

1. Backup para `data/skills_backup/`
2. Clone/pull de repositórios remotos
3. Copia skills approved
4. ValidaSKILL.md
5. Report

## Approved Skills List

| Source | Skill | Update Frequency |
|--------|-------|------------------|
| vibe-coder-kit | project-context-primer, code-review, github, ... | Mensal |
| Anthropic | frontend-design, theme-factory | Trimestral |
| CustoDoce | web-scraper, price-normalizer, ... | Quando mudar stack |

## Cron (suggested)

```yaml
# .github/workflows/maintenance.yml
name: Skills Maintenance
on:
  schedule:
    - cron: '0 9 1 * *'  # Monthly, day 1, 9am
  workflow_dispatch:
```

## Antipatterns

- ❌ Não rodar maintenance há >3 meses
- ❌ Não fazer backup antes de update
- ❌ Instalar skills não verificadas
- ❌ Ignorar skills desatualizadas

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | OK, nothing to do |
| 1 | Warnings (skills outdated) |
| 2 | Errors (invalid structure) |
| 3 | Update failed |