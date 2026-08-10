-- Migration 008: Add promoted_at column to store_registry
-- Tracks when a store was promoted from discovery to approved.

ALTER TABLE store_registry ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_store_registry_promoted_at ON store_registry(promoted_at);
