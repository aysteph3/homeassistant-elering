"""Constants for the Elering Estfeed integration."""

from __future__ import annotations

from typing import Final

DOMAIN = "elering_estfeed"

# Config-entry keys (set during initial setup, immutable)
CONF_API_HOST = "api_host"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_EIC = "eic"
CONF_COMMODITY_TYPE = "commodity_type"

# Options-flow keys (user-configurable after setup)
OPT_SCAN_INTERVAL = "scan_interval"
OPT_RESOLUTION = "resolution"
OPT_HISTORY_DAYS = "history_backfill_days"
OPT_ENABLE_ELECTRICITY = "enable_electricity"
OPT_ENABLE_GAS = "enable_gas"

# Resolution choices (label → API value)
RESOLUTION_OPTIONS: dict[str, str] = {
    "15min": "FIFTEEN_MIN",
    "1h": "HOUR",
    "1w": "WEEK",
    "1m": "MONTH",
}

# Defaults
DEFAULT_API_HOST = "https://estfeed.elering.ee"
DEFAULT_NAME = "Elering Estfeed"

DEFAULT_TOKEN_URL = (
    "https://kc.elering.ee/realms/elering-sso/protocol/openid-connect/token"
)

# API paths (appended to api_host)
METERING_POINTS_PATH = "/api/public/v1/metering-point-eics"
METERING_DATA_PATH = "/api/public/v1/metering-data"

# Metering data defaults
DEFAULT_RESOLUTION = "HOUR"
DEFAULT_DATA_WINDOW_HOURS = 2
DEFAULT_SCAN_INTERVAL = 300

# History backfill
HISTORY_BACKFILL_DAYS = 7  # fetched automatically on first setup
HISTORY_SERVICE_DEFAULT_DAYS = 90  # default when service is called manually
API_MAX_WINDOW_DAYS = 31  # max time-span per API request
STORAGE_VERSION = 1

# Refresh token this many seconds before it actually expires.
TOKEN_EXPIRY_MARGIN = 30

# Client-side rate limiting (seconds between API requests).
RATE_LIMIT_SECONDS = 5

# HTTP hardening
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_RETRY_ATTEMPTS = 3
REQUEST_RETRY_BASE_DELAY_SECONDS = 1.0

# History retention hardening
MAX_HISTORY_RETENTION_DAYS: Final[int] = 400
