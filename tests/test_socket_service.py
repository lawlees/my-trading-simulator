"""No-credential startup checks for the production socket service."""

import os
from types import SimpleNamespace

import pytest

from my_trading_simulator.market_data import socket_service


def test_identity_requires_dedicated_account(monkeypatch):
    monkeypatch.setattr(
        socket_service.pwd, "getpwnam", lambda username: SimpleNamespace(pw_uid=12345)
    )
    monkeypatch.setattr(socket_service.os, "geteuid", lambda: 12346)
    with pytest.raises(RuntimeError, match="schwab-worker"):
        socket_service.check_service_identity()


def test_identity_allows_dedicated_account(monkeypatch):
    monkeypatch.setattr(
        socket_service.pwd, "getpwnam", lambda username: SimpleNamespace(pw_uid=12345)
    )
    monkeypatch.setattr(socket_service.os, "geteuid", lambda: 12345)
    socket_service.check_service_identity()


def test_config_check_does_not_start_listener_or_schwab(monkeypatch, capsys):
    checks = []
    monkeypatch.setattr(socket_service, "check_service_identity", lambda: checks.append("uid"))
    monkeypatch.setattr(
        socket_service, "validate_socket_directory", lambda path: checks.append(path)
    )
    class ForbiddenServer:
        def __init__(self):
            raise AssertionError("Socket server initialized during check-config")
    monkeypatch.setattr(socket_service, "MarketDataSocketServer", ForbiddenServer)
    assert socket_service.main(["--check-config"]) == 0
    assert checks == ["uid", os.path.dirname(socket_service.SOCKET_PATH)]
    assert "Schwab API requests: NONE" in capsys.readouterr().out


def test_config_fails_closed_when_directory_insecure(monkeypatch):
    monkeypatch.setattr(socket_service, "check_service_identity", lambda: None)
    def reject(path):
        raise PermissionError("insecure directory")
    monkeypatch.setattr(socket_service, "validate_socket_directory", reject)
    with pytest.raises(PermissionError):
        socket_service.main(["--check-config"])
