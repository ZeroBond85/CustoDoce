# Contributing to CustoDoce
> Última atualização: 2026-07-20 05:57 UTC

## Development Setup

### 1. Clone e instale dependências

```bash
git clone https://github.com/YOUR_FORK/CustoDoce.git
cd CustoDoce
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Configure variáveis de ambiente

```bash
cp .env.example .env
# preencher SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY
```

### 3. Rode os testes

```bash
make test-unit    # testes unitários (~2min)
make test-int     # testes de integração (precisa DB real)
make lint         # ruff + bandit
make typecheck    # mypy
make quality      # quality gates (Great Expectations)
```

## Coding Standards

### Python Style

- **Linha máxima**: 120 caracteres (configurado em `pyproject.toml`)
- **Imports**: agrupados (stdlib → third-party → local), sem curingas
- **Docstrings**: Google style para funções públicas
- **Type hints**: obrigatórios para parâmetros e retornos de funções públicas

```python
def search_prices(
    ingredient: str,
    sort_by: str = "price_per_kg",
    sort_order: str = "asc",
    limit: int = 100,
    valid_only: bool = True,
) -> list[dict]:
    """Busca preços por ingrediente com ordenação server-side."""
```

### Error Handling

- Nunca use `except:` nu (especifique a exceção)
- Logging em vez de print
- Retorne valores, não faça exit() em bibliotecas

```python
# ✅ Correto
try:
    result = client.table("prices").upsert(data).execute()
except SupabaseError as e:
    logger.error("Upsert failed: %s", e)
    return {}
except Exception as e:
    logger.exception("Unexpected error in upsert_price")
    return {}
```

### SQL Patterns

Sempre use o Supabase client (não `psycopg2` direto):

```python
# ✅ Correto
client.table("prices").select("*").eq("store_id", store_id).execute()

# ❌ Errado
client.execute(f"SELECT * FROM prices WHERE store_id = '{store_id}'")
```

## Branching Strategy

```
master     ← produção (somente merge via PR aprovado)
├── develop ← integração (default para PRs)
├── feat/*  ← funcionalidades (a partir de develop)
├── fix/*   ← correções (a partir de develop)
├── docs/*  ← documentação (a partir de develop)
└── chore/* ← tarefas de manutenção (a partir de develop)
```

### Nomenclatura de Commits

Formato: `tipo(scope): descrição`

```
feat(matcher): add fallback para fuzzy ratio <80%
fix(scraper): retry on timeout for VTEX API
docs(api): add price_service reference
perf(scraper): parallel fetch for flyer PDFs
test(config): add coverage for ingredient upsert
```

Tipos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`

## Pull Request Process

### 1. Antes de abrir PR

```bash
# criar branch a partir de develop
git checkout develop && git pull
git checkout -b feat/minha-feature

# fazer mudanças
git add .
git commit -m "feat(scope): descrição"

# verificar código
make lint && make typecheck && make test-unit
```

### 2. Abrir PR

- Título descritivo (não "fix" ou "update")
- Descrição com: o que mudou, por que mudou, como testar
- Link para issue relacionada

### 3. CI Requirements

PR só é mergeado se todos passarem:

- ✅ Ruff (0 errors)
- ✅ MyPy (0 errors)
- ✅ Bandit (0 issues, exceto `nosec` marcados)
- ✅ pytest unit (483 testes + schema 94 = **577 passando**)
- ✅ pytest integration (**102 passando**, requer credenciais)
- ✅ `scripts/validate_dashboard_queries.py` — smoke test de queries contra Supabase real (roda no deploy-check)

### 4. Code Review

- Mínimo 1 aprovação
- Resolva todos os comments antes de merge
- Não force push após aprovação

## Testing Guidelines

### Test Structure

```
tests/
├── unit/           # 483 testes mockados (21 arquivos)
├── schema/         # 94 testes de DB via RPC (parametrizados, 1 arquivo)
├── integration/    # 13 arquivos (precisa credenciais DB)
├── e2e/            # 3 arquivos (Playwright, require setup)
└── real/           # 2 arquivos (slow/flaky, marcados @pytest.mark.real)
```

### Writing Tests

```python
def test_search_prices_returns_list():
    with patch("services.supabase_client.get_supabase") as mock_client:
        mock_client.return_value.table.return_value.select.return_value.execute.return_value.data = [
            {"store_name": "Assaí", "price_per_kg": 12.50}
        ]
        result = search_prices("Leite Condensado")
        assert len(result) == 1
        assert result[0]["store_name"] == "Assaí"
```

### Running Specific Tests

```bash
# só unit
python -m pytest tests/unit/ -q

# só um arquivo
python -m pytest tests/unit/test_matcher.py -v

# só um teste
python -m pytest tests/unit/test_matcher.py::test_fuzzymatch_ratio -v

# com cobertura
python -m pytest tests/unit/ --cov=services --cov-report=term-missing
```

## Scraper Development

### Adding a New Store

1. Adicionar config em `config/stores.yaml`
2. Implementar scraper em `scrapers/`
3. Testar com `python -m pytest tests/unit/test_scrapers.py`
4. Se tier 2a/3: adicionar em `config/features.yaml`

### Matcher Debug

```bash
python -c "
from parsers.matcher import match_ingredient
from config.ingredients import INGREDIENTS

result = match_ingredient('Leite Condensado Moça 395g 12un', INGREDIENTS)
print(result)
"
```

## Deploy Checklist

```bash
# 1. Testar local
make lint && make typecheck && make test-unit

# 2. Abrir PR e aguardar CI verde

# 3. Merge em develop → CI faz deploy-check (schema validate + deploy_check.py)

# 4. Merge em master → GitHub Actions dispara:
#    - scrape.yml (coleta prices)
#    - Notificação Telegram em caso de erro
```

## Issue Templates

Ao abrir issue, usar template:

**Bug**: passos para reproduzir, comportamento esperado vs atual, ambiente
**Feature**: problema que resolve, solução proposta, alternativas consideradas
**Question**: contexto, dúvida específica

## Recursos

- [ADR Documents](./adr/) — decisões de arquitetura
- [Architecture](./architecture.md) — visão geral
- [Deployment](./deployment.md) — setup de produção
- [API Reference](./api/) — documentação dos serviços

---

## 🧠 AI-Assisted Development (OpenCode Skills)

Este projeto usa **OpenCode** com **duas camadas de skills** para acelerar tarefas recorrentes:

| Camada | Localização | Acesso |
|--------|-------------|--------|
| **Global** | `~/.config/opencode/skills/` | Qualquer projeto |
| **Local (CustoDoce)** | `.opencode/skills/` | Só neste repo |

### Skills Globais Disponíveis (17)
`scraping-resilience`, `code-quality-pro`, `test-architect`, `api-design`, `code-review`, `debug-troubleshooting`, `docs-writer`, `git-workflow`, `github-actions`, `project-doc-sync`, `refactor-patterns`, `sql-optimizer`, `streamlit`, `telegram-bot`, `test-generation`, `humanizer`, `seo`, `ui-ux-pro-max`

### Overlays Locais (7)
`telegram-bot`, `docs-writer`, `sql-optimizer`, `streamlit`, `api-design`, `github-actions`, `project-doc-sync`

### Como usar
```bash
# No terminal com opencode ativo:
skill({ name: "code-review" })       # Checklist CRITICAL/HIGH/MEDIUM/LOW
skill({ name: "sql-optimizer" })     # Index patterns, RLS, partitioning
skill({ name: "test-architect" })    # Mocks, fixtures, parametrize, CI
skill({ name: "scraping-resilience" }) # Fallback chain, anti-bot
skill({ name: "telegram-bot" })      # Handlers, ConversationHandler, dedup
```

As skills locais injetam contexto específico (comandos `/preco`, schema `prices`, 21 pages do dashboard, 8 GHA workflows) sem duplicar o conteúdo global.
