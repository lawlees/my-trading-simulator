"""One-shot Discord publisher for committed SQLite TradeEvent records.

Paper-trading notifications only; never creates or repeats trades.
No HTTP request happens on import. A single call sends at most one event.

Status policy:
  PENDING -> SENDING (committed claim) -> SENT on acknowledged response.
  Known non-delivery -> FAILED (manual review/retry).
  Ambiguous delivery -> UNKNOWN (manual Discord reconciliation before retry).

A process crash after SENDING leaves SENDING for manual reconciliation.
That conservatively avoids duplicate posts; it does not guarantee delivery.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from sqlalchemy import select

from my_trading_simulator.database.models import TradeEvent
from my_trading_simulator.database.session import SessionLocal


class DefiniteDeliveryFailure(Exception):
    """Discord explicitly rejected the message before creating it."""


class UncertainDelivery(Exception):
    """Response was lost or ambiguous: message may already exist."""


@dataclass(frozen=True)
class PublishResult:
    status: str
    event_id: int | None
    detail: str


def _write_lock(session):
    if session.bind.dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _webhook_with_response(webhook_url: str) -> str:
    """Append wait=true so Discord returns an acknowledgement with message ID."""
    parts = urlsplit(webhook_url)
    if (parts.scheme != "https" or parts.hostname not in
            {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}
            or not parts.path.startswith("/api/webhooks/")):
        raise ValueError("Invalid Discord webhook URL")
    params = [(k, v) for k, v in parse_qsl(parts.query) if k != "wait"]
    params.append(("wait", "true"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))


def send_discord_webhook(webhook_url: str, content: str) -> str:
    """POST content and return Discord's confirmed message ID.

    Caller must not automatically retry after UncertainDelivery.
    """
    url = _webhook_with_response(webhook_url)
    request = Request(
        url,
        data=json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "my-trading-simulator-paper/1.0"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read()
    except HTTPError as exc:
        # A 4xx response (including rate limiting) indicates rejection. Do not
        # expose the exception text: it can include the secret webhook URL.
        if 400 <= exc.code < 500:
            raise DefiniteDeliveryFailure(f"Discord HTTP {exc.code}") from None
        raise UncertainDelivery(f"Discord HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError) as exc:
        # Network failures may happen AFTER Discord accepted the message.
        raise UncertainDelivery(f"Discord network error: {type(exc).__name__}") from None
    try:
        message = json.loads(raw)
        message_id = message["id"]
        if not isinstance(message_id, str) or not message_id.isdigit():
            raise ValueError("Missing Discord message id")
    except (ValueError, KeyError, TypeError):
        raise UncertainDelivery("Discord reply contained no valid message ID") from None
    return message_id


def publish_one_pending_event(*, session_factory=None, sender=None,
                              webhook_url: str | None = None) -> PublishResult:
    """Claim and publish ONE pending event; called explicitly by a worker.

    A committed claim prevents concurrent publishers from selecting the same
    event. This function does not automatically retry FAILED/UNKNOWN/SENDING.
    """
    sessions = session_factory or SessionLocal
    send = sender or send_discord_webhook
    if webhook_url is None:
        load_dotenv()
        webhook_url = os.getenv("DISCORD_NOTIFICATION_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("DISCORD_NOTIFICATION_WEBHOOK_URL is not configured")
    # Validate configuration before altering any event.
    _webhook_with_response(webhook_url)

    with sessions.begin() as session:
        _write_lock(session)
        event = session.scalar(select(TradeEvent).where(
            TradeEvent.delivery_status == "PENDING"
        ).order_by(TradeEvent.id).limit(1))
        if event is None:
            return PublishResult("EMPTY", None, "No pending events")
        event.delivery_status = "SENDING"
        event.delivery_attempts += 1
        event_id = event.id
        # Stable visible event identifier helps manual duplicate reconciliation.
        content = f"[Paper simulator event #{event.id}] {event.message}"
        if len(content) > 2000:
            content = content[:1997] + "..."

    # No DB transaction or SQLite write lock is held during network I/O.
    try:
        discord_id = send(webhook_url, content)
        if not isinstance(discord_id, str) or not discord_id.isdigit():
            raise UncertainDelivery("Sender returned no valid Discord message ID")
    except DefiniteDeliveryFailure as exc:
        status, detail = "FAILED", str(exc)
        discord_id = None
    except Exception as exc:
        # Unexpected errors from senders are also potentially ambiguous.
        status = "UNKNOWN"
        detail = str(exc) if isinstance(exc, UncertainDelivery) else f"Sender error: {type(exc).__name__}"
        discord_id = None
    else:
        status, detail = "SENT", "Discord acknowledged message"

    with sessions.begin() as session:
        _write_lock(session)
        event = session.get(TradeEvent, event_id)
        if event is None or event.delivery_status != "SENDING":
            raise RuntimeError("Delivery claim changed; manual reconciliation required")
        event.delivery_status = status
        if status == "SENT":
            event.discord_message_id = discord_id
            event.delivered_at = datetime.now(timezone.utc)
            event.last_error = None
        else:
            event.last_error = detail[:500]
    return PublishResult(status, event_id, detail)
