# Verification

Verified on 6 November 2026 using macOS ARM64 and Python 3.14.10 in isolated environments for Home Assistant Core 2026.10.2 and 2026.11.0.

## Results

**29 tests passed for 1.0.2 in each environment**: Core 2026.10.2 with Pillow 12.3.0, and Core 2026.11.0 with Pillow 13.0.0. Both use NumPy 2.3.2. Each complete run emitted six warnings from Home Assistant/aiohttp/backoff dependencies; no test failed. Source compilation, Python name checks and JavaScript syntax checks also passed.

Core 2026.11.0 requires Pillow 13.0.0, conflicting with Overhead 1.0.1's Pillow 12.3.0 pin. The dependency regression check and real resolver both reproduced this conflict before the fix. Overhead 1.0.2 declares `Pillow>=12.3.0,<14.0.0`, allowing Home Assistant's constraints to select its compatible version. Fresh dependency installation through Home Assistant's installer passed under both Core versions. Binary-only resolution for Python 3.14 on `aarch64-unknown-linux-musl` selected Pillow 13.0.0 and NumPy 2.3.2 under November's constraints. GitHub dependency validation now runs for both Core versions. The constraint test reads the bundled constraint file directly, without relying on an internal helper signature that changed in November.

Version 1.0.0's NumPy 2.5.4 pin conflicts with Core 2026.10.2's `package_constraints.txt`, which requires NumPy 2.3.2. The original environment already had 2.5.4 installed, so its setup tests skipped the constrained installation and missed the failure on a fresh Home Assistant installation. The conflict was reproduced with the real dependency resolver. The added regression test fails against 1.0.0's manifest and passes against the corrected manifest.

For 1.0.1, both runtime requirements installed into an empty temporary directory through Home Assistant's own package installer with its actual constraints. A binary-only resolution also succeeded for Python 3.14 on `aarch64-unknown-linux-musl`, the 64-bit Home Assistant OS package platform. These checks establish dependency compatibility; they do not establish execution on a physical Pi. An authenticated request to the real config-flow HTTP endpoint returned the setup form successfully. GitHub validation now checks the dependency constraints and performs a fresh dependency resolution.

The suite covers:

- Real Home Assistant custom-component discovery, dependency setup, config entry setup, creation of two real sensor entities, and unload/worker cleanup.
- Config-flow defaults, coordinate/settings validation, server-only option rejection, administrator restrictions and entry selection.
- Runtime requirements compatible with the tested Home Assistant Core package constraints.
- Feed fallback, malformed/non-finite aircraft values, explicit stale-feed labeling and shared feed polling.
- Closest approach, first/last seen, two-day retention, independent saved windows, non-consuming previews and persisted windows after restart.
- Resetting old traffic windows when the location, radius or feed is changed.
- Preview holds, explicit painting, concurrent deduplication, atomic estimated-budget reservations and recovery after interrupted submissions.
- Automatic resumption of budget-blocked work when the day changes; failed and uncertain submitted requests stay manual.
- Cancelling jobs that have not started on close/reload, without submitting them; refunding only their known-unused reservations.
- Complete painted-sheet rendering through the original prompt, image preparation and cut-out code with a simulated fal result.
- Painting reuse across compatible views, weather backdrop keys, and saved artwork remaining available without current photo metadata.
- Earlier-version restore with invalidation of derived/display image caches, deletion and preservation of budget history during purge.
- All four display views, empty and error messages, desktop/phone sizing without horizontal overflow, visual editor changes, nested preview detection, reconnect and asynchronous entry-selection races.

A fresh read-only reviewer examined the implementation. All five important findings were reproduced with failing tests, fixed, and verified by the passing complete suite. The reviewer found no critical issue. Documentation status was updated; request errors also clear previously stored render data so resize cannot replace the error with an old snapshot.

## Live checks and limits

One read-only public-feed smoke request at the demo coordinates (52.0, 13.0) returned a valid, empty adsb.lol observation with no error. These coordinates are sample data, not the user's location. This establishes connectivity at the time of that check; it does not establish local coverage around the user's Pi.

No paid fal.ai call was made. Model request formats were checked against official fal API documentation and exercised with simulated responses. Live model acceptance, output quality, provider-side billing, and current estimate accuracy remain unverified.

The user's Raspberry Pi, Home Assistant instance and any local receiver were not accessed. Physical Pi performance, dependency installation on the Pi, local flight coverage, and real dashboard installation remain unverified. This package targets Home Assistant 2026.10.0 or newer. It is an independent custom integration, not an integration certified by Home Assistant or a HACS catalogue release.

## Preview artifacts

- [Desktop preview](previews/desktop.png)
- [Phone preview](previews/phone.png)

These are screenshots of the actual custom card and adapted original renderer, using synthetic aircraft positions and a simple synthetic aircraft illustration. They are not live-feed photographs or examples of fal-generated output.

## Reproduce

Install `requirements-dev.txt`, install Playwright Chromium, then run:

```sh
python -m pytest tests -q
python -m compileall -q custom_components
ruff check custom_components/overhead tests --exclude vendor --select F
node --check custom_components/overhead/frontend/overhead-card.js
```

Browser and full Home Assistant lifecycle tests require permission to start local processes and bind a loopback port. Provider calls in the test suite are simulated.
