"""
Dashboard Page: Calculadora de Receitas
"""

import streamlit as st
import pandas as pd

from services.dashboard_queries import get_cheapest_prices_cached, get_active_ingredients
from services.price_service import upsert_recipe, upsert_recipe_item
from dashboard.components.ui import inject_css


def render_calculadora():
    inject_css()

    st.title("🧮 Calculadora de Receitas")

    tabs = st.tabs(["📝 Modo Simples", "🔧 Modo Completo", "📚 Receitas Salvas"])

    with tabs[0]:  # Modo Simples
        st.subheader("Cálculo Rápido de Custo")

        ingredients = get_active_ingredients()
        ing_names = [i["canonical_name"] for i in ingredients]

        col1, col2 = st.columns(2)
        with col1:
            recipe_name = st.text_input("Nome da Receita", placeholder="Ex: Brigadeiro Tradicional")
            yield_qty = st.number_input("Rendimento (unidades)", value=30, min_value=1)
        with col2:
            overhead_pct = st.number_input("Custo Fixo (%)", value=15.0, step=1.0, help="Embalagem, gás, energia")
            profit_pct = st.number_input("Margem de Lucro (%)", value=30.0, step=1.0)

        st.divider()
        st.markdown("### Ingredientes")

        # Inicializar session_state para ingredientes
        if "simple_ingredients" not in st.session_state:
            st.session_state.simple_ingredients = []

        with st.form("add_ingredient_simple"):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                sel_ing = st.selectbox("Ingrediente", ing_names)
            with col2:
                qty = st.number_input("Qtd (g/ml)", value=100.0, step=10.0, min_value=0.1)
            with col3:
                if st.form_submit_button("➕ Adicionar"):
                    st.session_state.simple_ingredients.append({"ingredient": sel_ing, "quantity_g": qty})
                    st.rerun()

        if st.session_state.simple_ingredients:
            df = pd.DataFrame(st.session_state.simple_ingredients)

            # Auto-fill com menor preço
            for idx, row in df.iterrows():
                cheapest = get_cheapest_prices_cached(row["ingredient"], top_n=1)
                if cheapest:
                    df.at[idx, "price_per_kg"] = cheapest[0].get("price_per_kg", 0)
                    df.at[idx, "store"] = cheapest[0].get("store_name", "N/A")
                    df.at[idx, "cost"] = (row["quantity_g"] / 1000) * cheapest[0].get("price_per_kg", 0)
                else:
                    df.at[idx, "price_per_kg"] = 0
                    df.at[idx, "store"] = "Sem dados"
                    df.at[idx, "cost"] = 0

            st.dataframe(df[["ingredient", "quantity_g", "price_per_kg", "store", "cost"]], use_container_width=True)

            total_cost = df["cost"].sum()
            cost_per_unit = (total_cost * (1 + overhead_pct / 100) * (1 + profit_pct / 100)) / yield_qty

            st.metric("Custo Total Ingredientes", f"R$ {total_cost:.2f}")
            st.metric("Custo + Fixo", f"R$ {total_cost * (1 + overhead_pct / 100):.2f}")
            st.metric(
                "Preço de Venda (Total)", f"R$ {total_cost * (1 + overhead_pct / 100) * (1 + profit_pct / 100):.2f}"
            )
            st.metric("Preço por Unidade", f"R$ {cost_per_unit:.2f}")

            if st.button("💾 Salvar Receita", type="primary"):
                if recipe_name:
                    recipe_id = upsert_recipe(
                        {
                            "name": recipe_name,
                            "yield_qty": yield_qty,
                            "overhead_pct": overhead_pct,
                            "profit_pct": profit_pct,
                        }
                    )
                    if recipe_id:
                        for ing in st.session_state.simple_ingredients:
                            cheapest = get_cheapest_prices_cached(ing["ingredient"], top_n=1)
                            if cheapest:
                                upsert_recipe_item(
                                    {
                                        "recipe_id": recipe_id,
                                        "ingredient_id": ing["ingredient"],
                                        "quantity_g": ing["quantity_g"],
                                        "selected_store": cheapest[0].get("store_name"),
                                        "price_per_kg": cheapest[0].get("price_per_kg"),
                                    }
                                )
                        st.success(f"Receita '{recipe_name}' salva!")
                        st.session_state.simple_ingredients = []
                        st.rerun()
                else:
                    st.error("Digite um nome para a receita")

    with tabs[1]:  # Modo Completo
        st.subheader("Cálculo Detalhado com Top 3 Lojas")

        ingredients = get_active_ingredients()
        ing_names = [i["canonical_name"] for i in ingredients]

        recipe_name = st.text_input("Nome da Receita", key="full_recipe_name")
        yield_qty = st.number_input("Rendimento", value=30, min_value=1, key="full_yield")
        overhead_pct = st.number_input("Custo Fixo (%)", value=15.0, key="full_overhead")
        profit_pct = st.number_input("Margem (%)", value=30.0, key="full_profit")

        if "full_ingredients" not in st.session_state:
            st.session_state.full_ingredients = []

        with st.form("add_ingredient_full"):
            col1, col2 = st.columns([3, 1])
            with col1:
                sel_ing = st.selectbox("Ingrediente", ing_names, key="full_ing_select")
            with col2:
                qty = st.number_input("Qtd (g)", value=100.0, step=10.0, key="full_qty")

            if st.form_submit_button("➕ Adicionar"):
                st.session_state.full_ingredients.append({"ingredient": sel_ing, "quantity_g": qty})
                st.rerun()

        if st.session_state.full_ingredients:
            df = pd.DataFrame(st.session_state.full_ingredients)

            # Buscar top 3 preços para cada
            results = []
            for _, row in df.iterrows():
                cheapest = get_cheapest_prices_cached(row["ingredient"], top_n=3)
                for i, c in enumerate(cheapest):
                    results.append(
                        {
                            "Ingrediente": row["ingredient"],
                            "Qtd (g)": row["quantity_g"],
                            f"Opção {i + 1} Loja": c.get("store_name"),
                            f"Opção {i + 1} R$/kg": c.get("price_per_kg"),
                            f"Opção {i + 1} Custo": (row["quantity_g"] / 1000) * c.get("price_per_kg", 0),
                        }
                    )

            if results:
                res_df = pd.DataFrame(results)
                st.dataframe(res_df, use_container_width=True)

                # Cenários
                st.subheader("📊 Cenários de Preço")

                scenarios = [
                    ("Melhor Caso (Menor preço)", lambda c: c[0]["price_per_kg"] if c else 0),
                    ("Médio (Média top 3)", lambda c: sum(x["price_per_kg"] for x in c) / len(c) if c else 0),
                    ("Pior Caso (Maior preço top 3)", lambda c: c[-1]["price_per_kg"] if c else 0),
                ]

                for label, calc_fn in scenarios:
                    total = 0
                    for _, row in df.iterrows():
                        cheapest = get_cheapest_prices_cached(row["ingredient"], top_n=3)
                        ppk = calc_fn(cheapest)
                        total += (row["quantity_g"] / 1000) * ppk

                    with_fixed = total * (1 + overhead_pct / 100)
                    final = with_fixed * (1 + profit_pct / 100)
                    per_unit = final / yield_qty

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(label, f"R$ {total:.2f}")
                    with col2:
                        st.metric("+ Fixo", f"R$ {with_fixed:.2f}")
                    with col3:
                        st.metric("+ Lucro", f"R$ {final:.2f}")
                    with col4:
                        st.metric("Por Unid.", f"R$ {per_unit:.2f}")

                if st.button("💾 Salvar Receita Completa", type="primary"):
                    if recipe_name:
                        recipe_id = upsert_recipe(
                            {
                                "name": recipe_name,
                                "yield_qty": yield_qty,
                                "overhead_pct": overhead_pct,
                                "profit_pct": profit_pct,
                            }
                        )
                        if recipe_id:
                            for ing in st.session_state.full_ingredients:
                                cheapest = get_cheapest_prices_cached(ing["ingredient"], top_n=1)
                                if cheapest:
                                    upsert_recipe_item(
                                        {
                                            "recipe_id": recipe_id,
                                            "ingredient_id": ing["ingredient"],
                                            "quantity_g": ing["quantity_g"],
                                            "selected_store": cheapest[0].get("store_name"),
                                            "price_per_kg": cheapest[0].get("price_per_kg"),
                                        }
                                    )
                            st.success(f"Receita '{recipe_name}' salva!")
                            st.session_state.full_ingredients = []
                            st.rerun()
                    else:
                        st.error("Nome da receita obrigatório")

    with tabs[2]:  # Receitas Salvas
        st.subheader("Receitas Cadastradas")

        from services.supabase_client import get_supabase

        client = get_supabase()
        recipes = client.table("recipes").select("*").execute()

        if recipes.data:
            df = pd.DataFrame(recipes.data)
            st.dataframe(
                df[["name", "yield_qty", "overhead_pct", "profit_pct", "created_at"]], use_container_width=True
            )

            # Detalhar receita
            sel_recipe = st.selectbox("Ver detalhes", [""] + df["name"].tolist())
            if sel_recipe:
                recipe_id = df[df["name"] == sel_recipe].iloc[0]["id"]
                items = client.table("recipe_items").select("*").eq("recipe_id", recipe_id).execute()
                if items.data:
                    st.dataframe(pd.DataFrame(items.data), use_container_width=True)
        else:
            st.info("Nenhuma receita salva ainda.")


__all__ = ["render_calculadora"]
