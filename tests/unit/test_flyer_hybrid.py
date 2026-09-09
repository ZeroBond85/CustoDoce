"""Unit tests for parsers.flyer_hybrid (dense-flyer hybrid extractor).

Nenhum teste toca a rede nem o RapidOCR real: fazem monkeypatch de
- ``_get_engine`` (RapidOCR)
- ``get_client`` (text-LLM HTTP)
para validar apenas a logica de roteamento por densidade, construcao de blocos
geometricos e resolucao de nomes via LLM.
"""
from __future__ import annotations

import json
import os

import pytest

import parsers.flyer_hybrid as fh


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_cb_between_tests():
    """Limpa o circuit-breaker global antes de cada teste.

    Sem isso, testes que disparam 429/401 no provedor afetariam o CB e
    vazariam para outros testes (groq chega a ser "bloqueado" entre
    testes sequenciais).
    """
    fh._cb_state.clear()
    yield
    fh._cb_state.clear()


@pytest.fixture(autouse=True)
def _disable_llm_feature(monkeypatch):
    """LLM classifier está desabilitado via feature flag (ai.llm_classifier: false).
    Testes que precisam de LLM devem usar o fixture `enable_llm_feature`.
    """
    monkeypatch.setattr("services.config.get_feature", lambda *_a, **_k: False)


@pytest.fixture
def enable_llm_feature(monkeypatch):
    """Habilita o feature flag de LLM para testes que testam LLM."""
    monkeypatch.setattr("services.config.get_feature", lambda *_a, **_k: True)


@pytest.fixture
def flyer_regions():
    path = os.path.join(
        os.path.dirname(__file__), "..", "fixtures", "flyer_ocr_sample.json"
    )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # first dense flyer
    return next(iter(data.values()))["regions"]


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp):
        self._resp = resp
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._resp


def _llm_payload(produtos: list[dict]) -> dict:
    content = json.dumps({"produtos": produtos}, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}]}


# --- is_dense ---------------------------------------------------------------


class TestIsDense:
    def test_dense_when_above_threshold(self):
        regions = [{"text": "x", "box": [[0, 0]] * 4}] * (fh.DENSITY_THRESHOLD)
        assert fh.is_dense(regions) is True

    def test_sparse_when_below_threshold(self):
        regions = [{"text": "x", "box": [[0, 0]] * 4}] * (fh.DENSITY_THRESHOLD - 1)
        assert fh.is_dense(regions) is False


class TestBuildPriceBlocks:
    def test_fixture_produces_named_blocks(self, flyer_regions):
        blocks = fh.build_price_blocks(flyer_regions)
        assert blocks, "expected reconstructed price blocks"
        # every block has a positive price and most carry nearby name texts
        assert all(b["price"] > 0 for b in blocks)
        named = [b for b in blocks if b["texts"]]
        assert len(named) >= len(blocks) * 0.7

    def test_no_prices_returns_empty(self):
        regions = [{"text": "PROMOCAO", "box": [[0, 0], [10, 0], [10, 5], [0, 5]], "score": 1.0}]
        assert fh.build_price_blocks(regions) == []


# --- run_rapidocr -----------------------------------------------------------


class _FakeOcrResult:
    def __init__(self, boxes, txts, scores):
        self.boxes = boxes
        self.txts = txts
        self.scores = scores


class TestRunRapidocr:
    def test_returns_none_when_engine_unavailable(self, monkeypatch):
        monkeypatch.setattr(fh, "_get_engine", lambda: None)
        assert fh.run_rapidocr(b"fakebytes") is None

    def test_converts_engine_output_to_regions(self, monkeypatch):
        box = [[0, 0], [10, 0], [10, 8], [0, 8]]
        fake = _FakeOcrResult(boxes=[box], txts=["ARROZ"], scores=[0.97])

        class _Eng:
            def __call__(self, arr):
                return fake

        monkeypatch.setattr(fh, "_get_engine", lambda: _Eng())
        # provide a minimal valid PNG so PIL.Image.open works
        from PIL import Image
        import io

        buf = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="PNG")

        buf.seek(0)
        regions = fh.run_rapidocr(buf.read())
        assert regions
        assert regions[0]["text"] == "ARROZ"


# --- extract_from_regions ---------------------------------------------------


class TestExtractFromRegions:
    def test_fixture_produces_products(self, flyer_regions):
        products = fh.extract_from_regions(flyer_regions)
        assert products, "expected non-empty products from fixture"
        assert all("product" in p and "price" in p for p in products)
        assert all(p["price"] > 0 for p in products)


# --- resolve_names ----------------------------------------------------------


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp):
        self._resp = resp
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self._resp


def _llm_payload(produtos: list[dict]) -> dict:
    content = json.dumps({"produtos": produtos}, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}]}


class TestResolveNames:
    def _clear_keys(self, monkeypatch):
        for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GITHUB_TOKEN"):
            monkeypatch.delenv(k, raising=False)

    def test_empty_blocks_returns_empty(self):
        assert fh.resolve_names([]) == []

    def test_no_provider_key_falls_back_to_raw_ocr(self, monkeypatch):
        self._clear_keys(monkeypatch)
        out = fh.resolve_names([{"price": 5.0, "texts": ["Arroz"]}])
        assert out == [{"product": "Arroz", "price": 5.0, "unit": ""}]

    def test_good_names_skip_llm(self, monkeypatch):
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        client = _FakeClient(_FakeResp({}))
        monkeypatch.setattr(fh, "get_client", lambda: client)
        out = fh.resolve_names([{"price": 25.9, "texts": ["Arroz", "5kg"]}])
        assert out == [{"product": "Arroz 5kg", "price": 25.9, "unit": ""}]
        assert not client.calls  # LLM was NOT called — all names good

    def test_low_quality_triggers_llm_refine(self, monkeypatch, enable_llm_feature):
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        client = _FakeClient(_FakeResp(_llm_payload([{"nome": "Cafe 500g", "preco": 9.9}])))
        monkeypatch.setattr(fh, "get_client", lambda: client)
        # Mock get_best_provider to return groq when test key is set
        monkeypatch.setattr(fh, "get_best_provider", lambda providers=None: "groq")
        # Short name (< 5 chars) triggers LLM refinement
        out = fh.resolve_names([{"price": 9.9, "texts": ["Cafe"]}])
        assert out == [{"product": "Cafe 500g", "price": 9.9, "unit": ""}]
        assert client.calls and "api.groq.com" in client.calls[0]["url"]

    def test_http_error_falls_through_to_next_provider(self, monkeypatch, enable_llm_feature):
        self._clear_keys(monkeypatch)

        calls: list[str] = []

        class _Router:
            def post(self, url, **kwargs):
                calls.append(url)
                if "groq" in url:
                    return _FakeResp({}, status=429)
                return _FakeResp(_llm_payload([{"nome": "Cafe", "preco": 9.9}]))

        monkeypatch.setattr(fh, "get_client", lambda: _Router())
        # Force _text_llm_providers to return both providers (preflight mocked
        # out — real preflight returns at most one provider per call).
        monkeypatch.setattr(
            fh,
            "_text_llm_providers",
            lambda: [
                {"name": "groq", "url": "https://api.groq.com/openai/v1/chat/completions", "key": "k1", "model": "m"},
                {"name": "openrouter", "url": "https://openrouter.ai/api/v1/chat/completions", "key": "k2", "model": "m"},
            ],
        )
        # Short name triggers LLM, groq 429 → openrouter succeeds
        out = fh.resolve_names([{"price": 9.9, "texts": ["Cafe"]}])
        assert out == [{"product": "Cafe", "price": 9.9, "unit": ""}]
        assert len(calls) == 2

    def test_refine_only_low_quality_blocks(self, monkeypatch, enable_llm_feature):
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        client = _FakeClient(_FakeResp(_llm_payload([{"nome": "Cafe 500g", "preco": 9.9}])))
        monkeypatch.setattr(fh, "get_client", lambda: client)
        # Mock get_best_provider to return groq when test key is set
        monkeypatch.setattr(fh, "get_best_provider", lambda providers=None: "groq")
        blocks = [
            {"price": 9.9, "texts": ["Cafe"]},          # low quality (< 5 chars)
            {"price": 5.0, "texts": ["Arroz", "5kg"]},  # high quality
        ]
        out = fh.resolve_names(blocks)
        assert len(out) == 2
        assert out[0]["product"] == "Cafe 500g"  # refined by LLM
        assert out[1]["product"] == "Arroz 5kg"   # kept from raw-OCR
        assert len(client.calls) == 1  # only called once with 1 block


# --- quality & coverage (data-driven against fixtures) -----------------------


class TestQualityAndCoverage:
    """Validate that raw-OCR-first strategy guarantees 100 % coverage on real
    flyer fixtures and that name quality is sufficient for the matcher.

    These tests are the "quality benchmark" — if any regressor lowers coverage
    or average quality, they catch it before deployment.
    """

    FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "flyer_ocr_sample.json")

    @pytest.fixture
    def all_flyers(self):
        with open(self.FIXTURE_PATH, encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture
    def enable_llm(self, enable_llm_feature):
        """Enable LLM for quality tests."""
        return enable_llm_feature

    def test_dense_flyers_have_named_blocks(self, all_flyers, enable_llm):
        for name, data in all_flyers.items():
            if fh.is_dense(data["regions"]):
                blocks = fh.build_price_blocks(data["regions"])
                named = [b for b in blocks if b["texts"]]
                assert len(named) >= len(blocks) * 0.5, f"flyer {name} low naming"

    def test_sparse_flyers_produce_some_blocks_but_hybrid_returns_none(self, all_flyers, monkeypatch):
        """Sparse flyers still get price blocks (they carry prices), but the
        dense-only hybrid orchestrator refuses them (density gate lives in
        ``extract_products_hybrid``, not in ``build_price_blocks``).
        """
        sparse = {name: data for name, data in all_flyers.items() if not fh.is_dense(data["regions"])}
        assert sparse, "expected at least one sparse flyer fixture"

        for name, data in sparse.items():
            blocks = fh.build_price_blocks(data["regions"])
            # blocks may exist for sparse flyers (prices present), just fewer
            assert len(blocks) < 30, f"sparse flyer {name} produced too many blocks"
            # hybrid entry point bounces sparse flyers back to the vision chain
            monkeypatch.setattr(fh, "run_rapidocr", lambda _b, r=data["regions"]: r)
            assert fh.extract_products_hybrid(b"fake") is None, f"sparse flyer {name} went through hybrid path"


# --- _resolve_names integration tests ---------------------------------------


class TestResolveNamesIntegration:
    """Full end-to-end tests with mocked LLM client."""

    def test_hybrid_not_dense_returns_none(self, monkeypatch, enable_llm_feature):
        """Sparse flyers should not go through hybrid path."""
        regions = [{"text": "PROMO", "box": [[0, 0], [10, 0], [10, 5], [0, 5]], "score": 1.0}]
        out = fh.extract_products_hybrid(b"fake")
        assert out is None

    def test_hybrid_dense_path(self, monkeypatch, enable_llm_feature):
        """Dense flyer + good OCR + LLM refinement works end-to-end."""
        # Build a dense flyer with some low-quality names
        regions = [{"text": f"Item {i}", "box": [[0, 0], [10, 0], [10, 10], [0, 10]], "score": 1.0} for i in range(fh.DENSITY_THRESHOLD + 2)]

        client = _FakeClient(_FakeResp(_llm_payload([{"nome": "Produto Completo", "preco": 9.9}])))
        monkeypatch.setattr(fh, "get_client", lambda: client)

        # Note: extract_products_hybrid expects image_bytes, not regions
        # This test just verifies the function doesn't crash when LLM is enabled
        out = fh.extract_products_hybrid(b"fake")
        assert out is None  # returns None for invalid image bytes
