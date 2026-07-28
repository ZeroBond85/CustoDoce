from pathlib import Path

import pytest
import yaml


@pytest.fixture
def selectors():
    path = Path(__file__).parent.parent.parent / "config" / "selectors.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_selectors_loads(selectors):
    assert selectors is not None


def test_defaults_present(selectors):
    assert "defaults" in selectors
    d = selectors["defaults"]
    assert "product_card" in d
    assert "product_name" in d
    assert "product_price" in d


def test_variants_have_required_keys(selectors):
    required = ["product_card", "product_name", "product_price"]
    for name, cfg in selectors.items():
        if name == "defaults":
            continue
        for key in required:
            assert key in cfg, f"{name} missing {key}"


def test_default_selectors_are_lists(selectors):
    for name, cfg in selectors.items():
        for key, val in cfg.items():
            assert isinstance(val, list), f"{name}.{key} should be list, got {type(val)}"


def test_variant_merges_default(selectors):
    d = selectors["defaults"]
    for name, cfg in selectors.items():
        if name == "defaults":
            continue
        for key in d:
            has_default = bool(d[key])
            has_override = bool(cfg.get(key))
            if has_default and not has_override:
                pytest.fail(f"{name} missing default key '{key}' without explicit override")


def test_ecomplus_specific(selectors):
    e = selectors.get("ecomplus", {})
    assert "a[href^='/produto/']" in e.get("product_card", [])
    assert "strong.text-base-800" in e.get("product_price", [])


def test_aggregator_specific(selectors):
    a = selectors.get("aggregator", {})
    assert "[data-testid='flyer_list_item']" in a.get("product_card", [])


def test_all_variants_loaded(selectors):
    variants = {"defaults", "ecomplus", "vtex", "aggregator", "shopify", "playwright"}
    loaded = set(selectors.keys())
    assert variants.issubset(loaded), f"Missing: {variants - loaded}"
