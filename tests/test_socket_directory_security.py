"""Tests for Schwab socket directory security."""

import grp
import os
import pwd
from types import SimpleNamespace

import pytest

from my_trading_simulator.market_data import (
    socket_directory_security as security,
)


def configure_expected_identity(monkeypatch):
    monkeypatch.setattr(
        security.pwd,
        "getpwnam",
        lambda name: SimpleNamespace(pw_uid=os.getuid()),
    )
    monkeypatch.setattr(
        security.grp,
        "getgrnam",
        lambda name: SimpleNamespace(gr_gid=os.getgid()),
    )


def test_secure_directory_accepted(tmp_path, monkeypatch):
    configure_expected_identity(monkeypatch)

    directory = tmp_path / "runtime"
    directory.mkdir()
    directory.chmod(0o2770)

    security.validate_socket_directory(directory)


def test_world_writable_directory_rejected(tmp_path, monkeypatch):
    configure_expected_identity(monkeypatch)

    directory = tmp_path / "runtime"
    directory.mkdir()
    directory.chmod(0o777)

    with pytest.raises(
        security.SocketDirectorySecurityError
    ):
        security.validate_socket_directory(directory)


def test_missing_directory_rejected(tmp_path, monkeypatch):
    configure_expected_identity(monkeypatch)

    with pytest.raises(
        security.SocketDirectorySecurityError
    ):
        security.validate_socket_directory(
            tmp_path / "missing"
        )


def test_symlink_directory_rejected(tmp_path, monkeypatch):
    configure_expected_identity(monkeypatch)

    target = tmp_path / "target"
    target.mkdir()
    target.chmod(0o2770)

    link = tmp_path / "runtime"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(
        security.SocketDirectorySecurityError
    ):
        security.validate_socket_directory(link)


def test_wrong_owner_rejected(tmp_path, monkeypatch):
    configure_expected_identity(monkeypatch)

    directory = tmp_path / "runtime"
    directory.mkdir()
    directory.chmod(0o2770)

    monkeypatch.setattr(
        security.pwd,
        "getpwnam",
        lambda name: SimpleNamespace(
            pw_uid=os.getuid() + 10000
        ),
    )

    with pytest.raises(
        security.SocketDirectorySecurityError
    ):
        security.validate_socket_directory(directory)


def test_wrong_group_rejected(tmp_path, monkeypatch):
    configure_expected_identity(monkeypatch)

    directory = tmp_path / "runtime"
    directory.mkdir()
    directory.chmod(0o2770)

    monkeypatch.setattr(
        security.grp,
        "getgrnam",
        lambda name: SimpleNamespace(
            gr_gid=os.getgid() + 10000
        ),
    )

    with pytest.raises(
        security.SocketDirectorySecurityError
    ):
        security.validate_socket_directory(directory)
