# Makefile para CustoDoce
# Comandos comuns para desenvolvimento, lint, typecheck, test e deploy

.PHONY: help lint typecheck test unit integration real deploy-check deploy execute clean

help:
	@echo "Comandos disponíveis:"
	@echo "  make lint           -> Roda ruff lint"
	@echo "  make typecheck      -> Roda mypy"
	@echo "  make test           -> Roda todos os testes (unit + integration + schema)"
	@echo "  make unit           -> Roda testes unitários"
	@echo "  make integration    -> Roda testes de integração"
	@echo "  make real           -> Roda testes reais (slow, flaky)"
	@echo "  make schema         -> Valida schema do banco via RPC"
	@echo "  make deploy-check   -> Verifica migração SQL sem executar"
	@echo "  make deploy         -> Executa migração SQL"
	@echo "  make clean          -> Remove arquivos temporários"
	@echo "  make sanity         -> Roda sanity check"

lint:
	python -m ruff check .

bandit:
	python -m bandit -r . -c pyproject.toml

pip-audit:
	python -m pip_audit

mypy:
	python -m mypy .

pre-commit:
	make lint && make bandit && make pip-audit && make mypy

unit:
	python -m pytest tests/unit/ tests/schema/ -q

integration:
	python -m pytest tests/integration/ -q

real:
	python -m pytest tests/real/ -q

test: unit integration real

schema:
	python scripts/validate_db_schema.py

sanity:
	python scripts/sanity_check.py

deploy-check:
	python scripts/deploy_database.py --dry-run

deploy:
	python scripts/deploy_database.py --execute

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type f -name "*.npy" -delete

ci:
	make lint && make mypy && make unit && make integration && make deploy-check && make real
