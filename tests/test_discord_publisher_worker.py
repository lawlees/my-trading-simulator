"""No network or production-database access: injected fake publisher only."""

from threading import Event

import pytest

from my_trading_simulator.discord.discord_outbox_publisher import PublishResult
from my_trading_simulator.discord.discord_publisher_worker import (
    publish_pending_batch,
    run_continuously,
)


def fake_publisher(*results):
    items = iter(results)
    return lambda: next(items)


def test_empty_queue():
    result = publish_pending_batch(publisher=fake_publisher(PublishResult("EMPTY", None, "none")))
    assert result.outcomes == ()
    assert result.queue_empty


def test_two_messages_sent_then_empty():
    pub = fake_publisher(PublishResult("SENT", 1, "ok"), PublishResult("SENT", 2, "ok"), PublishResult("EMPTY", None, "none"))
    result = publish_pending_batch(publisher=pub)
    assert result.sent == 2
    assert result.queue_empty


def test_failed_and_unknown_not_retried():
    pub = fake_publisher(PublishResult("FAILED", 10, "rejected"), PublishResult("UNKNOWN", 11, "uncertain"), PublishResult("EMPTY", None, "none"))
    result = publish_pending_batch(publisher=pub)
    assert result.sent == 0
    assert result.attention_required == 2
    assert [x.event_id for x in result.outcomes] == [10, 11]


def test_batch_limit():
    pub = fake_publisher(PublishResult("SENT", 1, "ok"), PublishResult("SENT", 2, "ok"))
    result = publish_pending_batch(max_events=2, publisher=pub)
    assert len(result.outcomes) == 2
    assert not result.queue_empty


def test_unexpected_status_fails_safe():
    with pytest.raises(RuntimeError, match="Unexpected"):
        publish_pending_batch(publisher=fake_publisher(PublishResult("SENDING", 1, "unexpected")))


def test_repeated_id_rejected():
    pub = fake_publisher(PublishResult("SENT", 1, "ok"), PublishResult("SENT", 1, "again"))
    with pytest.raises(RuntimeError, match="repeated"):
        publish_pending_batch(publisher=pub)


def test_continuous_stop_event_prevents_polling():
    stop = Event()
    stop.set()
    run_continuously(stop_event=stop, publisher=lambda: (_ for _ in ()).throw(AssertionError("called")))


def test_validation():
    with pytest.raises(ValueError):
        publish_pending_batch(max_events=0)
    with pytest.raises(ValueError):
        run_continuously(poll_seconds=0)
