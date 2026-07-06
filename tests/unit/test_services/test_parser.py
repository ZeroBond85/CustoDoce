class TestFlyerParser:
    def test_parse_flyer_lines_with_validity(self):
        """Validity lines sao capturadas e associadas ao proximo produto."""
        from scrapers.flyer_parser import parse_flyer_lines

        lines = [
            "LEITE CONDENSADO MOCA CX 12X395G",
            "R$ 42,90",
            "Valido ate 30/06/2026",
            "CREME DE LEITE LATA 300G",
            "R$ 8,90",
        ]

        products = parse_flyer_lines(lines)
        assert len(products) == 2
        assert products[0]["validity_raw"] == ""
        assert "valido" in products[1]["validity_raw"].lower()
        assert "30/06" in products[1]["validity_raw"]

    def test_parse_flyer_lines_no_validity(self):
        """Sem linhas de validade, validity_raw vazio."""
        from scrapers.flyer_parser import parse_flyer_lines

        lines = [
            "LEITE CONDENSADO MOCA CX 12X395G",
            "R$ 42,90",
            "CREME DE LEITE LATA 300G",
            "R$ 8,90",
        ]

        products = parse_flyer_lines(lines)
        assert len(products) == 2
        assert all(p["validity_raw"] == "" for p in products)

    def test_parse_flyer_lines_validity_before_product(self):
        """Valor captura validade que aparece antes do produto."""
        from scrapers.flyer_parser import parse_flyer_lines

        lines = [
            "Oferta valida ate 15/07",
            "LEITE NINHO INTEGRAL 400G",
            "R$ 25,90",
        ]

        products = parse_flyer_lines(lines)
        assert len(products) == 1
        assert "15/07" in products[0]["validity_raw"]
