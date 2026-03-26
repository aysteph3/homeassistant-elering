"""DataUpdateCoordinator for Elering Estfeed."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import EleringAuthError, EleringEstfeedApiClient, EleringEstfeedError
from .const import DEFAULT_DATA_WINDOW_HOURS, DEFAULT_RESOLUTION, DEFAULT_SCAN_INTERVAL, DOMAIN
from .history import EleringHistoryStore

_LOGGER = logging.getLogger(__name__)


class EleringEstfeedCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Elering Estfeed metering data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: EleringEstfeedApiClient,
        eic: str,
        commodity_type: str,
        history: EleringHistoryStore,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        resolution: str = DEFAULT_RESOLUTION,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.eic = eic
        self.commodity_type = commodity_type  # "ELECTRICITY" | "GAS"
        self.history = history
        self.resolution = resolution

    def update_options(self, scan_interval: int, resolution: str) -> None:
        """Apply new options from the options flow."""
        self.update_interval = timedelta(seconds=scan_interval)
        self.resolution = resolution
        _LOGGER.debug(
            "Coordinator options updated: scan_interval=%ds, resolution=%s",
            scan_interval,
            resolution,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest metering data for the configured EIC.

        Requests data for the last DEFAULT_DATA_WINDOW_HOURS hours and
        returns the full latest data-point dict (all fields preserved).
        If no data is available, returns an empty dict.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=DEFAULT_DATA_WINDOW_HOURS)

        try:
            measurements = await self.client.async_get_metering_data(
                eic=self.eic,
                start=start,
                end=now,
                resolution=self.resolution,
            )
        except EleringAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for EIC {self.eic}: {err}"
            ) from err
        except EleringEstfeedError as err:
            raise UpdateFailed(
                f"Error fetching metering data for {self.eic}: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error fetching metering data for {self.eic}: {err}"
            ) from err

        latest: dict[str, Any] = {}
        if measurements:
            latest = measurements[-1]

        _LOGGER.debug(
            "Coordinator update for EIC %s: %d measurement(s), latest keys=%s",
            self.eic,
            len(measurements),
            list(latest.keys()) if latest else "none",
        )

        return latest
