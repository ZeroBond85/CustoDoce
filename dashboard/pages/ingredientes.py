"""
Dashboard Page: Ingredientes
"""

import shutil
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from dashboard.components.ui import inject_css
from parsers.matcher import match_ingredient
from parsers.normalizer import normalize_price
from services.config_db import upsert_ingredient, add_alias_to_ingredient
from services.dashboard_queries import get_all_ingredients, get_active_ingredients

INGREDIENTS_YAML = Path("config/ingredients.yaml")
INGREDIENTS_BACKUP_DIR = Path("data/ingredient_backups")
ALIAS_SYNONYMS = {
    "leite condensado": ["leite moça", "condensado"],
    "creme de leite": ["creme leite", "nata"],
    "chocolate em pó": ["chocolate po", "cacau em po", "achocolatado"],
    "leite em pó": ["leite po", "leite ninho"],
    "açúcar mascavo": ["mascavo", "açucar mascavo"],
    "açúcar de confeiteiro": ["acucar confeiteiro", "glasé", "glace"],
    "fermento químico em pó": ["fermento po", "fermento royal", "fermento"],
    "essência de baunilha": ["essencia baunilha", "baunilha", "vanilla"],
}


def _load_yaml() -> list[dict]:
    if not INGREDIENTS_YAML.exists():
        return []
    with INGREDIENTS_YAML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("ingredients", [])


def _backup_yaml() -> Path | None:
    """Copy current YAML to timestamped backup file. Returns backup path or None."""
    if not INGREDIENTS_YAML.exists():
        return None
    INGREDIENTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = INGREDIENTS_BACKUP_DIR / f"ingredients.{suffix}.yaml"
    shutil.copy2(INGREDIENTS_YAML, backup_path)
    return backup_path


@st.dialog("Confirmar sobrescrita do YAML")
def _confirm_yaml_save_dialog(
    ingredients_yaml: list[dict],
    ing_dict: dict,
    canonical_name: str,
    is_new: bool,
):
    new_yaml = list(ingredients_yaml)
    updated = False
    for i, ing in enumerate(new_yaml):
        if ing.get("canonical_name") == canonical_name:
            new_yaml[i] = ing_dict
            updated = True
            break
    if not updated:
        new_yaml.append(ing_dict)

    action = "Adicionar" if is_new else "Atualizar"
    st.markdown(
        f"Você está prestes a **{action.lower()}** o ingrediente `{canonical_name}` "
        "no arquivo `config/ingredients.yaml`. Esta ação afeta os scrapers imediatamente."
    )

    with st.expander("🔍 Ver YAML resultante", expanded=False):
        st.code(yaml.dump({"ingredients": new_yaml}, allow_unicode=True, sort_keys=False), language="yaml")

    st.markdown("**Backups** são criados automaticamente em `data/ingredient_backups/` antes de salvar.")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("❌ Cancelar", key="cancel_yaml_save", width="stretch"):
            st.rerun()
    with col2:
        if st.button(
            "💾 Salvar (com backup)",
            key="confirm_yaml_save",
            type="primary",
            width="stretch",
        ):
            try:
                backup = _backup_yaml()
            except OSError as e:
                st.error(f"Falha ao criar backup: {e}")
                return
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
                return
            try:
                upsert_ingredient(ing_dict)
            except Exception as e:
                st.error(f"Falha ao sincronizar com o DB: {e}")
                return
            if backup is not None:
                st.success(f"Backup criado em `{backup}`")
            st.success(f"Ingrediente '{canonical_name}' salvo!")
            st.rerun()


def _suggest_aliases(canonical: str, brands: list[str], existing: list[str]) -> list[str]:
    import unicodedata

    def remove_accents(text):
        return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

    suggestions: set[str] = set()
    canon_lower = canonical.lower()

    for brand in brands or []:
        if brand.lower() in canon_lower:
            cleaned = canon_lower.replace(brand.lower(), "").strip()
            if cleaned:
                suggestions.add(cleaned)

    for key, syns in ALIAS_SYNONYMS.items():
        if key in canon_lower:
            suggestions.update(syns)

    suggestions.add(remove_accents(canonical).lower())

    existing_lower = {a.lower() for a in existing}
    return sorted({s for s in suggestions if s and s != canon_lower and s not in existing_lower})


def render_ingredientes():
    inject_css()

    st.title("Ingredientes")

    st.info("💡 Os ingredientes são salvos no YAML (fonte para scrapers) e sincronizados com o DB automaticamente.")

    tabs = st.tabs(
        ["📋 Lista", "➕ Adicionar/Editar", "🧪 Testar Normalizer", "🔍 Testar Matcher", "➕ Sugerir Aliases"]
    )

    ingredients_yaml = _load_yaml()

    with tabs[0]:  # Lista
        ingredients = get_all_ingredients(include_inactive=True)

        if not ingredients:
            st.info("Nenhum ingrediente cadastrado.")
            return

        df = pd.DataFrame(ingredients)

        col1, col2 = st.columns(2)
        with col1:
            categories = sorted(df["category"].dropna().unique().tolist())
            category_filter = st.multiselect("Categoria", categories)
        with col2:
            status_filter = st.selectbox("Status", ["Todos", "Ativos", "Inativos"])

        filtered = df.copy()
        if category_filter:
            filtered = filtered[filtered["category"].isin(category_filter)]
        if status_filter == "Ativos":
            filtered = filtered[filtered["active"]]
        elif status_filter == "Inativos":
            filtered = filtered[~filtered["active"]]

        display_cols = ["canonical_name", "category", "unit_target", "brands", "search_terms", "aliases", "active"]
        if not filtered.empty:
            st.dataframe(
                filtered[[c for c in display_cols if c in filtered.columns]].rename(
                    columns={
                        "canonical_name": "Nome Canônico",
                        "category": "Categoria",
                        "unit_target": "Unidade Base",
                        "brands": "Marcas",
                        "search_terms": "Termos de Busca",
                        "aliases": "Apelidos",
                        "active": "Ativo",
                    }
                ),
                use_container_width=True,
                column_config={
                    "Ativo": st.column_config.CheckboxColumn("Ativo"),
                },
            )

        st.info(f"Total: {len(filtered)} ingredientes")

    with tabs[1]:  # Adicionar/Editar
        st.subheader("Adicionar / Editar Ingrediente")

        ing_names = ["Novo Ingrediente"] + [i.get("canonical_name", "") for i in ingredients_yaml]
        selected = st.selectbox("Ingrediente para editar", ing_names)

        if selected == "Novo Ingrediente":
            ing_data: dict = {}
            is_new = True
        else:
            ing_data = next(
                (i for i in ingredients_yaml if i.get("canonical_name") == selected),
                {},
            )
            is_new = False

        CANONICAL_CATEGORIES = [
            "lacteos",
            "chocolates",
            "confeitos",
            "pastas",
            "secos",
            "acucares",
            "farinhas",
            "essencias",
            "outros",
        ]

        with st.form("ingredient_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                canonical = st.text_input("Nome Canônico*", value=ing_data.get("canonical_name", ""))
                try:
                    default_cat = ing_data.get("category", "outros")
                    cat_index = (
                        CANONICAL_CATEGORIES.index(default_cat)
                        if default_cat in CANONICAL_CATEGORIES
                        else CANONICAL_CATEGORIES.index("outros")
                    )
                except ValueError, TypeError:
                    cat_index = CANONICAL_CATEGORIES.index("outros")
                category = st.selectbox("Categoria", CANONICAL_CATEGORIES, index=cat_index)
                unit = st.text_input("Unidade Base", value=ing_data.get("unit_target", "kg"))
                active = st.checkbox("Ativo", value=ing_data.get("active", True))

            with col2:
                brands_lines = "\n".join(ing_data.get("brands", []) or [])
                search_lines = "\n".join(ing_data.get("search_terms", []) or [])
                aliases_lines = "\n".join(ing_data.get("aliases", []) or [])
                brands = st.text_area("Marcas (uma por linha)", value=brands_lines)
                search_terms = st.text_area("Termos de Busca (um por linha)", value=search_lines)
                aliases = st.text_area("Apelidos (um por linha)", value=aliases_lines)

            submitted = st.form_submit_button("💾 Salvar", type="primary")

            if submitted:
                if not canonical:
                    st.error("Nome canônico é obrigatório")
                else:
                    ing_dict = {
                        "canonical_name": canonical,
                        "category": category,
                        "unit_target": unit,
                        "brands": [b.strip() for b in brands.split("\n") if b.strip()],
                        "search_terms": [s.strip() for s in search_terms.split("\n") if s.strip()],
                        "aliases": [a.strip() for a in aliases.split("\n") if a.strip()],
                        "active": active,
                    }
                    is_actually_new = is_new or not any(i.get("canonical_name") == canonical for i in ingredients_yaml)
                    _confirm_yaml_save_dialog(
                        ingredients_yaml=ingredients_yaml,
                        ing_dict=ing_dict,
                        canonical_name=canonical,
                        is_new=is_actually_new,
                    )

    with tabs[2]:  # Testar Normalizer
        st.subheader("Testar Normalizer")
        st.markdown("Extrai quantidade, unidade e calcula R$/kg e R$/un")

        col1, col2 = st.columns(2)
        with col1:
            test_price = st.number_input("Preço Bruto", value=42.90, step=0.01)
        with col2:
            test_unit = st.text_input("Unidade Bruta", value="cx 12x395g")

        if st.button("Testar", key="test_norm"):
            with st.spinner("Normalizando..."):
                result = normalize_price(test_price, test_unit)
            st.json(result)

    with tabs[3]:  # Testar Matcher
        st.subheader("Testar Matcher")
        st.markdown("Encontra o ingrediente mais próximo usando fuzzy matching (RapidFuzz)")

        test_product = st.text_input("Nome do Produto", value="Leite Condensado Moça 12un 395g")

        if st.button("Testar", key="test_match"):
            with st.spinner("Comparando..."):
                ingredients = get_active_ingredients()
                if ingredients:
                    result = match_ingredient(test_product, ingredients)
                    st.json(result)
                else:
                    st.warning("Nenhum ingrediente ativo. Cadastre um na aba 'Adicionar/Editar'.")

    with tabs[4]:  # Sugerir Aliases
        st.subheader("Sugerir Aliases Automáticos")
        st.markdown("Gera aliases baseados no nome canônico (remoção de marca, sinônimos, etc.)")

        ingredients = get_active_ingredients()
        if not ingredients:
            st.warning("Nenhum ingrediente ativo para sugerir aliases.")
            return

        ing_names = [i.get("canonical_name", "") for i in ingredients]
        selected = st.selectbox("Ingrediente", ing_names)

        if st.button("Gerar Sugestões"):
            ing = next((i for i in ingredients if i.get("canonical_name") == selected), {})
            existing = ing.get("aliases", []) or []
            suggestions = _suggest_aliases(
                canonical=selected,
                brands=ing.get("brands", []) or [],
                existing=existing,
            )

            if not suggestions:
                st.info("Nenhuma sugestão nova encontrada para este ingrediente.")
                return

            st.markdown("**Sugestões de Aliases:**")
            for s in suggestions:
                if st.button(f"➕ Adicionar: {s}", key=f"add_alias_{s}"):
                    try:
                        result = add_alias_to_ingredient(selected, s)
                    except Exception as e:
                        st.error(f"Erro ao adicionar alias: {e}")
                        return
                    if result:
                        st.success(f"Alias '{s}' adicionado a '{selected}'")
                        st.rerun()
                    else:
                        st.error("Erro ao adicionar alias")


__all__ = ["render_ingredientes"]
