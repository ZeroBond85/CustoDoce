-- Migration: Add match_threshold column to ingredients + ensure llm_classifier feature flag
-- Date: 2026-09-XX

-- Add match_threshold column to ingredients table
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS match_threshold DECIMAL(3,2) DEFAULT 0.80;
COMMENT ON COLUMN ingredients.match_threshold IS 'Per-ingredient fuzzy match threshold (0-1). Overrides global default.';

-- Ensure feature_flags has llm_classifier entry (disabled per experiment results)
INSERT INTO feature_flags (key, enabled, description)
VALUES ('llm_classifier', false, 'LLM classifier for gray-zone matches (70-82%) — disabled per experiment')
ON CONFLICT (key) DO UPDATE SET enabled = false, description = EXCLUDED.description;