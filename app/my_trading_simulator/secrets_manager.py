"""Credential loading for local development and AWS Lightsail.

For AWS, the named boto3 profile must be backed by IAM Roles Anywhere.
Never fall back to local secrets after AWS retrieval fails.
"""

import json
import os
from functools import lru_cache

from dotenv import load_dotenv

SECRET_NAME = "my-trading-simulator/api-credentials"
AWS_REGION = "us-east-2"
AWS_PROFILE_NAME = "my-trading-simulator"

ALLOWED_CREDENTIALS = frozenset({
    "OPENAI_API_KEY", "SCHWAB_APP_KEY", "SCHWAB_APP_SECRET",
})


@lru_cache(maxsize=1)
def _load_aws_credentials() -> dict[str, str]:
    """Retrieve and cache the project secret, using temporary role credentials."""
    import boto3

    session = boto3.Session(profile_name=AWS_PROFILE_NAME, region_name=AWS_REGION)
    client = session.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=SECRET_NAME)
        payload = json.loads(response["SecretString"])
    except Exception:
        # AWS exception messages should not propagate into trading logs.
        raise RuntimeError("Cannot retrieve application credentials from Secrets Manager") from None

    if not isinstance(payload, dict):
        raise RuntimeError("Secrets Manager credentials have invalid format")
    return payload


def get_credential(name: str) -> str:
    """Retrieve an allowlisted key from an explicitly configured source.

    MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE=aws is REQUIRED on Lightsail.
    The default 'local' is exclusively for developer machines. To read the
    source selection from a local .env or the Lightsail .env, load it here.
    """
    if name not in ALLOWED_CREDENTIALS:
        raise ValueError(f"Unsupported credential: {name}")

    # load_dotenv does not override explicitly set environment variables.
    load_dotenv(override=False)
    source = os.getenv("MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE", "local").strip().lower()

    if source == "aws":
        value = _load_aws_credentials().get(name)
    elif source == "local":
        value = os.getenv(name)
    else:
        raise ValueError(f"Invalid credential source: {source}")

    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Credential {name} is not configured")
    return value.strip()
