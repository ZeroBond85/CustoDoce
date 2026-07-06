class TestEmailService:
    def test_build_full_report_html_structure(self):
        """HTML completo com promocao, validade, multiplos ingredientes."""
        from services.email_service import build_full_report_html

        prices = {
            "Leite Condensado": [
                {
                    "store_name": "Assai",
                    "raw_product": "Moca",
                    "raw_price": 42.90,
                    "raw_unit": "cx",
                    "normalized": {"price_per_kg": 10.5},
                    "is_promotion": False,
                    "valid_until": "2026-07-01",
                },
                {
                    "store_name": "Atacadao",
                    "raw_product": "Moca PROMO",
                    "raw_price": 39.90,
                    "raw_unit": "cx",
                    "normalized": {"price_per_kg": 9.98},
                    "is_promotion": True,
                    "valid_until": "2026-07-05",
                },
            ],
            "Creme de Leite": [
                {
                    "store_name": "Spani",
                    "raw_product": "Nestle Creme",
                    "raw_price": 8.90,
                    "raw_unit": "lata",
                    "normalized": {"price_per_kg": 35.60},
                    "is_promotion": False,
                    "valid_until": "",
                },
            ],
        }

        html = build_full_report_html(prices)
        assert "<!DOCTYPE html>" in html
        assert "Leite Condensado" in html
        assert "Creme de Leite" in html
        assert "Assai" in html and "Atacadao" in html and "Spani" in html
        assert "R$ 42.90" in html and "R$ 39.90" in html and "R$ 8.90" in html
        assert "PROMO" in html
        assert "at" in html
        assert "R$/kg" in html and "Loja" in html

    def test_build_full_report_html_empty(self):
        """Dict vazio gera HTML basico sem erros."""
        from services.email_service import build_full_report_html

        html = build_full_report_html({})
        assert "<!DOCTYPE html>" in html
        assert "CustoDoce" in html
