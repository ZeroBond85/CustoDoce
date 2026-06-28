"""
Capacity Planning Section (RFC Recurso 4).

Monitoramento de saúde do Free Tier:
- Disco Supabase (via pg_total_relation_size): tabela + índices.
- Minutos GitHub Actions (via SUM de duration_seconds).
- Cota SMTP (contagem dos envios das últimas 24h).

Cada métrica retorna um widget `st.metric` e `st.progress` para limite.
"""

from datetime import datetime, date, timedelta

import streamlit as st

from services.supabase_client import get_supabase


# Limites do Free Tier
SUPABASE_DISK_LIMIT_MB = 500  # 500 MB
GITHUB_ACTIONS_LIMIT_MIN = 2000  # 2000 min/mês
GMAIL_SMTP_LIMIT_24H = 500  # 500 e-mails/dia


def _get_disk_usage_mb() -> tuple[float, int]:
    """
    Soma os tamanhos de todas as tabelas do banco via RPC.
    Returns:
        (size_mb, table_count)
    """
    try:
        client = get_supabase()
        sql = (
            "SELECT SUM(pg_total_relation_size(quote_ident(tablename))) AS total_bytes "
            "FROM pg_tables WHERE schemaname = 'public'"
        )
        result = client.rpc("exec_sql_query", {"sql": sql}).execute()
        if result.data and len(result.data) > 0:
            row = result.data[0]
            bytes_total = float(row.get("total_bytes") or 0)
            return bytes_total / (1024 * 1024), 1
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug("Supabase disk check failed: %s", e)
    return 0.0, 0


def _get_actions_minutes_used() -> tuple[float, int]:
    """
    Soma os minutos de duração de scraping_logs do mês corrente.
    Esta é uma estimativa via scraper durations locais.
    """
    try:
        client = get_supabase()
        # Get logs started within current month
        first_day = date.today().replace(day=1).isoformat()
        result = client.table("scraping_logs").select("duration_seconds").gte("started_at", first_day).execute()
        if result.data:
            total_seconds = sum(r.get("duration_seconds") or 0 for r in result.data)
            return total_seconds / 60.0, len(result.data)
        return 0.0, 0
    except Exception:
        return 0.0, 0


def _get_smtp_quota_used() -> int:
    """
    Conta envios de e-mail das últimas 24h.
    We use the timestamp of scraping_logs as a fallback; if you have an
    email_logs table, extend the implementation.
    """
    try:
        client = get_supabase()
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        # Use the admin/notification pattern - count grouped runs as proxy.
        # Without an email_logs table, we estimate from scraping completions.
        result = client.table("scraping_logs").select("duration_seconds").gte("started_at", cutoff).execute()
        # Each scrape completion can trigger at most 1-2 emails.
        # We cap based on the assumption of e-mail frequency.
        # Replace with real email log table if it exists.
        # Conservative estimate: nr_scrapes_success_proxy * 1.
        proxy_count = len(result.data or [])
        return proxy_count
    except Exception:
        return 0


def render_capacity_planning():
    """
    Render the capacity planning section with Free Tier limits.
    """
    st.subheader("📊 Capacity Planning (Free Tier)")

    # ----------------------------------------------------------------
    # Disco Supabase
    # ----------------------------------------------------------------
    disk_mb, table_count = _get_disk_usage_mb()
    disk_pct = (disk_mb / SUPABASE_DISK_LIMIT_MB) if SUPABASE_DISK_LIMIT_MB else 0.0
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="💾 Disco Supabase (PG)",
            value=f"{disk_mb:.1f} MB",
            delta=f"{disk_pct * 100:.1f}% usado",
            delta_color="inverse" if disk_pct > 0.7 else "off",
        )
        st.progress(min(1.0, disk_pct))
        st.caption(f"Limite Free Tier: {SUPABASE_DISK_LIMIT_MB} MB")
        if disk_pct > 0.9:
            st.error("❌ Excede 90% da cota! Execute `cleanup_old_prices(days=45)`")
        elif disk_pct > 0.7:
            st.warning("⚠ Acima de 70% da cota — considere cleanup.")

    # ----------------------------------------------------------------
    # Minutos GitHub Actions (estimado)
    # ----------------------------------------------------------------
    actions_min, scrapes_count = _get_actions_minutes_used()
    actions_pct = actions_min / GITHUB_ACTIONS_LIMIT_MIN if GITHUB_ACTIONS_LIMIT_MIN else 0.0
    with col2:
        st.metric(
            label="⏱ GitHub Actions (mês)",
            value=f"{actions_min:.1f} min",
            delta=f"{actions_pct * 100:.1f}% do limite",
            delta_color="inverse" if actions_pct > 0.8 else "off",
        )
        st.progress(min(1.0, actions_pct))
        st.caption(f"Limite mensal: {GITHUB_ACTIONS_LIMIT_MIN} min ({scrapes_count} execuções detectadas)")
        if actions_pct > 0.9:
            st.error("❌ Estourando quota de GitHub Actions!")

    # ----------------------------------------------------------------
    # Cota SMTP (últimas 24h)
    # ----------------------------------------------------------------
    smtp_used = _get_smtp_quota_used()
    smtp_pct = (smtp_used / GMAIL_SMTP_LIMIT_24H) if GMAIL_SMTP_LIMIT_24H else 0.0
    with col3:
        st.metric(
            label="📨 SMTP Gmail (24h)",
            value=f"{smtp_used} envios",
            delta=f"{smtp_pct * 100:.1f}% da cota",
            delta_color="inverse" if smtp_pct > 0.8 else "off",
        )
        st.progress(min(1.0, smtp_pct))
        st.caption(f"Limite Gmail: {GMAIL_SMTP_LIMIT_24H} envios/dia")
        if smtp_pct > 0.9:
            st.error("❌ Perto do limite SMTP! Reduza frequência.")

    # ----------------------------------------------------------------
    # Ações recomendadas
    # ----------------------------------------------------------------
    with st.expander("🛠 Ações de Mitigação"):
        st.markdown(
            """
            - **Disco alto?** → `python scripts/cleanup_old_flyers_all.py` (TTL 180d)
            - **Actions alto?** → Desativar Tier 2b (Manual) ou reduzir frequência
              via `scrape_frequencies`
            - **SMTP alto?** → Reduzir geração de relatórios ou enviar só
              alterações significativas
            - Para verificar limites exatos visite
              [Supabase Dashboard](https://supabase.com/dashboard) e
              [GitHub Settings](https://github.com/settings/billing)
            """
        )


__all__ = ["render_capacity_planning"]
