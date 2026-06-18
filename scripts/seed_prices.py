#!/usr/bin/env python3
"""
CustoDoce — Seed de Dados Sintéticos

Gera ~90 dias de dados históricos realistas para testar:
- Ranking Histórico (preço por loja ao longo do tempo)
- Fontes & Ofertas (drill-down de flyers)
- Insights (heatmap, tendências, outliers)
- Testes de performance (queries com 10K+ registros)

Uso:
    python scripts/seed_prices.py --dry-run    # Mostra o que seria inserido
    python scripts/seed_prices.py --execute    # Insere no Supabase
    python scripts/seed_prices.py --json FILE  # Exporta para JSON
"""

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

random.seed(42)  # deterministic for reproducibility

# ─── Ingredientes e seus preços base realistas ─────────────────
# (preco_kg_base, unidade_tipica, variacao_diaria_pct)
INGREDIENT_BASES = {
    "Leite Condensado Integral": {"base_kg": 14.50, "unit": "cx 12x395g", "volatility": 0.08},
    "Creme de Leite 20% Gordura": {"base_kg": 18.00, "unit": "cx 12x200g", "volatility": 0.10},
    "Chocolate em Pó 50% Cacau": {"base_kg": 42.00, "unit": "1kg", "volatility": 0.06},
    "Leite Ninho Integral": {"base_kg": 38.00, "unit": "800g", "volatility": 0.07},
    "Granulado Melken Ao Leite": {"base_kg": 28.00, "unit": "1kg", "volatility": 0.09},
    "Granulado Melken Branco": {"base_kg": 28.00, "unit": "1kg", "volatility": 0.09},
    "Granulado Melken Meio Amargo": {"base_kg": 30.00, "unit": "1kg", "volatility": 0.09},
    "Nutella": {"base_kg": 65.00, "unit": "3kg", "volatility": 0.05},
    "Coloretti Granulado Colorido": {"base_kg": 24.00, "unit": "1kg", "volatility": 0.10},
    "Coco Ralado Grosso sem Açúcar": {"base_kg": 22.00, "unit": "1kg", "volatility": 0.12},
    "Chocolate Nobre Blend Harald": {"base_kg": 52.00, "unit": "2.1kg", "volatility": 0.06},
}

# Loja → fator de markup/markdown sobre o preço base
STORE_FACTORS = {
    "Assaí Atacadista": 0.92,
    "Atacadão": 0.90,
    "Spani Atacadista": 0.95,
    "Mercadão Atacadista": 0.93,
    "Tenda Atacado": 0.91,
    "Roldão Atacadista": 0.94,
    "Sam's Club": 1.05,
    "Max Atacadista": 0.96,
    "Makro Atacadista": 0.97,
    "Rizzo Supermercados": 1.10,
    "Amendolate": 1.20,
    "Cacau Center": 1.25,
    "Confeitos & Cia": 1.15,
    "Loja Santo Antônio": 1.12,
    "Padaria Padeirão": 1.18,
    "Central Flavor": 1.22,
    "BarraDoce": 1.28,
    "Casa dos Confeiteiros": 1.10,
    "Carrefour": 1.02,
    "Dia": 0.95,
}

PRODUCT_NAMES = {
    "Leite Condensado Integral": [
        "Leite Condensado Moça 12un", "Leite Condensado Piracanjuba 12x395g",
        "Leite Condensado Itambé 12un", "LC Integral 12un",
    ],
    "Creme de Leite 20% Gordura": [
        "Creme de Leite Nestlé 12x200g", "Creme de Leite Piracanjuba 12x200g",
        "CL Nestlé 12un", "Creme de Leite 20% 1L",
    ],
    "Chocolate em Pó 50% Cacau": [
        "Chocolate em Pó Melken 1kg", "Chocolate em Pó Sicao 1kg",
        "Cacau em Pó 50% 1kg", "Chocolate em Pó 500g",
    ],
    "Leite Ninho Integral": [
        "Leite Ninho Integral 800g", "Leite Ninho Integral 1kg",
        "Ninho Integral 800g", "Leite Ninho 380g",
    ],
    "Granulado Melken Ao Leite": [
        "Granulado Melken Ao Leite 1kg", "Granulado Ao Leite 1kg",
        "Granulado Melken 1kg Ao Leite",
    ],
    "Granulado Melken Branco": [
        "Granulado Melken Branco 1kg", "Granulado Branco 1kg",
        "Granulado Melken 1kg Branco",
    ],
    "Granulado Melken Meio Amargo": [
        "Granulado Melken Meio Amargo 1kg", "Granulado Meio Amargo 1kg",
        "Granulado Melken 1kg Meio Amargo",
    ],
    "Nutella": [
        "Nutella 3kg Food Service", "Nutella 650g",
        "Nutella 750g", "Nutella Pote 3kg",
    ],
    "Coloretti Granulado Colorido": [
        "Coloretti 1kg", "Granulado Colorido 1kg",
        "Coloretti 500g", "Confeito Colorido 1kg",
    ],
    "Coco Ralado Grosso sem Açúcar": [
        "Coco Ralado Grosso 1kg", "Coco Ralado 1kg",
        "Coco Ralado Grosso 500g",
    ],
    "Chocolate Nobre Blend Harald": [
        "Chocolate Nobre Blend Harald 2.1kg", "Chocolate Harald Blend 2.1kg",
        "Chocolate Nobre Blend Harald 1kg", "Cobertura nobre Blend Harald",
    ],
}

DIAS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]


def generate_prices(days: int = 90) -> list[dict]:
    """Generate synthetic price data for all ingredients × stores × days."""
    prices = []
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    store_list = list(STORE_FACTORS.items())

    for ing_canonical, info in INGREDIENT_BASES.items():
        base_kg = info["base_kg"]
        unit = info["unit"]
        volatility = info["volatility"]
        product_options = PRODUCT_NAMES[ing_canonical]

        # Random walk for price trend over time
        current_trend = 1.0  # start at base
        trend_slope = random.uniform(-0.003, 0.003)  # slow trend up/down

        for day_offset in range(days + 1):
            current_date = start_date + timedelta(days=day_offset)

            # Only generate for ~70% of days (not every store has data every day)
            if random.random() > 0.7:
                continue

            # Update trend with random walk + slope
            current_trend += trend_slope + random.uniform(-volatility / 2, volatility / 2)
            current_trend = max(0.8, min(1.2, current_trend))

            for store_name, factor in store_list:
                # ~30% chance of having data for this store on this day
                if random.random() > 0.3:
                    continue

                # Base price = base_kg × trend × store_factor
                price_kg = base_kg * current_trend * factor * random.uniform(0.95, 1.05)
                price_kg = round(price_kg, 2)

                # Convert kg price to product price
                # unit like "cx 12x395g" → total_kg = 12*0.395 = 4.74
                raw_price = price_kg * _total_kg_from_unit(unit)
                raw_price = round(raw_price, 2)

                product_name = random.choice(product_options)
                is_promo = random.random() < 0.08  # 8% chance of promotion

                price_entry = {
                    "ingredient_id": ing_canonical,
                    "store_id": store_name.lower().replace(" ", "_"),
                    "source": "automated",
                    "store_name": store_name,
                    "raw_product": product_name,
                    "raw_price": raw_price,
                    "raw_unit": unit,
                    "collected_at": current_date.isoformat(),
                    "valid_from": current_date.isoformat(),
                    "valid_until": (current_date + timedelta(days=7)).isoformat(),
                    "validity_raw": f"Válido até {(current_date + timedelta(days=7)).strftime('%d/%m/%Y')}",
                    "collected_weekday": DIAS_PT[current_date.weekday()],
                    "is_promotion": is_promo,
                    "tier": 1 if store_name in ["Assaí Atacadista", "Atacadão", "Spani Atacadista", "Mercadão Atacadista", "Tenda Atacado", "Roldão Atacadista", "Sam's Club", "Max Atacadista", "Makro Atacadista"] else
                           2 if store_name in ["Rizzo Supermercados", "Amendolate", "Cacau Center", "Confeitos & Cia", "Loja Santo Antônio", "Padaria Padeirão"] else 3,
                    "confidence": round(random.uniform(0.85, 1.0), 3),
                    "normalized": {
                        "qty": _qty_from_unit(unit),
                        "unit_kg": round(_unit_kg_from_unit(unit), 4),
                        "total_kg": round(_total_kg_from_unit(unit), 4),
                        "price_per_kg": round(price_kg, 2),
                        "price_per_un": round(raw_price, 2),
                    },
                    "city": random.choice(["Santos", "São Vicente", "Praia Grande", "São Paulo"]),
                    "logistics": random.choice(["pickup_local", "delivery"]),
                }
                prices.append(price_entry)

    return prices


def generate_flyers(count: int = 50) -> list[dict]:
    """Generate synthetic flyer metadata."""
    flyers = []
    store_names = list(STORE_FACTORS.keys())[:10]

    for i in range(count):
        store = random.choice(store_names)
        days_ago = random.randint(0, 30)
        flyer_date = date.today() - timedelta(days=days_ago)
        img_id = random.randint(1000, 9999)
        flyer = {
            "store_name": store,
            "region": random.choice(["Santos", "São Vicente", "Praia Grande", "São Paulo"]),
            "city": random.choice(["Santos", "São Vicente", "Praia Grande", "São Paulo"]),
            "flyer_title": f"Encarte {store} - Semana {flyer_date.isocalendar().week}",
            "flyer_date_start": flyer_date.isoformat(),
            "flyer_date_end": (flyer_date + timedelta(days=7)).isoformat(),
            "image_url": f"https://example.com/flyers/{store.lower().replace(' ', '_')}/{img_id}.jpg",
            "image_hash": hashlib.md5(f"{store}_{img_id}".encode(), usedforsecurity=False).hexdigest(),
            "image_type": "webp",
            "ocr_status": random.choice(["pending", "done", "failed"]),
            "products_extracted": random.randint(0, 25),
            "source": random.choice(["tiendeo", "kimbino", "manual"]),
            "collected_at": flyer_date.isoformat(),
        }
        flyers.append(flyer)

    return flyers


def generate_review_queue(count: int = 20) -> list[dict]:
    """Generate synthetic review queue items."""
    items = []
    store_names = list(STORE_FACTORS.keys())[:8]

    for i in range(count):
        store = random.choice(store_names)
        ing = random.choice(list(INGREDIENT_BASES.keys()))
        products = PRODUCT_NAMES[ing]
        product = random.choice(products) + " (verificar)"
        days_ago = random.randint(0, 15)

        items.append({
            "raw_product": product,
            "raw_price": round(random.uniform(15, 150), 2),
            "raw_unit": random.choice(["1kg", "500g", "cx 12x395g"]),
            "store_name": store,
            "source": "automated",
            "confidence": round(random.uniform(0.3, 0.79), 3),
            "suggestions": [ing, random.choice(list(INGREDIENT_BASES.keys()))],
            "validity_raw": f"Válido até {(date.today() + timedelta(days=7)).strftime('%d/%m/%Y')}",
            "status": "pending",
            "collected_at": (date.today() - timedelta(days=days_ago)).isoformat(),
        })

    return items


def _total_kg_from_unit(unit: str) -> float:
    """Estimate total kg from a unit string."""
    if "12x395g" in unit:
        return 12 * 0.395  # 4.74
    if "12x200g" in unit:
        return 12 * 0.200  # 2.4
    if "800g" in unit:
        return 0.8
    if "500g" in unit:
        return 0.5
    if "380g" in unit:
        return 0.38
    if "2.1kg" in unit:
        return 2.1
    if "3kg" in unit:
        return 3.0
    if "650g" in unit:
        return 0.65
    if "750g" in unit:
        return 0.75
    if "1L" in unit or "1kg" in unit:
        return 1.0
    return 1.0


def _qty_from_unit(unit: str) -> int:
    if unit.startswith("cx") or unit.startswith("12x"):
        return 12
    return 1


def _unit_kg_from_unit(unit: str) -> float:
    total = _total_kg_from_unit(unit)
    qty = _qty_from_unit(unit)
    return total / qty


def main():
    parser = argparse.ArgumentParser(description="Seed synthetic price data")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without inserting")
    parser.add_argument("--execute", action="store_true", help="Insert into Supabase")
    parser.add_argument("--json", type=str, help="Export to JSON file")
    parser.add_argument("--days", type=int, default=90, help="Days of history (default: 90)")
    args = parser.parse_args()

    print(f"Gerando dados sintéticos para {len(INGREDIENT_BASES)} ingredientes x {len(STORE_FACTORS)} lojas...")

    prices = generate_prices(days=args.days)
    flyers = generate_flyers(count=50)
    review_items = generate_review_queue(count=20)

    print(f"\n  Preços gerados: {len(prices)}")
    print(f"  Flyers gerados: {len(flyers)}")
    print(f"  Review queue: {len(review_items)}")

    # Date range of generated data
    if prices:
        dates = sorted(set(p["collected_at"] for p in prices))
        print(f"  Período: {dates[0]} a {dates[-1]} ({len(dates)} dias únicos)")

    if args.json:
        output = {
            "prices": prices,
            "flyers": flyers,
            "review_queue": review_items,
            "generated_at": datetime.now().isoformat(),
        }
        path = Path(args.json)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nJSON exportado para: {path} ({len(json.dumps(output))} bytes)")

    if args.execute:
        print("\nInserindo no Supabase...")
        try:
            from services.price_service import upsert_price
            from services.flyer_service import upsert_flyer
            from services.price_service import insert_review_item
        except Exception as e:
            print(f"  ERRO: Não foi possível conectar ao Supabase: {e}")
            print("  Certifique-se que SUPABASE_URL e SUPABASE_SERVICE_KEY estão no .env")
            sys.exit(1)

        ok, fail = 0, 0
        for p in prices[:500]:  # limit to 500 for safety
            try:
                upsert_price(p)
                ok += 1
            except Exception:
                fail += 1
        print(f"  Preços: {ok} inseridos, {fail} falhas")

        ok2, fail2 = 0, 0
        for f in flyers:
            try:
                upsert_flyer(f)
                ok2 += 1
            except Exception:
                fail2 += 1
        print(f"  Flyers: {ok2} inseridos, {fail2} falhas")

        ok3, fail3 = 0, 0
        for r in review_items:
            try:
                insert_review_item(r)
                ok3 += 1
            except Exception:
                fail3 += 1
        print(f"  Review queue: {ok3} inseridos, {fail3} falhas")

        print(f"\nTotal: {ok + ok2 + ok3} registros inseridos, {fail + fail2 + fail3} falhas")

    if args.dry_run:
        print("\nUse --execute para inserir ou --json para exportar.")


if __name__ == "__main__":
    main()
