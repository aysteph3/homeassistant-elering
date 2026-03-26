"""Tests for the Elering Estfeed config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.elering_estfeed.const import (
    CONF_API_HOST,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_COMMODITY_TYPE,
    CONF_EIC,
    DEFAULT_API_HOST,
    DOMAIN,
)
from custom_components.elering_estfeed.config_flow import EleringEstfeedConfigFlow

from .conftest import MOCK_CLIENT_ID, MOCK_CLIENT_SECRET, MOCK_EIC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flow() -> EleringEstfeedConfigFlow:
    """Instantiate a flow with a minimal hass mock."""
    flow = EleringEstfeedConfigFlow()
    return flow


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_config_flow_success(
    mock_metering_points: list[dict[str, Any]],
) -> None:
    """Test the happy-path config flow: credentials → EIC selection → entry."""

    with (
        patch(
            "custom_components.elering_estfeed.config_flow.async_get_clientsession"
        ),
        patch(
            "custom_components.elering_estfeed.config_flow.EleringEstfeedApiClient"
        ) as mock_cls,
    ):
        mock_client = AsyncMock()
        mock_client.async_get_access_token = AsyncMock(return_value="tok")
        mock_client.async_get_metering_points = AsyncMock(
            return_value=mock_metering_points
        )
        mock_cls.return_value = mock_client

        flow = _flow()

        # Provide a minimal hass-like mock with async_set_unique_id support
        flow.hass = AsyncMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = lambda: None  # type: ignore[assignment]

        # ── Step 1: submit credentials ────────────────────────────
        result = await flow.async_step_user(
            user_input={
                CONF_API_HOST: DEFAULT_API_HOST,
                CONF_CLIENT_ID: MOCK_CLIENT_ID,
                CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
            }
        )

        # The flow should transition to step 2 (show form for EIC selection).
        assert result["type"] == "form"
        assert result["step_id"] == "select_eic"

        # ── Step 2: select EIC ────────────────────────────────────
        result2 = await flow.async_step_select_eic(
            user_input={CONF_EIC: MOCK_EIC}
        )

        assert result2["type"] == "create_entry"
        assert result2["data"][CONF_EIC] == MOCK_EIC
        assert result2["data"][CONF_COMMODITY_TYPE] == "ELECTRICITY"
        assert result2["data"][CONF_CLIENT_ID] == MOCK_CLIENT_ID


@pytest.mark.asyncio
async def test_config_flow_invalid_auth(
) -> None:
    """Test that invalid credentials surface an error on step 1."""
    from custom_components.elering_estfeed.api import EleringAuthError

    with (
        patch(
            "custom_components.elering_estfeed.config_flow.async_get_clientsession"
        ),
        patch(
            "custom_components.elering_estfeed.config_flow.EleringEstfeedApiClient"
        ) as mock_cls,
    ):
        mock_client = AsyncMock()
        mock_client.async_get_access_token = AsyncMock(
            side_effect=EleringAuthError("bad creds")
        )
        mock_cls.return_value = mock_client

        flow = _flow()
        flow.hass = AsyncMock()

        result = await flow.async_step_user(
            user_input={
                CONF_API_HOST: DEFAULT_API_HOST,
                CONF_CLIENT_ID: "bad",
                CONF_CLIENT_SECRET: "bad",
            }
        )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"


@pytest.mark.asyncio
async def test_config_flow_invalid_api_host() -> None:
    """Test that non-HTTPS/non-Elering hosts are rejected."""
    flow = _flow()
    flow.hass = AsyncMock()

    result = await flow.async_step_user(
        user_input={
            CONF_API_HOST: "http://evil.example.com",
            CONF_CLIENT_ID: MOCK_CLIENT_ID,
            CONF_CLIENT_SECRET: MOCK_CLIENT_SECRET,
        }
    )

    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_api_host"
