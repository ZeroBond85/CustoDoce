"""
Dashboard Page: Diagnóstico
"""

import time

import pandas as pd
import streamlit as st

from dashboard.components.ui import inject_css
from dashboard.pages.capacity_planning import render_capacity_planning
from services.dashboard_queries import (
    cached_get_all_ingredients,
    cached_get_all_stores,
    clear_all_caches,
    get_latest_prices_cached,
)
from services.supabase_client import get_supabase


def render_diagnostico():
    inject_css()

    st.title("🔬 Diagnóstico do Sistema")

    tabs = st.tabs(["01 Performance", "02 Conectividade", "03 Integridade de Dados", "04 Capacity Planning"])

    with tabs[0]:  # Performance
        st.subheader("Testes de Latência e Cache")

        if st.button("🚀 Executar Benchmarks", type="primary"):
            results = []

            # Test 1: Cold cache latest prices
            clear_all_caches()

            start = time.perf_counter()
            get_latest_prices_cached(limit=100)
            results.append({"Componente": "Preços (Cold Cache)", "Tempo (s)": round(time.perf_counter() - start, 3)})

            # Test 2: Warm cache latest prices
            start = time.perf_counter()
            get_latest_prices_cached(limit=100)
            results.append({"Componente": "Preços (Warm Cache)", "Tempo (s)": round(time.perf_counter() - start, 3)})

            # Test 3: Stores loading
            start = time.perf_counter()
            cached_get_all_stores(include_inactive=True)
            results.append({"Componente": "Lojas (DB Load)", "Tempo (s)": round(time.perf_counter() - start, 3)})

            # Test 4: Ingredients loading
            start = time.perf_counter()
            cached_get_all_ingredients(include_inactive=True)
            results.append({"Componente": "Ingredientes (DB Load)", "Tempo (s)": round(time.perf_counter() - start, 3)})

            st.table(pd.DataFrame(results))

            st.info("💡 Warm cache deve ser significativamente mais rápido que cold cache.")

    with tabs[1]:  # Conectividade
        st.subheader("Status de Conexões Externas")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Supabase**")
            if st.button("Testar Supabase", key="test_sb"):
                try:
                    client = get_supabase()
                    client.table("stores").select("id", count="exact").limit(1).execute()
                    st.success("✅ OK")
                except Exception as e:
                    st.error(f"❌ ERRO: {e}")

        with col2:
            st.markdown("**SMTP (Gmail)**")
            if st.button("Testar SMTP", key="test_smtp"):
                from services.email_service import test_smtp_connection

                ok, msg = test_smtp_connection()
                if ok:
                    st.success("✅ OK")
                else:
                    st.error(f"❌ {msg}")

        with col3:
            st.markdown("**Telegram Bot**")
            if st.button("Testar Telegram", key="test_tg"):
                from services.telegram_service import test_telegram_connection

                ok, msg = test_telegram_connection()
                if ok:
                    st.success("✅ OK")
                else:
                    st.error(f"❌ {msg}")

    with tabs[2]:  # Integridade
        st.subheader("Auditoria Rápida de Dados")

        if st.button("🔍 Validar Consistência", type="primary"):
            with st.spinner("Analisando tabelas..."):
                client = get_supabase()

                # Check for orphaned prices
                prices = client.table("prices").select("ingredient_id, store_id").limit(2000).execute()
                ingredients = client.table("ingredients").select("id").execute()
                stores = client.table("stores").select("id").execute()
                ing_ids = {i["id"] for i in ingredients.data}
                store_ids = {s["id"] for s in stores.data}

                orphans_ing = [p["ingredient_id"] for p in prices.data if p["ingredient_id"] not in ing_ids]
                orphans_store = [p["store_id"] for p in prices.data if p["store_id"] not in store_ids]

                col1, col2 = st.columns(2)
                with col1:
                    if orphans_ing:
                        st.warning(f"⚠️ {len(orphans_ing)} preços com ingredient_id órfão")
                        st.write(set(orphans_ing)[:20])
                    else:
                        st.success("✅ Nenhum ingrediente órfão")

                with col2:
                    if orphans_store:
                        st.warning(f"⚠️ {len(orphans_store)} preços com store_id órfão")
                        st.write(set(orphans_store)[:20])
                    else:
                        st.success("✅ Nenhuma loja órfã")

                # Check price distribution
                df = pd.DataFrame(prices.data)
                if not df.empty:
                    st.write("**Distribuição de preços por ingrediente (Amostra 2000):**")
                    st.bar_chart(df["ingredient_id"].value_counts())

                # Check review queue
                rq = client.table("review_queue").select("id", count="exact").limit(1).execute()
                st.info(f"📋 Fila de revisão: {rq.count if hasattr(rq, 'count') else len(rq.data)} itens")

    with tabs[3]:  # Capacity Planning
        render_capacity_planning()


__all__ = ["render_diagnostico"]
