"""Testes da camada de retry do upsert_price (fecha gap de cobertura).

A análise apontou que _is_transient_net_err tinha testes apenas para o
predicado, não para o caminho real de retry. Aqui verificamos que
_upsert_price_rpc_with_retry retenta em erro transitório (httpx.TransportError)
e NÃO retenta em erro permanente.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services import price_repository as pr


def test_rpc_with_retry_retries_on_transient():
    """Erro transitório nas 2 primeiras → sucesso na 3ª, rpc_execute 3x."""
    rpc = MagicMock()
    ok = [{"status": "ok"}]
    rpc.side_effect = [
        httpx.RemoteProtocolError("Server disconnected without sending a response"),
        httpx.RemoteProtocolError("Server disconnected without sending a response"),
        ok,
    ]

    with patch.object(pr, "rpc_execute", rpc), patch.object(pr, "time", MagicMock()):
        result = pr._upsert_price_rpc_with_retry(MagicMock(), {"x": 1})

    assert rpc.call_count == 3
    assert result == ok


def test_rpc_with_retry_raises_on_permanent():
    """Erro permanente (ex.: ValueError) NÃO retenta, relança imediatamente."""
    rpc = MagicMock()
    rpc.side_effect = ValueError("bad request")

    with patch.object(pr, "rpc_execute", rpc) as m:
        with pytest.raises(ValueError):
            pr._upsert_price_rpc_with_retry(MagicMock(), {"x": 1})

    assert m.call_count == 1


def test_transient_predicate_matches_known_flakes():
    """_is_transient_net_err reconhece o RemoteProtocolError da CI (#117/#124)."""
    assert pr._is_transient_net_err(httpx.RemoteProtocolError("Server disconnected"))
    assert pr._is_transient_net_err(httpx.NetworkError("Connection reset by peer"))
    assert pr._is_transient_net_err(httpx.TimeoutException("timed out"))


def test_transient_predicate_rejects_permanent():
    assert not pr._is_transient_net_err(ValueError("boom"))
