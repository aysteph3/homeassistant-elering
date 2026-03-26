# Release Checklist

Before publishing a new release:

1. Create a GitHub release (and tag) for the new version.
2. Confirm `hacs.json` exists and metadata is valid.
3. Verify `custom_components/elering_estfeed/` structure is complete.
4. Verify config flow works end-to-end (credentials + EIC selection).
5. Verify diagnostics export is safe (secrets redacted, no sensitive leakage).
6. Verify README renders correctly on GitHub and reflects current behavior.
