"""Testes reais do Assaí Dynamic Scraper."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

pytestmark = pytest.mark.slow


class TestAssaiDynamic:
    def test_assai_store_config(self):
        """Verifica se o Assaí está configurado no stores.yaml."""
        import yaml

        with open("config/stores.yaml", encoding="utf-8") as f:
            stores = yaml.safe_load(f).get("stores", [])
        assai = next((s for s in stores if "Assaí" in s.get("name", "")), None)
        assert assai is not None, "Assaí não encontrado no stores.yaml"
        assert assai.get("state") == "sp"

    @pytest.mark.skip(reason="Requer Playwright + internet. Descomentar para testar manualmente.")
    def test_assai_dynamic_scrape(self):
        """Teste real: navega, baixa PDF, extrai ≥5 produtos."""
        import yaml

        from scrapers.assai_dynamic import AssaiDynamicScraper

        with open("config/stores.yaml", encoding="utf-8") as f:
            stores = yaml.safe_load(f).get("stores", [])
        assai = next((s for s in stores if "Assaí" in s.get("name", "")), None)
        assert assai is not None

        scraper = AssaiDynamicScraper(assai)
        results = scraper.run()
        assert len(results) >= 5, f"Assaí retornou {len(results)} produtos (<5)"
