import streamlit as st
import base64
from pathlib import Path

_LOGO_PATH = Path(__file__).parent.parent.parent / "custodocelogo3.png"
_LOGO_BRANCO_PATH = Path(__file__).parent.parent.parent / "custodocelogobranco.png"
_LOGO_SIDEBAR_PATH = Path(__file__).parent.parent.parent / "custodocelogobranco_sidebar.png"


def get_logo_base64() -> str:
    if _LOGO_PATH.exists():
        return base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    if _LOGO_BRANCO_PATH.exists():
        return base64.b64encode(_LOGO_BRANCO_PATH.read_bytes()).decode()
    return ""


def get_logo_branco_base64() -> str:
    if _LOGO_BRANCO_PATH.exists():
        return base64.b64encode(_LOGO_BRANCO_PATH.read_bytes()).decode()
    return get_logo_base64()


def get_logo_sidebar_base64() -> str:
    if _LOGO_SIDEBAR_PATH.exists():
        return base64.b64encode(_LOGO_SIDEBAR_PATH.read_bytes()).decode()
    return get_logo_branco_base64()


def inject_css():
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

:root {
    --cd-orange: #F59E42;
    --cd-orange-light: #FBBF5E;
    --cd-orange-dark: #D97706;
    --cd-pink: #E8739A;
    --cd-pink-light: #F4A5C0;
    --cd-pink-dark: #C94D78;
    --cd-blue: #3B7DD8;
    --cd-blue-light: #60A5FA;
    --cd-blue-dark: #2563EB;
    --cd-success: #10B981;
    --cd-warning: #F59E0B;
    --cd-danger: #EF4444;
    --cd-bg: #FFF9F5;
    --cd-bg-card: #FFFFFF;
    --cd-bg-sidebar: linear-gradient(180deg, #B45309 0%, #BE185D 100%);
    --cd-text: #3D2C1E;
    --cd-text-secondary: #8B7355;
    --cd-border: #F0E6DB;
    --cd-radius: 14px;
    --cd-radius-sm: 10px;
    --cd-shadow: 0 2px 8px rgba(245,158,66,0.08), 0 1px 3px rgba(0,0,0,0.04);
    --cd-shadow-lg: 0 12px 32px rgba(245,158,66,0.12), 0 4px 12px rgba(0,0,0,0.06);
    --cd-font: 'Nunito', -apple-system, BlinkMacSystemFont, sans-serif;
}

.stApp {
    background-color: var(--cd-bg);
    font-family: var(--cd-font);
}

.stApp > header {
    background: transparent;
}

div[data-testid="stSidebar"] {
    background: var(--cd-bg-sidebar) !important;
    border-right: none !important;
}
div[data-testid="stSidebar"] * {
    color: #FFF !important;
}
div[data-testid="stSidebar"] .st-bw {
    background-color: rgba(255,255,255,0.15) !important;
}
div[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.2);
}
div[data-testid="stSidebar"] .stMarkdown p {
    color: rgba(255,255,255,0.85) !important;
}

.cd-card {
    background: var(--cd-bg-card);
    border-radius: var(--cd-radius);
    padding: 1.25rem;
    box-shadow: var(--cd-shadow);
    border: 1px solid var(--cd-border);
    transition: box-shadow 0.2s, transform 0.15s;
    margin-bottom: 1rem;
}
.cd-card:hover {
    box-shadow: var(--cd-shadow-lg);
    transform: translateY(-1px);
}

.cd-metric {
    background: var(--cd-bg-card);
    border-radius: var(--cd-radius);
    padding: 1rem 1.25rem;
    box-shadow: var(--cd-shadow);
    border: 1px solid var(--cd-border);
    border-left: 4px solid var(--cd-orange);
}
.cd-metric .label {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--cd-text-secondary);
    margin-bottom: 0.2rem;
}
.cd-metric .value {
    font-size: 1.75rem;
    font-weight: 800;
    color: var(--cd-text);
    line-height: 1.2;
}
.cd-metric .delta {
    font-size: 0.8rem;
    margin-top: 0.2rem;
}
.cd-metric .delta.positive { color: var(--cd-success); }
.cd-metric .delta.negative { color: var(--cd-danger); }

.cd-badge {
    display: inline-block;
    padding: 0.15rem 0.7rem;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 700;
    line-height: 1.5;
}
.cd-badge.success { background: #D1FAE5; color: #065F46; }
.cd-badge.warning { background: #FEF3C7; color: #92400E; }
.cd-badge.danger { background: #FEE2E2; color: #991B1B; }
.cd-badge.info { background: #DBEAFE; color: #1E40AF; }
.cd-badge.neutral { background: #F3F4F6; color: #374151; }

.cd-section {
    margin: 1.5rem 0 1rem;
}
.cd-section h2 {
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--cd-text);
    margin: 0 0 0.25rem;
    font-family: var(--cd-font);
}
.cd-section .subtitle {
    font-size: 0.875rem;
    color: var(--cd-text-secondary);
    margin: 0 0 1rem;
}

.cd-info-box {
    padding: 0.75rem 1rem;
    border-radius: var(--cd-radius-sm);
    border-left: 4px solid;
    margin-bottom: 1rem;
    font-size: 0.85rem;
}
.cd-info-box.info { background: #EFF6FF; border-color: var(--cd-blue); color: #1E40AF; }
.cd-info-box.success { background: #ECFDF5; border-color: var(--cd-success); color: #065F46; }
.cd-info-box.warning { background: #FFFBEB; border-color: var(--cd-warning); color: #92400E; }
.cd-info-box.error { background: #FEF2F2; border-color: var(--cd-danger); color: #991B1B; }

div[data-testid="stMetric"] {
    background: var(--cd-bg-card);
    border-radius: var(--cd-radius);
    padding: 1rem 1.25rem;
    box-shadow: var(--cd-shadow);
    border: 1px solid var(--cd-border);
    border-left: 4px solid var(--cd-orange);
}

div[data-testid="stTabs"] > div > div > div > div[role="tab"] {
    font-family: var(--cd-font);
    font-weight: 700;
}

div[data-testid="stDataFrame"] > div {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch !important;
}
div[data-testid="stDataFrame"] table {
    min-width: 600px;
}

@media (max-width: 768px) {
    .cd-card { padding: 0.85rem; }
    .cd-metric .value { font-size: 1.25rem; }
    div[data-testid="stMetric"] { padding: 0.75rem 1rem; }
    div[data-testid="stMetric"] label { font-size: 0.7rem; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 1.25rem; }

    .cd-kpi-row {
        flex-wrap: wrap !important;
    }
    .cd-kpi-row > * {
        flex: 0 0 calc(50% - 0.5rem) !important;
        margin-bottom: 0.75rem !important;
    }

    .cd-price-mini-card {
        padding: 0.7rem !important;
    }
    .cd-price-mini-card .price {
        font-size: 1.1rem !important;
    }
}

.cd-flyer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
    margin: 1rem 0;
}
.cd-flyer-card {
    background: #FFF;
    border-radius: var(--cd-radius);
    border: 1px solid var(--cd-border);
    box-shadow: var(--cd-shadow);
    padding: 1rem;
    transition: box-shadow 0.2s, transform 0.15s;
}
.cd-flyer-card:hover {
    box-shadow: var(--cd-shadow-lg);
    transform: translateY(-1px);
}
.cd-flyer-card .store {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--cd-text);
    margin-bottom: 0.15rem;
}
.cd-flyer-card .title {
    font-size: 0.78rem;
    color: var(--cd-text-secondary);
    margin-bottom: 0.6rem;
    line-height: 1.3;
}
.cd-flyer-card .meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.3rem;
}
.cd-flyer-card .meta-item {
    font-size: 0.7rem;
    color: #6B7280;
    font-weight: 600;
}
.cd-flyer-card .products {
    font-size: 0.7rem;
    color: var(--cd-blue);
    font-weight: 700;
}
.cd-flyer-card .date {
    font-size: 0.68rem;
    color: #9CA3AF;
}
.cd-flyer-detail {
    background: #FFF;
    border-radius: var(--cd-radius);
    border: 1px solid var(--cd-border);
    box-shadow: var(--cd-shadow);
    padding: 1.5rem;
    margin-top: 1rem;
}

.stButton>button:focus-visible {
    outline: 2px solid var(--cd-orange);
    outline-offset: 2px;
}

div[data-testid="stSidebar"] .stButton>button:focus-visible {
    outline: 2px solid #FFF !important;
    outline-offset: 2px;
}

/* ── Calculator ────────────────────────────── */
.cd-calc-result-card {
    background: var(--cd-bg-card);
    border-radius: var(--cd-radius);
    padding: 1.25rem;
    border: 1px solid var(--cd-border);
    box-shadow: var(--cd-shadow);
    margin-bottom: 0.75rem;
}
.cd-calc-result-card .cd-calc-label {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--cd-text-secondary);
    letter-spacing: 0.02em;
}
.cd-calc-result-card .cd-calc-value {
    font-size: 1.5rem;
    font-weight: 800;
    color: var(--cd-text);
}
.cd-calc-result-card .cd-calc-value.highlight {
    color: var(--cd-orange);
    font-size: 2rem;
}
.cd-calc-ing-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.75rem;
    background: var(--cd-bg);
    border-radius: var(--cd-radius-sm);
    border: 1px solid var(--cd-border);
    margin-bottom: 0.4rem;
    gap: 1rem;
    flex-wrap: wrap;
}
.cd-calc-ing-row .store-opt {
    font-size: 0.75rem;
    color: var(--cd-text-secondary);
}
.cd-calc-ing-row .price-mini {
    font-size: 0.85rem;
    font-weight: 700;
    white-space: nowrap;
}
.cd-calc-scenario {
    text-align: center;
    padding: 1rem;
    border-radius: var(--cd-radius-sm);
    border: 1px solid var(--cd-border);
    background: var(--cd-bg-card);
}
.cd-calc-scenario h4 {
    font-size: 0.8rem;
    text-transform: uppercase;
    color: var(--cd-text-secondary);
    margin: 0 0 0.3rem;
}
.cd-calc-scenario .price {
    font-size: 1.3rem;
    font-weight: 800;
    color: var(--cd-text);
}
.cd-calc-scenario .profit {
    font-size: 0.8rem;
    color: var(--cd-success);
    font-weight: 700;
}
.cd-calc-alert {
    font-size: 0.75rem;
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    background: #FEF3C7;
    color: #92400E;
    font-weight: 600;
    display: inline-block;
}

@media (max-width: 640px) {
    .cd-flyer-grid {
        grid-template-columns: 1fr;
        gap: 0.75rem;
    }
}
@media (min-width: 641px) and (max-width: 1024px) {
    .cd-flyer-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
@media (min-width: 1025px) {
    .cd-flyer-grid {
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    }
}
</style>
""",
        unsafe_allow_html=True,
    )


def metric_card(label: str, value, delta=None, delta_positive=True, help_text="", key=""):
    delta_class = "positive" if delta_positive else "negative"
    delta_html = f'<div class="delta {delta_class}">{delta}</div>' if delta is not None else ""
    help_attr = f'title="{help_text}"' if help_text else ""
    st.markdown(
        f'<div class="cd-metric" {help_attr}>'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f"{delta_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def status_badge(status: str):
    mapping = {
        "active": "success",
        "approved": "success",
        "success": "success",
        "pending": "warning",
        "partial": "warning",
        "error": "danger",
        "failed": "danger",
        "rejected": "danger",
        "info": "info",
        "running": "info",
        "processing": "info",
    }
    cls = mapping.get(status.lower(), "neutral")
    st.markdown(
        f'<span class="cd-badge {cls}">{status}</span>',
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str = ""):
    sub = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="cd-section"><h2>{title}</h2>{sub}</div>',
        unsafe_allow_html=True,
    )


def info_box(message: str, type: str = "info"):
    st.markdown(
        f'<div class="cd-info-box {type}">{message}</div>',
        unsafe_allow_html=True,
    )


def card(content: str, key=""):
    st.markdown(
        f'<div class="cd-card">{content}</div>',
        unsafe_allow_html=True,
    )


def logo_small(size: int = 36):
    logo_b64 = get_logo_base64()
    if logo_b64:
        st.markdown(
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="width:{size}px;height:{size}px;border-radius:8px;object-fit:contain;" />',
            unsafe_allow_html=True,
        )


def logo_full(width: int = 220):
    logo_b64 = get_logo_base64()
    if logo_b64:
        st.markdown(
            f'<div style="text-align:center;margin-bottom:1rem;">'
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="width:{width}px;max-width:100%;height:auto;" />'
            f"</div>",
            unsafe_allow_html=True,
        )


def plotly_theme():
    import plotly.graph_objects as go
    import plotly.io as pio

    pio.templates["custodoce"] = go.layout.Template(
        layout=go.Layout(
            font={"family": "Nunito, sans-serif", "color": "#3D2C1E"},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=["#F59E42", "#E8739A", "#3B7DD8", "#FBBF5E", "#60A5FA", "#C94D78"],
            xaxis={"gridcolor": "#F0E6DB", "zerolinecolor": "#F0E6DB"},
            yaxis={"gridcolor": "#F0E6DB", "zerolinecolor": "#F0E6DB"},
            hoverlabel={
                "bgcolor": "#FFFFFF",
                "font": {"family": "Nunito, sans-serif", "color": "#3D2C1E"},
            },
            margin={"l": 50, "r": 20, "t": 40, "b": 50},
        )
    )
    pio.templates.default = "custodoce"
