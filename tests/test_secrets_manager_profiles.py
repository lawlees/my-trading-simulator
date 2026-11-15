
"""Offline tests for AWS credential profile selection."""

import json
import sys
from types import SimpleNamespace

import pytest

from my_trading_simulator import secrets_manager as secrets


@pytest.fixture(autouse=True)
def isolated_profile_environment(monkeypatch):
    monkeypatch.delenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        raising=False,
    )

    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE",
        "aws",
    )

    # Prevent ambient .env values from affecting these tests.
    monkeypatch.setattr(
        secrets,
        "load_dotenv",
        lambda **kwargs: None,
    )

    secrets._load_aws_credentials.cache_clear()

    yield

    secrets._load_aws_credentials.cache_clear()


def install_fake_boto3(monkeypatch):
    calls = []

    class FakeClient:
        def get_secret_value(self, *, SecretId):
            calls.append(("secret", SecretId))
            return {
                "SecretString": json.dumps({
                    "OPENAI_API_KEY": "test-openai",
                    "SCHWAB_APP_KEY": "test-schwab-key",
                    "SCHWAB_APP_SECRET": "test-schwab-secret",
                })
            }

    class FakeSession:
        def __init__(self, *, profile_name, region_name):
            calls.append(
                ("profile", profile_name, region_name)
            )

        def client(self, service_name):
            assert service_name == "secretsmanager"
            return FakeClient()

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(Session=FakeSession),
    )

    return calls


def test_default_aws_profile(monkeypatch):
    calls = install_fake_boto3(monkeypatch)

    value = secrets.get_credential("OPENAI_API_KEY")

    assert value == "test-openai"

    assert (
        "profile",
        "my-trading-simulator",
        "us-east-2",
    ) in calls


def test_dedicated_schwab_profile(monkeypatch):
    calls = install_fake_boto3(monkeypatch)

    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        "my-trading-simulator-schwab",
    )

    value = secrets.get_credential("SCHWAB_APP_KEY")

    assert value == "test-schwab-key"

    assert (
        "profile",
        "my-trading-simulator-schwab",
        "us-east-2",
    ) in calls


def test_cache_is_separate_per_profile(monkeypatch):
    calls = install_fake_boto3(monkeypatch)

    secrets.get_credential("OPENAI_API_KEY")

    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        "my-trading-simulator-schwab",
    )

    secrets.get_credential("SCHWAB_APP_KEY")
    secrets.get_credential("SCHWAB_APP_SECRET")

    profile_calls = [
        call for call in calls
        if call[0] == "profile"
    ]

    assert len(profile_calls) == 2

    assert profile_calls[0][1] == "my-trading-simulator"
    assert profile_calls[1][1] == "my-trading-simulator-schwab"


def test_reject_unapproved_profile(monkeypatch):
    calls = install_fake_boto3(monkeypatch)

    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        "unexpected-admin-profile",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported AWS credential profile",
    ):
        secrets.get_credential("SCHWAB_APP_KEY")

    assert calls == []


def test_failed_aws_retrieval_does_not_use_local(monkeypatch):
    monkeypatch.setenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        "my-trading-simulator-schwab",
    )

    monkeypatch.setenv(
        "SCHWAB_APP_KEY",
        "local-key-must-not-be-used",
    )

    class BrokenSession:
        def __init__(self, **kwargs):
            raise RuntimeError("Simulated AWS failure")

    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(Session=BrokenSession),
    )

    with pytest.raises(
        RuntimeError,
        match="Cannot retrieve application credentials",
    ):
        secrets.get_credential("SCHWAB_APP_KEY")
