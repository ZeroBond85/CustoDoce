# CustoDoce — Estrutura de Testes e Qualidade
> Última atualização: 2026-07-14 00:59 UTC

Este projeto utiliza uma estratégia de testes em múltiplas camadas para garantir a estabilidade de toda a pipeline de coleta e análise de preços.

## 🧪 Camadas de Teste

### 1. Testes Unitários (`tests/unit/`)
**Quantidade**: ~508 testes (22 arquivos)
**Objetivo**: Validar a lógica pura de cada componente isoladamente, utilizando mocks para dependências externas.
- **Normalizer**: Testes de conversão de unidades (ex: `cx 12x395g` $\rightarrow$ `4.74kg`). **31 casos parametrizados** cobrindo todas as unidades reais (g/kg, cx/pacote/fardo, lata/pote/barra, ml/l) + edge cases.
- **Matcher**: Testes de precisão do matching (exato, alias, fuzzy, fuzzy ≥80%).
- **LLM**: Cache, Strategy Pattern (Groq/OpenRouter/HF), Classifier.
- **Services**: Validação de payloads de RPC e lógica de negócio.
- **Dashboard**: Testes de renderização de componentes e handlers de página.
- **Cart Optimizer**: Monofonte/Multifonte.
- **App Wiring** (`test_app_wiring.py`): 7 testes que validam a **fiação entre módulos** do `admin/app.py` sem executar Streamlit. Usa AST + imports para detectar: `render_login()` chamado com argumento que não aceita (TypeError que estava em produção desde FASE 8), `PAGE_FUNCTIONS` com entradas quebradas, páginas com assinatura inesperada. Version-independent (não usa `st.testing`).
- **Contract Tests** (`test_dashboard_contracts.py`): validam o **shape dos dados retornados** pelas funções de `services/dashboard_queries.py` consumidas pelo dashboard (`get_dashboard_kpis`, `get_coverage_by_ingredient`, `get_active_promotions`, `get_scraper_health_dashboard`). Garante chaves críticas (`price_per_kg`, `is_promotion`, `status_label`, `latency_label`) sem precisar de DB real.
- **CI Infrastructure** (`test_ci_infrastructure.py`): 13 testes sem mock que validam config CI real (CATCH-BEFORE-PUSH). Não passam se `requirements.txt` tem `--index-url` inline, ou se pyproject.toml excludes de check_*.py somem, etc.
- **sync_docs v2** (`test_sync_docs_v2.py`): 25 testes unitários (puros, sem I/O) que cobrem os 5 módulos de `scripts/sync_docs_v2/`: `truth.py` (mock subprocess.run, chaves, erro), `parser.py` (headings spans via markdown-it, skip dirs), `classifier.py` (13 casos parametrizados — matriz CURRENT/HISTORICAL/AMBIGUOUS), `updater.py` (`\bNUMBER\b`, dry-run, preservação HISTORICAL), `cli.py` (exit codes, output JSON).

### 2. Testes de Schema (`tests/schema/`)
**Quantidade**: 94 testes parametrizados
**Objetivo**: Garantir que a infraestrutura do Supabase esteja correta.
- Verifica a existência de tabelas, colunas e tipos de dados.
- Valida índices de performance e constraints de unicidade.
- Testa a execução de functions RPC essenciais.

### 3. Testes de Integração (`tests/integration/`)
**Quantidade**: 13 arquivos (~102 testes)
**Objetivo**: Validar a comunicação real entre o Python e o Supabase (via RPC).
- **upsert_price_rpc**: Testa a inserção e deduplicação real de preços.
- **Review Queue**: Testa o fluxo completo de aprovação/rejeição.
- **Performance**: Benchmarks de tempo de resposta de queries.
- **Feature Flags**: Testa override por ingrediente.

### 4. Testes E2E (`tests/e2e/`)
**Quantidade**: 3 arquivos (requer Playwright setup)
**Objetivo**: Validar a interface do usuário (UI) via Playwright.
- Fluxo de login e autenticação.
- Navegação entre as 18 abas do dashboard.
- Interações complexas na calculadora de receitas.
- Regressão visual via screenshots.

### 5. Testes Reais (`tests/real/`)
**Quantidade**: 2 arquivos (6 testes, marcados como slow/flaky)
**Objetivo**: Validar scrapers contra sites reais (Slow/Flaky).
- Testes de conectividade e parsing de sites ativos.
- Validação de tokens de API e headers de requisição.

---

## 🛠️ Como Executar os Testes

### Execução Rápida (CI Mode)
Roda apenas os testes unitários e de schema (ignora testes lentos e reais):
```bash
python -m pytest tests/unit/ tests/schema/ -q
```

### Execução Completa (Full Suite)
Roda todos os testes, incluindo integração e E2E:
```bash
python -m pytest tests/ -v
```

### Executar Apenas Testes Lentos (Real Scrapers)
```bash
python -m pytest tests/real/ -v
```

---

### 6. Smoke Test de Queries (`scripts/validate_dashboard_queries.py`)
**Quantidade**: 10 checks (roda no CI pós-deploy)
**Objetivo**: Validar que as 10 queries principais do dashboard funcionam contra o Supabase real e retornam as colunas esperadas pelos `column_config` das páginas. Pega schema mismatch antes do usuário ver erro 500.

---

## 🔄 Conexão com DB nos Testes

Todas as operações de DB em testes passam pela **porta 443** (REST API), nunca pela 5432 (TCP direto), porque GitHub Actions **bloqueia a porta 5432**. O fixture `db_conn` em `tests/conftest.py` encapsula `client.rpc("exec_sql_query", {"sql": ...})` por trás de uma interface psycopg2-like (`_SchemaCursor`/`_SchemaConn`), mantendo os testes legíveis sem abrir exceções de rede no CI.

```python
# ✅ CERTO (funciona via 443 em CI):
def test_x(db_conn):
    cur = db_conn.cursor()
    cur.execute("SELECT 1 FROM prices LIMIT 1")
    assert cur.fetchone() is not None

# ❌ ERRADO (bloqueado no CI):
import psycopg2
psycopg2.connect(host="db.fqdn.supabase.co", port=5432)  # timeout
```

---

## 🛡️ Checklist de Qualidade (CI/CD)

Cada commit deve passar pelas seguintes validações antes do merge:

1. **Linting**: `ruff check .` (Zero erros)
2. **Typecheck**: `mypy .` (Zero erros em source files)
3. **Security**: `bandit -r .` e `pip-audit` (Zero vulnerabilidades)
4. **Unit/Schema**: 100% de passagem nos testes rápidos.
5. **Integration**: 100% de passagem contra o banco de staging/prod.
6. **Smoke Queries**: `scripts/validate_dashboard_queries.py` — 10/10 checks contra Supabase real (roda no deploy-check).

## 📜 Regras de Ouro para Novos Testes
- **Mocks Cirúrgicos**: Use `unittest.mock` para APIs externas.
- **Sempre Parametrizar**: Use `@pytest.mark.parametrize` para testar múltiplos casos de borda (edge cases).
- **Isolamento**: Cada teste de integração deve limpar seus próprios dados (`_cleanup()`) para evitar poluição.
- **Siga o Padrão**: Nomeie arquivos como `test_*.py` e funções como `test_*`.
