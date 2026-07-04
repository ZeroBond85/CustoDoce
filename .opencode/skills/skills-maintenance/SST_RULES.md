# SST Rules — Skills Single Source of Truth

> Este documento é parte da skill skills-maintenance.
> Define como alterar o catálogo de skills sem quebrar o SST.

## Single Source of Truth (SST)

A lista canônica de skills é mantida em 3 lugares que devem estar sempre sincronizados:

1. **Disco**: `.opencode/skills/<skill>/SKILL.md` — pasta com frontmatter válido
2. **Aprovação**: `scripts/skills_maintenance.py::APPROVED_SKILLS` — lista explícita
3. **Documentação**: `docs/skills.md` — gerado por `sync_docs --sync`

## Como adicionar uma skill nova

1. Criar pasta `.opencode/skills/<nome>/SKILL.md` com frontmatter (name, description)
2. Adicionar `<nome>` em `scripts/skills_maintenance.py::APPROVED_SKILLS`
3. Adicionar em `SKILL_CATEGORIES` (dict no mesmo arquivo)
4. Rodar `python scripts/sync_docs.py --sync` → regenera `docs/skills.md`
5. Stagelar: `.opencode/skills/<nome>/SKILL.md` + `scripts/skills_maintenance.py` + `docs/skills.md`
6. Pre-commit Layer 6 bloqueia se skill mudar sem docs/skills.md

## Como remover

1. Remover pasta `.opencode/skills/<nome>/`
2. Remover de `APPROVED_SKILLS` + `SKILL_CATEGORIES`
3. Rodar `sync_docs --sync`
4. Stagelar remoção + docs/skills.md atualizado

## Gatilhos de validação

| Gatilho | O que roda | Falha se |
|---------|-----------|----------|
| pre-commit (Layer 6) | grep por .opencode/skills/ vs docs/skills.md | skill alterada sem docs |
| pre-push (Step 5) | `agents_tool --full` | schema inválido ou sync desatualizado |
| CI docs-sync | `sync_docs --check --strict --experimental` + `agents_tool --check` | qualquer drift |
| Cron mensal | `skills_maintenance --full` | skills estaleiradas (>30d sem update) |
| PR skills/ | `skills_maintenance --validate --check` | frontmatter inválido ou fora da approved |
