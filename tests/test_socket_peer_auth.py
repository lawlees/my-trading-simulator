"""Tests for Linux Unix socket peer authorization."""

import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from my_trading_simulator.market_data import socket_peer_auth
from my_trading_simulator.market_data.socket_peer_auth import (
    PeerAuthorizationError,
    authorize_socket_peer,
)


def configure_linux_peer(monkeypatch, uid=1000):
    monkeypatch.setattr(
        socket_peer_auth.socket,
        "SO_PEERCRED",
        17,
        raising=False,
    )

    monkeypatch.setattr(
        socket_peer_auth.pwd,
        "getpwnam",
        lambda username: SimpleNamespace(pw_uid=uid),
    )


def fake_connection(pid, uid, gid=1000):
    connection = Mock()
    connection.getsockopt.return_value = struct.pack(
        "3i", pid, uid, gid
    )
    return connection


def test_authorized_peer_accepted(monkeypatch):
    configure_linux_peer(monkeypatch)

    connection = fake_connection(1234, 1000)

    assert authorize_socket_peer(connection) == 1000


def test_unauthorized_peer_rejected(monkeypatch):
    configure_linux_peer(monkeypatch)

    connection = fake_connection(1234, 999)

    with pytest.raises(
        PeerAuthorizationError,
        match="Unauthorized",
    ):
        authorize_socket_peer(connection)


def test_invalid_peer_pid_rejected(monkeypatch):
    configure_linux_peer(monkeypatch)

    connection = fake_connection(0, 1000)

    with pytest.raises(PeerAuthorizationError):
        authorize_socket_peer(connection)


def test_missing_credentials_rejected(monkeypatch):
    configure_linux_peer(monkeypatch)

    connection = Mock()
    connection.getsockopt.return_value = b"bad"

    with pytest.raises(PeerAuthorizationError):
        authorize_socket_peer(connection)


def test_socket_credential_error_rejected(monkeypatch):
    configure_linux_peer(monkeypatch)

    connection = Mock()
    connection.getsockopt.side_effect = OSError(
        "Permission denied"
    )

    with pytest.raises(PeerAuthorizationError):
        authorize_socket_peer(connection)


def test_unknown_account_rejected(monkeypatch):
    configure_linux_peer(monkeypatch)

    def missing_user(username):
        raise KeyError(username)

    monkeypatch.setattr(
        socket_peer_auth.pwd,
        "getpwnam",
        missing_user,
    )

    with pytest.raises(PeerAuthorizationError):
        authorize_socket_peer(fake_connection(1234, 1000))


def test_missing_so_peercred_rejected(monkeypatch):
    monkeypatch.delattr(
        socket_peer_auth.socket,
        "SO_PEERCRED",
        raising=False,
    )

    with pytest.raises(
        PeerAuthorizationError,
        match="unavailable",
    ):
        authorize_socket_peer(fake_connection(1234, 1000))
