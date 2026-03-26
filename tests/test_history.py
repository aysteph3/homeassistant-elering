"""History retention tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from custom_components.elering_estfeed.history import EleringHistoryStore


def test_history_prunes_old_points() -> None:
    store = EleringHistoryStore(hass=MagicMock(), client=MagicMock(), eic="38ZEE")
    old = (datetime.now(timezone.utc) - timedelta(days=500)).strftime(
        "%Y-%m-%dT%H:%M:%S%z"
    )
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    store._measurements = [{"timestamp": old, "value": 1}, {"timestamp": recent, "value": 2}]
    store._prune()

    assert len(store._measurements) == 1
    assert store._measurements[0]["timestamp"] == recent
