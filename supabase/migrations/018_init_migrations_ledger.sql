-- ============================================================
-- MIGRATION LEDGER: rastreia cada migration aplicada no banco.
-- ============================================================
-- Objetivo: detectar drift entre o que está no disco (supabase/migrations/)
-- e o que foi de fato aplicado em PROD. O script scripts/validate_migrations.py
-- compara SHA-256 do arquivo local com o checksum gravado aqui.
--
-- Criada ANTES de todas as outras phases no consolidated_migration.sql
-- (PHASE 0) para que o bootstrap (Fase E) possa registrar 001..017
-- retroativamente. Writes são service_role-only.

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version   TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    checksum  TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

-- Service role (e quem tem a chave service) pode ler/escrever o ledger.
DROP POLICY IF EXISTS "schema_migrations_service_all" ON public.schema_migrations;
CREATE POLICY "schema_migrations_service_all" ON public.schema_migrations
    FOR ALL TO service_role USING (true) WITH CHECK (true);
