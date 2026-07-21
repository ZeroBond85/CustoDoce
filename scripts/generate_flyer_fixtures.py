"""Generate synthetic OCR fixtures for Assaí and Giga Atacadista flyers.

Assaí flyers have a different layout from Tenda:
- Fewer columns (2-3 vs 4)
- Larger text
- Different price positioning (price below product name, not above)
- More white space between products

Giga Atacadista (e-commerce) has:
- Product cards with image + name + price
- Different density
- Price often on same line as name
"""
from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(42)

ASSAI_PRODUCTS = [
    ("Leite Condensado", "23.90"),
    ("Creme de Leite", "12.50"),
    ("Chocolate 50%", "18.90"),
    ("Leite em Pó", "28.90"),
    ("Granulado Ao Leite", "15.90"),
    ("Coco Ralado", "8.90"),
    ("Açúcar Mascavo", "6.50"),
    ("Farinha de Trigo", "5.90"),
    ("Manteiga", "32.90"),
    ("Fermento", "3.50"),
    ("Baunilha", "22.90"),
    ("Chocolate 70%", "25.90"),
    ("Gotas Branco", "19.90"),
    ("Top Confete", "14.90"),
    ("Micro Ball", "16.90"),
]

GIGA_PRODUCTS = [
    ("Leite Condensado Nescau", "22.90"),
    ("Creme de Leite Philadelphia", "35.90"),
    ("Chocolate 50% Taita", "28.90"),
    ("Leite em Pó Ninho", "38.90"),
    ("Granulado Ao Leite Garoto", "24.90"),
    ("Coco Ralado 1kg", "12.90"),
    ("Açúcar Mascavo 1kg", "8.90"),
    ("Farinha de Trigo Dona Benta", "7.90"),
    ("Manteiga sem Sal", "42.90"),
    ("Fermento Químico", "5.90"),
]


def make_box(x: int, y: int, w: int, h: int) -> list[list[float]]:
    return [[float(x), float(y)], [float(x + w), float(y)], [float(x + w), float(y + h)], [float(x), float(y + h)]]


def generate_assai_flyer() -> dict:
    """Assaí flyer: 2-3 columns, price BELOW name, larger text, more spacing.

    Assaí uses a different layout from Tenda:
    - Price is rendered as a single tall blob (e.g. "2390") rather than
      separate reais/cents regions
    - Product names are longer and more descriptive
    - More white space, fewer regions overall
    """
    regions = []
    x_positions = [100, 700, 1300]  # 3 columns
    y_start = 200
    y_step = 300  # More vertical spacing than Tenda

    for col, x in enumerate(x_positions):
        for row, (name, price) in enumerate(ASSAI_PRODUCTS):
            if row * y_step + y_start > 2000:
                break
            y = y_start + row * y_step

            # Brand text (small, above name)
            brand = name.split()[0] if name.split() else name
            regions.append({
                "text": brand,
                "box": make_box(x, y - 40, 120, 25),
                "score": 0.98,
            })

            # Product name (larger, below brand)
            regions.append({
                "text": name,
                "box": make_box(x, y, 200, 35),
                "score": 0.99,
            })

            # Weight/unit (small, below name)
            weight = "1kg" if "1kg" in name else "395g"
            regions.append({
                "text": weight,
                "box": make_box(x, y + 40, 80, 20),
                "score": 0.95,
            })

            # Price (below weight, right-aligned) - single tall blob "RRCC"
            price_x = x + 250
            price_val = price.replace(".", "")
            regions.append({
                "text": price_val,
                "box": make_box(price_x, y + 55, 70, 70),
                "score": 0.97,
            })

    # Add some promo text that should be filtered
    for i in range(3):
        regions.append({
            "text": "Cliente APP",
            "box": make_box(50 + i * 700, 50, 150, 25),
            "score": 0.90,
        })

    # Add flyer header
    regions.append({
        "text": "ASSAI",
        "box": make_box(20, 20, 200, 60),
        "score": 0.99,
    })
    regions.append({
        "text": "SEMPRE COM VOCÊ",
        "box": make_box(250, 20, 180, 30),
        "score": 0.98,
    })

    return {"regions": regions}


def generate_giga_flyer() -> dict:
    """Giga Atacadista e-commerce: product cards, price on same line, lower density."""
    regions = []
    cards_per_row = 2
    rows = 5
    card_width = 500
    card_height = 400
    x_gap = 100
    y_gap = 50
    x_start = 50
    y_start = 100

    for row in range(rows):
        for col in range(cards_per_row):
            idx = row * cards_per_row + col
            if idx >= len(GIGA_PRODUCTS):
                break
            name, price = GIGA_PRODUCTS[idx]
            x = x_start + col * (card_width + x_gap)
            y = y_start + row * (card_height + y_gap)

            # Product name (top of card)
            regions.append({
                "text": name,
                "box": make_box(x, y, 280, 30),
                "score": 0.99,
            })

            # Brand
            brand = name.split()[0]
            regions.append({
                "text": brand,
                "box": make_box(x, y - 25, 100, 20),
                "score": 0.97,
            })

            # Weight
            weight = "1kg" if "1kg" in name else "500g"
            regions.append({
                "text": weight,
                "box": make_box(x, y + 35, 80, 20),
                "score": 0.95,
            })

            # Price (right side, same card) - single tall blob "RRCC"
            price_x = x + 320
            price_val = price.replace(".", "")
            regions.append({
                "text": price_val,
                "box": make_box(price_x, y + 10, 60, 70),
                "score": 0.98,
            })

            # Category tag
            regions.append({
                "text": "OFERTA",
                "box": make_box(price_x, y - 25, 60, 20),
                "score": 0.90,
            })

    # Header
    regions.append({
        "text": "GIGA",
        "box": make_box(20, 20, 150, 40),
        "score": 0.99,
    })
    regions.append({
        "text": "ATACADISTA",
        "box": make_box(200, 20, 150, 30),
        "score": 0.98,
    })

    # Promo text to filter
    for i in range(3):
        regions.append({
            "text": "Limite por CPF",
            "box": make_box(50 + i * 700, 70, 120, 20),
            "score": 0.92,
        })

    return {"regions": regions}


def main():
    fixtures_path = Path("tests/fixtures/flyer_ocr_sample.json")
    with open(fixtures_path, encoding="utf-8") as f:
        data = json.load(f)

    data["assai_0.jpg"] = generate_assai_flyer()
    data["giga_0.jpg"] = generate_giga_flyer()

    with open(fixtures_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Added fixtures: assai_0.jpg ({len(data['assai_0.jpg']['regions'])} regions)")
    print(f"Added fixtures: giga_0.jpg ({len(data['giga_0.jpg']['regions'])} regions)")


if __name__ == "__main__":
    main()
