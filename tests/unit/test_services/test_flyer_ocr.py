"""Unit tests for scrapers.flyer_ocr and the vision-LLM wiring of the
api_flyer scrapers (Max / Roldao).

Estes testes NAO tocam a rede nem o Tesseract: fazem monkeypatch de
- extract_products_via_vision (vision-LLM)
- extract_products (OCR fallback)
- o download HTTP da imagem
para validar apenas a logica de orquestracao/normalizacao.
"""
from __future__ import annotations

import scrapers.flyer_ocr as flyer_ocr
from scrapers.flyer_ocr import extract_flyer_products


class _FakeResp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class _FakeHttp:
    def __init__(self, mapping: dict[str, bytes]):
        self._mapping = mapping
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return _FakeResp(self._mapping.get(url, b"bytes"))


IMG_ENTRIES = [
    {"image_url": "https://x/enc-1.jpg", "image_hash": "h1", "post_date": "2026-07-13"},
    {"image_url": "https://x/enc-2.jpg", "image_hash": "h2"},
]


class TestExtractFlyerProducts:
    def test_vision_first_normalizes(self, monkeypatch):
        def fake_vision(_b):
            return [
                {"product": "Leite Condensado 395g", "price": 4.99, "unit": "395g", "validity": "13/07"},
                {"product": "X", "price": 1.0},  # nome curto -> descartado
                {"product": "Sem preco", "price": None},  # sem preco -> descartado
            ]

        monkeypatch.setattr(flyer_ocr, "extract_products_via_vision", fake_vision)
        http = _FakeHttp({})
        out = extract_flyer_products(http, IMG_ENTRIES, "Loja X", source="max_flyer")
        # 1 valido por imagem x 2 imagens
        assert len(out) == 2
        first = out[0]
        assert first["product"] == "Leite Condensado 395g"
        assert first["price"] == 4.99
        assert first["store"] == "Loja X"
        assert first["source"] == "max_flyer"
        assert first["validity_raw"] == "13/07"

    def test_falls_back_to_ocr_when_vision_empty(self, monkeypatch):
        monkeypatch.setattr(flyer_ocr, "extract_products_via_vision", lambda _b: None)

        def fake_ocr(_content, source_type="image"):
            return ([{"product": "Creme de Leite 200g", "price": 3.5, "unit": "200g", "validity_raw": "x"}], "txt", "text_sparse")

        monkeypatch.setattr(flyer_ocr, "extract_products", fake_ocr)
        http = _FakeHttp({})
        out = extract_flyer_products(http, [IMG_ENTRIES[0]], "Loja Y")
        assert len(out) == 1
        assert out[0]["product"] == "Creme de Leite 200g"
        assert out[0]["source"] == "flyer"

    def test_uses_post_date_as_fallback_validity(self, monkeypatch):
        monkeypatch.setattr(
            flyer_ocr, "extract_products_via_vision",
            lambda _b: [{"product": "Farinha de Trigo 1kg", "price": 5.0}],
        )
        http = _FakeHttp({})
        out = extract_flyer_products(http, [IMG_ENTRIES[0]], "Loja Z")
        assert out[0]["validity_raw"] == "2026-07-13"

    def test_dedup_by_hash(self, monkeypatch):
        monkeypatch.setattr(
            flyer_ocr, "extract_products_via_vision",
            lambda _b: [{"product": "Acucar Refinado 1kg", "price": 4.0}],
        )
        http = _FakeHttp({})
        dupes = [IMG_ENTRIES[0], dict(IMG_ENTRIES[0])]
        out = extract_flyer_products(http, dupes, "Loja W")
        assert len(out) == 1
        assert len(http.calls) == 1

    def test_max_images_limit(self, monkeypatch):
        monkeypatch.setattr(
            flyer_ocr, "extract_products_via_vision",
            lambda _b: [{"product": "Manteiga 200g", "price": 9.0}],
        )
        http = _FakeHttp({})
        out = extract_flyer_products(http, IMG_ENTRIES, "Loja V", max_images=1)
        assert len(out) == 1
        assert len(http.calls) == 1

    def test_skips_negative_and_zero_price(self, monkeypatch):
        monkeypatch.setattr(
            flyer_ocr, "extract_products_via_vision",
            lambda _b: [
                {"product": "Gratis Item", "price": 0.0},
                {"product": "Preco Negativo Item", "price": -5.0},
            ],
        )
        http = _FakeHttp({})
        out = extract_flyer_products(http, [IMG_ENTRIES[0]], "Loja U")
        assert out == []

    def test_download_failure_is_skipped(self, monkeypatch):
        monkeypatch.setattr(flyer_ocr, "extract_products_via_vision", lambda _b: [{"product": "abc def", "price": 1.0}])

        class _BoomHttp:
            def get(self, url, **kwargs):
                raise RuntimeError("network down")

        out = extract_flyer_products(_BoomHttp(), [IMG_ENTRIES[0]], "Loja T")
        assert out == []


class TestMaxRoldaoWiring:
    def test_max_run_uses_flyer_ocr(self, monkeypatch):
        from scrapers.max_api_scraper import MaxApiScraper

        scraper = MaxApiScraper({"name": "Max SP", "store_id": "120"})
        monkeypatch.setattr(
            scraper, "get_offers",
            lambda: [{"flyer": [{"item": [{"image": "//h/a.jpg", "id": "1"}]}]}],
        )
        monkeypatch.setattr(
            "scrapers.max_api_scraper.extract_flyer_products",
            lambda http, entries, name, source: [{"product": "P", "price": 1.0, "store": name, "source": source}],
        )
        monkeypatch.setattr(scraper, "report_success", lambda **k: {"recorded": True})
        out = scraper.run([])
        assert out and out[0]["source"] == "max_flyer"
        scraper.close()

    def test_max_default_store_id_is_sp(self):
        from scrapers.max_api_scraper import MaxApiScraper

        scraper = MaxApiScraper({"name": "Max SP"})
        assert scraper.store_id == "120"
        scraper.close()

    def test_giga_run_uses_flyer_ocr(self, monkeypatch):
        from scrapers.giga_flyer_scraper import GigaFlyerScraper

        scraper = GigaFlyerScraper({"name": "Giga", "base_url": "https://www.giga.com.vc"})
        assert scraper.encartes_url == "https://www.giga.com.vc/encartes"
        monkeypatch.setattr(
            scraper, "_collect_flyer_images_sync",
            lambda: [{"image_url": "https://x/enc.jpg", "image_hash": "h", "validity_raw": "13/07"}],
            raising=False,
        )
        import scrapers.giga_flyer_scraper as gmod
        monkeypatch.setattr(gmod.asyncio, "run", lambda coro: (coro.close(), [{"image_url": "https://x/enc.jpg", "image_hash": "h", "validity_raw": "13/07"}])[1])
        monkeypatch.setattr(
            "scrapers.giga_flyer_scraper.extract_flyer_products",
            lambda http, entries, name, source: [{"product": "P", "price": 2.0, "store": name, "source": source}],
        )
        monkeypatch.setattr(scraper, "report_success", lambda **k: {"recorded": True})
        out = scraper.run([])
        assert out and out[0]["source"] == "giga_flyer"
        scraper.close()

    def test_giga_run_reports_failure_when_no_images(self, monkeypatch):
        from scrapers.giga_flyer_scraper import GigaFlyerScraper

        scraper = GigaFlyerScraper({"name": "Giga", "base_url": "https://www.giga.com.vc"})
        import scrapers.giga_flyer_scraper as gmod
        monkeypatch.setattr(gmod.asyncio, "run", lambda coro: (coro.close(), [])[1])
        called = {}
        monkeypatch.setattr(scraper, "report_failure", lambda **k: called.update(k) or {"recorded": True})
        out = scraper.run([])
        assert out == []
        assert "reason" in called
        scraper.close()

    def test_roldao_run_reports_failure_when_empty(self, monkeypatch):
        from scrapers.roldao_api_scraper import RoldaoApiScraper

        scraper = RoldaoApiScraper({"name": "Roldao"})
        monkeypatch.setattr(scraper, "get_posts", lambda: [])
        monkeypatch.setattr(
            "scrapers.roldao_api_scraper.extract_flyer_products",
            lambda http, entries, name, source: [],
        )
        called = {}
        monkeypatch.setattr(scraper, "report_failure", lambda **k: called.update(k) or {"recorded": True})
        out = scraper.run([])
        assert out == []
        assert "reason" in called
        scraper.close()
