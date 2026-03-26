"""Config flow for the Elering Estfeed integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    EleringAuthError,
    EleringConnectionError,
    EleringEstfeedApiClient,
    EleringEstfeedError,
    is_valid_api_host,
)
from .const import (
    CONF_API_HOST,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_COMMODITY_TYPE,
    CONF_EIC,
    DEFAULT_API_HOST,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HISTORY_SERVICE_DEFAULT_DAYS,
    OPT_ENABLE_ELECTRICITY,
    OPT_ENABLE_GAS,
    OPT_HISTORY_DAYS,
    OPT_RESOLUTION,
    OPT_SCAN_INTERVAL,
    RESOLUTION_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_HOST, default=DEFAULT_API_HOST): str,
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
    }
)

COMMODITY_LABELS: dict[str, str] = {
    "ELECTRICITY": "Electricity",
    "GAS": "Gas",
}


class EleringEstfeedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Elering Estfeed."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._user_input: dict[str, Any] = {}
        self._client: EleringEstfeedApiClient | None = None
        self._metering_points: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    # ------------------------------------------------------------------
    # Step 1 – credentials
    # ------------------------------------------------------------------

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the credentials step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not is_valid_api_host(user_input[CONF_API_HOST]):
                errors["base"] = "invalid_api_host"
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                )

            session = async_get_clientsession(self.hass)
            client = EleringEstfeedApiClient(
                api_host=user_input[CONF_API_HOST],
                client_id=user_input[CONF_CLIENT_ID],
                client_secret=user_input[CONF_CLIENT_SECRET],
                session=session,
            )

            error = await self._async_validate_credentials(client)
            if error:
                errors["base"] = error
            else:
                mp_error = await self._async_fetch_metering_points(client)
                if mp_error:
                    errors["base"] = mp_error
                else:
                    self._user_input = user_input
                    self._client = client
                    return await self.async_step_select_eic()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2 – select metering point
    # ------------------------------------------------------------------

    async def async_step_select_eic(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Let the user pick one metering point from the discovered list."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_eic = user_input[CONF_EIC]

            await self.async_set_unique_id(selected_eic)
            self._abort_if_unique_id_configured()

            point = next(
                (p for p in self._metering_points if p.get("eic") == selected_eic),
                None,
            )
            raw_commodity = (
                (point.get("commodityType") or "").upper() if point else ""
            )
            commodity_label = COMMODITY_LABELS.get(raw_commodity, raw_commodity)

            title = f"{DEFAULT_NAME} – {selected_eic}"
            if commodity_label:
                title = f"{DEFAULT_NAME} – {selected_eic} ({commodity_label})"

            return self.async_create_entry(
                title=title,
                data={
                    **self._user_input,
                    CONF_EIC: selected_eic,
                    CONF_COMMODITY_TYPE: raw_commodity,
                },
            )

        eic_options: dict[str, str] = {}
        for point in self._metering_points:
            eic = point.get("eic", "")
            raw_type = (point.get("commodityType") or "").upper()
            label = COMMODITY_LABELS.get(raw_type, raw_type)
            valid_from = point.get("validFrom", "")
            valid_to = point.get("validTo", "")
            period = ""
            if valid_from:
                period = f", from {valid_from}"
                if valid_to:
                    period += f" to {valid_to}"
            eic_options[eic] = f"{eic} ({label}{period})"

        schema = vol.Schema(
            {vol.Required(CONF_EIC): vol.In(eic_options)}
        )

        return self.async_show_form(
            step_id="select_eic",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            entry_data["entry_id"]
        )
        self._user_input = {
            CONF_API_HOST: entry_data.get(CONF_API_HOST, DEFAULT_API_HOST),
            CONF_CLIENT_ID: entry_data.get(CONF_CLIENT_ID, ""),
            CONF_CLIENT_SECRET: "",
        }
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reauthentication confirmation."""
        errors: dict[str, str] = {}

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_API_HOST,
                    default=self._user_input.get(CONF_API_HOST, DEFAULT_API_HOST),
                ): str,
                vol.Required(
                    CONF_CLIENT_ID,
                    default=self._user_input.get(CONF_CLIENT_ID, ""),
                ): str,
                vol.Required(CONF_CLIENT_SECRET): str,
            }
        )

        if user_input is not None:
            if not is_valid_api_host(user_input[CONF_API_HOST]):
                errors["base"] = "invalid_api_host"
            else:
                session = async_get_clientsession(self.hass)
                client = EleringEstfeedApiClient(
                    api_host=user_input[CONF_API_HOST],
                    client_id=user_input[CONF_CLIENT_ID],
                    client_secret=user_input[CONF_CLIENT_SECRET],
                    session=session,
                )
                error = await self._async_validate_credentials(client)
                if error:
                    errors["base"] = error
                elif self._reauth_entry is not None:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={**self._reauth_entry.data, **user_input},
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Options flow hook
    # ------------------------------------------------------------------

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return EleringEstfeedOptionsFlow(config_entry)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _async_validate_credentials(
        client: EleringEstfeedApiClient,
    ) -> str | None:
        """Try to obtain an access token. Return an error key or None."""
        try:
            await client.async_get_access_token()
        except EleringAuthError:
            return "invalid_auth"
        except EleringConnectionError:
            return "cannot_connect"
        except EleringEstfeedError:
            return "unknown"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during credential validation")
            return "unknown"
        return None

    async def _async_fetch_metering_points(
        self,
        client: EleringEstfeedApiClient,
    ) -> str | None:
        """Fetch metering points. Return an error key or None."""
        try:
            self._metering_points = await client.async_get_metering_points()
        except EleringAuthError:
            return "invalid_auth"
        except EleringConnectionError:
            return "cannot_connect"
        except EleringEstfeedError:
            return "unknown"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error fetching metering points")
            return "unknown"

        if not self._metering_points:
            return "no_metering_points"

        return None


# ======================================================================
# Options flow
# ======================================================================


class EleringEstfeedOptionsFlow(OptionsFlow):
    """Handle options for Elering Estfeed."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options

        resolution_choices = list(RESOLUTION_OPTIONS.keys())

        schema = vol.Schema(
            {
                vol.Optional(
                    OPT_SCAN_INTERVAL,
                    default=current.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=60, max=3600)),
                vol.Optional(
                    OPT_RESOLUTION,
                    default=current.get(OPT_RESOLUTION, "1h"),
                ): vol.In(resolution_choices),
                vol.Optional(
                    OPT_HISTORY_DAYS,
                    default=current.get(
                        OPT_HISTORY_DAYS, HISTORY_SERVICE_DEFAULT_DAYS
                    ),
                ): vol.All(int, vol.Range(min=0, max=365)),
                vol.Optional(
                    OPT_ENABLE_ELECTRICITY,
                    default=current.get(OPT_ENABLE_ELECTRICITY, True),
                ): bool,
                vol.Optional(
                    OPT_ENABLE_GAS,
                    default=current.get(OPT_ENABLE_GAS, True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
