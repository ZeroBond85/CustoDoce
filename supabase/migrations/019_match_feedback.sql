-- ============================================================
-- FEEDBACK LOOP: match_feedback (Fase B4 — aprendizado com decisões humanas)
-- ============================================================
-- Armazena cada decisão (automática ou manual) sobre matches na fila de revisão.
-- Sem isso, o sistema não aprende: mesma taxa de erro persiste sozinho.
-- Feedback fica em quatro categorias: auto_persist (score>=gate), llm_confirmed,
-- manual_approve, manual_reject. Serve para calibrar thresholds ao longo do tempo.
--
-- Segurança: somente service_role deve escrever (auto/coletor). Anon não lê nem escreve.
--   - sem policies explícitas para anon/authenticated (são negadas por default em RLS)
--   - policy "match_feedback_service_all" permite todas as op p/ service_role

CREATE TABLE IF NOT EXISTS public.match_feedback (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ingredient_id   UUID REFERENCES ingredients(id) ON DELETE CASCADE,
    store_id        TEXT REFERENCES stores(id) ON DELETE CASCADE,
    raw_product     TEXT NOT NULL,
    score           NUMERIC(8,4) NOT NULL,                 -- combined [0,1]
    rf_score        NUMERIC(8,4),                          -- RapidFuzz [0,100]
    semantic_score  NUMERIC(8,4),                          -- [0,1]
    llm_confidence  NUMERIC(8,4),                           -- [0,1]
    llm_provider    TEXT,
    llm_reason      TEXT,
    match_type      TEXT,                                   -- exato / proximo_apelido / etc
    decision_type   TEXT NOT NULL CHECK (decision_type IN (
                        'auto_persist',
                        'llm_confirmed',
                        'manual_approve',
                        'manual_reject',
                        'auto_reject'
                    )),
    decided_by      TEXT NOT NULL DEFAULT 'service',       -- service | dashboard | telegram
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices para análises de calibração (por score, por ingrediente, por tipo)
CREATE INDEX IF NOT EXISTS idx_match_feedback_decision_type ON public.match_feedback (decision_type);
CREATE INDEX IF NOT EXISTS idx_match_feedback_ingredient     ON public.match_feedback (ingredient_id);
CREATE INDEX IF NOT EXISTS idx_match_feedback_created_at     ON public.match_feedback (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_match_feedback_score          ON public.match_feedback (score);

COMMENT ON TABLE public.match_feedback IS
'Registra todas as decisões de match (auto/manual) para calibração contínua de thresholds.';

-- RLS on
ALTER TABLE public.match_feedback ENABLE ROW LEVEL SECURITY;

-- service_role escreve/lê (coletor + pipeline de validação)
CREATE POLICY "match_feedback_service_all" ON public.match_feedback
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Nenhuma policy para anon/authenticated → negado por default (RLS)
COMMENT ON POLICY "match_feedback_service_all" ON public.match_feedback IS
'Somente service_role (pipeline de coleta/scraper) pode ler/escrever feedback.';
