class TestBrandExtractor:
    """Testes P0 para parsers/brand_extractor.py."""

    INGREDIENT = {
        "canonical": "Leite Condensado Integral",
        "brands": ["Moça", "Piracanjuba", "Itambé"],
    }
    MULTI_INGREDIENTS = [
        INGREDIENT,
        {"canonical": "Chocolate em Pó 50% Cacau", "brands": ["Melken", "Nestlé"]},
    ]

    def test_extract_brand_found_word_boundary(self):
        from parsers.brand_extractor import extract_brand

        assert extract_brand("Leite Condensado Moça 395g", self.INGREDIENT) == "Moça"

    def test_extract_brand_found_multiple_words(self):
        from parsers.brand_extractor import extract_brand

        assert extract_brand("Leite Piracanjuba 1kg", self.INGREDIENT) == "Piracanjuba"

    def test_extract_brand_not_found(self):
        from parsers.brand_extractor import extract_brand

        assert extract_brand("Leite Condensado Genérico", self.INGREDIENT) == "Desconhecido"

    def test_extract_brand_empty_brands_list(self):
        from parsers.brand_extractor import extract_brand

        assert extract_brand("Leite Condensado", {"brands": []}) == "Desconhecido"

    def test_extract_brand_no_brands_key(self):
        from parsers.brand_extractor import extract_brand

        assert extract_brand("Leite Condensado", {}) == "Desconhecido"

    def test_extract_brand_case_insensitive(self):
        from parsers.brand_extractor import extract_brand

        assert extract_brand("LEITE CONDENSADO MOÇA 395G", self.INGREDIENT) == "Moça"

    def test_extract_brand_partial_word_no_match(self):
        from parsers.brand_extractor import extract_brand

        ing = {"canonical": "Teste", "brands": ["Moca"]}
        assert extract_brand("Mocambo 1kg", ing) == "Desconhecido"

    def test_extract_brand_fuzzy_match(self):
        from parsers.brand_extractor import extract_brand

        ing = {"canonical": "Leite Condensado", "brands": ["Piracanjuba"]}
        assert extract_brand("Leite Condensado Piracajuba 395g", ing) == "Piracanjuba"

    def test_extract_brand_substring_precedes_partial_word(self):
        from parsers.brand_extractor import extract_brand

        ing = {"canonical": "Teste", "brands": ["Melken"]}
        assert extract_brand("Cobertura Melken 1kg", ing) == "Melken"
        assert extract_brand("Melkenzada 500g", ing) == "Desconhecido"

    def test_extract_brand_substring_with_number_boundary(self):
        from parsers.brand_extractor import extract_brand

        ing = {"canonical": "Teste", "brands": ["Ninho"]}
        assert extract_brand("Ninho 400g", ing) == "Ninho"
        assert extract_brand("Ninho400g", ing) == "Ninho"

    def test_extract_brand_from_all_found(self):
        from parsers.brand_extractor import extract_brand_from_all

        assert extract_brand_from_all("Chocolate Melken 1kg", self.MULTI_INGREDIENTS) == "Melken"

    def test_extract_brand_from_all_not_found(self):
        from parsers.brand_extractor import extract_brand_from_all

        assert extract_brand_from_all("Produto Genérico", self.MULTI_INGREDIENTS) is None

    def test_extract_brand_from_all_skips_duplicates(self):
        from parsers.brand_extractor import extract_brand_from_all

        ings = [
            {"canonical": "A", "brands": ["Nestlé"]},
            {"canonical": "B", "brands": ["Nestlé"]},
        ]
        assert extract_brand_from_all("Nestlé 1kg", ings) == "Nestlé"

    def test_extract_brand_from_all_empty(self):
        from parsers.brand_extractor import extract_brand_from_all

        assert extract_brand_from_all("Teste", []) is None
