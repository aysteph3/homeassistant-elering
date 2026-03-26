"""Security and reliability hardening tests for API client."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from custom_components.elering_estfeed.api import (
    EleringEstfeedApiClient,
    _validate_measurements,
    is_valid_api_host,
)


class _FakeResponse:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload
        self.headers: dict[str, str] = {}

    async def json(self, content_type: Any = None) -> dict[str, Any]:
        return self._payload


class _FakeCtx:
    def __init__(self, response: _FakeResponse, delay: float = 0.0) -> None:
        self._response = response
        self._delay = delay

    async def __aenter__(self) -> _FakeResponse:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._response

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse], delay: float = 0.0) -> None:
        self._responses = responses
        self._delay = delay
        self.post_calls = 0
        self.request_calls = 0

    def post(self, *args: Any, **kwargs: Any) -> _FakeCtx:
        self.post_calls += 1
        return _FakeCtx(self._responses[min(self.post_calls - 1, len(self._responses) - 1)], self._delay)

    def request(self, *args: Any, **kwargs: Any) -> _FakeCtx:
        self.request_calls += 1
        return _FakeCtx(self._responses[min(self.request_calls - 1, len(self._responses) - 1)])


def test_api_host_validation() -> None:
    assert is_valid_api_host("https://estfeed.elering.ee")
    assert is_valid_api_host("https://api.elering.ee")
    assert not is_valid_api_host("http://estfeed.elering.ee")
    assert not is_valid_api_host("https://evil.example.com")


def test_validate_measurements_filters_invalid_rows() -> None:
    result = _validate_measurements(
        [
            {"timestamp": "2025-01-01T00:00:00+0000", "value": 1},
            {"value": 2},
            "bad",
        ]
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_token_refresh_is_locked() -> None:
    session = _FakeSession(
        [_FakeResponse(200, {"access_token": "tok", "expires_in": 300})],
        delay=0.05,
    )
    client = EleringEstfeedApiClient(
        api_host="https://estfeed.elering.ee",
        client_id="id",
        client_secret="secret",
        session=session,  # type: ignore[arg-type]
    )

    token1, token2 = await asyncio.gather(
        client.async_get_access_token(), client.async_get_access_token()
    )

    assert token1 == "tok"
    assert token2 == "tok"
    assert session.post_calls == 1


@pytest.mark.asyncio
async def test_request_retries_transient_failure() -> None:
    session = _FakeSession(
        [
            _FakeResponse(500, {}),
            _FakeResponse(200, {"ok": True}),
        ]
    )
    client = EleringEstfeedApiClient(
        api_host="https://estfeed.elering.ee",
        client_id="id",
        client_secret="secret",
        session=session,  # type: ignore[arg-type]
    )

    from unittest.mock import AsyncMock

    client.async_get_access_token = AsyncMock(return_value="tok")

    result = await client._async_request("GET", "/api/public/v1/metering-data")
    assert result["ok"] is True
    assert session.request_calls == 2
