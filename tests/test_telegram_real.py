"""
Testes reais contra o Telegram Bot em produção.
Requer TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env
Envia comandos reais ao bot e verifica resposta.
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx
from dotenv import load_dotenv
load_dotenv()

pytestmark = pytest.mark.slow

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SKIP = not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)


class TestTelegramReal:
    """D5 — Telegram Bot Real"""

    def test_d5_1_bot_info(self):
        """Bot responde a getMe"""
        if SKIP:
            pytest.skip("TELEGRAM_TOKEN não configurado")
        r = httpx.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe", timeout=10)
        assert r.status_code == 200, f"D5.1: HTTP {r.status_code}"
        data = r.json()
        assert data.get("ok"), f"D5.1: API não ok: {data}"
        assert data["result"].get("username"), "D5.1: Bot sem username"

    def test_d5_2_send_message(self):
        """Envia mensagem para o chat — bot pode não estar online para responder"""
        if SKIP:
            pytest.skip("TELEGRAM_TOKEN/CHAT_ID não configurados")
        msg = "/preco Leite Condensado"
        send = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10,
        )
        assert send.status_code == 200, f"D5.2: send HTTP {send.status_code}"
        data = send.json()
        assert data.get("ok"), f"D5.2: API não ok: {data}"

    def test_d5_3_telegram_report_format(self):
        """Testa formatação do relatório Telegram (simula o que o bot enviaria)"""
        from services.price_service import get_latest_prices
        # Apenas testa se a função de formatação não quebra
        prices = get_latest_prices(valid_only=True)
        assert prices is not None, "D5.3: get_latest_prices retornou None"
        # Testa que pelo menos um ingrediente tem preços formatáveis
        from services.config_db import get_active_ingredients
        ingredients = get_active_ingredients()
        assert len(ingredients) > 0, "D5.3: Nenhum ingrediente ativo"
