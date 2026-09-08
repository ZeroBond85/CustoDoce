"""Testes unitários do retry em _SchemaCursor.execute (dersiver de flakes #124).

Exec_sql_query é read-only (SELECT) — repetir é idempotente/seguro, então o
retry transitório não duplica nada. Verifica que o RPC é tentado de novo após
RemoteProtocolError/NetworkError transitórios.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from tests.conftest import _SchemaCursor


class FakeRpcResult:
    def __init__(self, data):
        self.data = data


def _make_client(side_effect=None, data=None):
    client = MagicMock()
    rpc = MagicMock()
    call = MagicMock()
    if side_effect is not None:
        call.execute.side_effect = side_effect
    else:
        call.execute.return_value = FakeRpcResult(data)
    rpc.return_value = call
    client.rpc = rpc
    return client


def test_transient_error_retries_and_succeeds():
    """Falha transitória (RemoteProtocolError) nas 2 primeiras → sucesso na 3ª."""
    data = [{"id": 1, "name": "Leite Condensado"}]
    err = httpx.RemoteProtocolError("Server disconnected without sending a response")
    client = _make_client(side_effect=[err, err, FakeRpcResult(data)])

    cursor = _SchemaCursor(client)
    cursor.execute("SELECT * FROM ingredients;")

    assert client.rpc.call_count == 3
    assert cursor.fetchall() == [(1, "Leite Condensado")]


def test_exhausts_after_all_attempts():
    """Após esgotar tentativas, relança a última exceção (hard fail, não silêncio)."""
    err = httpx.NetworkError("Connection reset by peer")
    client = _make_client(side_effect=[err, err, err])

    cursor = _SchemaCursor(client)
    with pytest.raises(httpx.NetworkError):
        cursor.execute("SELECT 1;")

    assert client.rpc.call_count == 3
