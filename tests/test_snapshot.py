"""Tests for picking which gameweek to snapshot (src/snapshot.py)."""

from datetime import datetime, timezone

from src.snapshot import gameweek_to_snapshot

EVENTS = [
    {"id": 7, "deadline_time": "2026-10-03T10:00:00Z"},
    {"id": 8, "deadline_time": "2026-10-24T10:00:00Z"},
    {"id": 9, "deadline_time": "2026-10-31T11:00:00Z"},
]


def _at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def test_before_a_deadline_snapshots_that_gameweek():
    assert gameweek_to_snapshot(EVENTS, _at("2026-10-20T12:00:00")) == 8


def test_just_after_a_deadline_moves_on_to_the_next():
    # GW8's deadline has passed, so its last snapshot is frozen; we now save GW9.
    assert gameweek_to_snapshot(EVENTS, _at("2026-10-24T10:00:01")) == 9


def test_after_the_last_deadline_there_is_nothing_to_save():
    assert gameweek_to_snapshot(EVENTS, _at("2027-06-01T00:00:00")) is None
