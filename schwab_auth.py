
import os

from dotenv import load_dotenv
from schwab.auth import client_from_manual_flow

load_dotenv()

APP_KEY = os.getenv("SCHWAB_APP_KEY")
APP_SECRET = os.getenv("SCHWAB_APP_SECRET")
CALLBACK_URL = os.getenv("SCHWAB_CALLBACK_URL")

if not all([APP_KEY, APP_SECRET, CALLBACK_URL]):
    raise RuntimeError(
        "Missing Schwab credentials in .env"
    )

print("Starting Schwab OAuth authentication...")

client = client_from_manual_flow(
    api_key=APP_KEY,
    app_secret=APP_SECRET,
    callback_url=CALLBACK_URL,
    token_path="schwab_token.json",
)

print("Schwab authentication completed successfully!")
