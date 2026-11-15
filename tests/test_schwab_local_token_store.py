
"""Tests for secure local Schwab OAuth token storage."""

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from my_trading_simulator.market_data.schwab_local_token_store import (
    SchwabLocalTokenStore,
)


@pytest.fixture
def fake_token():
    return {
        "creation_timestamp": 1700000000,
        "token": {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
        },
    }


def test_writes_and_reads_valid_token(tmp_path, fake_token):
    store = SchwabLocalTokenStore(tmp_path / "schwab_token.json")

    store.write_token(fake_token)

    assert store.read_token() == fake_token


def test_token_file_has_owner_only_permissions(tmp_path, fake_token):
    path = tmp_path / "schwab_token.json"
    store = SchwabLocalTokenStore(path)

    store.write_token(fake_token)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_invalid_token_does_not_overwrite_existing_token(
    tmp_path, fake_token
):
    path = tmp_path / "schwab_token.json"
    store = SchwabLocalTokenStore(path)

    store.write_token(fake_token)

    with pytest.raises(ValueError):
        store.write_token({"token": {}})

    assert store.read_token() == fake_token


def test_failed_replace_preserves_original_token(
    tmp_path, fake_token
):
    path = tmp_path / "schwab_token.json"
    store = SchwabLocalTokenStore(path)

    store.write_token(fake_token)

    updated_token = {
        "creation_timestamp": 1700000000,
        "token": {
            "access_token": "new-fake-access-token",
            "refresh_token": "new-fake-refresh-token",
        },
    }

    with patch(
        "my_trading_simulator.market_data."
        "schwab_local_token_store.os.replace",
        side_effect=OSError("Simulated disk error"),
    ):
        with pytest.raises(OSError):
            store.write_token(updated_token)

    assert store.read_token() == fake_token


def test_successful_write_leaves_no_temp_files(
    tmp_path, fake_token
):
    store = SchwabLocalTokenStore(tmp_path / "schwab_token.json")

    store.write_token(fake_token)

    assert list(tmp_path.glob(".schwab-token-*.tmp")) == []


def test_read_rejects_invalid_token(tmp_path):
    path = tmp_path / "schwab_token.json"
    path.write_text(json.dumps({"status": "NOT_CONFIGURED"}))

    # Secure the file so the test reaches token-content validation.
    path.chmod(0o600)

    store = SchwabLocalTokenStore(path)

    with pytest.raises(ValueError):
        store.read_token()


def test_rejects_read_from_insecure_file(tmp_path, fake_token):
    path = tmp_path / "schwab_token.json"
    path.write_text(json.dumps(fake_token))
    path.chmod(0o644)

    store = SchwabLocalTokenStore(path)

    with pytest.raises(PermissionError, match="0600"):
        store.read_token()


def test_rejects_write_to_insecure_existing_file(tmp_path, fake_token):
    path = tmp_path / "schwab_token.json"
    path.write_text(json.dumps(fake_token))
    path.chmod(0o644)

    store = SchwabLocalTokenStore(path)

    with pytest.raises(PermissionError, match="0600"):
        store.write_token(fake_token)

    # The original file must remain unchanged.
    assert json.loads(path.read_text()) == fake_token


def test_rejects_symbolic_link(tmp_path, fake_token):
    actual_file = tmp_path / "actual_token.json"
    actual_file.write_text(json.dumps(fake_token))
    actual_file.chmod(0o600)

    link_path = tmp_path / "schwab_token.json"
    link_path.symlink_to(actual_file)

    store = SchwabLocalTokenStore(link_path)

    with pytest.raises(PermissionError):
        store.read_token()

    with pytest.raises(PermissionError):
        store.write_token(fake_token)


def test_rejects_insecure_token_directory(tmp_path, fake_token):
    token_dir = tmp_path / "oauth"
    token_dir.mkdir(mode=0o700)

    token_path = token_dir / "schwab_token.json"
    store = SchwabLocalTokenStore(token_path)
    store.write_token(fake_token)

    # Make the directory accessible to other users.
    token_dir.chmod(0o755)

    with pytest.raises(PermissionError):
        store.read_token()


def test_rejects_symlinked_token_directory(tmp_path, fake_token):
    real_dir = tmp_path / "real"
    real_dir.mkdir(mode=0o700)

    token_path = real_dir / "schwab_token.json"
    SchwabLocalTokenStore(token_path).write_token(fake_token)

    linked_dir = tmp_path / "linked"
    linked_dir.symlink_to(real_dir, target_is_directory=True)

    store = SchwabLocalTokenStore(linked_dir / "schwab_token.json")

    with pytest.raises(PermissionError):
        store.read_token()