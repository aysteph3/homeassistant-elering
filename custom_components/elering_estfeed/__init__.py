"""The Elering Estfeed integration."""

from __future__ import annotations

import logging
import asyncio

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    EleringAuthError,
    EleringConnectionError,
    EleringEstfeedApiClient,
    is_valid_api_host,
)
from .const import (
    CONF_API_HOST,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_COMMODITY_TYPE,
    CONF_EIC,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HISTORY_BACKFILL_DAYS,
    HISTORY_SERVICE_DEFAULT_DAYS,
    OPT_ENABLE_ELECTRICITY,
    OPT_ENABLE_GAS,
    OPT_HISTORY_DAYS,
    OPT_RESOLUTION,
    OPT_SCAN_INTERVAL,
    RESOLUTION_OPTIONS,
)
from .coordinator import EleringEstfeedCoordinator
from .history import EleringHistoryStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_FETCH_HISTORY = "fetch_history"
SERVICE_FETCH_HISTORY_SCHEMA = vol.Schema(
    {
        vol.Optional("days", default=HISTORY_SERVICE_DEFAULT_DAYS): vol.All(
            int, vol.Range(min=1, max=365)
        ),
    }
)


def _resolve_resolution(key: str) -> str:
    """Map a user-facing resolution key to the API value."""
    from .const import DEFAULT_RESOLUTION

    return RESOLUTION_OPTIONS.get(key, DEFAULT_RESOLUTION)


def _get_options(entry: ConfigEntry) -> tuple[int, str, int, bool, bool]:
    """Extract options with sensible defaults."""
    scan_interval: int = entry.options.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    resolution_key: str = entry.options.get(OPT_RESOLUTION, "1h")
    resolution = _resolve_resolution(resolution_key)
    history_days: int = entry.options.get(
        OPT_HISTORY_DAYS, HISTORY_SERVICE_DEFAULT_DAYS
    )
    enable_elec: bool = entry.options.get(OPT_ENABLE_ELECTRICITY, True)
    enable_gas: bool = entry.options.get(OPT_ENABLE_GAS, True)
    return scan_interval, resolution, history_days, enable_elec, enable_gas


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Elering Estfeed from a config entry."""
    if not is_valid_api_host(entry.data[CONF_API_HOST]):
        raise ConfigEntryNotReady("Configured API host is invalid or unsafe")

    session = async_get_clientsession(hass)
    client = EleringEstfeedApiClient(
        api_host=entry.data[CONF_API_HOST],
        client_id=entry.data[CONF_CLIENT_ID],
        client_secret=entry.data[CONF_CLIENT_SECRET],
        session=session,
    )

    eic: str = entry.data[CONF_EIC]
    commodity_type: str = entry.data.get(CONF_COMMODITY_TYPE, "")

    scan_interval, resolution, history_days, enable_elec, enable_gas = _get_options(
        entry
    )

    # Skip setup when the commodity is disabled by the user.
    if commodity_type == "ELECTRICITY" and not enable_elec:
        _LOGGER.info("Electricity is disabled for EIC %s – skipping", eic)
        return True
    if commodity_type == "GAS" and not enable_gas:
        _LOGGER.info("Gas is disabled for EIC %s – skipping", eic)
        return True

    # Validate connectivity early – raise ConfigEntryNotReady on transient errors
    # so HA retries automatically instead of marking the entry as failed.
    try:
        await client.async_get_access_token()
    except EleringAuthError as err:
        raise ConfigEntryAuthFailed(
            f"Authentication failed for EIC {eic}: {err}"
        ) from err
    except EleringConnectionError as err:
        raise ConfigEntryNotReady(
            f"Cannot reach Elering API for EIC {eic}: {err}"
        ) from err

    # History store – load cached data from disk.
    history = EleringHistoryStore(hass, client, eic)
    await history.async_load()

    coordinator = EleringEstfeedCoordinator(
        hass,
        client,
        eic=eic,
        commodity_type=commodity_type,
        history=history,
        scan_interval=scan_interval,
        resolution=resolution,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Background history backfill (non-blocking – log warning on failure).
    backfill_days = history_days if history_days > 0 else HISTORY_BACKFILL_DAYS
    if history_days != 0:
        hass.async_create_task(
            _async_backfill(history, eic, backfill_days),
            f"elering_estfeed_backfill_{eic}",
        )

    # Register the fetch_history service once (idempotent).
    if not hass.services.has_service(DOMAIN, SERVICE_FETCH_HISTORY):

        async def handle_fetch_history(call: ServiceCall) -> None:
            """Handle the fetch_history service call."""
            days: int = call.data.get("days", HISTORY_SERVICE_DEFAULT_DAYS)
            semaphore = asyncio.Semaphore(3)

            async def _fetch_for(coord: EleringEstfeedCoordinator) -> None:
                async with semaphore:
                    try:
                        await coord.history.async_fetch_history(days)
                        coord.async_set_updated_data(coord.data or {})
                    except Exception:  # noqa: BLE001
                        _LOGGER.warning(
                            "History fetch service failed for EIC %s",
                            coord.eic,
                            exc_info=True,
                        )

            tasks = [
                _fetch_for(coord)
                for coord in hass.data.get(DOMAIN, {}).values()
                if isinstance(coord, EleringEstfeedCoordinator)
            ]
            if tasks:
                await asyncio.gather(*tasks)

        hass.services.async_register(
            DOMAIN,
            SERVICE_FETCH_HISTORY,
            handle_fetch_history,
            schema=SERVICE_FETCH_HISTORY_SCHEMA,
        )

    # Listen for options changes – reload the entry to apply them.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry when options change."""
    _LOGGER.debug("Options changed for %s – reloading", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_backfill(
    history: EleringHistoryStore, eic: str, days: int
) -> None:
    """Run initial history backfill, logging warnings on failure."""
    try:
        await history.async_fetch_history(days)
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Initial history backfill failed for EIC %s. "
            "Data will be retried via the fetch_history service",
            eic,
            exc_info=True,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Unregister service if no more entries remain.
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, SERVICE_FETCH_HISTORY)

    return unload_ok
