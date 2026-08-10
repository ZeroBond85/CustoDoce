"""
scripts/update_stores_yaml.py

Appends a new store entry to config/stores.yaml with schema validation.
Usage:
    python scripts/update_stores_yaml.py --dry-run < input.json
    python scripts/update_stores_yaml.py --apply < input.json
    python scripts/update_stores_yaml.py --interactive

Schema: see AGENTS.md §Estrutura de Diretórios and config/stores.yaml.
"""

import json
import os
import sys
from pathlib import Path

import yaml

STORES_PATH = Path("config/stores.yaml")

VALID_TIERS = {1, 2, 3, 4}
VALID_TYPES = {
    "pdf_flyer", "api_flyer", "extra_flyer", "pao_flyer",
    "vipcommerce_api", "vtex_api", "website_catalog", "website_js",
    "aggregator", "aggregator_js", "facebook_flyer",
    "physical_atacado", "manual",
}
VALID_LOGISTICS = {"pickup_local", "pickup_sp", "delivery"}
VALID_COLLECTION_METHODS = {"automated", "manual_visit", "manual"}
VALID_SCRAPERS = {
    "flyer_scraper", "tenda_api_scraper", "roldao_api_scraper",
    "max_api_scraper", "extra_flyer_scraper", "pao_flyer_scraper",
    "vtex_scraper", "website_scraper", "carrefour_hybrid_scraper",
    "playwright_price_scraper", "ecomplus_scraper",
    "vipcommerce_api_scraper", "aggregator_scraper",
    "playwright_scraper", "roldao_flyer_scraper", "giga_flyer_scraper",
    "facebook_flyer_scraper", "manual_visit_spreadsheet",
}
VALID_PUBLISH_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
VALID_URL_TYPES = {"printpdf", "direct_pdf"}
VALID_ZONES = {"centro", "sul", "norte", "leste", "oeste", "pari", "bras",
               "interior_sp", "centro_oeste", "baixada_santista"}
VALID_VIP_MODES = {"search"}

TIER_COLLECTION_METHOD = {1: "automated", 2: "automated", 3: "automated", 4: "manual"}

SCRAPER_BY_TYPE = {
    "pdf_flyer": "flyer_scraper",
    "extra_flyer": "extra_flyer_scraper",
    "pao_flyer": "pao_flyer_scraper",
}

TYPE_REQUIRED_API = {"api_flyer", "vipcommerce_api", "vtex_api", "aggregator", "aggregator_js"}


def load_stores() -> list[dict]:
    with open(STORES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("stores", [])


def save_stores(stores: list[dict], backup: bool = True):
    if backup:
        backup_path = STORES_PATH.with_suffix(".yaml.bak")
        STORES_PATH.rename(backup_path)
    with open(STORES_PATH, "w", encoding="utf-8") as f:
        yaml.dump({"stores": stores}, f, allow_unicode=True, sort_keys=False)


def next_priority(stores: list[dict]) -> int:
    priorities = [s.get("priority", 0) for s in stores if isinstance(s.get("priority"), int)]
    return (max(priorities) + 1) if priorities else 100


def validate_store(store: dict, existing_names: set[str]) -> list[str]:
    errors = []

    if "name" not in store or not store["name"]:
        errors.append("'name' is required and must be non-empty")
    elif not isinstance(store["name"], str):
        errors.append("'name' must be a string")
    elif store["name"] in existing_names:
        errors.append(f"store name '{store['name']}' already exists")

    tier = store.get("tier")
    if tier is None:
        errors.append("'tier' is required")
    elif not isinstance(tier, int) or tier not in VALID_TIERS:
        errors.append(f"'tier' must be one of {sorted(VALID_TIERS)}")

    stype = store.get("type")
    if not stype:
        errors.append("'type' is required")
    elif stype not in VALID_TYPES:
        errors.append(f"'type' must be one of {sorted(VALID_TYPES)}")

    if "logistics" in store and store["logistics"] not in VALID_LOGISTICS:
        errors.append(f"'logistics' must be one of {sorted(VALID_LOGISTICS)}")

    if "collection_method" in store:
        cm = store["collection_method"]
        if cm not in VALID_COLLECTION_METHODS:
            errors.append(f"'collection_method' must be one of {sorted(VALID_COLLECTION_METHODS)}")

    scraper = store.get("scraper")
    if scraper and scraper not in VALID_SCRAPERS:
        errors.append(f"'scraper' must be one of {sorted(VALID_SCRAPERS)}")

    if tier == 1 and stype in ("pdf_flyer", "extra_flyer", "pao_flyer") and not scraper:
        default = SCRAPER_BY_TYPE.get(stype)
        if default:
            store["scraper"] = default

    if "publish_day" in store and store["publish_day"] not in VALID_PUBLISH_DAYS:
        errors.append(f"'publish_day' must be one of {sorted(VALID_PUBLISH_DAYS)}")

    if "url_type" in store and store["url_type"] not in VALID_URL_TYPES:
        errors.append(f"'url_type' must be one of {sorted(VALID_URL_TYPES)}")

    if stype == "vipcommerce_api":
        vip_required = ["vip_domain", "vip_api_base", "vip_org_id", "vip_filial_id", "vip_cd_id"]
        # O login key é segredo: NUNCA deve ir para stores.yaml. Se a env
        # VIP_LOGIN_KEY não estiver definida, exigimos o campo vazio como
        # placeholder (o scraper cai no env em runtime).
        if "VIP_LOGIN_KEY" not in os.environ and "vip_login_key" not in store:
            errors.append("'vip_login_key' is required for type=vipcommerce_api (ou defina a env VIP_LOGIN_KEY)")
        for field in vip_required:
            if field not in store:
                errors.append(f"'{field}' is required for type=vipcommerce_api")

    if stype == "website_catalog" and scraper == "website_scraper" and "selectors" not in store:
        errors.append("'selectors' is required for website_scraper")

    if stype == "website_js" and "selectors" not in store:
        errors.append("'selectors' is required for type=website_js")

    if stype == "facebook_flyer" and "page_url" not in store:
        errors.append("'page_url' is required for type=facebook_flyer")

    if stype == "physical_atacado":
        for field in ("address", "zone", "coverage", "visit_frequency"):
            if field not in store:
                errors.append(f"'{field}' is required for type=physical_atacado")

    if isinstance(tier, int) and tier == 4 and stype == "manual":
        for field in ("address", "city"):
            if field not in store:
                errors.append(f"'{field}' is required for type=manual")

    if "units" in store:
        if not isinstance(store["units"], list):
            errors.append("'units' must be a list")
        elif store["units"]:
            for i, unit in enumerate(store["units"]):
                if not isinstance(unit, dict):
                    errors.append(f"units[{i}] must be a dict")
                else:
                    if "name" not in unit:
                        errors.append(f"units[{i}] missing 'name'")
                    if "address" not in unit:
                        errors.append(f"units[{i}] missing 'address'")

    if "selectors" in store:
        if not isinstance(store["selectors"], dict):
            errors.append("'selectors' must be a dict")
        else:
            for key, val in store["selectors"].items():
                if not isinstance(val, list):
                    errors.append(f"'selectors.{key}' must be a list of CSS selectors")
                elif not val:
                    errors.append(f"'selectors.{key}' must not be empty")

    if "cities" in store:
        if not isinstance(store["cities"], list):
            errors.append("'cities' must be a list")
        elif not store["cities"]:
            errors.append("'cities' must not be empty")

    if isinstance(store.get("regions"), list) is False and "regions" in store:
        errors.append("'regions' must be a list")

    if isinstance(store.get("browse_urls"), list) is False and "browse_urls" in store:
        errors.append("'browse_urls' must be a list")
    elif "browse_urls" in store and not store["browse_urls"]:
        errors.append("'browse_urls' must not be empty")

    if isinstance(store.get("category_urls"), list) is False and "category_urls" in store:
        errors.append("'category_urls' must be a list")

    if "rate_limit" in store:
        rl = store["rate_limit"]
        if not isinstance(rl, int) or rl < 0:
            errors.append("'rate_limit' must be a non-negative integer")

    if "matcher_threshold" in store:
        mt = store["matcher_threshold"]
        if not isinstance(mt, int) or mt < 0 or mt > 100:
            errors.append("'matcher_threshold' must be an int 0-100")

    for bool_field in ["is_active", "browse_parallel", "verify_ssl", "flyer_mode",
                        "anti_bot", "cloudflare", "shopify_json", "shopify_curl_cffi",
                        "shopify_playwright_fallback", "api_fallback", "persist_cookies"]:
        if bool_field in store and not isinstance(store[bool_field], bool):
            errors.append(f"'{bool_field}' must be a boolean")

    if "zone" in store and store["zone"] not in VALID_ZONES:
        errors.append(f"'zone' must be one of {sorted(VALID_ZONES)}")

    if "vip_mode" in store and store["vip_mode"] not in VALID_VIP_MODES:
        errors.append(f"'vip_mode' must be one of {sorted(VALID_VIP_MODES)}")

    if "api_endpoints" in store and not isinstance(store["api_endpoints"], dict):
        errors.append("'api_endpoints' must be a dict")

    if "api_endpoint" in store and not isinstance(store["api_endpoint"], str):
        errors.append("'api_endpoint' must be a string")

    if "headers_custom" in store and not isinstance(store["headers_custom"], dict):
        errors.append("'headers_custom' must be a dict")

    if "graphql_variables_template" in store and not isinstance(store["graphql_variables_template"], dict):
        errors.append("'graphql_variables_template' must be a dict")

    if "api_base_fallbacks" in store and not isinstance(store["api_base_fallbacks"], list):
        errors.append("'api_base_fallbacks' must be a list")

    if "vip_search_ingredients" in store and not isinstance(store["vip_search_ingredients"], list):
        errors.append("'vip_search_ingredients' must be a list")

    if "block_resources" in store and not isinstance(store["block_resources"], list):
        errors.append("'block_resources' must be a list")

    return errors


def infer_from_registry(entry: dict) -> dict:
    """Build a partial store config from a store_registry entry."""
    store = {
        "name": entry.get("name", "Unknown"),
        "tier": entry.get("tier", 3),
        "type": entry.get("config", {}).get("type", "website_catalog"),
        "logistics": entry.get("logistics", "pickup_local"),
    }
    if entry.get("address"):
        store["address"] = entry["address"]
    if entry.get("city"):
        store["cities"] = [entry["city"]]
    if entry.get("region"):
        store["regions"] = [entry["region"]]
    if entry.get("config"):
        cfg = entry["config"]
        if isinstance(cfg, dict):
            for k in ("scraper", "base_url", "search_url", "api_endpoint",
                      "rate_limit", "selectors", "publish_day"):
                if k in cfg:
                    store[k] = cfg[k]
    return store


def format_yaml_entry(store: dict) -> str:
    """Format a single store entry as YAML text with proper indentation."""
    header = yaml.dump({"stores": [store]}, allow_unicode=True, sort_keys=False)
    lines = header.splitlines()
    result = []
    for line in lines:
        if line.startswith("stores:"):
            continue
        result.append(line)
    return "\n".join(result)


def append_store(store: dict, dry_run: bool = False) -> bool:
    stores = load_stores()
    existing_names = {s.get("name", "") for s in stores}

    errors = validate_store(store, existing_names)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return False

    if "priority" not in store or not isinstance(store.get("priority"), int):
        store["priority"] = next_priority(stores)

    if "collection_method" not in store:
        tier = store.get("tier", 3)
        if tier in TIER_COLLECTION_METHOD:
            store["collection_method"] = TIER_COLLECTION_METHOD[tier]

    yaml_text = format_yaml_entry(store)

    if dry_run:
        name = store.get("name", "unknown")
        print(f"[DRY RUN] Would append store '{name}' with priority={store['priority']}:")
        print("--- config/stores.yaml +++")
        print(yaml_text)
        return True

    with open(STORES_PATH, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write(yaml_text)
        f.write("\n")

    print(f"Store '{store['name']}' appended with priority={store['priority']}")
    return True


def interactive():
    """Interactive CLI prompt for entering store data."""
    print("=== Interactive Store Creator ===")
    store = {}

    store["name"] = input("Store name: ").strip()
    while True:
        try:
            store["tier"] = int(input("Tier (1-4): ").strip())
            if store["tier"] in VALID_TIERS:
                break
            print(f"Tier must be one of {sorted(VALID_TIERS)}")
        except ValueError:
            print("Enter a number")

    print(f"Type must be one of: {', '.join(sorted(VALID_TYPES))}")
    store["type"] = input("Store type: ").strip()

    print(f"Logistics must be one of: {', '.join(sorted(VALID_LOGISTICS))}")
    store["logistics"] = input("Logistics: ").strip() or "pickup_local"

    scraper = input("Scraper (optional, press Enter to auto-detect): ").strip()
    if scraper:
        store["scraper"] = scraper

    base_url = input("Base URL (optional): ").strip()
    if base_url:
        store["base_url"] = base_url

    search_url = input("Search URL (optional, use {query}): ").strip()
    if search_url:
        store["search_url"] = search_url

    api_base = input("API base URL (optional): ").strip()
    if api_base:
        store["api_base"] = api_base

    cities_raw = input("Cities (comma-separated, optional): ").strip()
    if cities_raw:
        store["cities"] = [c.strip() for c in cities_raw.split(",")]

    print(f"Publish day: {', '.join(sorted(VALID_PUBLISH_DAYS))}")
    publish_day = input("Publish day (optional): ").strip()
    if publish_day:
        store["publish_day"] = publish_day

    units_raw = input("Units as JSON list (optional, [{\"name\":..., \"address\":...}]): ").strip()
    if units_raw:
        try:
            store["units"] = json.loads(units_raw)
        except json.JSONDecodeError:
            print("Invalid JSON, skipping units")

    extra_raw = input("Extra fields as JSON (optional, {\"key\": \"value\"}): ").strip()
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
            store.update(extra)
        except json.JSONDecodeError:
            print("Invalid JSON, skipping extra fields")

    return store


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Append a store to config/stores.yaml")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Append the store to the file")
    group.add_argument("--dry-run", action="store_true", help="Validate and preview without writing")
    parser.add_argument("--interactive", action="store_true", help="Interactive prompt mode")
    parser.add_argument("--json", type=str, help="JSON string with store data")
    parser.add_argument("--from-registry", type=str, help="Registry entry JSON to convert to store config")

    args = parser.parse_args()

    if args.interactive:
        store = interactive()
    elif args.json:
        store = json.loads(args.json)
    elif args.from_registry:
        entry = json.loads(args.from_registry)
        store = infer_from_registry(entry)
    else:
        if sys.stdin.isatty():
            parser.print_help()
            print("\nPipe JSON data to stdin or use --json/--interactive/--from-registry", file=sys.stderr)
            sys.exit(1)
        store = json.load(sys.stdin)

    dry_run = args.dry_run or not args.apply
    success = append_store(store, dry_run=dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
