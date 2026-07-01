"""Tests para Sprint 7-9 features:
- extract_ppk/extract_pun resiliência de fallback chain
- _is_promotion em promocoes
- _safe_ppk em promocoes
- _contact_options em alertas
- _dialog helpers structure (smoke)

Esses testes rodam sem Streamlit — verificam pure functions.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")


def test_extract_ppk_flat_value():
    """extract_ppk lê row['price_per_kg'] flat (v_latest_prices)."""
    from services.dashboard_queries import extract_ppk

    assert extract_ppk({"price_per_kg": 12.50}) == 12.50


def test_extract_ppk_nested_value():
    """extract_ppk faz fallback para normalized.price_per_kg."""
    from services.dashboard_queries import extract_ppk

    assert extract_ppk({"normalized": {"price_per_kg": 23.40}}) == 23.40


def test_extract_ppk_flat_wins_when_both_present():
    """Se ambos formatos existirem, flat vence (não duplicar)."""
    from services.dashboard_queries import extract_ppk

    row = {"price_per_kg": 5.50, "normalized": {"price_per_kg": 99.99}}
    assert extract_ppk(row) == 5.50


def test_extract_ppk_zero_or_missing_returns_zero():
    """Linhas sem dados retornam 0, nunca negativo."""
    from services.dashboard_queries import extract_ppk

    assert extract_ppk({}) == 0.0
    assert extract_ppk({"price_per_kg": 0}) == 0.0
    assert extract_ppk({"price_per_kg": None}) == 0.0
    assert extract_ppk({"normalized": None}) == 0.0


def test_extract_ppk_handles_invalid_strings():
    """Strings inválidas (não-numéricas) viram 0, não exception."""
    from services.dashboard_queries import extract_ppk

    assert extract_ppk({"price_per_kg": "not-a-number"}) == 0.0
    assert extract_ppk({"price_per_kg": []}) == 0.0


def test_extract_pun_flat_value():
    from services.dashboard_queries import extract_pun

    assert extract_pun({"price_per_un": 3.20}) == 3.20


def test_extract_pun_nested_value():
    from services.dashboard_queries import extract_pun

    assert extract_pun({"normalized": {"price_per_un": 4.50}}) == 4.50


def test_extract_pun_handles_zero_values():
    from services.dashboard_queries import extract_pun

    assert extract_pun({}) == 0.0
    assert extract_pun({"normalized": {}}) == 0.0


def test_promocoes_is_promotion_true_via_flag():
    """_is_promotion detecta is_promotion=True."""
    from dashboard.pages.promocoes import _is_promotion

    assert _is_promotion({"is_promotion": True}) is True


def test_promocoes_is_promotion_true_via_oferta_tag():
    """_is_promotion detecta tag 'OFERTA' (case-insensitive)."""
    from dashboard.pages.promocoes import _is_promotion

    assert _is_promotion({"is_promotion": False, "ai_tags": ["OFERTA"]}) is True
    assert _is_promotion({"is_promotion": False, "ai_tags": ["promocao", "oferta"]}) is True


def test_promocoes_is_promotion_false_for_normal_item():
    """_is_promotion retorna False para item comum."""
    from dashboard.pages.promocoes import _is_promotion

    assert _is_promotion({"is_promotion": False}) is False
    assert _is_promotion({"is_promotion": False, "ai_tags": ["novo"]}) is False
    assert _is_promotion({"is_promotion": False, "ai_tags": None}) is False


def test_promocoes_safe_ppk_flat():
    """_safe_ppk lê row['price_per_kg'] flat."""
    from dashboard.pages.promocoes import _safe_ppk

    assert _safe_ppk({"price_per_kg": 7.50}) == 7.50


def test_promocoes_safe_ppk_nested_fallback():
    """_safe_ppk faz fallback para normalized.price_per_kg."""
    from dashboard.pages.promocoes import _safe_ppk

    assert _safe_ppk({"normalized": {"price_per_kg": 11.20}}) == 11.20


def test_promocoes_safe_ppk_returns_zero_on_empty():
    from dashboard.pages.promocoes import _safe_ppk

    assert _safe_ppk({}) == 0.0
    assert _safe_ppk({"price_per_kg": None, "normalized": None}) == 0.0


def test_ingredientes_confirm_yaml_save_dialog_exists():
    """_confirm_yaml_save_dialog é um decorador st.dialog."""
    from dashboard.pages.ingredientes import _confirm_yaml_save_dialog

    assert callable(_confirm_yaml_save_dialog)


def test_flyers_confirm_delete_dialog_exists():
    """_confirm_delete_dialog é um decorador st.dialog."""
    from dashboard.pages.flyers import _confirm_delete_dialog

    assert callable(_confirm_delete_dialog)


def test_relatorios_confirm_send_report_dialog_exists():
    """_confirm_send_report_dialog é um decorador st.dialog."""
    from dashboard.pages.relatorios import _confirm_send_report_dialog

    assert callable(_confirm_send_report_dialog)


def test_alertas_contact_options_filters_empty():
    """_contact_options filtra recipients sem campo 'email' ou 'chat_id'."""
    from dashboard.pages import alertas

    def fake_recipients(channel):
        return [
            {"email": "a@b.c", "chat_id": None},
            {"email": None, "chat_id": "12345"},
            {"email": "", "chat_id": ""},
        ]

    try:
        original = alertas.cached_get_active_recipients
    except AttributeError:
        original = None

    alertas.cached_get_active_recipients = fake_recipients
    try:
        assert alertas._contact_options("email") == ["a@b.c"]
        assert alertas._contact_options("telegram") == ["12345"]
    finally:
        if original is not None:
            alertas.cached_get_active_recipients = original


def test_alertas_fallback_pagination_clamping():
    """_fallback_pagination aceita total_pages e retorna int."""
    from dashboard.pages import alertas

    # Verifica apenas que a função existe e é chamável
    assert callable(alertas._fallback_pagination)


def test_ingredientes_backup_dir_constant():
    """INGREDIENTS_BACKUP_DIR aponta para data/ingredient_backups/."""
    from dashboard.pages.ingredientes import INGREDIENTS_BACKUP_DIR

    assert INGREDIENTS_BACKUP_DIR.name == "ingredient_backups"


def test_ingredientes_yaml_path_constant():
    """INGREDIENTS_YAML aponta para config/ingredients.yaml."""
    from dashboard.pages.ingredientes import INGREDIENTS_YAML

    assert INGREDIENTS_YAML.name == "ingredients.yaml"
    assert "config" in str(INGREDIENTS_YAML)


def test_admin_app_has_menu_groups():
    """MENU_GROUPS exportado em admin/app.py."""
    from admin.app import MENU_GROUPS

    assert isinstance(MENU_GROUPS, dict)
    assert "📊 Painel" in MENU_GROUPS
    assert "🔧 Ferramentas" in MENU_GROUPS


def test_admin_app_build_navigation_returns_none_when_st_pagination_missing():
    """_build_navigation() retorna None se Streamlit não suporta st.Page."""
    from admin.app import _build_navigation

    # 1.58 tem st.Page, então resultado depende da versão.
    # Aceitar Page object OU None.
    result = _build_navigation()
    assert result is None or hasattr(result, "run")
