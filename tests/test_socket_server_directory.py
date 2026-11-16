"""Verify unsafe socket directories prevent server startup."""

import pytest

from my_trading_simulator.market_data.socket_server import (
    MarketDataSocketServer,
)
from my_trading_simulator.market_data.socket_directory_security import (
    SocketDirectorySecurityError,
)


def test_unsafe_directory_prevents_socket_creation(tmp_path):
    socket_path = tmp_path / "schwab.sock"
    calls = []

    def reject_directory(directory):
        calls.append(directory)
        raise SocketDirectorySecurityError(
            "Unsafe runtime directory"
        )

    server = MarketDataSocketServer(
        socket_path=socket_path,
        directory_validator=reject_directory,
    )

    with pytest.raises(
        SocketDirectorySecurityError,
        match="Unsafe runtime directory",
    ):
        server.serve(max_connections=1)

    assert calls == [tmp_path]
    assert not socket_path.exists()
