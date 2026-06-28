"""Sanity check rápido do CustoDoce."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
import importlib.util
import yaml

load_dotenv()

errors = []

# 1. YAML válido
try:
    with open("config/ingredients.yaml") as f:
        ing = yaml.safe_load(f)
    assert len(ing["ingredients"]) >= 20, "Menos de 20 ingredientes"
    print(f"[OK] ingredients.yaml: {len(ing['ingredients'])} ingredientes")
except Exception as e:
    errors.append(f"YAML ingredients: {e}")
    print(f"[FAIL] YAML ingredients: {e}")

try:
    with open("config/stores.yaml", encoding="utf-8") as f:
        st = yaml.safe_load(f)
    assert len(st["stores"]) >= 40, "Menos de 40 lojas"
    print(f"[OK] stores.yaml: {len(st['stores'])} lojas")
except Exception as e:
    errors.append(f"YAML stores: {e}")
    print(f"[FAIL] YAML stores: {e}")

try:
    with open("config/features.yaml") as f:
        feat = yaml.safe_load(f)
    assert "features" in feat
    print(f"[OK] features.yaml: {len(feat['features'])} flags")
except Exception as e:
    errors.append(f"YAML features: {e}")
    print(f"[FAIL] YAML features: {e}")

# 2. Módulos críticos importam
modules = ["main", "parsers.matcher", "services.price_service", "services.config_db", "services.flyer_service"]
for mod in modules:
    try:
        importlib.import_module(mod)
        print(f"[OK] import {mod}")
    except Exception as e:
        errors.append(f"import {mod}: {e}")
        print(f"[FAIL] import {mod}: {e}")

# 3. Supabase conecta
try:
    from services.config_db import get_all_ingredients, get_all_stores

    ings = get_all_ingredients(include_inactive=True)
    assert len(ings) >= 20, f"DB retornou {len(ings)} ingredientes"
    print(f"[OK] Supabase: {len(ings)} ingredientes, {len(get_all_stores(include_inactive=True))} lojas")
except Exception as e:
    errors.append(f"Supabase: {e}")
    print(f"[FAIL] Supabase: {e}")

# 4. Features carregam
try:
    from services.config import get

    val = get("features.ai.enabled")
    assert val in (True, False), "Feature flag inválida"
    print(f"[OK] Config: features.ai.enabled={val}")
except Exception as e:
    errors.append(f"Config: {e}")
    print(f"[FAIL] Config: {e}")

# 5. Scrapers principais existem
scrapers = [
    "scrapers.flyer_scraper",
    "scrapers.vtex_scraper",
    "scrapers.website_scraper",
    "scrapers.carrefour_scraper",
    "scrapers.extra_flyer_scraper",
]
for s in scrapers:
    spec = importlib.util.find_spec(s)
    if spec is None:
        errors.append(f"Scraper {s} não encontrado")
        print(f"[FAIL] {s}")
    else:
        print(f"[OK] {s}")

# Resultado final
print("\n" + "=" * 50)
if errors:
    print(f"Sanity check FALHOU ({len(errors)} erros):")
    for err in errors:
        print(f"  - {err}")
    sys.exit(1)
else:
    print("Sanity check OK!")
    sys.exit(0)
