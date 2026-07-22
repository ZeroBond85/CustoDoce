from parsers.address_extractor import extract_address, best_address


class TestExtractAddress:
    def test_rua_com_numero(self):
        result = extract_address("Rua XV de Novembro, 123 - Centro, Santos")
        assert len(result) >= 1
        rua = [r for r in result if r.source_field == "rua_com_numero"]
        assert len(rua) == 1
        assert "Rua XV de Novembro, 123" in rua[0].address
        assert rua[0].confidence == 10.0

    def test_avenida_com_numero(self):
        result = extract_address("Av. Ana Costa, 340 - Vila Matias, Santos")
        rua = [r for r in result if r.source_field == "rua_com_numero"]
        assert len(rua) == 1
        assert "Av. Ana Costa, 340" in rua[0].address

    def test_cep(self):
        result = extract_address("CEP: 11010-000")
        cep = [r for r in result if r.source_field == "cep"]
        assert len(cep) == 1
        assert "11010-000" in cep[0].address
        assert cep[0].confidence == 8.0

    def test_telefone(self):
        result = extract_address("Tel: (13) 3222-1234")
        phone = [r for r in result if r.source_field == "telefone"]
        assert len(phone) == 1

    def test_whatsapp(self):
        result = extract_address("WhatsApp: (13) 99123-4567")
        phone = [r for r in result if r.source_field == "telefone"]
        assert len(phone) == 1

    def test_bairro(self):
        result = extract_address("Vila Matias")
        bairro = [r for r in result if r.source_field == "bairro"]
        assert len(bairro) >= 1

    def test_cidade_estado(self):
        result = extract_address("Centro, Santos")
        cidade = [r for r in result if r.source_field == "cidade_estado"]
        assert len(cidade) >= 1

    def test_empty_text_returns_empty(self):
        assert extract_address("") == []
        assert extract_address(None) == []

    def test_phone_with_ddd(self):
        result = extract_address("Telefone: (13) 3222-1234 | WhatsApp: (13) 99999-8888")
        phones = [r for r in result if r.source_field == "telefone"]
        assert len(phones) >= 1

    def test_cep_sem_hifen(self):
        result = extract_address("CEP 11010000")
        cep = [r for r in result if r.source_field == "cep"]
        assert len(cep) == 1

    def test_endereco_completo_flyer(self):
        text = """
        Ofertas do Assaí Atacadista - Santos
        Av. Ana Costa, 340 - Vila Matias
        CEP: 11010-000 | Tel: (13) 3222-1234
        Válido até 31/07/2026
        Leite Condensado R$ 8,90
        Creme de Leite R$ 6,50
        """
        result = extract_address(text)
        assert len(result) >= 2
        rua = [r for r in result if r.source_field == "rua_com_numero"]
        assert len(rua) >= 1
        cep = [r for r in result if r.source_field == "cep"]
        assert len(cep) >= 1

    def test_sem_endereco(self):
        result = extract_address("Leite Condensado R$ 8,90 | Creme de Leite R$ 6,50")
        assert len(result) == 0

    def test_only_store_name(self):
        result = extract_address("Assaí Atacadista - Leite Condensado 8,90")
        assert len(result) == 0


class TestBestAddress:
    def test_best_returns_highest_confidence(self):
        text = "Rua XV de Novembro, 123 - Centro, Santos - CEP: 11010-000"
        best = best_address(text)
        assert best is not None
        assert best.confidence >= 7.0
        assert "Rua" in best.address

    def test_best_no_address(self):
        assert best_address("Leite Condensado R$ 8,90") is None

    def test_best_combines_multiple_clues(self):
        text = "Centro - CEP: 11010-000 - Tel: (13) 3222-1234"
        best = best_address(text)
        assert best is not None
        assert best.source_field == "combinado" or best.confidence >= 7.0

    def test_best_empty_text(self):
        assert best_address("") is None
        assert best_address(None) is None
