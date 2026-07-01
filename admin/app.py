"""
CustoDoce Dashboard - Main Application (Modular Architecture)
Refactored from 3664 lines to ~200 lines using dashboard/pages modules.

Architecture: st.navigation() (Streamlit 1.36+) with grouped sidebar.
Single source of truth: dashboard/navigation_config.py (MENU_GROUPS, PAGE_FUNCTIONS, etc.)
"""

import os
import sys
from pathlib import Path

import streamlit as st

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from dashboard.components.layout import (
    render_sidebar,
    render_skip_link,
)
from dashboard.login_page import render_login

# Single source of truth — all navigation constants from one place
from dashboard.navigation_config import (
    PAGE_FUNCTIONS,
    MENU_GROUPS,
    DEFAULT_PAGE,
)

st.set_page_config(
    page_title="CustoDoce - Painel de Preços",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Password from env or generated
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    import secrets

    ADMIN_PASSWORD = secrets.token_urlsafe(16)
    os.environ.setdefault("ADMIN_PASSWORD", ADMIN_PASSWORD)


# ── Helpers (re-exported for test compatibility) ─────────────
def _flyer_status_color(status):
    colors = {"done": "#10B981", "processed": "#10B981", "pending": "#F59E0B", "failed": "#EF4444", "error": "#EF4444"}
    return colors.get(status, "#6B7280")


def _flyer_status_label(status):
    labels = {
        "done": "processado",
        "processed": "processado",
        "pending": "pendente",
        "failed": "falha",
        "error": "falha",
    }
    return labels.get(status, "unknown")


def _format_kg(normalized):
    if isinstance(normalized, dict):
        return normalized.get("price_per_kg", 0)
    return 0


def _get_kg(df):
    return df["normalized"].apply(_format_kg)


def _build_navigation():
    """Build a grouped st.navigation() from MENU_GROUPS and PAGE_FUNCTIONS.

    Returns None if Streamlit version doesn't support st.navigation() (defensive).
    Tests import PAGE_FUNCTIONS separately and don't touch the returned Page
    object — the legacy render flow runs alongside.
    """
    if not hasattr(st, "navigation") or not hasattr(st, "Page"):
        return None
    try:
        groups: dict[str, list] = {}
        for group_label, group_pages in MENU_GROUPS.items():
            group_pages_list = []
            for label, icon, page_id in group_pages:
                fn = PAGE_FUNCTIONS.get(page_id)
                if fn is None:
                    continue
                group_pages_list.append(
                    st.Page(
                        fn,
                        title=label,
                        icon=icon,
                        url_path=page_id,
                        default=(page_id == DEFAULT_PAGE),
                    )
                )
            if group_pages_list:
                groups[group_label] = group_pages_list
        if not groups:
            return None
        return st.navigation(groups)
    except Exception:
        return None


def _render_page_by_id(page_id: str) -> None:
    """Legacy fallback path: dispatch to PAGE_FUNCTIONS[page_id]()."""
    page_fn = PAGE_FUNCTIONS.get(page_id)
    if page_fn is None:
        st.error(f"Página '{page_id}' não encontrada.")
        st.session_state.page = DEFAULT_PAGE
        st.rerun()
    page_fn()


def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "page" not in st.session_state:
        st.session_state.page = DEFAULT_PAGE

    if not st.session_state.authenticated:
        render_login()
        st.stop()

    if hasattr(st, "navigation") and hasattr(st, "Page"):
        page_obj = _build_navigation()
        if page_obj is not None:
            render_skip_link()
            page_obj.run()
            return

    # Legacy fallback (Streamlit pre-1.36 or Page build failure)
    render_sidebar()
    render_skip_link()
    current_page = st.session_state.get("page", DEFAULT_PAGE)
    _render_page_by_id(current_page)


if __name__ == "__main__":
    main()
