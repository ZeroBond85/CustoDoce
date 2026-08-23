"""Regressão: crash da Calculadora (StreamlitAPIException selectbox index).

Causa raiz (produção, 2026-08-21): st.selectbox(key="calc_tab") guarda o LABEL
selecionado (string) no session_state; na rerun, o valor era lido e passado como
index= → StreamlitAPIException. E as comparações tab_index == 0/1/2 com label
string deixavam a página em branco.

Fix: _resolve_tab_index() normaliza label/índice para índice válido, e o índice
real é derivado do label retornado pelo widget.
"""

from dashboard.pages.calculadora import _resolve_tab_index


def test_resolve_index_vazio_retorna_zero():
    assert _resolve_tab_index(["A", "B", "C"]) == 0


def test_resolve_index_int_valido(monkeypatch):
    import dashboard.pages.calculadora as calc

    monkeypatch.setattr(calc.st, "session_state", {"calc_tab": 2})
    assert calc._resolve_tab_index(["A", "B", "C"]) == 2


def test_resolve_index_label_string(monkeypatch):
    import dashboard.pages.calculadora as calc

    monkeypatch.setattr(calc.st, "session_state", {"calc_tab": "B"})
    assert calc._resolve_tab_index(["A", "B", "C"]) == 1


def test_resolve_index_label_desconhecido_cai_em_zero(monkeypatch):
    import dashboard.pages.calculadora as calc

    monkeypatch.setattr(calc.st, "session_state", {"calc_tab": "Inexistente"})
    assert calc._resolve_tab_index(["A", "B", "C"]) == 0


def test_resolve_index_int_fora_do_range_cai_em_zero(monkeypatch):
    import dashboard.pages.calculadora as calc

    monkeypatch.setattr(calc.st, "session_state", {"calc_tab": 99})
    assert calc._resolve_tab_index(["A", "B", "C"]) == 0


def test_resolve_index_int_negativo_cai_em_zero(monkeypatch):
    import dashboard.pages.calculadora as calc

    monkeypatch.setattr(calc.st, "session_state", {"calc_tab": -1})
    assert calc._resolve_tab_index(["A", "B", "C"]) == 0
