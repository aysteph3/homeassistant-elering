"""Diagnostics support for Elering Estfeed."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_EIC, DOMAIN
from .coordinator import EleringEstfeedCoordinator

TO_REDACT = {CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_EIC}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {
        "config_entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "config_entry_options": dict(entry.options),
    }

    coordinator: EleringEstfeedCoordinator | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id)
    )

    if coordinator is not None:
        data["coordinator_data"] = _sanitize_coordinator_data(coordinator.data)
        data["eic"] = _redact_eic(coordinator.eic)
        data["commodity_type"] = coordinator.commodity_type
        data["update_interval_seconds"] = (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        )
        data["resolution"] = coordinator.resolution
        data["rate_limit_info"] = coordinator.client.rate_limit_info
        data["history"] = {
            "available": coordinator.history.history_available,
            "points": coordinator.history.history_points,
        }
    else:
        # Entry may be disabled or skipped via commodity toggle.
        data["coordinator_data"] = None

    return data


def _redact_eic(eic: str) -> str:
    """Redact EIC while keeping a recognizable suffix for support use."""
    if len(eic) <= 4:
        return "***"
    return f"***{eic[-4:]}"


def _sanitize_coordinator_data(payload: Any) -> dict[str, Any] | None:
    """Sanitize coordinator payload for share-safe diagnostics."""
    if not isinstance(payload, dict):
        return None

    numeric_fields = 0
    keys = []
    for key, value in payload.items():
        keys.append(key)
        if isinstance(value, (int, float)):
            numeric_fields += 1

    return {
        "field_count": len(payload),
        "numeric_field_count": numeric_fields,
        "keys": sorted(keys),
        "has_timestamp": "timestamp" in payload,
    }
