# Elering Estfeed for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/aysteph3/homeassistant-elering)](https://github.com/aysteph3/homeassistant-elering/releases)
[![License](https://img.shields.io/github/license/aysteph3/homeassistant-elering)](LICENSE)

A production-minded custom integration for [Home Assistant](https://www.home-assistant.io/) that connects to the Elering Estfeed/Datahub API and exposes metering data as sensors.

> This integration uses **official API credentials** (OAuth2 client credentials) for Estfeed access. It is **not** a Smart-ID/browser login automation for the consumer portal.

## Features

- OAuth2 client-credentials authentication against Elering SSO
- Guided config flow with metering point (EIC) discovery
- Dynamic sensor creation from numeric metering fields returned by the API
- Built-in client-side rate limiting and retry handling
- Optional historical backfill with local cache in Home Assistant storage
- Reauthentication and options flow support (scan interval, resolution, commodity toggles)
- Diagnostics support with secret redaction

## Requirements / Prerequisites

Before setup, ensure you have:

- A working Home Assistant installation (minimum version is defined in `manifest.json`)
- Valid Estfeed/Datahub technical API credentials:
  - `client_id`
  - `client_secret`
- Access rights to at least one metering point (EIC) via those credentials

If you only use the Elering consumer web portal login flow (for example Smart-ID in a browser), request API-oriented credentials/access first.

## Installation via HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Go to **Integrations** → **⋮** → **Custom repositories**.
3. Add this repository URL:
   - `https://github.com/aysteph3/homeassistant-elering`
4. Category: **Integration**.
5. Install **Elering Estfeed** from HACS.
6. Restart Home Assistant.

## Manual Installation

1. Download the latest release from GitHub.
2. Copy `custom_components/elering_estfeed` to:
   - `<config>/custom_components/elering_estfeed`
3. Restart Home Assistant.

## Configuration / Setup

1. In Home Assistant, open **Settings → Devices & Services**.
2. Click **Add Integration** and select **Elering Estfeed**.
3. Enter:
   - API host (default: `https://estfeed.elering.ee`)
   - Client ID
   - Client Secret
4. Select the discovered metering point (EIC).
5. Complete setup; sensors are created automatically.

### Options after setup

Use **Configure** on the integration card to adjust:

- Scan interval
- Data resolution (`15min`, `1h`, `1w`, `1m`)
- History backfill days
- Commodity toggles (electricity/gas)

## Authentication

This integration authenticates using OAuth2 `client_credentials` against Elering SSO token endpoint(s), then uses that token for Estfeed API calls.

- Credentials are provided during config flow.
- Token usage is cached with early refresh handling.
- Reauthentication flow is supported if credentials change.

Again: this is API credential auth, not browser-session or Smart-ID portal scraping.

## Data / Entities Provided

The integration creates entities per configured metering point:

- **Metering sensors:** numeric values from Estfeed payloads (for example energy/power-related fields when present)
- **Rate-limit diagnostic sensors:** request timing and blocked-request counters; optional server rate-limit headers when returned
- **History diagnostic sensors:** cache availability and cached point count

It also registers service:

- `elering_estfeed.fetch_history` — manually trigger historical fetch (1–365 days)

## Security & Privacy Notes

- API host validation is restricted to HTTPS and `*.elering.ee`
- Sensitive fields are redacted in diagnostics output
- EIC values in diagnostics are partially masked
- Entity unique IDs are derived from hashed EIC values for privacy-oriented identifiers

As with any Home Assistant custom integration, protect your HA instance, backups, and secrets.

## Troubleshooting

If setup or updates fail:

1. Verify client credentials are valid and have Datahub/Estfeed API rights.
2. Confirm API host is correct and reachable.
3. Check Home Assistant logs for `custom_components.elering_estfeed`.
4. Use **Reconfigure/Reauthenticate** from the integration card if credentials changed.
5. If you see sparse data, verify EIC access scope and selected commodity.

## Diagnostics

Home Assistant diagnostics are supported for this integration and are intended for safe issue reporting:

- Credentials are redacted
- EIC is masked
- Payload diagnostics are summarized/sanitized

Even with redaction, review exported diagnostics before sharing publicly.

## Limitations

- Requires API-level Estfeed/Datahub access (not just consumer portal access)
- Data availability and fields depend on the metering point and API response
- Polling integrations are subject to network/API availability and rate limits
- This integration is not part of Home Assistant Core

## Contributing

Issues and pull requests are welcome.

When contributing:

- Keep changes focused and testable
- Include clear reproduction steps for bug reports
- Avoid including secrets or full unredacted diagnostics in tickets

## Release Checklist

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for a short pre-release checklist (HACS metadata, structure, config flow, diagnostics safety, README rendering, release creation).

## Disclaimer

This is an independent community custom integration and is not officially endorsed by Elering or the Home Assistant project.

## Support

- Open an issue: <https://github.com/aysteph3/homeassistant-elering/issues>
- If this project helps you, consider starring the repository to support maintenance.

## 🙏 Credits

This integration is based on the work of  
[KaarelKelk/homeassistant-elering](https://github.com/KaarelKelk/homeassistant-elering).

The original project provided the foundation for this implementation.  
This version includes additional improvements such as security hardening, diagnostics safety, and enhanced reliability.
