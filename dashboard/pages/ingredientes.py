"""
Dashboard Page: Ingredientes
"""

import streamlit as st
import pandas as pd
import yaml

from services.dashboard_queries import get_all_ingredients, get_active_ingredients
from services.config_db import upsert_ingredient, add_alias_to_ingredient
from parsers.normalizer import normalize_price
from parsers.matcher import match_ingredient
from dashboard.components.ui import inject_css


def render_ingredientes():
    inject_css()

    st.title("Ingredientes")

    tabs = st.tabs(
        ["📋 Lista", "➕ Adicionar/Editar", "🧪 Testar Normalizer", "🔍 Testar Matcher", "➕ Sugerir Aliases"]
    )

    # Carregar YAML
    with open("config/ingredients.yaml", encoding="utf-8") as f:
        ingredients_yaml = yaml.safe_load(f).get("ingredients", [])

    with tabs[0]:  # Lista
        ingredients = get_all_ingredients(include_inactive=True)

        if not ingredients:
            st.info("Nenhum ingrediente cadastrado.")
            return

        df = pd.DataFrame(ingredients)

        col1, col2 = st.columns(2)
        with col1:
            category_filter = st.multiselect("Categoria", df["category"].dropna().unique().tolist())
        with col2:
            status_filter = st.selectbox("Status", ["Todos", "Ativos", "Inativos"])

        filtered = df.copy()
        if category_filter:
            filtered = filtered[filtered["category"].isin(category_filter)]
        if status_filter == "Ativos":
            filtered = filtered[filtered["is_active"]]
        elif status_filter == "Inativos":
            filtered = filtered[~filtered["is_active"]]

        display_cols = ["canonical_name", "category", "unit", "brands", "search_terms", "aliases", "is_active"]
        st.dataframe(
            filtered[[c for c in display_cols if c in filtered.columns]].rename(
                columns={
                    "canonical_name": "Nome Canônico",
                    "category": "Categoria",
                    "unit": "Unidade Base",
                    "brands": "Marcas",
                    "search_terms": "Termos de Busca",
                    "aliases": "Apelidos",
                    "is_active": "Ativo",
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

        ing_names = ["Novo Ingrediente"] + [i["canonical_name"] for i in ingredients_yaml]
        selected = st.selectbox("Ingrediente para editar", ing_names)

        if selected == "Novo Ingrediente":
            ing_data = {}
        else:
            ing_data = next(i for i in ingredients_yaml if i["canonical_name"] == selected)

        with st.form("ingredient_form"):
            col1, col2 = st.columns(2)
            with col1:
                canonical = st.text_input("Nome Canônico*", value=ing_data.get("canonical_name", ""))
                category = st.selectbox(
                    "Categoria",
                    [
                        "lacteos",
                        "chocolates",
                        "confeitos",
                        "pastas",
                        "secos",
                        "acucares",
                        "farinhas",
                        "essencias",
                        "outros",
                    ],
                    index=[
                        "lacteos",
                        "chocolates",
                        "confeitos",
                        "pastas",
                        "secos",
                        "acucares",
                        "farinhas",
                        "essencias",
                        "outros",
                    ].index(ing_data.get("category", "outros")),
                )
                unit = st.text_input("Unidade Base", value=ing_data.get("unit", "kg"))
                is_active = st.checkbox("Ativo", value=ing_data.get("is_active", True))

            with col2:
                brands = st.text_area("Marcas (uma por linha)", value="\n".join(ing_data.get("brands", [])))
                search_terms = st.text_area(
                    "Termos de Busca (um por linha)", value="\n".join(ing_data.get("search_terms", []))
                )
                aliases = st.text_area("Apelidos (um por linha)", value="\n".join(ing_data.get("aliases", [])))

            submitted = st.form_submit_button("💾 Salvar", type="primary")

            if submitted:
                if not canonical:
                    st.error("Nome canônico é obrigatório")
                else:
                    ing_dict = {
                        "canonical_name": canonical,
                        "category": category,
                        "unit": unit,
                        "brands": [b.strip() for b in brands.split("\n") if b.strip()],
                        "search_terms": [s.strip() for s in search_terms.split("\n") if s.strip()],
                        "aliases": [a.strip() for a in aliases.split("\n") if a.strip()],
                        "is_active": is_active,
                    }

                    # Atualizar YAML
                    updated = False
                    for i, ing in enumerate(ingredients_yaml):
                        if ing["canonical_name"] == canonical:
                            ingredients_yaml[i] = ing_dict
                            updated = True
                            break
                    if not updated:
                        ingredients_yaml.append(ing_dict)

                    with open("config/ingredients.yaml", "w", encoding="utf-8") as f:
                        yaml.dump({"ingredients": ingredients_yaml}, f, allow_unicode=True, sort_keys=False)

                    # Salvar no DB
                    upsert_ingredient(ing_dict)

                    st.success(f"Ingrediente '{canonical}' salvo!")
                    st.rerun()

    with tabs[2]:  # Testar Normalizer
        st.subheader("Testar Normalizer")
        st.markdown("Extrai quantidade, unidade e calcula R$/kg e R$/un")

        col1, col2 = st.columns(2)
        with col1:
            test_price = st.number_input("Preço Bruto", value=42.90, step=0.01)
        with col2:
            test_unit = st.text_input("Unidade Bruta", value="cx 12x395g")

        if st.button("Testar", key="test_norm"):
            result = normalize_price(test_price, test_unit)
            st.json(result)

    with tabs[3]:  # Testar Matcher
        st.subheader("Testar Matcher")
        st.markdown("Encontra o ingrediente mais próximo usando fuzzy matching (RapidFuzz)")

        test_product = st.text_input("Nome do Produto", value="Leite Condensado Moça 12un 395g")

        if st.button("Testar", key="test_match"):
            ingredients = get_active_ingredients()
            result = match_ingredient(test_product, ingredients)
            st.json(result)

    with tabs[4]:  # Sugerir Aliases
        st.subheader("Sugerir Aliases Automáticos")
        st.markdown("Gera aliases baseados no nome canônico (remoção de marca, sinônimos, etc.)")

        ingredients = get_active_ingredients()
        ing_names = [i["canonical_name"] for i in ingredients]
        selected = st.selectbox("Ingrediente", ing_names)

        if st.button("Gerar Sugestões"):
            ing = next(i for i in ingredients if i["canonical_name"] == selected)

            # Gerar sugestões
            suggestions = set()
            canonical = selected

            # 1. Remover marcas conhecidas
            for brand in ing.get("brands", []):
                if brand.lower() in canonical.lower():
                    suggestions.add(canonical.lower().replace(brand.lower(), "").strip())

            # 2. Sinônimos comuns
            synonyms = {
                "leite condensado": ["leite moça", "condensado"],
                "creme de leite": ["creme leite", "nata"],
                "chocolate em pó": ["chocolate po", "cacau em po", "achocolatado"],
                "leite em pó": ["leite po", "leite ninho"],
                "açúcar mascavo": ["mascavo", "açucar mascavo"],
                "açúcar de confeiteiro": ["acucar confeiteiro", "glasé", "glace"],
                "fermento químico em pó": ["fermento po", "fermento royal", "fermento"],
                "essência de baunilha": ["essencia baunilha", "baunilha", "vanilla"],
            }

            for key, syns in synonyms.items():
                if key in canonical.lower():
                    suggestions.update(syns)

            # 3. Variações sem acentos
            import unicodedata

            def remove_accents(text):
                return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

            suggestions.add(remove_accents(canonical).lower())

            # Filtrar sugestões que não são o próprio nome
            suggestions = [
                s
                for s in suggestions
                if s and s != canonical.lower() and s not in [a.lower() for a in ing.get("aliases", [])]
            ]

            st.markdown("**Sugestões de Aliases:**")
            for s in sorted(suggestions):
                if st.button(f"➕ Adicionar: {s}", key=f"add_alias_{s}"):
                    result = add_alias_to_ingredient(selected, s)
                    if result:
                        st.success(f"Alias '{s}' adicionado a '{selected}'")
                        st.rerun()
                    else:
                        st.error("Erro ao adicionar alias")


__all__ = ["render_ingredientes"]
