# Deployment Staging
> Última atualização: 2026-07-18 04:46 UTC

Guia para criar e operar um ambiente de staging isolado antes de promotionar para produção.

## Arquitetura

```
┌─────────────────────┐     ┌─────────────────────┐
│   custodoce-staging  │     │    custodoce-prod    │
│   (2º Supabase)      │ --> │   (Supabase principal) │
│                      │     │                       │
│  • DB separado       │     │  • DB produção         │
│  • 500MB free tier   │     │  • 500MB free tier     │
│  • Schema independente │    │  • Schema locked       │
│  • Testes E2E        │     │  • App Streamlit       │
│  • Validação de PR   │     │  • Produção real       │
└─────────────────────┘     └─────────────────────┘
```

**Por que staging separado?**
- Validar migrations sem risco em produção
- Testar scrapers com dados reais sem poluir produção
- CI de PRs roda contra staging (não produção)

## Setup do Projeto Staging

### 1. Criar projeto Supabase staging

1. Ir para [supabase.com](https://supabase.com) > New Project
2. Nome: `CustoDoce Staging`
3. Region: same as production (São Paulo)
4. Database Password: gerar com `openssl rand -hex 20`
5. Plano: Free (500MB)

### 2. Configurar GitHub Secrets staging

No repositório GitHub, adicionar secrets:

| Secret | Valor |
|--------|-------|
| `STAGING_SUPABASE_URL` | URL do projeto staging (https://xxx.supabase.co) |
| `STAGING_SUPABASE_SERVICE_ROLE_KEY` | Service role key do staging |
| `STAGING_SUPABASE_DB_PASSWORD` | Database password do staging |

**Importante:** Não usar a mesma senha de produção.

### 3. Aplicar schema no staging

```bash
# Dry-run primeiro
python scripts/deploy_database.py --dry-run --env staging

# Aplicar
python scripts/deploy_database.py --execute --env staging
```

### 4. Popular com dados mínimos

```bash
# Sync stores do YAML → staging
python scripts/sync_all_store_fields.py --dry-run

# Seed ingredientes (usa env var STAGING_SUPABASE_URL/KEY)
STAGING_SUPABASE_URL=... STAGING_SUPABASE_SERVICE_ROLE_KEY=... python scripts/seed_config_db.py --dry-run

# Seed preços sintéticos (opcional)
STAGING_SUPABASE_URL=... STAGING_SUPABASE_SERVICE_ROLE_KEY=... python scripts/seed_prices.py --dry-run
```

## Workflow CI/CD Staging

### `.github/workflows/deploy-staging.yml`

Triggers em PRs para branches `develop` e `feat/*`:

```yaml
on:
  pull_request:
    branches: [develop, master]
```

Jobs:
1. **lint + typecheck + unit** (mesmos do CI normal)
2. **deploy-staging-schema**: aplica migrations no DB staging
3. **validate-staging**: roda `scripts/validate_db_schema.py` contra staging
4. **seed-staging**: dados mínimos para testes

### Promotionar para Produção

```
develop ──PR merge──> master
                        │
                        ▼
              deploy_check.py (staging)
                        │
                        ▼ (se tudo OK)
              scrape.yml (produção real)
```

## Configurando Aplicação Streamlit para Staging

Em `admin/app.py`, detectar ambiente:

```python
import os

ENV = os.environ.get("CUSTODOCE_ENV", "production")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
```

No `.streamlit/secrets.toml` do Streamlit Cloud Staging:
```toml
SUPABASE_URL = "https://xxx.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJ..."
CUSTODOCE_ENV = "staging"
```

## Diferenças Staging vs Produção

| Aspecto | Staging | Produção |
|---------|---------|----------|
| URL | `custodoce-staging` (2º projeto) | `custodoce` (projeto principal) |
| Dados | Mínimos/sintéticos | Reais (preços reais) |
| Scraper | Desabilitado por default | Habilitado |
| Notifications | Silent (sem Telegram real) | Ativas |
| Scraping logs | Mantidos para debug | Limpados após 90 dias |
| RLS | Mesma política | Mesma política |

## Testar Migration antes de Produção

```bash
# 1. Backup via Supabase Dashboard
# Project > Database > Backups > Restore

# 2. Gerar diff do schema (via RPC 443)
python scripts/check_schema_diff.py --from staging --to prod > diff.sql

# 3. Aplicar no staging primeiro (via RPC 443)
python scripts/deploy_database.py --execute

# 4. Validar (via RPC 443)
python scripts/validate_db_schema.py

# 5. Se OK, aplicar em produção
python scripts/deploy_database.py --execute
```

## Rollback

Se algo falhar em produção:

```bash
# Restaurar de backup (supabase dashboard)
# Project > Database > Backups > Restore

# Ou via REST API (porta 443, NÃO use psql/porta 5432)
# Suporte Supabase restaura diretamente do dashboard
```

## Monitoramento

### Health Check Staging

```bash
python scripts/deploy_check.py --env staging
```

### Alertas específicos staging

Em `services/alert_service.py`, verificar `CUSTODOCE_ENV`:
- Staging: alertas vão só para log (não Telegram real)
- Produção: alertas normais

## Checklist de Promotion

- [ ] Schema migration aplicada e validada no staging
- [ ] Testes unit + schema passando (CI verde)
- [ ] Testes de integração passando contra staging
- [ ] NOVO: Arquivos de docs atualizados (changelog.md)
- [ ] NOVO: Se nova API/funcionalidade, doc em docs/api/
- [ ] Secrets de produção verificados (não staging)
- [ ] Backup mais recente disponível (restore-test.yml verde)
- [ ] Diff de schema revisado (`scripts/check_schema_diff.py`)
