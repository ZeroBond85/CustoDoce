-- ============================================================
-- PHASE 4: LLM Match Cache (Recurso 3 do RFC)
-- Armazena decisões de matching do LLM para evitar chamadas redundantes
-- TTL: 30 dias (para capturar mudanças de embalagem)
-- ============================================================

-- Tabela de cache para decisões do LLM
CREATE TABLE IF NOT EXISTS llm_match_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_raw_name TEXT NOT NULL,
    brand TEXT DEFAULT '',
    ingredient_id TEXT NOT NULL,
    match_decision JSONB NOT NULL,
    -- JSON structure: {"match": bool, "canonical_name": str, "confidence_score": float, "reason": str, "provider": str}
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Unique constraint on product + brand (avoid duplicates)
    CONSTRAINT llm_match_cache_product_brand_key UNIQUE (product_raw_name, brand)
);

-- Índice para busca rápida por product name
CREATE INDEX IF NOT EXISTS idx_llm_cache_product ON llm_match_cache(product_raw_name);

-- Índice para buscar por ingredient (útil para analytics)
CREATE INDEX IF NOT EXISTS idx_llm_cache_ingredient ON llm_match_cache(ingredient_id);

-- Índice para buscar por data (para TTL cleanup)
CREATE INDEX IF NOT EXISTS idx_llm_cache_created ON llm_match_cache(created_at DESC);

-- Trigger para updated_at
CREATE OR REPLACE FUNCTION update_llm_cache_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_llm_cache_updated_at ON llm_match_cache;
CREATE TRIGGER trg_llm_cache_updated_at
    BEFORE UPDATE ON llm_match_cache
    FOR EACH ROW EXECUTE FUNCTION update_llm_cache_updated_at();

-- RLS:allow service_role full access, anon read-only
ALTER TABLE llm_match_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON llm_match_cache
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "anon_read" ON llm_match_cache
    FOR SELECT USING (true);

-- ============================================================
-- Cleanup function para o cache (TTL 30 dias)
-- ============================================================
CREATE OR REPLACE FUNCTION cleanup_old_llm_cache(retention_days int DEFAULT 30)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM llm_match_cache
    WHERE created_at < now() - (retention_days || ' days')::interval;
END;
$$;

COMMENT ON TABLE llm_match_cache IS 'Cache de decisões de matching LLM para evitar chamadas redundantes à API Groq. TTL de 30 dias.';
COMMENT ON COLUMN llm_match_cache.product_raw_name IS 'Nome bruto do produto conforme extraído do scraper (PK junto com brand)';
COMMENT ON COLUMN llm_match_cache.brand IS 'Marca extraída do produto (pode ser vazio)';
COMMENT ON COLUMN llm_match_cache.ingredient_id IS 'ID canônico do ingredienteMatched (ex: leite_condensado_integral)';
COMMENT ON COLUMN llm_match_cache.match_decision IS 'Decisão completa do LLM em JSON: {match, canonical_name, confidence_score, reason, provider}';