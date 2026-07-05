# Security Policy
> Última atualização: 2026-07-05 19:08 UTC

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
def normalize_price(raw_price: float, raw_unit: str) -> NormalizedPrice | None:
    if raw_price <= 0:
        return None
    parsed = parse_unit(raw_unit)
    if parsed is None:
        return None
    parsed.price_per_kg = round(raw_price / parsed.total_kg, 4)
    parsed.price_per_un = round(raw_price / parsed.qty, 4)
    return parsed
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
| `diskcache` (transitivo) | CVE-2025-69872 | Média | Falso positivo — não usado em runtime, aceito via `docs/security.md` §Histórico (Sprint 12) |
| `pytest` 9.x (dev) | CVE-2025-71176 | Média | **Corrigido** — upgrade 8.3.3 → 9.0.3 (Sprint 12) |

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

## Dependências e CVEs

### Como gerenciamos vulnerabilidades conhecidas

O projeto usa **`pip-audit --strict -r requirements.txt`** em CI (`ci.yml > lint`) para bloquear pushes com vulnerabilidades reais. Além disso, um workflow mensal (`dependency-audit.yml`) executa auditoria completa em prod + dev + teste:

- **`audit-prod`**: bloqueia PR se `pip-audit --strict -r requirements.txt` falhar
- **`audit-dev`**: informativo (não bloqueia) — CVEs Medium/Low em dev aceitas conforme política abaixo
- **`full-scan`**: mensal — `deptry` + `pip-licenses` + relatório consolidado
- **`lock-validation`**: valida que `requirements.lock` está sincronizado com `requirements*.txt`

Quando uma CVE é detectada:

1. **Atualizar primeiro** — bump do pacote para a versão patched
2. **Se quebra dependência** — investigar alternativa ou fork
3. **Último caso** — documentar em SECURITY.md com rationale + data de revisão

### Histórico: Dependabot Alertas (Junho 2026)

Em 2026-06, GitHub Dependabot reportou **7 alertas** baseados em versões antigas cacheadas:

| # | Pacote | Severidade | CVE | Versão instalada |
|---|--------|------------|-----|------------------|
| 1 | Pillow | high | CVE-2023-4863 (libwebp) | 12.2.0 (patched) |
| 2 | Pillow | **critical** | CVE-2023-50447 | 12.2.0 (patched) |
| 3 | Pillow | high | CVE-2024-28219 | 12.2.0 (patched) |
| 4 | Pillow | medium | CVE-2026-42308 | 12.2.0 (patched) |
| 5 | Pillow | medium | CVE-2026-42310 | 12.2.0 (patched) |
| 6 | diskcache | medium | CVE-2025-69872 | N/A (transitive) |
| 7 | pytest | medium | CVE-2025-71176 | 9.x (patched) |

Todos foram **dismissed como `inaccurate`** após verificação local com `pip-audit --strict` retornar "No known vulnerabilities found". O ambiente de runtime já usa versões patched (Pillow 12.2.0, pytest 9.x, etc).

### Sprint 12 — Higienização + Auditoria Automatizada (Julho 2026)

Em 2026-07, o projeto passou por higienização completa de dependências como preparação para auditoria recorrente:

| Ação | Detalhe |
|------|---------|
| Deps transitivas declaradas | `numpy`, `transformers`, `pillow`, `joblib` adicionados explicitamente ao `requirements.txt` |
| pytest CVE corrigido | CVE-2025-71176: 8.3.3 → 9.0.3 |
| pytest-asyncio atualizado | 0.24 → 1.4.0 (compat pytest 9.x) |
| psycopg2-binary movido | Dev → prod (scripts de deploy precisam dele) |
| lock-validation CI | Novo job valida `requirements.lock` ↔ `requirements*.txt` a cada PR |
| dependency-audit workflow | Novo workflow mensal com audit-prod (bloqueante) + audit-dev + full-scan + lock-validation |

**Regra permanente:** Toda mudança em `requirements*.txt` → `pip-compile` + commit do `requirements.lock` atualizado.

### Política de pins por risco

- **CRITICAL/HIGH (prod)** — bloquear push. Atualizar imediatamente.
- **MEDIUM (prod)** — atualizar em até 30 dias via PR.
- **LOW (prod)** — aceitar até segunda notificação.
- **Dev/test CVEs** — não bloqueiam release. Aceitas até próximo sprint, documentadas nesta seção.
- **Falsos positivos** — CVEs em dependências transitivas sem uso direto no runtime (ex: `diskcache`) são aceitos. Nunca remover sem `grep import <pkg>` em todo o codebase.

### Como auditar localmente

```bash
python -m pip_audit --strict -r requirements.txt
python scripts/audit_secrets.py --strict
```



## Dashboard Security (Sprint 1.1)

Em 2026-06-28, duas superfícies de exposição foram removidas do dashboard:

### Tabs de edição removidas
- **`config.py`**: Tab ".env Editor" removida (exibia variáveis de ambiente como `SUPABASE_SERVICE_ROLE_KEY` na UI). Substituída por info + link para Secrets do Streamlit/GitHub.
- **`lojas.py`**: Tab "Formulário YAML" removida (permitia edição raw de `stores.yaml` via textarea). Substituída por CRUD via DB com permissões RLS.
- **`ingredientes.py`**: Banner informativo adicionado sobre a sincronização YAML → DB (sem expor conteúdo do arquivo).

### Pre-commit hook (`.githooks/pre-commit`)
Bloqueia commits que contenham padrões de secrets no staged files:
`sk-*`, `gsk_*`, `sk-or-*`, `sk-or-v1-*`, `sk-proj-*`, `hf_*`, `github_pat_*`, `nvapi-*`, `mOns*`, `AQ.*`.

### Monitoramento ativo
- **`scripts/validate_dashboard_queries.py`**: roda no CI pós-deploy para verificar que as queries do dashboard não expõem colunas sensíveis e retornam o schema esperado.
- **`scripts/audit_secrets.py --strict`**: varre histórico do git por chaves vazadas (roda no pre-push hook).

## Auditoria

`scripts/db_audit.py` roda a cada deploy para verificar:
- Ausência de SQL injection patterns
- Consistência de RLS policies
- Credenciais vazias em tabelas
