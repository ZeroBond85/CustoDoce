-- ============================================================
-- Migration 006: Fix RLS policies — service_role only
-- 
-- Problem: Phase 1 RLS policies named "Enable write for service role"
-- use USING (true) / WITH CHECK (true) instead of
-- auth.role() = 'service_role'. Any authenticated user (or anon)
-- can INSERT/UPDATE on 6 critical tables.
-- 
-- Fix: Drop insecure policies, recreate with proper role check.
-- ============================================================

-- ============================================================
-- prices
-- ============================================================
DROP POLICY IF EXISTS "Enable write for service role" ON prices;
DROP POLICY IF EXISTS "Enable update for service role" ON prices;

CREATE POLICY "service_role_insert" ON prices
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_update" ON prices
    FOR UPDATE USING (auth.role() = 'service_role');

-- ============================================================
-- price_history
-- ============================================================
DROP POLICY IF EXISTS "Enable write for service role" ON price_history;

CREATE POLICY "service_role_insert" ON price_history
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- review_queue
-- ============================================================
DROP POLICY IF EXISTS "Enable write for service role" ON review_queue;
DROP POLICY IF EXISTS "Enable update for service role" ON review_queue;

CREATE POLICY "service_role_insert" ON review_queue
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_update" ON review_queue
    FOR UPDATE USING (auth.role() = 'service_role');

-- ============================================================
-- scraping_logs
-- ============================================================
DROP POLICY IF EXISTS "Enable write for service role" ON scraping_logs;

CREATE POLICY "service_role_insert" ON scraping_logs
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- ============================================================
-- stores
-- ============================================================
DROP POLICY IF EXISTS "Enable write for service role" ON stores;
DROP POLICY IF EXISTS "Enable update for service role" ON stores;

CREATE POLICY "service_role_insert" ON stores
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_update" ON stores
    FOR UPDATE USING (auth.role() = 'service_role');

-- ============================================================
-- flyers
-- ============================================================
DROP POLICY IF EXISTS "Enable write for service role" ON flyers;
DROP POLICY IF EXISTS "Enable update for service role" ON flyers;

CREATE POLICY "service_role_insert" ON flyers
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "service_role_update" ON flyers
    FOR UPDATE USING (auth.role() = 'service_role');
