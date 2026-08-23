"""
Dashboard Page: Ingredientes
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from dashboard.components.ui import inject_css
from parsers.matcher import match_ingredient
from services.config_db import upsert_ingredient
from services.dashboard_queries import get_active_ingredients, get_all_ingredients

INGREDIENTS_YAML = Path("config/ingredients.yaml")
INGREDIENTS_BACKUP_DIR = Path("data/ingredient_backups")


def _load_yaml() -> list[dict]:
    if not INGREDIENTS_YAML.exists():
        return []
    with INGREDIENTS_YAML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("ingredients", [])


def _backup_yaml() -> Path | None:
    if not INGREDIENTS_YAML.exists():
        return None
    INGREDIENTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = INGREDIENTS_BACKUP_DIR / f"ingredients.{suffix}.yaml"
    shutil.copy2(INGREDIENTS_YAML, backup_path)
    return backup_path


def _save_ingredient(ing_dict: dict, is_new: bool) -> bool:
    ingredients_yaml = _load_yaml()
    new_yaml = list(ingredients_yaml)
    updated = False
    for i, ing in enumerate(new_yaml):
        if ing.get("canonical_name") == ing_dict["canonical_name"]:
            new_yaml[i] = ing_dict
            updated = True
            break
    if not updated:
        new_yaml.append(ing_dict)

    backup = _backup_yaml()
    if backup is None:
        st.error("Falha ao criar backup")
        return False

    try:
        with INGREDIENTS_YAML.open("w", encoding="utf-8") as f:
            yaml.dump(
                {"ingredients": new_yaml},
                f,
                allow_unicode=True,
                sort_keys=False,
            )
    except OSError as e:
        st.error(f"Falha ao escrever YAML: {e}")
        return False

    try:
        upsert_ingredient(ing_dict)
    except Exception as e:
        st.error(f"Falha ao sincronizar com DB: {e}")
        return False

    st.success(f"Salvo com backup em `{backup.name}`")
    return True


def _coerce_editor_df(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    """Normaliza dtypes para o st.data_editor (evita StreamlitAPIException).

    Colunas JSONB chegam do Supabase como listas Python (object dtype), que
    quebram o _check_type_compatibilities do TextColumn. Converte para texto
    multi-linha; garante bool em Ativo e string nos demais.
    """
    out = df.rename(columns=col_map).copy()
    for col in ("Marcas", "Busca", "Apelidos"):
        if col in out.columns:
            out[col] = out[col].apply(
                lambda v: "\n".join(str(i) for i in v) if isinstance(v, (list, tuple)) else ("" if v is None else str(v))
            )
    if "Ativo" in out.columns:
        out["Ativo"] = out["Ativo"].fillna(False).astype(bool)
    for col in ("Categoria", "Unidade", "Nome Canônico"):
        if col in out.columns:
            out[col] = out[col].fillna("").astype(str)
    return out


def render_ingredientes():
    inject_css()
    st.title("🥄 Ingredientes")

    st.caption("Fonte: `config/ingredients.yaml` → sincronizado com DB (scrapers usam DB).")

    tabs = st.tabs(["📋 Ingredientes", "➕ Novo", "🔍 Testar Matcher"])

    # ==================== ABA 1: LISTA COM EDIÇÃO INLINE ====================
    with tabs[0]:
        ingredients = get_all_ingredients(include_inactive=True)
        if not ingredients:
            st.info("Nenhum ingrediente cadastrado.")
            return

        df = pd.DataFrame(ingredients)

        col1, col2 = st.columns([3, 1])
        with col1:
            categories = sorted(df["category"].dropna().unique().tolist())
            category_filter = st.multiselect("Categoria", categories, default=categories)
        with col2:
            status_filter = st.selectbox("Status", ["Todos", "Ativos", "Inativos"])

        filtered = df.copy()
        if category_filter:
            filtered = filtered[filtered["category"].isin(category_filter)]
        if status_filter == "Ativos":
            filtered = filtered[filtered["active"]]
        elif status_filter == "Inativos":
            filtered = filtered[~filtered["active"]]

        # Editor inline simples
        display_cols = ["canonical_name", "category", "unit_target", "brands", "search_terms", "aliases", "active"]
        col_map = {
            "canonical_name": "Nome Canônico",
            "category": "Categoria",
            "unit_target": "Unidade",
            "brands": "Marcas",
            "search_terms": "Busca",
            "aliases": "Apelidos",
            "active": "Ativo",
        }
        available = [c for c in display_cols if c in filtered.columns]

        edited = st.data_editor(
            _coerce_editor_df(filtered[available], col_map),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ativo": st.column_config.CheckboxColumn("Ativo"),
                "Marcas": st.column_config.TextColumn("Marcas", help="Uma por linha"),
                "Busca": st.column_config.TextColumn("Termos de Busca", help="Um por linha"),
                "Apelidos": st.column_config.TextColumn("Apelidos", help="Um por linha"),
            },
            disabled=["Nome Canônico"],
            key="ing_editor",
        )

        if st.button("💾 Salvar Alterações", type="primary", width="stretch"):
            for _, row in edited.iterrows():
                canonical = row["Nome Canônico"]

                def parse_free(text):
                    if not text:
                        return []
                    return [x.strip() for x in str(text).replace(";", ",").replace("\n", ",").split(",") if x.strip()]

                ing_dict = {
                    "canonical_name": canonical,
                    "category": row["Categoria"],
                    "unit_target": row["Unidade"],
                    "brands": parse_free(row["Marcas"]),
                    "search_terms": parse_free(row["Busca"]),
                    "aliases": parse_free(row["Apelidos"]),
                    "active": row["Ativo"],
                }

                if not _save_ingredient(ing_dict, is_new=False):
                    return

            st.rerun()

        st.caption(f"Total: {len(filtered)} ingredientes")

    # ==================== ABA 2: NOVO INGREDIENTE ====================
    with tabs[1]:
        st.subheader("Adicionar Novo Ingrediente")

        CANONICAL_CATEGORIES = [
            "lacteos", "chocolates", "confeitos", "pastas",
            "secos", "acucares", "farinhas", "essencias", "outros",
        ]

        with st.form("new_ingredient", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                canonical = st.text_input("Nome Canônico*", placeholder="Ex: Leite Condensado Integral")
                category = st.selectbox("Categoria", CANONICAL_CATEGORIES)
                unit = st.text_input("Unidade Base", value="kg")
                active = st.checkbox("Ativo", value=True)
            with col2:
                st.caption("Cole à vontade — backend normaliza (remove duplicatas, limpa espaços)")
                brands = st.text_area("Marcas", placeholder="Nestlé, Piracanjuba")
                search_terms = st.text_area("Termos de Busca", placeholder="leite condensado, condensado, moca")
                aliases = st.text_area("Apelidos", placeholder="Leite Moça 12x395g; LC Integral 395g")

            submitted = st.form_submit_button("💾 Criar", type="primary", width="stretch")

            if submitted:
                if not canonical:
                    st.error("Nome canônico é obrigatório")
                elif any(i.get("canonical_name") == canonical for i in _load_yaml()):
                    st.error("Já existe ingrediente com este nome")
                else:
                    def parse_free(text):
                        """Aceita vírgula, ponto-e-vírgula, nova linha, espaços extras."""
                        if not text:
                            return []
                        return [x.strip() for x in text.replace(";", ",").replace("\n", ",").split(",") if x.strip()]

                    ing_dict = {
                        "canonical_name": canonical.strip(),
                        "category": category,
                        "unit_target": unit.strip(),
                        "brands": parse_free(brands),
                        "search_terms": parse_free(search_terms),
                        "aliases": parse_free(aliases),
                        "active": active,
                    }

                    if _save_ingredient(ing_dict, is_new=True):
                        st.balloons()
                        st.rerun()

    # ==================== ABA 3: TESTAR MATCHER ====================
    with tabs[2]:
        st.subheader("Testar Matcher")
        st.caption("Como o scraper vê o produto — fuzzy + exact + penalidade de cobertura")

        test_product = st.text_input(
            "Nome do Produto (como vem do site/PDF)",
            value="Leite Condensado Moça 12un 395g",
            help="Cole aqui o título bruto do produto",
        )

        if st.button("🔍 Testar", type="primary", width="stretch"):
            if not test_product.strip():
                st.warning("Digite um nome de produto")
            else:
                with st.spinner("Comparando..."):
                    ingredients = get_active_ingredients()
                    if not ingredients:
                        st.error("Nenhum ingrediente ativo cadastrado")
                    else:
                        result = match_ingredient(test_product, ingredients)
                        st.divider()
                        if result[0]:
                            ing, score, mtype = result
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Match", ing["canonical_name"])
                            col2.metric("Score", f"{score:.1f}%")
                            col3.metric("Tipo", mtype)
                            st.json({
                                "canonical": ing["canonical_name"],
                                "category": ing["category"],
                                "brands": ing.get("brands", []),
                                "matched_via": mtype,
                                "confidence": round(score / 100, 2),
                            })
                        else:
                            st.error("❌ Nenhum match (score < 55)")
                            st.info("Vai para review_queue ou rejeição explícita")


__all__ = ["render_ingredientes"]
