# Guia de Migração e Manutenção do Banco de Dados
> Última atualização: 2026-07-20 05:57 UTC

Este documento descreve como aplicar alterações no schema do banco de dados Supabase e como validar a integridade dos dados.

## 🔄 Fluxo de Alteração do Schema

Para garantir que o banco de dados esteja sempre sincronizado com o código, siga este fluxo:

1. **Modificação**: Altere o arquivo `supabase/seed.sql` ou crie um novo arquivo de migração em `supabase/` (ex: `002_add_column.sql`).
2. **Dry-Run**: Execute o script de deploy em modo de simulação para validar a sintaxe SQL:
   ```bash
   python scripts/deploy_database.py --dry-run
   ```
3. **Execução**: Aplique as mudanças no banco real:
   ```bash
   python scripts/deploy_database.py --execute
   ```
4. **Validação**: Execute a suíte de validação de schema para garantir que todas as tabelas, colunas e índices estão corretos:
   ```bash
   python scripts/validate_db_schema.py
   ```

---

## 🛠️ Ferramentas de Manutenção

### 1. `deploy_database.py`
Responsável por ler os arquivos SQL e executá-los no Supabase via RPC.
- `--dry-run`: Apenas imprime o SQL que seria executado.
- `--execute`: Aplica as mudanças ao banco de dados.

### 2. `validate_db_schema.py`
Executa mais de 80 checks automatizados no banco de dados, verificando:
- Existência de tabelas e colunas obrigatórias.
- Presença de índices de performance (B-Tree).
- Validação de constraints `UNIQUE` e `FOREIGN KEY`.
- Disponibilidade das functions RPC.

### 3. `db_audit.py`
Realiza uma auditoria de integridade nos dados:
- Busca por "orphan prices" (preços sem loja ou ingrediente correspondente).
- Verifica a consistência da `review_queue`.
- Identifica queries lentas (> 2s).

---

## 🚨 Recuperação e Rollback

### Rollback de Alterações
Como o Supabase não possui migrações versionadas nativamente via código (estamos usando scripts simples), o rollback deve ser feito:
1. Identificando a alteração no SQL.
2. Escrevendo o comando inverso (ex: `ALTER TABLE prices DROP COLUMN ...`).
3. Executando via SQL Editor do Supabase ou criando um novo script de migração.

### Recuperação de Desastres
1. **Backup**: O sistema realiza dumps semanais via GitHub Actions (ver `docs/adr/005-free-tier-limits.md`).
2. **Restore**: Para restaurar, utilize o comando `psql` ou o SQL Editor do Supabase para importar o dump `.sql` mais recente.

---

## ⚠️ Regras de Ouro

- **NUNCA** use `psycopg2` ou conexões diretas à porta 5432 em ambientes de produção/CI. Use sempre as RPCs via porta 443.
- **Sempre** execute o `validate_db_schema.py` após qualquer alteração de banco.
- **Sempre** use a `service_role` para operações de manutenção e a `anon_key` para consultas do dashboard.
