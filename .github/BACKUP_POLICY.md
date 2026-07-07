# BACKUP_POLICY.md — Política de Backup e Restauração

## Objetivo
Definir uma política clara para backups do banco de dados Supabase, garantindo integridade, retenção e restauração automática para testes.

## Regras

### 1. Frequência e Tipo de Backup
| Tipo | Frequência | Destino | Validação |
|------|------------|---------|-----------|
| Backup Completo | Diário (02:00 UTC) | GitHub Releases | SHA256 + `gzip -t` |
| Backup Incremental | Semanal (Domingo 02:00 UTC) | GitHub Releases | SHA256 + `gzip -t` |
| Backup On-Demand | Sob demanda (via `backup.yml` manual) | GitHub Releases | SHA256 + `gzip -t` |

### 2. Retenção
- **Backups Diários:** Mantidos por **30 dias**
- **Backups Semanais:** Mantidos por **90 dias**
- **Backups On-Demand:** Mantidos por **7 dias**

### 3. Validação de Integridade
Todo backup gerado deve passar por:
- Verificação de checksum SHA256
- Teste de descompressão (`gzip -t`)
- Validação de estrutura básica (pelo menos 1 tabela deve existir)

**Exemplo de validação no workflow:**
```yaml
- name: Validate backup integrity
  run: |
    sha256sum backup.sql.gz > backup.sha256
    gzip -t backup.sql.gz
    # Validar estrutura mínima
    pg_restore --list backup.sql.gz | grep -q "TABLE public.prices" || exit 1
```

### 4. Restauração Automática
Após a execução de `backup.yml`, o workflow `restore-test.yml` deve ser executado automaticamente via `workflow_run`.

**Critério de Sucesso:**
- O número de linhas restauradas deve ser igual ao número de linhas no backup original.
- Nenhum erro deve ser lançado durante a restauração.

### 5. Destino: GitHub Releases (Não Repositório Git)
- **Motivo:** Evitar inflar o histórico do Git com arquivos grandes (`.sql.gz`).
- **Artefato:** Cada release contém:
  - `backup-<run_id>.sql.gz`
  - `backup-<run_id>.sha256`

### 6. Acesso
- **Backups Diários/Semanais:** Acessíveis apenas para admins (via GitHub Releases)
- **Backups On-Demand:** Acessíveis para todos os colaboradores (via GitHub Releases)

### 7. Recuperação de Emergência
Em caso de falha crítica no Supabase:
1. Baixar o último backup diário válido do GitHub Releases.
2. Restaurar manualmente via `supabase db reset` ou `psql`.
3. Notificar toda a equipe via Telegram e Email.

## Referências
- `scripts/backup_database.py` (gera o backup)
- `scripts/restore_database.py` (restaura o backup)
- `.github/workflows/backup.yml`
- `.github/workflows/restore-test.yml`

---
> Última atualização: 2026-07-06 00:00 UTC