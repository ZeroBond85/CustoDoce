#!/usr/bin/env python3
"""
Testes de integration para relatorios do dashboard.

Valida que build_daily_report_html() e build_telegram_summary() funcionam
contra Supabase real (ou com mock rico).

Requer SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY no env ou .env.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_db_creds() -> bool:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return False
    try:
        proj = url.split("//")[1].split(".")[0]
        return len(proj) > 10
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_db_creds(),
    reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set",
)


class TestBuildReportHtml:
    """Valida geracao de relatorio HTML contra Supabase real."""

    def test_build_report_html_against_real_db(self):
        """Gera HTML usando dados reais do Supabase via REST API."""
        from dashboard.pages.relatorios import build_daily_report_html, build_telegram_summary

        html = build_daily_report_html()
        assert "CustoDoce" in html or "Sem dados" in html
        msg = build_telegram_summary()
        assert "CustoDoce" in msg or "Sem dados" in msg


def test_test_smtp():
    from services.email_service import send_email

    assert callable(send_email)
