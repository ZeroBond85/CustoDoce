import base64
from datetime import UTC
from pathlib import Path

import streamlit as st

_CSS_PATH = Path(__file__).parent.parent / "static" / "style.css"
_LOGO_PATH = Path(__file__).parent.parent.parent / "custodocelogo3.png"
_LOGO_BRANCO_PATH = Path(__file__).parent.parent.parent / "custodocelogobranco.png"
_LOGO_SIDEBAR_PATH = Path(__file__).parent.parent.parent / "custodocelogobranco_sidebar.png"


@st.cache_data(ttl=3600)
def get_logo_base64() -> str:
    if _LOGO_PATH.exists():
        return base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    if _LOGO_BRANCO_PATH.exists():
        return base64.b64encode(_LOGO_BRANCO_PATH.read_bytes()).decode()
    return ""


@st.cache_data(ttl=3600)
def get_logo_branco_base64() -> str:
    if _LOGO_BRANCO_PATH.exists():
        return base64.b64encode(_LOGO_BRANCO_PATH.read_bytes()).decode()
    return get_logo_base64()


@st.cache_data(ttl=3600)
def get_logo_sidebar_base64() -> str:
    if _LOGO_SIDEBAR_PATH.exists():
        return base64.b64encode(_LOGO_SIDEBAR_PATH.read_bytes()).decode()
    return get_logo_branco_base64()


@st.cache_data
def _load_css() -> str:
    if _CSS_PATH.exists():
        return _CSS_PATH.read_text(encoding="utf-8")
    return ""


def inject_css():
    css = _load_css()
    if css:
        st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


def _freshness_badge_html(collected_at, now=None):
    from datetime import datetime

    if not collected_at:
        return '<span class="cd-badge neutral">n/d</span>'
    if isinstance(collected_at, str):
        s = collected_at.replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(s)
        except ValueError:
            return '<span class="cd-badge neutral">n/d</span>'
    else:
        ts = collected_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    ref = now or datetime.now(UTC)
    days = (ref - ts).days
    if days <= 7:
        label = f"{days}d" if days > 0 else "hoje"
        return f'<span class="cd-badge success">{label}</span>'
    elif days <= 30:
        return f'<span class="cd-badge warning">{days}d</span>'
    else:
        return f'<span class="cd-badge danger">{days}d stale</span>'


def freshness_column(collected_at, now=None):
    return _freshness_badge_html(collected_at, now)


def info_box(message: str, type: str = "info"):
    st.markdown(
        f'<div class="cd-info-box {type}">{message}</div>',
        unsafe_allow_html=True,
    )


def render_user_badge(username: str):
    st.markdown(
        f'<div style="text-align:center;padding:0.5rem 0;font-size:0.78rem;"><strong>{username}</strong></div>',
        unsafe_allow_html=True,
    )
