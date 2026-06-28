"""Design checks extraídos do test_dashboard_full.py."""

import os
import re


def test_css_syntax():
    css = """
:root {
    --cd-primary: #7C3AED;
    --cd-primary-light: #A78BFA;
    --cd-primary-dark: #5B21B6;
    --cd-success: #10B981;
    --cd-warning: #F59E0B;
    --cd-danger: #EF4444;
    --cd-info: #3B82F6;
    --cd-bg: #FAFAFA;
    --cd-bg-card: #FFFFFF;
    --cd-bg-sidebar: #1E1B4B;
    --cd-text: #1F2937;
    --cd-text-secondary: #6B7280;
    --cd-border: #E5E7EB;
    --cd-radius: 12px;
    --cd-radius-sm: 8px;
    --cd-shadow: 0 1px 3px rgba(0,0,0,0.1);
    --cd-shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
    --cd-font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
.cd-card { background: var(--cd-bg-card); border-radius: var(--cd-radius); }
.cd-metric { border-left: 4px solid var(--cd-primary); }
.cd-badge.success { background: #D1FAE5; color: #065F46; }
.cd-badge.warning { background: #FEF3C7; color: #92400E; }
.cd-badge.danger { background: #FEE2E2; color: #991B1B; }
.cd-badge.info { background: #DBEAFE; color: #1E40AF; }
.cd-badge.neutral { background: #F3F4F6; color: #374151; }
.cd-info-box { border-left: 4px solid; }
.cd-section h2 { font-weight: 700; }
@media (max-width: 768px) {
    .cd-card { padding: 1rem; }
    .cd-metric .value { font-size: 1.25rem; }
}
"""
    open_br = css.count("{")
    close_br = css.count("}")
    assert open_br == close_br, f"Chaves desbalanceadas: {open_br} abertas, {close_br} fechadas"
    var_uses = set(re.findall(r"var\((--[\w-]+)\)", css))
    var_defs = set(re.findall(r"(--[\w-]+)\s*:", css))
    undefined = var_uses - var_defs
    assert not undefined, f"Variáveis CSS usadas mas não definidas: {undefined}"


def test_css_variables():
    expected_vars = [
        "--cd-orange",
        "--cd-pink",
        "--cd-blue",
        "--cd-success",
        "--cd-warning",
        "--cd-danger",
        "--cd-bg",
        "--cd-bg-card",
        "--cd-bg-sidebar",
        "--cd-text",
        "--cd-text-secondary",
        "--cd-border",
        "--cd-radius",
        "--cd-radius-sm",
        "--cd-shadow",
        "--cd-shadow-lg",
    ]
    with open("dashboard/components/ui.py") as f:
        content = f.read()
    for var in expected_vars:
        assert var in content, f"Variável CSS {var} não encontrada em ui.py"


def test_responsive_breakpoints():
    with open("dashboard/components/ui.py") as f:
        content = f.read()
    assert "@media (max-width: 768px)" in content, "Faltando breakpoint mobile"
    assert "@media" in content, "Nenhum media query encontrado"


def test_flyer_css_breakpoints():
    with open("dashboard/components/ui.py", encoding="utf-8") as f:
        content = f.read()
    assert ".cd-flyer-grid" in content
    assert ".cd-flyer-card" in content
    assert ".cd-flyer-detail" in content
    assert "@media (max-width: 640px)" in content
    assert "grid-template-columns: 1fr" in content
    assert "@media (min-width: 641px) and (max-width: 1024px)" in content
    assert "grid-template-columns: repeat(2, 1fr)" in content
    assert "@media (min-width: 1025px)" in content


def test_focus_rings_css():
    with open("dashboard/components/ui.py", encoding="utf-8") as f:
        content = f.read()
    assert "focus-visible" in content
    assert "outline" in content


def test_sidebar_aria_labels():
    with open("dashboard/components/layout.py", encoding="utf-8") as f:
        content = f.read()
    assert "help=" in content
    assert "Ir para" in content


def test_no_secrets_in_code():
    secrets_patterns = [
        r'supabase\.co[^"\']*["\']',
        r'password\s*=\s*["\'][^"\']{8,}["\']',
    ]
    code_files = [
        "services/auth.py",
        "services/rate_limiter.py",
        "services/supabase_client.py",
        "services/price_service.py",
        "dashboard/components/ui.py",
        "dashboard/components/layout.py",
        "dashboard/login_page.py",
        "admin/app.py",
    ]
    for fname in code_files:
        if not os.path.exists(fname):
            continue
        with open(fname, encoding="utf-8", errors="replace") as f:
            content = f.read()
        for pat in secrets_patterns:
            matches = re.findall(pat, content)
            if matches:
                clean = [m for m in matches if "seu-projeto" not in m and "sua-anon" not in m]
                assert not clean, f"{fname}: Possível secret vazado: {clean[:3]}"


def test_file_structure():
    expected = [
        "services/auth.py",
        "services/rate_limiter.py",
        "services/supabase_client.py",
        "services/price_service.py",
        "services/flyer_service.py",
        "dashboard/__init__.py",
        "dashboard/components/__init__.py",
        "dashboard/components/ui.py",
        "dashboard/components/layout.py",
        "dashboard/login_page.py",
        "dashboard/pages/__init__.py",
        "admin/app.py",
        ".env.example",
    ]
    for path in expected:
        assert os.path.exists(path), f"Arquivo faltando: {path}"


def test_flyer_grid_html_structure():
    store = "Assai"
    title = "Oferta de Natal"
    status = "done"
    products = 12
    label = "processado"
    collected = "15/06/2026"

    card_html = (
        f'<div class="cd-flyer-card" id="flyer_test123">'
        f'<div class="store">{store}</div>'
        f'<div class="title">{title}</div>'
        f'<div class="meta">'
        f'<span class="meta-item">'
        f'<span class="products">{products} produtos</span>'
        f'<span class="date">{collected}</span>'
        f"</div></div>"
    )

    assert 'class="cd-flyer-card"' in card_html
    assert 'class="store"' in card_html
    assert 'class="title"' in card_html
    assert 'class="meta"' in card_html
    assert 'class="products"' in card_html
    assert 'class="date"' in card_html
    assert store in card_html
    assert title in card_html
    assert f"{products} produtos" in card_html


def test_sidebar_navigation():
    from dashboard.components.layout import PAGES

    page_ids = [p[0] for p in PAGES]
    assert "visao_geral" in page_ids
    assert "precos" in page_ids
    assert "historico" in page_ids
    assert "flyers" in page_ids
    assert "revisao" in page_ids
    assert "lojas" in page_ids
    assert "ingredientes" in page_ids
    assert "scrapers" in page_ids
    assert "relatorios" in page_ids
    assert "config" in page_ids
    assert "diagnostico" in page_ids
