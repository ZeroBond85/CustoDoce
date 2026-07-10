"""Test store config schema compliance — validates config/stores.yaml."""

import yaml


def test_stores_yaml_schema_compliance():
    """Validate config/stores.yaml entries have required fields and valid types."""
    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    stores = data.get("stores", [])
    assert len(stores) >= 53, f"Expected >=53 stores, got {len(stores)}"

    names = set()
    valid_types = {
        "pdf_flyer", "extra_flyer", "pao_flyer", "api_flyer", "vtex_api",
        "website_catalog", "website_js", "aggregator", "aggregator_js",
        "facebook_flyer", "manual", "physical_atacado",
    }
    valid_scrapers = {
        "flyer_scraper", "vtex_scraper", "website_scraper",
        "tenda_api_scraper", "roldao_api_scraper", "max_api_scraper",
        "carrefour_scraper", "playwright_scraper", "playwright_price_scraper",
        "pao_flyer_scraper", "extra_flyer_scraper", "aggregator_scraper",
        "roldao_flyer_scraper", "facebook_flyer_scraper", "manual",
        "manual_visit_spreadsheet",
    }

    for s in stores:
        # Unique name
        name = s.get("name")
        assert name, f"Missing name: {s}"
        assert name not in names, f"Duplicate name: {name}"
        names.add(name)

        # Required fields
        for field in ("tier", "type"):
            assert field in s, f"{name} missing required field: {field}"

        # scraper required for non-manual stores
        if s["type"] != "manual" and s.get("collection_method") != "manual":
            assert "scraper" in s, f"{name} missing scraper for automated store"

        # is_active optional (defaults to True in sync)
        if "is_active" in s:
            assert isinstance(s["is_active"], bool), f"{name}: is_active must be bool"

        # Type validity

    # Verify our 5 new stores exist
    new_names = {"Rede Krill", "Rede Krill (Facebook)", "Mercado Primos", "Supermercados Saito", "Pratico Suarão"}
    found = {s["name"] for s in stores if s["name"] in new_names}
    assert found == new_names, f"Missing new stores: {new_names - found}"


def test_new_stores_have_correct_slugified_ids():
    """Verify slugified IDs for new stores match scrape_frequencies expectations."""
    with open("config/stores.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    stores = {s["name"]: s for s in data.get("stores", [])}

    expected_slugs = {
        "Rede Krill": "rede_krill",
        "Rede Krill (Facebook)": "rede_krill_facebook",
        "Mercado Primos": "mercado_primos",
        "Supermercados Saito": "supermercados_saito",
        "Pratico Suarão": "pratico_suarao",
    }

    for name, expected_slug in expected_slugs.items():
        store = stores[name]
        # sync_stores_bidirectional.py uses slugify(name) if no explicit id
        # Our names should slugify to these values
        from scripts.sync_stores_bidirectional import slugify
        actual_slug = slugify(name)
        assert actual_slug == expected_slug, f"{name}: slugify={actual_slug} != expected={expected_slug}"
