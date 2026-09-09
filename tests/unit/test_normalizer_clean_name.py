"""Testes para a função clean_name do normalizer."""


from parsers.normalizer import clean_name


class TestCleanName:
    """Testes para a função clean_name."""

    def test_remove_pack_sizes(self):
        """Remove tamanhos de embalagem como 'cx 12x395g'."""
        assert clean_name("Chocolate cx 12x395g") == "chocolate"
        assert clean_name("Leite 12x395g") == "leite"
        assert clean_name("Creme 12x 395g") == "creme"

    def test_remove_standalone_weights(self):
        """Remove pesos isolados como '395g', '1kg'."""
        assert clean_name("Leite 395g") == "leite"
        assert clean_name("Açúcar 1kg") == "açúcar"
        assert clean_name("Farinha 500g") == "farinha"
        assert clean_name("Leite 1.5kg") == "leite"
        assert clean_name("Óleo 500ml") == "óleo"

    def test_remove_parentheses(self):
        """Remove conteúdo entre parênteses."""
        assert clean_name("Chocolate (promo)") == "chocolate"
        assert clean_name("Leite (light)") == "leite"
        assert clean_name("Creme (zero açúcar)") == "creme"

    def test_remove_slash_suffix(self):
        """Remove sufixo após barra."""
        assert clean_name("Chocolate / promo") == "chocolate"
        assert clean_name("Leite / oferta") == "leite"

    def test_remove_promo_prefixes(self):
        """Remove prefixos promocionais."""
        assert clean_name("Promo Chocolate") == "chocolate"
        assert clean_name("Oferta Leite") == "leite"
        assert clean_name("Promocao Creme") == "creme"
        assert clean_name("Promoção Açúcar") == "açúcar"
        assert clean_name("Super Promo Chocolate") == "chocolate"
        assert clean_name("Mega Oferta Leite") == "leite"
        assert clean_name("Ultra Promo Creme") == "creme"

    def test_normalize_abbreviations(self):
        """Normaliza abreviações comuns."""
        assert clean_name("Choc 50%") == "chocolate 50%"
        assert clean_name("Chocol 70%") == "chocolate 70%"
        assert clean_name("Leite Cond 395g") == "leite condensado"
        assert clean_name("Leite Condens 395g") == "leite condensado"
        assert clean_name("Creme Leite 200g") == "creme de leite"
        assert clean_name("Creme de Avel 200g") == "creme de avelã"
        assert clean_name("Creme Avela 200g") == "creme de avelã"
        assert clean_name("Acucar Mascavo") == "açúcar mascavo"
        assert clean_name("Acucar Conf 500g") == "açúcar confeiteiro"
        assert clean_name("Far Trigo 1kg") == "farinha de trigo"
        assert clean_name("Fermento Bio 10g") == "fermento biologico"
        assert clean_name("Ess Baunilha 30ml") == "essencia de baunilha"
        assert clean_name("Ess Vainilla 25ml") == "essencia de vainilla"

    def test_normalize_whitespace(self):
        """Normaliza espaços em branco."""
        assert clean_name("  Chocolate   50%  ") == "chocolate 50%"
        assert clean_name("Chocolate    50%") == "chocolate 50%"
        assert clean_name("  Leite   Condensado  ") == "leite condensado"

    def test_empty_and_invalid(self):
        """Testa entradas vazias e inválidas."""
        assert clean_name("") == ""
        assert clean_name(None) == ""
        assert clean_name(123) == ""
        assert clean_name("   ") == ""

    def test_complex_examples(self):
        """Testa exemplos complexos reais."""
        assert clean_name("Chocolate ao Leite 50% cx 12x395g (promo)") == "chocolate ao leite 50%"
        assert clean_name("Leite Condensado 395g (light)") == "leite condensado"
        assert clean_name("Creme de Leite 900g / promo") == "creme de leite"
        assert clean_name("Granulado Ao Leite 500g (promoção)") == "granulado ao leite"
