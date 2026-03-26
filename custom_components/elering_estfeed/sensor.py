"""Sensor platform for Elering Estfeed."""

from __future__ import annotations

import logging
import re
from hashlib import blake2b
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EleringEstfeedCoordinator

_LOGGER = logging.getLogger(__name__)

# Keys that are never exposed as metric sensors (metadata, not metrics).
_SKIP_KEYS: set[str] = {
    "timestamp",
    "resolution",
    "meteringPointEic",
    "eic",
    "commodityType",
    "unit",
}

# Friendly commodity labels for sensor names.
_COMMODITY_LABELS: dict[str, str] = {
    "ELECTRICITY": "Electricity",
    "GAS": "Gas",
}

# Diagnostic sensors that are always created (rate-limit).
_DIAG_ALWAYS: tuple[tuple[str, str, SensorDeviceClass | None], ...] = (
    ("last_request_time", "Last Request Time", SensorDeviceClass.TIMESTAMP),
    ("next_allowed_time", "Next Allowed Time", SensorDeviceClass.TIMESTAMP),
    ("blocked_requests_count", "Blocked Requests", None),
)

# Diagnostic sensors created only when the server returns rate-limit headers.
_DIAG_HEADER_KEYS: tuple[tuple[str, str], ...] = (
    ("rate_limit_limit", "Rate Limit"),
    ("rate_limit_remaining", "Rate Limit Remaining"),
    ("rate_limit_reset", "Rate Limit Reset"),
)

# Diagnostic sensors for history cache state.
_DIAG_HISTORY: tuple[tuple[str, str], ...] = (
    ("history_available", "History Available"),
    ("history_points", "History Points"),
)


# ------------------------------------------------------------------
# Unit / device-class inference for metering metrics
# ------------------------------------------------------------------


def _classify_metric(
    key: str,
    unit_hint: str | None,
) -> tuple[
    SensorDeviceClass | None,
    SensorStateClass | None,
    str | None,
]:
    """Infer device_class, state_class, and native_unit from metric key/unit.

    Returns (device_class, state_class, native_unit_of_measurement).
    """
    hint = (unit_hint or "").lower().strip()
    key_lower = key.lower()

    # --- energy (kWh) ---
    if hint in ("kwh", "kwht") or "kwh" in key_lower or "energy" in key_lower:
        return (
            SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL_INCREASING,
            UnitOfEnergy.KILO_WATT_HOUR,
        )

    # --- power (kW) ---
    if hint == "kw" or "power" in key_lower:
        return (
            SensorDeviceClass.POWER,
            SensorStateClass.MEASUREMENT,
            UnitOfPower.KILO_WATT,
        )

    # Fallback – generic measurement, no unit.
    return (None, SensorStateClass.MEASUREMENT, unit_hint or None)


def _key_to_name(key: str) -> str:
    """Convert a camelCase or snake_case metric key to a human-readable name.

    Examples:
        "energyIn"  -> "Energy In"
        "reactive_power" -> "Reactive Power"
    """
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key)
    spaced = spaced.replace("_", " ")
    return spaced.title()


def _build_device_info(eic: str, commodity: str) -> DeviceInfo:
    """Build a DeviceInfo that groups all entities under one HA device."""
    commodity_label = _COMMODITY_LABELS.get(commodity, commodity)
    return DeviceInfo(
        identifiers={(DOMAIN, eic)},
        name=(
            f"Estfeed Meter ({commodity_label})"
            if commodity_label
            else "Estfeed Meter"
        ),
        manufacturer="Elering",
        model="Estfeed Metering Point",
        entry_type=DeviceEntryType.SERVICE,
    )


def _eic_hash(eic: str) -> str:
    """Return a short stable privacy-safe ID derived from EIC."""
    return blake2b(eic.encode(), digest_size=6).hexdigest()


# ------------------------------------------------------------------
# Platform setup
# ------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Elering Estfeed sensor entities from a config entry."""
    coordinator: EleringEstfeedCoordinator = hass.data[DOMAIN][entry.entry_id]

    latest = coordinator.data or {}
    commodity = coordinator.commodity_type
    eic = coordinator.eic
    commodity_label = _COMMODITY_LABELS.get(commodity, commodity)
    device_info = _build_device_info(eic, commodity)

    entities: list[SensorEntity] = []

    # ── Metering metric sensors ──────────────────────────────────────
    for key, value in latest.items():
        if key in _SKIP_KEYS:
            continue
        if not isinstance(value, (int, float)):
            continue

        unit_hint = latest.get("unit")
        device_class, state_class, native_unit = _classify_metric(key, unit_hint)

        entities.append(
            EleringEstfeedSensor(
                coordinator=coordinator,
                metric_key=key,
                eic=eic,
                commodity=commodity,
                commodity_label=commodity_label,
                sensor_name=_key_to_name(key),
                device_class=device_class,
                state_class=state_class,
                native_unit=native_unit,
                device_info=device_info,
            )
        )

    # ── Diagnostic rate-limit sensors (always created) ───────────────
    for diag_key, diag_name, diag_device_class in _DIAG_ALWAYS:
        entities.append(
            EleringRateLimitSensor(
                coordinator=coordinator,
                diag_key=diag_key,
                eic=eic,
                sensor_name=diag_name,
                device_class=diag_device_class,
                device_info=device_info,
            )
        )

    # ── Diagnostic rate-limit sensors (header-based, conditional) ────
    rl_info = coordinator.client.rate_limit_info
    for header_key, header_name in _DIAG_HEADER_KEYS:
        if header_key in rl_info:
            entities.append(
                EleringRateLimitSensor(
                    coordinator=coordinator,
                    diag_key=header_key,
                    eic=eic,
                    sensor_name=header_name,
                    device_class=None,
                    device_info=device_info,
                )
            )

    # ── Diagnostic history sensors ───────────────────────────────────
    for hist_key, hist_name in _DIAG_HISTORY:
        entities.append(
            EleringHistorySensor(
                coordinator=coordinator,
                diag_key=hist_key,
                eic=eic,
                sensor_name=hist_name,
                device_info=device_info,
            )
        )

    _LOGGER.debug(
        "Creating %d sensor(s) for EIC %s: %s",
        len(entities),
        eic,
        [
            getattr(e, "metric_key", None) or getattr(e, "_diag_key", None)
            for e in entities
        ],
    )

    ent_reg = er.async_get(hass)
    for entity in entities:
        old_unique_id = getattr(entity, "legacy_unique_id", None)
        new_unique_id = getattr(entity, "unique_id", None)
        if not old_unique_id or not new_unique_id or old_unique_id == new_unique_id:
            continue
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if entity_id:
            ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)

    async_add_entities(entities)


# ------------------------------------------------------------------
# Metering metric entity
# ------------------------------------------------------------------


class EleringEstfeedSensor(
    CoordinatorEntity[EleringEstfeedCoordinator],
    SensorEntity,
):
    """Representation of a single Elering Estfeed metric sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EleringEstfeedCoordinator,
        metric_key: str,
        eic: str,
        commodity: str,
        commodity_label: str,
        sensor_name: str,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        native_unit: str | None,
        device_info: DeviceInfo,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.metric_key = metric_key
        eic_id = _eic_hash(eic)

        self.legacy_unique_id = f"{eic}_{commodity.lower()}_{metric_key}".lower()
        self._attr_unique_id = f"{eic_id}_{commodity.lower()}_{metric_key}".lower()
        self._attr_name = f"{commodity_label} {sensor_name}"
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = native_unit
        self._attr_device_info = device_info

    @property
    def native_value(self) -> float | None:
        """Return the current value of this metric."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.metric_key)
        if isinstance(value, (int, float)):
            return value
        return None


# ------------------------------------------------------------------
# Diagnostic rate-limit entity
# ------------------------------------------------------------------


class EleringRateLimitSensor(
    CoordinatorEntity[EleringEstfeedCoordinator],
    SensorEntity,
):
    """Diagnostic sensor exposing API rate-limit state."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EleringEstfeedCoordinator,
        diag_key: str,
        eic: str,
        sensor_name: str,
        device_class: SensorDeviceClass | None,
        device_info: DeviceInfo,
    ) -> None:
        """Initialise the diagnostic sensor."""
        super().__init__(coordinator)
        self._diag_key = diag_key
        eic_id = _eic_hash(eic)

        self.legacy_unique_id = f"{eic}_diag_{diag_key}".lower()
        self._attr_unique_id = f"{eic_id}_diag_{diag_key}".lower()
        self._attr_name = f"Estfeed {sensor_name}"
        self._attr_device_class = device_class
        self._attr_device_info = device_info

        # Blocked count is a monotonically increasing counter.
        if diag_key == "blocked_requests_count":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> Any:
        """Return the current value from the API client's rate-limit info."""
        info = self.coordinator.client.rate_limit_info
        return info.get(self._diag_key)


# ------------------------------------------------------------------
# Diagnostic history entity
# ------------------------------------------------------------------


class EleringHistorySensor(
    CoordinatorEntity[EleringEstfeedCoordinator],
    SensorEntity,
):
    """Diagnostic sensor exposing history cache state."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EleringEstfeedCoordinator,
        diag_key: str,
        eic: str,
        sensor_name: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialise the history diagnostic sensor."""
        super().__init__(coordinator)
        self._diag_key = diag_key
        eic_id = _eic_hash(eic)

        self.legacy_unique_id = f"{eic}_diag_{diag_key}".lower()
        self._attr_unique_id = f"{eic_id}_diag_{diag_key}".lower()
        self._attr_name = f"Estfeed {sensor_name}"
        self._attr_device_info = device_info

        if diag_key == "history_points":
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        """Return the current value from the history store."""
        history = self.coordinator.history
        if self._diag_key == "history_available":
            return history.history_available
        if self._diag_key == "history_points":
            return history.history_points
        return None
