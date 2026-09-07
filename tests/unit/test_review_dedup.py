"""Tests for services/review_dedup.py — Fase C."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.review_dedup import (
    SEMANTIC_DEDUP_THRESHOLD,
    find_pending_duplicates,
    is_semantic_duplicate,
)


class TestIsSemanticDuplicate:
    def test_none_empty(self) -> None:
        assert is_semantic_duplicate("", []) is None
        assert is_semantic_duplicate("", ["x"]) is None

    def test_identical(self) -> None:
        result = is_semantic_duplicate("Leite Condensado Mococa 395g", ["Leite Condensado Mococa 395g"])
        assert result is not None
        assert result["score"] >= 90

    def test_reordered_tokens(self) -> None:
        result = is_semantic_duplicate(
            "Leite Condensado Mococa 395g",
            ["Mococa Leite Condensado 395g"],
        )
        assert result is not None
        assert result["existing_product"] == "Mococa Leite Condensado 395g"
        assert result["score"] >= 90

    def test_accent_normalization(self) -> None:
        result = is_semantic_duplicate(
            "Chocolate meio amargo 50g",
            ["Chocolate meio amargo 50g"],
        )
        assert result is not None

    def test_different_product_below_threshold(self) -> None:
        result = is_semantic_duplicate(
            "Leite Condensado Mococa 395g",
            ["Granulado Colorido 100g"],
        )
        assert result is None

    def test_slightly_different_above_threshold(self) -> None:
        result = is_semantic_duplicate(
            "Leite Condensado Mococa 395g",
            ["Leite Condensado Mococa 395g caixa"],
        )
        assert result is not None

    def test_empty_existing_list(self) -> None:
        assert is_semantic_duplicate("qualquer coisa", []) is None


class TestFindPendingDuplicates:
    @patch("services.review_dedup.get_supabase")
    @patch("services.review_dedup.safe_execute")
    def test_found_duplicate(self, mock_safe: MagicMock, mock_client: MagicMock) -> None:
        mock_safe.return_value = [
            {"raw_product": "Mococa Leite Condensado 395g"},
            {"raw_product": "Granulado Colorido 100g"},
        ]
        result = find_pending_duplicates("Leite Condensado Mococa 395g", "Loja A")
        assert result is not None
        assert result["existing_product"] == "Mococa Leite Condensado 395g"

    @patch("services.review_dedup.get_supabase")
    @patch("services.review_dedup.safe_execute")
    def test_no_duplicate(self, mock_safe: MagicMock, mock_client: MagicMock) -> None:
        mock_safe.return_value = [
            {"raw_product": "Granulado Colorido 100g"},
            {"raw_product": "Coco Ralado 100g"},
        ]
        result = find_pending_duplicates("Leite Condensado Mococa 395g", "Loja A")
        assert result is None

    @patch("services.review_dedup.get_supabase")
    @patch("services.review_dedup.safe_execute")
    def test_no_pending_items(self, mock_safe: MagicMock, mock_client: MagicMock) -> None:
        mock_safe.return_value = []
        result = find_pending_duplicates("Leite Condensado Mococa 395g", "Loja A")
        assert result is None

    @patch("services.review_dedup.get_supabase")
    @patch("services.review_dedup.safe_execute")
    def test_ignores_empty_raw_product(self, mock_safe: MagicMock, mock_client: MagicMock) -> None:
        mock_safe.return_value = [{"raw_product": ""}]
        result = find_pending_duplicates("Leite Condensado Mococa 395g", "Loja A")
        assert result is None

    def test_threshold_constant_is_90(self) -> None:
        assert SEMANTIC_DEDUP_THRESHOLD == 90.0
