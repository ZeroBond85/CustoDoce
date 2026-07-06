#!/usr/bin/env python3
"""
Testes unitários para handlers do Telegram Bot.
Valida lógica de resposta, formatação e integração com serviços.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.handlers import (
    format_price_entry,
    help_command,
    lista_command,
    precos_command,
    start_command,
    status_command,
)


@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    return update


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    context.bot = AsyncMock()
    return context


class TestTelegramHandlers:
    """Valida o comportamento dos comandos do bot."""

    def test_format_price_entry(self):
        """Valida formatação de linha de preço."""
        entry = {
            "store_name": "Store Test",
            "raw_product": "Prod Test 395g",
            "raw_price": 10.50,
            "raw_unit": "un",
            "normalized": {"price_per_kg": 15.0, "price_per_un": 10.50},
        }
        res = format_price_entry(entry, 1)
        assert "🥇 <b>Store Test</b>" in res
        assert "R$ 10.50/un" in res
        assert "R$ 15.00/kg" in res

    @pytest.mark.asyncio
    async def test_start_command(self, mock_update, mock_context):
        """/start deve enviar mensagem de boas-vindas."""
        await start_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        assert "Bem-vindo ao CustoDoce" in args[0]

    @pytest.mark.asyncio
    async def test_help_command(self, mock_update, mock_context):
        """/ajuda deve enviar instruções."""
        await help_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        assert "🆘 <b>Ajuda CustoDoce</b>" in args[0]

    @pytest.mark.asyncio
    async def test_lista_command(self, mock_update, mock_context):
        """/lista deve listar ingredientes por categoria."""
        with patch("telegram_bot.handlers.load_ingredients") as mock_load:
            mock_load.return_value = [
                {"canonical_name": "Leite Condensado", "category": "lacteos"},
                {"canonical_name": "Creme de Leite", "category": "lacteos"},
                {"canonical_name": "Chocolate", "category": "chocolates"},
            ]
            await lista_command(mock_update, mock_context)
            mock_context.bot.send_message.assert_called_once()
            args, kwargs = mock_context.bot.send_message.call_args
            msg = kwargs.get("text", args[0] if args else "")
            assert "LACTEOS" in msg
            assert "CHOCOLATES" in msg
            assert "Leite Condensado" in msg

    @pytest.mark.asyncio
    async def test_precos_command_no_args(self, mock_update, mock_context):
        """/preco sem argumentos deve pedir o ingrediente."""
        mock_context.args = []
        await precos_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        assert "Use: /preco <ingrediente>" in args[0]

    @pytest.mark.asyncio
    async def test_precos_command_not_found(self, mock_update, mock_context):
        """/preco com ingrediente inexistente deve avisar."""
        mock_context.args = ["ingrediente_fantasma"]
        with patch("telegram_bot.handlers.load_ingredients") as mock_load:
            mock_load.return_value = [{"canonical_name": "Leite Condensado"}]
            await precos_command(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once()
            args, kwargs = mock_update.message.reply_text.call_args
            assert "não encontrado" in args[0]

    @pytest.mark.asyncio
    async def test_precos_command_success(self, mock_update, mock_context):
        """/preco com ingrediente válido deve listar preços."""
        mock_context.args = ["leite"]
        with (
            patch("telegram_bot.handlers.load_ingredients") as mock_load,
            patch("telegram_bot.handlers.get_prices_for_ingredient") as mock_get,
        ):
            mock_load.return_value = [{"canonical_name": "Leite Condensado"}]
            mock_get.return_value = [
                {
                    "store_name": "Loja A",
                    "raw_product": "Leite Moça",
                    "raw_price": 10.0,
                    "raw_unit": "un",
                    "normalized": {"price_per_kg": 12.0, "price_per_un": 10.0},
                }
            ]

            await precos_command(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once()
            args, kwargs = mock_update.message.reply_text.call_args
            msg = args[0]
            assert "Leite Condensado" in msg
            assert "Loja A" in msg
            assert "R$ 10.00" in msg

    @pytest.mark.asyncio
    async def test_status_command(self, mock_update, mock_context):
        """/status deve mostrar resumo do sistema."""
        with (
            patch("telegram_bot.handlers.get_latest_prices") as mock_get,
            patch("telegram_bot.handlers.load_ingredients") as mock_load,
        ):
            mock_get.return_value = [
                {"collected_at": "2026-06-27T10:00:00Z", "store_name": "Store 1", "confidence": 0.9},
                {"collected_at": "2026-06-27T10:00:00Z", "store_name": "Store 2", "confidence": 0.7},
            ]
            mock_load.return_value = [{"id": "1"}, {"id": "2"}]

            await status_command(mock_update, mock_context)
            mock_update.message.reply_text.assert_called_once()
            args, kwargs = mock_update.message.reply_text.call_args
            msg = args[0]
            assert "Status CustoDoce" in msg
            assert "Total de preços: 2" in msg
            assert "Lojas com dados: 2" in msg
            assert "Preços confiáveis (≥80%): 1" in msg
