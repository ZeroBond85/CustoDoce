"""Regressão: crash do data_editor na aba Ingredientes.

Causa raiz (produção, 2026-08-21): colunas JSONB (brands, search_terms, aliases)
chegam do Supabase como listas Python → object dtype → _check_type_compatibilities
lança StreamlitAPIException contra TextColumn. Fix: _coerce_editor_df() normaliza
listas para texto multi-linha e garante bool/str nos demais campos.
"""

import numpy as np
import pandas as pd

from dashboard.pages.ingredientes import _coerce_editor_df

COL_MAP = {
    "canonical_name": "Nome Canônico",
    "category": "Categoria",
    "unit_target": "Unidade",
    "brands": "Marcas",
    "search_terms": "Busca",
    "aliases": "Apelidos",
    "active": "Ativo",
}


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "canonical_name": "Leite Condensado Integral",
                "category": "lacteos",
                "unit_target": "kg",
                "brands": ["Moça", "Piracanjuba"],
                "search_terms": ["leite condensado"],
                "aliases": ["Leite Moça"],
                "active": True,
            },
            {
                "canonical_name": "Manteiga",
                "category": "lacteos",
                "unit_target": "kg",
                "brands": None,
                "search_terms": ["manteiga"],
                "aliases": None,
                "active": None,
            },
        ]
    )


def test_listas_viram_texto_multilinha():
    out = _coerce_editor_df(_sample_df(), COL_MAP)
    assert out["Marcas"].iloc[0] == "Moça\nPiracanjuba"
    assert out["Busca"].iloc[0] == "leite condensado"
    assert isinstance(out["Marcas"].iloc[0], str)


def test_nulos_de_lista_viram_string_vazia():
    out = _coerce_editor_df(_sample_df(), COL_MAP)
    assert out["Marcas"].iloc[1] == ""
    assert out["Apelidos"].iloc[1] == ""


def test_ativo_bool_sem_null():
    out = _coerce_editor_df(_sample_df(), COL_MAP)
    assert out["Ativo"].dtype == bool
    assert bool(out["Ativo"].iloc[1]) is False


def test_colunas_texto_sem_none():
    out = _coerce_editor_df(_sample_df(), COL_MAP)
    assert out["Nome Canônico"].iloc[0] == "Leite Condensado Integral"
    assert out["Categoria"].iloc[0] == "lacteos"


def test_numpy_arrays_tambem_sao_convertidos():
    df = pd.DataFrame([{"brands": np.array(["Harald"]), "search_terms": [], "aliases": []}])
    out = _coerce_editor_df(df, {"brands": "Marcas", "search_terms": "Busca", "aliases": "Apelidos"})
    assert isinstance(out["Marcas"].iloc[0], str) or out["Marcas"].iloc[0] == ""
