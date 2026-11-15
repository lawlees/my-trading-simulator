
import json
from unittest.mock import MagicMock, patch

import pytest

from my_trading_simulator.market_data.schwab_client import (
    SCHWAB_TOKEN_SECRET_NAME,
    SchwabOAuthSecretStore,
)


@pytest.fixture
def fake_token():
    return {
        "creation_timestamp": 1700000000,
        "token": {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "token_type": "Bearer",
        },
    }


@pytest.fixture
def mock_store():
    with patch("boto3.Session") as session_class:
        session = MagicMock()
        client = MagicMock()

        session_class.return_value = session
        session.client.return_value = client

        store = SchwabOAuthSecretStore()

        yield store, client, session_class


def test_uses_dedicated_schwab_profile(mock_store):
    _, _, session_class = mock_store

    session_class.assert_called_once_with(
        profile_name="my-trading-simulator-schwab",
        region_name="us-east-2",
    )


def test_reads_valid_oauth_token(mock_store, fake_token):
    store, client, _ = mock_store

    client.get_secret_value.return_value = {
        "SecretString": json.dumps(fake_token)
    }

    result = store.read_token()

    assert result == fake_token

    client.get_secret_value.assert_called_once_with(
        SecretId=SCHWAB_TOKEN_SECRET_NAME
    )


def test_rejects_uninitialized_oauth_secret(mock_store):
    store, client, _ = mock_store

    client.get_secret_value.return_value = {
        "SecretString": json.dumps({
            "status": "NOT_CONFIGURED"
        })
    }

    with pytest.raises(RuntimeError):
        store.read_token()


def test_writes_refreshed_oauth_token(mock_store, fake_token):
    store, client, _ = mock_store

    store.write_token(fake_token)

    client.put_secret_value.assert_called_once()

    kwargs = client.put_secret_value.call_args.kwargs

    assert kwargs["SecretId"] == SCHWAB_TOKEN_SECRET_NAME
    assert json.loads(kwargs["SecretString"]) == fake_token


def test_rejects_invalid_token_before_writing(mock_store):
    store, client, _ = mock_store

    with pytest.raises(ValueError):
        store.write_token({"token": {}})

    client.put_secret_value.assert_not_called()


def test_propagates_aws_write_failure(mock_store, fake_token):
    store, client, _ = mock_store

    client.put_secret_value.side_effect = RuntimeError(
        "Simulated AWS failure"
    )

    with pytest.raises(RuntimeError):
        store.write_token(fake_token)

def test_failed_token_write_does_not_succeed(mock_store, fake_token):
    """A failed Secrets Manager write must propagate to the caller."""
    store, client, _ = mock_store

    client.put_secret_value.side_effect = RuntimeError(
        "Simulated token persistence failure"
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated token persistence failure",
    ):
        store.write_token(fake_token)

    client.put_secret_value.assert_called_once()