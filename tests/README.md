# CustoDoce — Estrutura de Testes e Qualidade

Este projeto utiliza uma estratégia de testes em múltiplas camadas para garantir a estabilidade de toda a pipeline de coleta e análise de preços.

## 🧪 Camadas de Teste

### 1. Testes Unitários (`tests/unit/`)
**Quantidade**: 383 testes (20 arquivos)
**Objetivo**: Validar a lógica pura de cada componente isoladamente, utilizando mocks para dependências externas.
- **Normalizer**: Testes de conversão de unidades (ex: `cx 12x395g` $\rightarrow$ `4.74kg`).
- **Matcher**: Testes de precisão do matching (exato, alias, fuzzy, fuzzy ≥80%).
- **LLM**: Cache, Strategy Pattern (Groq/OpenRouter/HF), Classifier.
- **Services**: Validação de payloads de RPC e lógica de negócio.
- **Dashboard**: Testes de renderização de componentes e handlers de página.
- **Cart Optimizer**: Monofonte/Multifonte.

### 2. Testes de Schema (`tests/schema/`)
**Quantidade**: 94 testes parametrizados
**Objetivo**: Garantir que a infraestrutura do Supabase esteja correta.
- Verifica a existência de tabelas, colunas e tipos de dados.
- Valida índices de performance e constraints de unicidade.
- Testa a execução de functions RPC essenciais.

### 3. Testes de Integração (`tests/integration/`)
**Quantidade**: 13 arquivos (∼100 testes)
**Objetivo**: Validar a comunicação real entre o Python e o Supabase (via RPC).
- **upsert_price_rpc**: Testa a inserção e deduplicação real de preços.
- **Review Queue**: Testa o fluxo completo de aprovação/rejeição.
- **Performance**: Benchmarks de tempo de resposta de queries.
- **Feature Flags**: Testa override por ingrediente.

### 4. Testes E2E (`tests/e2e/`)
**Quantidade**: 4 arquivos (0 collected — requer Playwright setup)
**Objetivo**: Validar a interface do usuário (UI) via Playwright.
- Fluxo de login e autenticação.
- Navegação entre as 17 abas do dashboard.
- Interações complexas na calculadora de receitas.
- Regressão visual via screenshots.

### 5. Testes Reais (`tests/real/`)
**Quantidade**: 3 arquivos (6 testes, marcados como slow/flaky)
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

## 🛡️ Checklist de Qualidade (CI/CD)

Cada commit deve passar pelas seguintes validações antes do merge:

1. **Linting**: `ruff check .` (Zero erros)
2. **Typecheck**: `mypy .` (Zero erros em source files)
3. **Security**: `bandit -r .` e `pip-audit` (Zero vulnerabilidades)
4. **Unit/Schema**: 100% de passagem nos testes rápidos.
5. **Integration**: 100% de passagem contra o banco de staging/prod.

## 📜 Regras de Ouro para Novos Testes
- **Mocks Cirúrgicos**: Use `unittest.mock` para APIs externas.
- **Sempre Parametrizar**: Use `@pytest.mark.parametrize` para testar múltiplos casos de borda (edge cases).
- **Isolamento**: Cada teste de integração deve limpar seus próprios dados (`_cleanup()`) para evitar poluição.
- **Siga o Padrão**: Nomeie arquivos como `test_*.py` e funções como `test_*`.
