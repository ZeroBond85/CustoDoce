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


# --- build_price_blocks -----------------------------------------------------


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
        regions = fh.run_rapidocr(buf.getvalue())
        assert regions == [{"text": "ARROZ", "box": [[0.0, 0.0], [10.0, 0.0], [10.0, 8.0], [0.0, 8.0]], "score": pytest.approx(0.97)}]

    def test_handles_missing_scores(self, monkeypatch):
        box = [[0, 0], [10, 0], [10, 8], [0, 8]]
        fake = _FakeOcrResult(boxes=[box], txts=["LEITE"], scores=None)

        class _Eng:
            def __call__(self, arr):
                return fake

        monkeypatch.setattr(fh, "_get_engine", lambda: _Eng())
        from PIL import Image
        import io

        buf = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="PNG")
        regions = fh.run_rapidocr(buf.getvalue())
        assert regions[0]["text"] == "LEITE"
        assert regions[0]["score"] == 0.0


# --- _parse_llm_json --------------------------------------------------------


class TestParseLlmJson:
    def test_plain_json(self):
        out = fh._parse_llm_json('{"produtos": [{"nome": "Arroz", "preco": 5.0}]}')
        assert out == [{"nome": "Arroz", "preco": 5.0}]

    def test_fenced_json(self):
        out = fh._parse_llm_json('```json\n{"produtos": [{"nome": "X", "preco": 1}]}\n```')
        assert out == [{"nome": "X", "preco": 1}]

    def test_bad_json_returns_none(self):
        assert fh._parse_llm_json("not json at all") is None

    def test_empty_returns_none(self):
        assert fh._parse_llm_json("") is None

    def test_missing_produtos_returns_empty_list(self):
        assert fh._parse_llm_json('{"other": 1}') == []


# --- _to_products -----------------------------------------------------------


class TestToProducts:
    def test_normalizes_and_filters(self):
        items = [
            {"nome": "Arroz 5kg", "preco": 25.9},
            {"nome": None, "preco": 5.0},  # null name dropped
            {"nome": "Gratis", "preco": 0.0},  # zero price dropped
            {"nome": "Bad", "preco": "abc"},  # unparseable dropped
            {"preco": 3.0},  # no name dropped
            "garbage",  # non-dict dropped
        ]
        out = fh._to_products(items)
        assert out == [{"product": "Arroz 5kg", "price": 25.9, "unit": ""}]

    def test_accepts_english_keys(self):
        out = fh._to_products([{"product": "Milk", "price": 2.5}])
        assert out == [{"product": "Milk", "price": 2.5, "unit": ""}]


# --- resolve_names ----------------------------------------------------------


class TestResolveNames:
    def _clear_keys(self, monkeypatch):
        for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GH_MODELS_TOKEN", "GITHUB_TOKEN"):
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

    def test_low_quality_triggers_llm_refine(self, monkeypatch):
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        client = _FakeClient(_FakeResp(_llm_payload([{"nome": "Cafe 500g", "preco": 9.9}])))
        monkeypatch.setattr(fh, "get_client", lambda: client)
        # Short name (< 5 chars) triggers LLM refinement
        out = fh.resolve_names([{"price": 9.9, "texts": ["Cafe"]}])
        assert out == [{"product": "Cafe 500g", "price": 9.9, "unit": ""}]
        assert client.calls and "api.groq.com" in client.calls[0]["url"]

    def test_http_error_falls_through_to_next_provider(self, monkeypatch):
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "k1")
        monkeypatch.setenv("OPENROUTER_API_KEY", "k2")

        calls: list[str] = []

        class _Router:
            def post(self, url, **kwargs):
                calls.append(url)
                if "groq" in url:
                    return _FakeResp({}, status=429)
                return _FakeResp(_llm_payload([{"nome": "Cafe", "preco": 9.9}]))

        monkeypatch.setattr(fh, "get_client", lambda: _Router())
        # Short name triggers LLM, groq 429 → openrouter succeeds
        out = fh.resolve_names([{"price": 9.9, "texts": ["Cafe"]}])
        assert out == [{"product": "Cafe", "price": 9.9, "unit": ""}]
        assert len(calls) == 2

    def test_refine_only_low_quality_blocks(self, monkeypatch):
        self._clear_keys(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        client = _FakeClient(_FakeResp(_llm_payload([{"nome": "Cafe 500g", "preco": 9.9}])))
        monkeypatch.setattr(fh, "get_client", lambda: client)
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

    def test_all_prices_have_names(self, all_flyers, monkeypatch):
        """Coverage: every block with text MUST produce a product name.

        Blocks with empty ``texts`` (orphan prices with no nearby OCR
        fragments) are skipped by ``_raw_ocr_fallback`` — that's expected.
        """
        cls = _FakeClient(_FakeResp({}))
        monkeypatch.setattr(fh, "get_client", lambda: cls)

        for name, data in all_flyers.items():
            blocks = fh.build_price_blocks(data["regions"])
            products = fh.resolve_names(blocks)

            blocks_with_text = sum(1 for b in blocks if b.get("texts"))
            assert len(products) == blocks_with_text, (
                f"{name}: {len(products)} names for {blocks_with_text} blocks "
                f"with text ({len(blocks)} total, {len(blocks) - blocks_with_text} empty)"
            )

    def test_name_quality_distribution(self, all_flyers, monkeypatch):
        """Quality: most raw-OCR names should score above threshold, meaning
        the LLM is only needed for a minority of blocks."""
        cls = _FakeClient(_FakeResp({}))
        monkeypatch.setattr(fh, "get_client", lambda: cls)

        low_quality = 0
        total = 0
        qualities = []

        for data in all_flyers.values():
            blocks = fh.build_price_blocks(data["regions"])
            products = fh.resolve_names(blocks)
            for p in products:
                q = fh._name_quality(p.get("product", ""))
                qualities.append(q)
                if q < fh.QUALITY_THRESHOLD:
                    low_quality += 1
                total += 1

        low_pct = low_quality / max(total, 1)
        avg_q = sum(qualities) / max(len(qualities), 1)

        assert low_pct < 0.4, (
            f"{low_quality}/{total} ({low_pct:.1%}) blocks below quality "
            f"threshold (avg={avg_q:.2f}) — too many would need LLM refinement"
        )

    def test_raw_ocr_preserves_all_prices(self, all_flyers, monkeypatch):
        """Prices from geometry must be preserved verbatim by raw-OCR pass.

        Matches by price value rather than position to handle orphan blocks
        (empty texts) that skip the output.
        """
        cls = _FakeClient(_FakeResp({}))
        monkeypatch.setattr(fh, "get_client", lambda: cls)

        for name, data in all_flyers.items():
            blocks = fh.build_price_blocks(data["regions"])
            products = fh.resolve_names(blocks)
            block_prices = {b["price"] for b in blocks}
            product_prices = {p["price"] for p in products}
            # Every product price must come from a block (no phantom prices)
            assert product_prices.issubset(block_prices), (
                f"{name}: products contain prices not in blocks: "
                f"{product_prices - block_prices}"
            )


# --- orchestration ----------------------------------------------------------


class TestOrchestration:
    def test_extract_from_regions_empty_blocks(self, monkeypatch):
        monkeypatch.setattr(fh, "reconstruct_prices", lambda r: [])
        assert fh.extract_from_regions([{"text": "x", "box": [[0, 0]] * 4}]) is None

    def test_extract_from_regions_calls_resolve(self, monkeypatch):
        monkeypatch.setattr(fh, "reconstruct_prices", lambda r: [fh.Price(1.0, [[0,0]]*4, "src")])
        monkeypatch.setattr(fh, "deduplicate_dual_prices", lambda p: p)
        monkeypatch.setattr(fh, "_blocks_from_prices", lambda p, r: [{"price": 1.0, "texts": ["A"]}])
        monkeypatch.setattr(fh, "resolve_names", lambda b: [{"product": "A B C", "price": 1.0, "unit": ""}])
        out = fh.extract_from_regions([{"text": "x", "box": [[0, 0]] * 4}])
        assert out == [{"product": "A B C", "price": 1.0, "unit": ""}]

    def test_hybrid_not_dense_returns_none(self, monkeypatch):
        monkeypatch.setattr(fh, "run_rapidocr", lambda b: [{"text": "x", "box": [[0, 0]] * 4}])
        assert fh.extract_products_hybrid(b"bytes") is None

    def test_hybrid_no_ocr_returns_none(self, monkeypatch):
        monkeypatch.setattr(fh, "run_rapidocr", lambda b: None)
        assert fh.extract_products_hybrid(b"bytes") is None

    def test_hybrid_dense_path(self, monkeypatch):
        dense = [{"text": "x", "box": [[0, 0]] * 4}] * fh.DENSITY_THRESHOLD
        monkeypatch.setattr(fh, "run_rapidocr", lambda b: dense)
        monkeypatch.setattr(fh, "extract_from_regions", lambda r, image_bytes=None: [{"product": "P", "price": 1.0, "unit": ""}])
        out = fh.extract_products_hybrid(b"bytes")
        assert out == [{"product": "P", "price": 1.0, "unit": ""}]
