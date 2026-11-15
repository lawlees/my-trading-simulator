
"""Tests for AWS Schwab OAuth storage and worker identity.

All tests use fake credentials and temporary files.
No AWS or Schwab requests are made.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from my_trading_simulator.market_data import schwab_client


@pytest.fixture
def aws_worker(monkeypatch):
    """Simulate the dedicated AWS Schwab worker on a Mac."""
    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE",
        "aws",
    )
    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        "my-trading-simulator-schwab",
    )

    with patch.object(
        schwab_client,
        "require_schwab_worker_identity",
    ) as identity_check:
        yield identity_check


@pytest.fixture
def fake_token():
    return {
        "creation_timestamp": 1700000000,
        "token": {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
        },
    }


def test_aws_mode_requires_dedicated_profile(
    monkeypatch,
    aws_worker,
):
    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        "my-trading-simulator",
    )

    with pytest.raises(
        RuntimeError,
        match="dedicated Schwab worker IAM profile",
    ):
        schwab_client.SchwabMarketDataClient()


def test_aws_mode_rejects_missing_token_file(
    monkeypatch,
    tmp_path,
    aws_worker,
):
    missing_file = tmp_path / "missing-token.json"

    monkeypatch.setattr(
        schwab_client,
        "AWS_SCHWAB_TOKEN_PATH",
        missing_file,
    )

    with patch.object(
        schwab_client,
        "get_credential",
        return_value="fake-credential",
    ):
        with pytest.raises(
            RuntimeError,
            match="not initialized",
        ):
            schwab_client.SchwabMarketDataClient()


def test_aws_mode_uses_local_token_store(
    monkeypatch,
    tmp_path,
    aws_worker,
    fake_token,
):
    token_dir = tmp_path / "oauth"
    token_dir.mkdir(mode=0o700)
    token_dir.chmod(0o700)

    token_path = token_dir / "schwab_token.json"

    store = schwab_client.SchwabLocalTokenStore(
        token_path
    )
    store.write_token(fake_token)

    monkeypatch.setattr(
        schwab_client,
        "AWS_SCHWAB_TOKEN_PATH",
        token_path,
    )

    fake_broker_client = MagicMock()

    with (
        patch.object(
            schwab_client,
            "get_credential",
            return_value="fake-credential",
        ),
        patch.object(
            schwab_client,
            "client_from_access_functions",
            return_value=fake_broker_client,
        ) as factory,
    ):
        client = schwab_client.SchwabMarketDataClient()

    assert isinstance(
        client.token_store,
        schwab_client.SchwabLocalTokenStore,
    )

    assert client.token_store.token_path == token_path
    assert client.client is fake_broker_client

    factory.assert_called_once()

    kwargs = factory.call_args.kwargs

    assert (
        kwargs["token_read_func"]
        == client.token_store.read_token
    )

    assert (
        kwargs["token_write_func"]
        == client.token_store.write_token
    )

    aws_worker.assert_called_once()


def test_rejects_missing_linux_worker_account():
    """Verify the real identity guard fails closed."""
    with patch.object(
        schwab_client.pwd,
        "getpwnam",
        side_effect=KeyError,
    ):
        with pytest.raises(
            RuntimeError,
            match="Linux account not found",
        ):
            schwab_client.require_schwab_worker_identity()


def test_rejects_wrong_linux_user():
    """An unauthorized Linux user must be rejected."""
    fake_account = SimpleNamespace(pw_uid=997)

    with (
        patch.object(
            schwab_client.pwd,
            "getpwnam",
            return_value=fake_account,
        ),
        patch.object(
            schwab_client.os,
            "geteuid",
            return_value=1000,
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="requires the schwab-worker Linux account",
        ):
            schwab_client.require_schwab_worker_identity()


def test_accepts_correct_linux_user():
    """The dedicated worker's effective UID must be accepted."""
    fake_account = SimpleNamespace(pw_uid=997)

    with (
        patch.object(
            schwab_client.pwd,
            "getpwnam",
            return_value=fake_account,
        ),
        patch.object(
            schwab_client.os,
            "geteuid",
            return_value=997,
        ),
    ):
        schwab_client.require_schwab_worker_identity()
