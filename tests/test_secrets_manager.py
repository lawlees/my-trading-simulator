"""Offline credential tests: never call AWS, OpenAI, or Schwab."""
import json
import sys
from types import SimpleNamespace

import pytest

from my_trading_simulator import secrets_manager as secrets


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    secrets._load_aws_credentials.cache_clear()
    monkeypatch.delenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", raising=False)
    yield
    secrets._load_aws_credentials.cache_clear()


def test_local_credential(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "local")
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
    assert secrets.get_credential("OPENAI_API_KEY") == "local-test-key"


def test_reject_unknown_credential():
    with pytest.raises(ValueError, match="Unsupported credential"):
        secrets.get_credential("AWS_SECRET_ACCESS_KEY")


def test_reject_unknown_source(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "other")
    with pytest.raises(ValueError, match="Invalid credential source"):
        secrets.get_credential("OPENAI_API_KEY")


def fake_aws(monkeypatch, response=None, exception=None):
    calls = []
    def get_secret_value(*, SecretId):
        calls.append(SecretId)
        if exception:
            raise exception
        return response
    class Session:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def client(self, service):
            assert service == "secretsmanager"
            return SimpleNamespace(get_secret_value=get_secret_value)
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=Session))
    return calls


def test_aws_credentials_and_cache(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "aws")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-use-local")
    calls = fake_aws(monkeypatch, {"SecretString": json.dumps({
        "OPENAI_API_KEY": "aws-test-openai", "SCHWAB_APP_KEY": "aws-test-schwab",
        "SCHWAB_APP_SECRET": "aws-test-secret",
    })})
    assert secrets.get_credential("OPENAI_API_KEY") == "aws-test-openai"
    assert secrets.get_credential("SCHWAB_APP_SECRET") == "aws-test-secret"
    assert len(calls) == 2
    assert calls[0] == {"profile_name": "my-trading-simulator", "region_name": "us-east-2"}
    assert calls[1] == secrets.SECRET_NAME


def test_aws_failure_does_not_fallback(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "aws")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-use-local")
    fake_aws(monkeypatch, exception=RuntimeError("secret test failure"))
    with pytest.raises(RuntimeError, match="Cannot retrieve application credentials"):
        secrets.get_credential("OPENAI_API_KEY")


def test_aws_missing_key_does_not_fallback(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "aws")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-use-local")
    fake_aws(monkeypatch, {"SecretString": '{"SCHWAB_APP_KEY":"present"}'})
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not configured"):
        secrets.get_credential("OPENAI_API_KEY")


def test_aws_invalid_json_is_masked(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "aws")
    fake_aws(monkeypatch, {"SecretString": "not-json"})
    with pytest.raises(RuntimeError, match="Cannot retrieve application credentials"):
        secrets.get_credential("OPENAI_API_KEY")


def test_aws_non_object(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "aws")
    fake_aws(monkeypatch, {"SecretString": "[]"})
    with pytest.raises(RuntimeError, match="invalid format"):
        secrets.get_credential("OPENAI_API_KEY")
