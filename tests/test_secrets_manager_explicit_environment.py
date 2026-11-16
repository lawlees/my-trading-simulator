"""Configured AWS credential source never probes a protected working directory."""

from my_trading_simulator import secrets_manager as secrets


def test_explicit_aws_source_never_loads_dotenv(monkeypatch):
    monkeypatch.setenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "aws")
    monkeypatch.setenv("MY_TRADING_SIMULATOR_AWS_PROFILE", "my-trading-simulator-schwab")
    monkeypatch.setattr(secrets, "load_dotenv", lambda **_: (_ for _ in ()).throw(OSError("not accessible")))
    monkeypatch.setattr(secrets, "_load_aws_credentials", lambda profile_name: {"SCHWAB_APP_KEY": "test-key"})
    assert secrets.get_credential("SCHWAB_APP_KEY") == "test-key"
