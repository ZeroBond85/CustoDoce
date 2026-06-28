# Security Policy

## Secrets Management

### GitHub Secrets

Todos os secrets são armazenados em **GitHub Secrets** (Settings > Secrets and variables > Actions). Nunca exponha secrets em logs ou outputs de CI.

Secrets utilizados:

| Secret | Descrição | Acesso |
|--------|-----------|--------|
| `SUPABASE_URL` | URL do projeto Supabase | CI, Production |
| `SUPABASE_SERVICE_ROLE_KEY` | Chave admin do Supabase | CI, Production |
| `SUPABASE_DB_PASSWORD` | Senha do banco | CI (backup workflow) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | Credenciais Gmail SMTP | CI (email reports) |
| `GROQ_API_KEY` | Chave da Groq API | CI (LLM classifier) |
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram | CI (notify on failure) |
| `ADMIN_PASSWORD` | Senha do dashboard Streamlit | Streamlit Cloud env |

### Local Development

```bash
# .env (NÃO commitiar)
cp .env.example .env
# editar com suas credenciais
```

Para obter credenciais, consulte `docs/deployment.md`.

## Row Level Security (RLS)

O Supabase usa RLS em todas as tabelas. O `service_role` ignora RLS — usar apenas em scripts server-side.

| Tabela | Política |
|--------|----------|
| `prices` | Service role: read/write. Anon: read (via RPC). |
| `ingredients` | Service role: full. Anon: read. |
| `stores` | Service role: full. Anon: read. |
| `review_queue` | Service role: full. Anon: none. |
| `scraping_logs` | Service role: append. Anon: none. |

## Input Validation

### Scraping Output

Todos os dados de scrapers passam por validação:

```python
# parsers/normalizer.py
def normalize_price(raw_price: float, raw_unit: str) -> dict:
    assert raw_price > 0, "raw_price must be positive"
    assert raw_unit, "raw_unit cannot be empty"
    # ... parsing logic
```

### SQL Injection Prevention

Todas as queries usam **Prepared Statements** via Supabase client. SQL strings nunca são construídas com f-strings.

```python
# ✅ Correto
client.table("prices").select("*").eq("store_id", store_id).execute()

# ❌ Errado — SQL injection
client.execute(f"SELECT * FROM prices WHERE store_id = '{store_id}'")
```

### LLM Input Sanitization

Inputs para Groq API são sanitizados antes do envio:

```python
# services/llm_classifier.py
def _sanitize_input(text: str) -> str:
    return text.encode("utf-8", errors="ignore")[:2000].decode("utf-8")
```

## Dependency Security

### Dependabot

Dependabot está habilitado no repositório para:
- `pip`: atualizações semanais de Python packages
- `github-actions`: atualizações de actions

### Vulnerabilidades Conhecidas

| Pacote | CVE | Severidade | Status |
|--------|-----|------------|--------|
| `transformers` 4.57.6 | PYSEC-2025-217, CVE-2026-1839 | Média | Known risk (fix requires 5.0.0rc3, pre-release) |

O upgrade para `transformers>=5.0.0` será feito quando sair stable.

## Relatando Vulnerabilidades

Se encontrar uma vulnerabilidade, abra uma **Issue privada** (não PR) com:
1. Descrição do problema
2. Passos para reproduzir
3. Impacto potencial
4. Sugestão de correção (opcional)

Resposta em até 48h.

## Ambiente de Produção

- **Streamlit Cloud**: 1 app privado, acesso via convite
- **Supabase**: projeto específico (não localhost)
- **GitHub Actions**: secrets configurados via repo settings
- **Sem exposed admin panel** fora da organização

## Auditoria

`scripts/db_audit.py` roda a cada deploy para verificar:
- Ausência de SQL injection patterns
- Consistência de RLS policies
- Credenciais vazias em tabelas