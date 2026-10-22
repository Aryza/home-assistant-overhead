# Overhead for Home Assistant

Aircraft overhead, on your Home Assistant dashboard: **Photo, Plate, Cluster and Scene**, adapted from [dmellok/tesserae-widget-overhead](https://github.com/dmellok/tesserae-widget-overhead). Tracking runs on your Home Assistant server, including when the dashboard is closed. Photos work without a paid account; optional paintings use your own fal.ai account.

This is an independent custom integration, with the original rendering, aircraft metadata, artwork styles, cut-out and packing logic. It does not require Tesserae.

**Target: Home Assistant Core 2026.10.0 or newer, on a current 64-bit Raspberry Pi installation. Tested locally with Core 2026.10.2 and Python 3.14.8.** The Pi itself has not been accessed or tested. Earlier Home Assistant versions are not supported by this package's new config/schema APIs.

## Install with HACS

HACS must already be installed in Home Assistant. Add this custom repository:

**Repository:** `https://github.com/Aryza/home-assistant-overhead`

**Type:** **Integration**

1. Open **HACS → ⋮ → Custom repositories**, paste the repository URL, select **Integration**, and add it.
2. Find **Overhead** in HACS and download it.
3. Restart Home Assistant completely.
4. Open **Settings → Devices & services → Add integration → Overhead** and configure your observation location.
5. Add `/overhead-static/overhead-card.js?v=1.0.0` to your dashboard resources as a **JavaScript module**. Reload the browser and add the **Overhead** card.

```yaml
type: custom:overhead-card
profile_id: living_room_overhead
view: photo
height: 420
```

HACS installs the integration and its bundled card together. Register the dashboard JavaScript resource once using the URL above. No separate frontend repository is needed.

See [HACS custom repository instructions](https://www.hacs.xyz/docs/faq/custom_repositories/) for the repository menu. Home Assistant's built-in integration picker does not accept GitHub URLs directly.

## Manual installation

1. Extract the supplied ZIP on your computer. Copy **`custom_components/overhead`** into your Home Assistant configuration directory, so the final path is **`/config/custom_components/overhead/manifest.json`** on Home Assistant OS. Use your usual Samba, SSH or file-management access. On Container/Core installations, use the mounted configuration directory instead of `/config`.
2. Restart Home Assistant completely. Its integration installer downloads the pinned Pillow and NumPy dependencies; the first restart can take longer on a Pi.
3. Open **Settings → Devices & services → Add integration**, search for **Overhead**, and add it. Home Assistant's home coordinates are prefilled. The default is a 25 km radius with public aircraft feeds. Supply an email or website contact for the planespotters.net photo API.
4. In your dashboard's **Resources** list, add a **JavaScript module** resource with this URL:

   ```text
   /overhead-static/overhead-card.js?v=1.0.0
   ```

   Enable Advanced Mode in your Home Assistant profile if the resource list is hidden. For YAML dashboards, the resource entry is:

   ```yaml
   lovelace:
     resources:
       - url: /overhead-static/overhead-card.js?v=1.0.0
         type: module
   ```

5. Reload the browser, edit your dashboard, add **Overhead**, and choose a view. Or add this manual card:

   ```yaml
   type: custom:overhead-card
   profile_id: living_room_overhead
   view: photo
   height: 420
   ```

Each card needs its own stable `profile_id`. Do not reuse an ID for different cards: it identifies the saved settings and history window. Up to twelve cards can be saved per integration. An administrator must first open the saved dashboard card to register its configuration; other signed-in users can then view it. With multiple Overhead integrations, select the desired location in the visual card editor, which writes `entry_id` for you.

This repository supports HACS installation as a custom repository. It has not been submitted to the default HACS catalogue. Manual installation remains supported.

## Choose a view

| `view` | What it shows |
| --- | --- |
| `photo` | The nearest airframe's photograph, flight details, and additional aircraft along a strip. |
| `plate` | One aircraft beside its particulars, with the original ruled plate and boarding-pass/tiles/poster/split alternatives. |
| `cluster` | A photo log or a specimen arrangement of painted aircraft, scaled by wingspan. |
| `scene` | One complete painted scene, with the selected aircraft and backdrop. Photos are a fallback until a painting exists. |
| `management` | Artwork, daily estimated use, queue/errors, style/card filters, versions and catalogue statistics. |

See [examples/dashboard.yaml](examples/dashboard.yaml) for all four views, traffic history and artwork management.

## Optional AI painting

In **Settings → Devices & services → Overhead → Configure**, add your fal.ai key, choose a daily estimated limit, and explicitly enable generation. The default is **off**, a **US$1 estimated daily limit**, and **one concurrent job**. A zero budget permits no new jobs. API credentials stay in Home Assistant's server configuration and are never sent to dashboard JavaScript.

Set `pictures: paintings` on a Plate, Cluster or Scene card. Each airframe/style/view/backdrop combination is cached. Preserve a style with `style: poster`, choose a different original style in the editor, use `style: builder` with `build_*` fields, or use `style: custom` and `custom_style`. `backdrop: live` uses Open-Meteo weather and sunrise/sunset information. Enable optional visitors with `ufo: 10` (an hourly 10% chance) and a `visitors` list of upstream craft IDs, such as `saucer`, `orb`, `shuttle` or `voyager`.

Editor previews collect requests and show cached artwork or photo/silhouette fallbacks. They do not submit paid requests. Opening the saved dashboard card can generate automatically when generation is enabled. **Paint now** in the management card explicitly submits currently held subjects. Changing a preview's style drops its unused held requests; existing paintings remain in the collection.

```yaml
type: custom:overhead-card
view: management
```

Artwork changes require an administrator. Repaint and deletion actions ask for confirmation. Earlier versions can be restored. Purging artwork retains the spend-reservation ledger. Closing or reloading cancels jobs that have not started; only their known-unused reservations are refunded. Budget-blocked active subjects resume when daily allowance becomes available. An interrupted, failed or uncertain submitted request is never automatically resubmitted; inspect your fal.ai account before choosing Repaint.

Daily limits reserve costs using the original model cost estimates before each submission. **They are integration-side estimates, not a guarantee of fal.ai billing.** Check current provider prices and set a provider-side account limit as appropriate. No paid API request was made while developing or testing this package.

## Tracking, history and storage

The integration asks adsb.lol every sixty seconds, with adsb.fi as fallback. A selected local readsb/dump1090/tar1090 receiver is polled every thirty seconds. Provide an HTTP(S) receiver base URL, such as `http://192.168.1.50:8080`, or the full `aircraft.json` URL. Equivalent observation locations share feed polling. Routes come from adsbdb; airframe photos come from planespotters.net and retain photographer credits.

Use these options for an hourly history sheet:

```yaml
type: custom:overhead-card
profile_id: hourly_traffic
view: cluster
pictures: photos
period: since
snapshot_minutes: 60
count: 12
```

The first history sheet covers the preceding hour of available observations. Later windows chain from the previous snapshot and advance on the configured interval; reopening the dashboard or editing its preview does not consume a window. The background coordinator continues observing without a browser. Each aircraft is shown at closest approach with first/last-seen times. Observations persist across restarts and expire after two days, with a 100,000-point safety cap for busy receivers. A stopped server cannot observe traffic while offline. Changing the observation location, radius or source starts fresh traffic windows; saved artwork is retained.

The integration creates **Aircraft nearby** and **Nearest aircraft** sensors for automations. Full traffic lists and image data travel over Home Assistant's authenticated WebSocket connection, outside entity state and recorder history. Static public files contain only frontend code and silhouettes; photos, artwork and credentials are not published in the static directory.

Data lives under `/config/.storage/overhead/<entry_id>/`. Include it and Home Assistant's config entries in backups. The default 512 MB allowance is divided between re-fetchable network caches and artwork. Artwork admission reserves room for pending images; originals/versions are not silently deleted. The allowance is a practical working limit, not a filesystem quota: history, ledgers and transient processing also use space. Delete artwork through its management view or raise the allowance if admission stops. The catalogue holds at most 2,000 artwork records; thumbnails are included for the latest 100 to keep management responses small.

## Card options

The visual editor exposes common options and an additional-options JSON field. The examples below use YAML. Server connection settings and credentials belong in integration options.

| Option | Values / default |
| --- | --- |
| `entry_id` | Optional with one integration; choose the location in the editor when there are several. |
| `profile_id` | Required for display cards; 1–64 letters, digits, `_` or `-`. |
| `view` | `photo` (default), `plate`, `cluster`, `scene`, `management`. |
| `height` / `aspect_ratio` | Height 200–1400 px, default 420; optional width/height ratio up to 5. |
| `pictures` | `photos` (default) or `paintings`. Photo view always uses photographs. |
| `period` / `snapshot_minutes` | `now` or `since`; scheduled window length 1–1440 minutes, default 60. |
| `order` | `nearest`, `lowest`, `highest`, `largest`, `fastest`. |
| `count` / `strip` | Cluster aircraft count up to 12 / additional Photo aircraft up to 8. |
| `include_ground` | `true` to include aircraft on the ground. |
| `labels` | List from `airline`, `type`, `reg`, `route`, `altitude`, `distance`, `speed`, `heading`, `seen`. |
| `style` | Original style ID; editor loads all original styles, plus `builder` and `custom`. |
| `custom_style` | Your words for `style: custom`. |
| `build_*` | `build_medium`, `build_period`, `build_palette`, `build_line`, `build_texture`, `build_mood`, `build_extra`. |
| `model` | `nano_banana`, `nano_banana_pro`, `flux_kontext`, `gpt_image`, `seedream`. |
| `backdrop` | Original backdrop ID; e.g. `none`, `sky`, `clouds`, `sunset`, `night`, `storm`, `ornate`, `live`. |
| `viewpoint` | `side`, `livery`, `quarter`, `above`; separate from the card's `view`. |
| `font` / `paper` | `fell`, `archivo`, `georgia`, `page` / `cream`, `white`, `aged`, `blueprint`, `sky`. |
| `look` / `colours` | Plate: `plate`, `pass`, `tiles`, `poster`, `split` / `paper` or `airline`. |
| `logos` | `off` by default; `on` fetches optional airline marks. |
| `unpainted` | `photo`, `silhouette`, `skip`; upstream view-specific fallback rules apply. |
| `panel` / `text_size` / `scale` | `colour`, `gray16`, `gray4`, `mono` / 60–150 / 40–100. |
| `header` / `footer` | `top`, `bottom`, `hidden` / `show`, `credits`, `hide`. Credits remain available in management; keep them visible where practical. |
| `photo_fit` / `fidelity` | `cover` or `contain` / `photo` (default) or `free`. |
| `ufo` / `visitors` | Hourly visitor chance 0–100 / list of upstream craft IDs. |

## Troubleshooting

- **Custom element doesn't exist:** restart Home Assistant, check the JavaScript module resource URL, and reload the browser. Check for errors in the Home Assistant log.
- **No integration found:** check the exact `custom_components/overhead/manifest.json` path and the supported Home Assistant version, then restart.
- **No aircraft:** try a wider integration radius; the current feed may have no nearby coverage. Stale feed responses are labelled and excluded from new observations.
- **Silhouettes instead of photos:** check the planespotters.net contact, photo availability, and network access. Some registrations have no photo. Negative results are cached.
- **Card needs an administrator:** an administrator must open the saved card once to register or change its profile settings. Editing previews alone does not register it.
- **Artwork held, budget or storage state:** enable generation and configure the key; increase the estimated limit/storage allowance or delete artwork if needed, then use Paint now or Repaint as appropriate. Failed/uncertain work requires an explicit Repaint.
- **Removed card still active:** remove its saved profile in the management card. Also remove the dashboard card itself so it does not register again.

## Development and verification

See [docs/VERIFICATION.md](docs/VERIFICATION.md) for exact checks and limitations. Tests use deterministic provider responses and synthetic images. No user's Home Assistant instance, receiver or fal.ai account was accessed.

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest tests -q
```

`demo/index.html` is an offline UI preview with synthetic data. Serve the source folder with `python -m http.server` and open `/demo/`; modules need HTTP rather than opening the file directly.

## Source and credits

See [UPSTREAM.md](UPSTREAM.md), [ATTRIBUTION.md](ATTRIBUTION.md) and [LICENSE](LICENSE). Original fonts and their licenses are bundled. The complete corresponding source accompanies the integration. Original artwork model APIs were checked against fal's official documentation; live generation, provider billing and Raspberry Pi deployment remain unverified.

Provider API references: [Nano Banana](https://fal.ai/models/fal-ai/nano-banana/edit/api), [Nano Banana Pro](https://fal.ai/models/fal-ai/nano-banana-pro/edit/api), [FLUX Kontext](https://fal.ai/models/fal-ai/flux-pro/kontext/api), [Seedream](https://fal.ai/models/fal-ai/bytedance/seedream/v4/edit/api), [GPT Image](https://fal.ai/models/openai/gpt-image-2/edit/api).
