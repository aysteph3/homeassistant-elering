"""Diagnostics hardening tests."""

from __future__ import annotations

from custom_components.elering_estfeed.diagnostics import (
    _redact_eic,
    _sanitize_coordinator_data,
)


def test_redact_eic() -> None:
    assert _redact_eic("38ZEE-1000000A-B").startswith("***")
    assert _redact_eic("38ZEE-1000000A-B").endswith("0A-B")


def test_sanitize_coordinator_data() -> None:
    payload = {
        "timestamp": "2025-01-01T00:00:00+0000",
        "energyIn": 1.2,
        "status": "ok",
    }
    result = _sanitize_coordinator_data(payload)
    assert result is not None
    assert result["field_count"] == 3
    assert result["numeric_field_count"] == 1
    assert result["has_timestamp"] is True
