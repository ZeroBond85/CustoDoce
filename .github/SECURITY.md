# SECURITY.md — Política de Segurança para Pull Requests

## Objetivo
Garantir que nenhum Pull Request com vulnerabilidades críticas ou altas seja mergeado, reduzindo a janela de risco de exposição de CVEs de 30 dias para 0.

## Regras

### 1. Auditoria de Dependências em Todo PR
Todo PR que modificar `requirements.txt` ou `requirements-dev.txt` deve passar por auditoria automática de vulnerabilidades.

**Job:** `audit-prod`
**Trigger:** `pull_request` com alteração em `requirements*.txt`
**Ferramenta:** `pip-audit --strict -r requirements.txt`

```yaml
jobs:
  audit-prod:
    if: hashFiles('requirements.txt') != ''
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14.6'
      - run: pip install pip-audit
      - run: pip-audit --strict -r requirements.txt
```

### 2. Severidade de CVEs
- **Bloquear:** CVEs com severidade `HIGH` ou `CRITICAL`
- **Warning:** CVEs com severidade `MEDIUM` ou `LOW` (apenas log, não bloqueia PR)

### 3. Notificação de CVEs Altas/Críticas
Se um CVE alto/crítico for detectado em um PR, o workflow deve notificar via:
- **Telegram Bot** (mensagem privada para admins)
- **Email** (para lista de segurança)

**Script:** `scripts/notify_security_issue.py`

### 4. Atualização de Dependências
- **Atualizar dependências:** Sempre que possível, atualizar pacotes para versões sem CVEs.
- **Justificativa:** Se não for possível atualizar, deve-se documentar no PR o motivo e o plano de mitigação.

### 5. Revisão Manual Obrigatória
Mesmo que o workflow passe, um revisor humano deve validar:
- Ajustes de versão propostos
- Impacto no código existente
- Testes de regressão

## Referências
- [pip-audit](https://pypi.org/project/pip-audit/)
- `scripts/notify_security_issue.py` (a ser criado)
- `services/telegram_bot/handlers.py` (para notificação)

---
Última atualização: $(date +%Y-%m-%d)