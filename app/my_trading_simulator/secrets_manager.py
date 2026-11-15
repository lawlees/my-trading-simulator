
"""Credential loading for local development and AWS Lightsail.

AWS credentials are retrieved from Secrets Manager using an
explicitly allowlisted IAM Roles Anywhere profile.

Security:
- Never fall back to local credentials after AWS failure.
- Only approved AWS profiles are permitted.
- Cache secrets separately for each AWS profile.
- Never log or display credential values.
"""

import json
import os
from functools import lru_cache

from dotenv import load_dotenv


SECRET_NAME = "my-trading-simulator/api-credentials"
AWS_REGION = "us-east-2"

AWS_PROFILE_NAME = "my-trading-simulator"
SCHWAB_AWS_PROFILE_NAME = "my-trading-simulator-schwab"

ALLOWED_AWS_PROFILES = frozenset({
    AWS_PROFILE_NAME,
    SCHWAB_AWS_PROFILE_NAME,
})

ALLOWED_CREDENTIALS = frozenset({
    "OPENAI_API_KEY",
    "SCHWAB_APP_KEY",
    "SCHWAB_APP_SECRET",
})


def get_aws_profile() -> str:
    """Select only an explicitly approved AWS profile."""
    profile = os.getenv(
        "MY_TRADING_SIMULATOR_AWS_PROFILE",
        AWS_PROFILE_NAME,
    ).strip()

    if profile not in ALLOWED_AWS_PROFILES:
        raise ValueError(
            "Unsupported AWS credential profile"
        )

    return profile


@lru_cache(maxsize=2)
def _load_aws_credentials(
    profile_name: str = AWS_PROFILE_NAME,
) -> dict[str, str]:
    """Retrieve credentials, cached separately by AWS profile."""
    if profile_name not in ALLOWED_AWS_PROFILES:
        raise ValueError(
            "Unsupported AWS credential profile"
        )

    import boto3

    try:
        session = boto3.Session(
            profile_name=profile_name,
            region_name=AWS_REGION,
        )

        client = session.client("secretsmanager")

        response = client.get_secret_value(
            SecretId=SECRET_NAME,
        )

        payload = json.loads(response["SecretString"])

    except Exception:
        # Never expose AWS exception details or credential data.
        raise RuntimeError(
            "Cannot retrieve application credentials "
            "from Secrets Manager"
        ) from None

    if not isinstance(payload, dict):
        raise RuntimeError(
            "Secrets Manager credentials have invalid format"
        )

    return payload


def get_credential(name: str) -> str:
    """Retrieve an allowlisted credential from the selected source."""
    if name not in ALLOWED_CREDENTIALS:
        raise ValueError(
            f"Unsupported credential: {name}"
        )

    load_dotenv(override=False)

    source = os.getenv(
        "MY_TRADING_SIMULATOR_CREDENTIAL_SOURCE",
        "local",
    ).strip().lower()

    if source == "aws":
        profile_name = get_aws_profile()

        value = _load_aws_credentials(
            profile_name
        ).get(name)

    elif source == "local":
        value = os.getenv(name)

    else:
        raise ValueError(
            f"Invalid credential source: {source}"
        )

    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(
            f"Credential {name} is not configured"
        )

    return value.strip()
