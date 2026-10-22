# Overhead for Home Assistant

Port design · 22 October 2026 · approved by the user

## Intended result

An installable Home Assistant custom integration and dashboard card for a Raspberry Pi, adapted from [dmellok/tesserae-widget-overhead](https://github.com/dmellok/tesserae-widget-overhead). The user wants the original functionality on a Home Assistant dashboard. No connection to their Home Assistant instance has been supplied; deliver the installation package and instructions locally, then help with installation when access or configuration is available.

Source inspected: commit `ea70e3998caa714ea061aca17948ba6ca63c8eea`. Retain the upstream AGPL-3.0 license, source attribution, and bundled font licenses. Mark adapted files and include the complete corresponding source with the package.

## User experience

Add **Overhead** in Settings → Devices & services. Use Home Assistant's home coordinates and timezone by default, with configurable observation locations, radius, feed, and optional local receiver. Add an **Overhead** card to any dashboard and choose a view:

| View | Behavior |
| --- | --- |
| Photo | Nearest aircraft's actual airframe photograph, flight details, and a strip of additional aircraft. |
| Plate | A single aircraft with particulars beside its photograph or painting; preserve the original alternative layouts. |
| Cluster | Nearby aircraft as a specimen arrangement scaled by wingspan, or photo cards. |
| Scene | A complete generated picture containing the aircraft and a chosen or current-weather backdrop. |

Preserve callsign, registration, aircraft type, airline, route, altitude, speed, heading, direction, and distance where provided. Preserve original sorting, counts, ground-aircraft inclusion, typography, colors, labels, and photo fallback options. Show useful loading, empty, feed-error, and missing-image states.

Support current traffic and traffic since the card's last scheduled snapshot. A stable card identifier owns its history window. Editor previews and dashboard reopening must not consume a window; a configured snapshot interval advances it. Preserve closest approach and first/last seen times, two-day retention, first-window behavior, and background observation independent of an open browser. These semantics replace Tesserae's panel-render lifecycle explicitly.

## Feature parity

* Positions: adsb.lol, fallback adsb.fi, or a local readsb/dump1090/tar1090 receiver.
* Metadata and pictures: original type/operator mappings, adsbdb routes, credited planespotters.net images, optional airline logos.
* Paintings: original styles, custom style builder and prompts, viewpoints, backdrops, current-weather/time backdrop, cut-outs, and cached output. Preserve optional UFO/spacecraft visitors and credited references.
* Artwork management: a dashboard management view for queued/running/failed work, daily use, Paint now, repaint, delete, earlier versions, and purge. Include sightings/catalogue statistics and the original Chao1 estimate.
* Preview behavior: editor previews may reuse cached artwork but must not start paid jobs. Explicit Paint now or enabled dashboard generation starts jobs. This is a deliberate Home Assistant adaptation of upstream's preview settlement behavior.

## Implementation choices proposed by the builder

Use a Python integration under `custom_components/overhead/` plus a JavaScript custom element `custom:overhead-card`. Preserve upstream rendering, packing, cut-out, metadata, styles, and prompt logic where practical; replace Tesserae-specific imports, routes, and lifecycle calls with explicit Home Assistant adapters. Do not require Tesserae to be installed.

Use Home Assistant config entries and an options flow. A shared coordinator polls public feeds no more frequently than once per minute, and a receiver every thirty seconds. Deduplicate observations for identical locations/feed settings and cache metadata and pictures. Existing synchronous upstream HTTP and Pillow processing must run in executor jobs, with bounded concurrency and lifecycle cleanup; never block Home Assistant's event loop. Bound image and cache sizes for Pi storage. Keep data and artwork in a persistent integration-owned directory under the Home Assistant configuration directory.

Use authenticated Home Assistant WebSocket commands for card snapshots and management. Publish only small sensor values, such as aircraft count and nearest-aircraft metadata, into entity state; keep image payloads and traffic history out of the recorder. Serve media through authenticated access or short-lived signed URLs compatible with image elements. Scope all management operations to the selected entry and require an administrator for artwork deletion, purge, credentials, and generation settings. Frontend rendering must validate image sources and escape external text.

Keep the fal.ai key in server-side integration configuration. AI is disabled until a key and an explicit generation setting are configured. Use a persisted, atomic daily job reservation/cost estimate ledger, bounded workers, and deduplication by artwork key. Never retry an uncertain paid submission automatically. Present the limit as an integration-side estimate, not a guarantee of the provider's billing. Confirm current provider API/model support during implementation. Reuse saved work across dashboard refreshes and restarts.

Initial defaults proposed: Photo view, 25 km radius, nearest first, airborne traffic, sixty-second public-feed polling, airline logos off, AI generation off. These are builder choices, not preferences the user has stated.

## Packaging and validation

Deliver a source folder, installation ZIP, documented manual installation steps, and example dashboard YAML. Include the card resources with the integration. Do not claim HACS catalogue availability; a hosted custom repository or submission is a separate publishing step.

Validate feed fallback, radius/filter/sort behavior, enrichment failures, history windows across restarts and previews, artwork job deduplication and budget reservations, authentication/authorization, and unload/reload cleanup. Adapt applicable upstream tests and run offline tests without paid API calls. Check all four layouts at phone and desktop sizes, including no aircraft and no photos. Validate installation and config flow against an identified supported Home Assistant release; test or clearly report Raspberry Pi deployment and live-provider checks that cannot be performed here.

The final report must distinguish implemented and verified features from unverified live-service behavior. A photo-only fallback is useful during development, but must not be represented as completion of this full-parity design.

## Confirmed and outstanding context

Confirmed: Home Assistant runs on a Raspberry Pi, and the widget belongs on a Home Assistant dashboard. Full upstream functionality is the requested scope.

The Home Assistant version, installation type, and available access are not yet known. These affect final compatibility verification and installation instructions; they do not prevent preparing the port. No existing ADS-B receiver or fal.ai account is assumed. The builder can select internal module structure, cache limits, and test tooling while preserving the behavior above.

## References

* [Original repository and README](https://github.com/dmellok/tesserae-widget-overhead)
* [Home Assistant custom cards](https://contributors.home-assistant.io/frontend/custom-ui/card/)
* [Home Assistant coordinated data fetching](https://contributors.home-assistant.io/core/integrations/fetching-data/)
