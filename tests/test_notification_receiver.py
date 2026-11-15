
"""
Integration tests for the notification receiver.

Uses an isolated temporary SQLite database.
Never executes trades or contacts Schwab/Discord.
"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

import my_trading_simulator.api.receiver as receiver
from my_trading_simulator.database.models import IncomingNotification


@pytest.fixture
def api_environment(tmp_path, monkeypatch):
    database_path = tmp_path / "test_notifications.db"

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")
        cursor.close()

    IncomingNotification.__table__.create(bind=engine)

    test_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(
        receiver,
        "SessionLocal",
        test_session_factory,
    )

    headers = {
        "Authorization": f"Bearer {receiver.API_TOKEN}",
    }

    yield {
        "client": TestClient(receiver.app),
        "headers": headers,
        "session_factory": test_session_factory,
    }

    engine.dispose()


def make_payload(
    *,
    source="IPHONE_NOTIFICATION",
    message_text="TEST: SPY calls here",
    key=None,
):
    return {
        "source": source,
        "message_text": message_text,
        "idempotency_key": key or uuid4().hex,
    }


def count_notifications(session_factory):
    with session_factory() as session:
        return session.scalar(
            select(func.count()).select_from(IncomingNotification)
        )


def test_health_endpoint(api_environment):
    response = api_environment["client"].get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_authentication_rejected(api_environment):
    response = api_environment["client"].post(
        "/api/v1/notifications",
        json=make_payload(),
    )

    assert response.status_code == 401
    assert count_notifications(
        api_environment["session_factory"]
    ) == 0


def test_invalid_authentication_rejected(api_environment):
    response = api_environment["client"].post(
        "/api/v1/notifications",
        headers={"Authorization": "Bearer invalid-token"},
        json=make_payload(),
    )

    assert response.status_code == 401


def test_new_notification_saved(api_environment):
    response = api_environment["client"].post(
        "/api/v1/notifications",
        headers=api_environment["headers"],
        json=make_payload(),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["status"] == "RECEIVED"
    assert result["duplicate"] is False

    with api_environment["session_factory"]() as session:
        saved = session.get(
            IncomingNotification,
            result["notification_id"],
        )

        assert saved is not None
        assert saved.message_text == "TEST: SPY calls here"
        assert saved.processing_status == "RECEIVED"


def test_same_request_is_idempotent(api_environment):
    payload = make_payload(key="same-request-12345")
    client = api_environment["client"]
    headers = api_environment["headers"]

    first = client.post(
        "/api/v1/notifications",
        headers=headers,
        json=payload,
    )

    second = client.post(
        "/api/v1/notifications",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["status"] == "RECEIVED"
    assert second.json()["status"] == "DUPLICATE"
    assert second.json()["duplicate"] is True

    assert (
        first.json()["notification_id"]
        == second.json()["notification_id"]
    )

    assert count_notifications(
        api_environment["session_factory"]
    ) == 1


def test_conflicting_idempotency_key_rejected(api_environment):
    client = api_environment["client"]
    headers = api_environment["headers"]

    first = make_payload(
        key="conflict-test-12345",
        message_text="SPY calls",
    )

    second = make_payload(
        key="conflict-test-12345",
        message_text="QQQ puts",
    )

    assert client.post(
        "/api/v1/notifications",
        headers=headers,
        json=first,
    ).status_code == 200

    response = client.post(
        "/api/v1/notifications",
        headers=headers,
        json=second,
    )

    assert response.status_code == 409
    assert count_notifications(
        api_environment["session_factory"]
    ) == 1


def test_cross_source_possible_duplicate(api_environment):
    client = api_environment["client"]
    headers = api_environment["headers"]

    iphone = make_payload(
        source="IPHONE_NOTIFICATION",
        message_text="SPY calls here",
    )

    manual = make_payload(
        source="MANUAL_DISCORD",
        message_text=" SPY   CALLS here ",
    )

    first = client.post(
        "/api/v1/notifications",
        headers=headers,
        json=iphone,
    )

    second = client.post(
        "/api/v1/notifications",
        headers=headers,
        json=manual,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json()["status"] == "RECEIVED"
    assert second.json()["status"] == "POSSIBLE_DUPLICATE"

    assert (
        first.json()["notification_id"]
        != second.json()["notification_id"]
    )

    assert count_notifications(
        api_environment["session_factory"]
    ) == 2


def test_concurrent_same_key_creates_one_record(api_environment):
    payload = make_payload(
        key="concurrent-test-12345",
        message_text="TEST: Concurrent notification",
    )

    headers = api_environment["headers"]

    def submit():
        with TestClient(receiver.app) as client:
            response = client.post(
                "/api/v1/notifications",
                headers=headers,
                json=payload,
            )
            return response

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: submit(), range(2)))

    assert all(response.status_code == 200 for response in responses)

    statuses = sorted(
        response.json()["status"]
        for response in responses
    )

    assert statuses == ["DUPLICATE", "RECEIVED"]

    assert count_notifications(
        api_environment["session_factory"]
    ) == 1


def test_blank_message_rejected(api_environment):
    payload = make_payload(message_text="   ")

    response = api_environment["client"].post(
        "/api/v1/notifications",
        headers=api_environment["headers"],
        json=payload,
    )

    assert response.status_code == 422

    assert count_notifications(
        api_environment["session_factory"]
    ) == 0
