-- ============================================================
-- SCRAPER ALERT STATE: cooldown para alertas de anomalia (Fase C)
-- ============================================================
-- Evita spam de Telegram: cada loja só dispara alerta com cooldown configurável.
-- Mantém estado (último alerta, último score, se está ativo) por store_name.
--
-- Segurança: somente service_role escreve/lê. Anon não tem access.
--   - sem policies para anon/authenticated (negadas por default em RLS)
--   - policy "scraper_alert_state_service_all" permite todas as ops para service_role

CREATE TABLE IF NOT EXISTS public.scraper_alert_state (
    store_name          TEXT PRIMARY KEY,
    last_alerted_at     TIMESTAMPTZ,
    last_trend_score    DOUBLE PRECISION,
    last_status         TEXT,           -- 'normal' | 'degraded' | 'critical'
    active              BOOLEAN DEFAULT FALSE,  -- TRUE = alerta ativo (não resolvido)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.scraper_alert_state IS
'Estado de cooldown para alertas de anomalia de scrapers. Cada loja dispara alerta com intervalo mínimo.';

-- RLS on
ALTER TABLE public.scraper_alert_state ENABLE ROW LEVEL SECURITY;

-- service_role escreve/lê (pipeline de coleta/watcher)
CREATE POLICY "scraper_alert_state_service_all" ON public.scraper_alert_state
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Nenhuma policy para anon/authenticated → negado por default (RLS)
COMMENT ON POLICY "scraper_alert_state_service_all" ON public.scraper_alert_state IS
'Somente service_role (watcher/pipeline) pode ler/escrever estado de alertas.';
