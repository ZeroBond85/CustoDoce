# Rollback Template for Production Validation
> Última atualização: 2026-08-12 14:22 UTC
# This file is generated to guide recovery in case of critical failure during full_prod_validation.py

## 🚨 ROLLBACK PROCEDURE

### 1. Database Restore
If the database schema or data was corrupted:
- **Action**: Restore the latest `.sql` dump created before validation.
- **Command** (RPC porta 443, NUNCA psql/5432): execute o dump via Supabase SQL Editor (projeto → SQL Editor → colar conteúdo do `backup_prod_YYYYMMDD.sql`), ou `python scripts/restore_from_json.py --execute` para backups JSON do `rpc_backup.py`.

### 2. Config Revert
If `stores.yaml` or `features.yaml` were accidentally modified:
- **Action**: Revert using Git.
- **Command**: `git checkout master -- config/features.yaml config/stores.yaml`

### 3. Cleanup Production Data
If test data was accidentally inserted into `prices` or `price_history`:
- **Action**: Run a cleanup script targeting the `collected_at` window of the validation.
- **SQL**: `DELETE FROM prices WHERE collected_at >= '[START_DATE]' AND collected_at <= '[END_DATE]';`

---
**Validation Log**: [Link to data/validation_*.jsonl]
**Backup File**: `backup_prod_YYYYMMDD.sql`
