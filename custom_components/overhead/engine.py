"""Synchronous host adapter. All entrypoints run in the HA executor."""

from copy import deepcopy
from pathlib import Path
import threading
import time
from .artwork import Artwork
from .history import History
from .storage import load, save
from .validation import settings_of, options_of, profile_id
from .vendor import adsb, sheet, sightings


_FEEDS = {}
_FEED_LOCK = threading.Lock()


class Engine:
    def __init__(self, folder, settings):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.settings = settings_of(settings)
        self.lock = threading.RLock()
        self.history = History(self.folder / "history.json")
        observation = {
            k: self.settings[k]
            for k in ("source", "receiver_url", "latitude", "longitude", "radius_km")
        }
        previous = load(self.folder / "observation.json", None)
        if previous is not None and previous != observation:
            # Distances/closest approaches belong to the observation location and radius.
            self.history.points.clear()
            self.history.windows.clear()
            self.history.persist()
        save(self.folder / "observation.json", observation)
        self.profiles = load(self.folder / "profiles.json", {})
        self.artwork = Artwork(self.folder, self.settings)
        self.rows = []
        self.error = "Waiting for the first aircraft observation"
        self.feed = ""
        self.updated = 0
        self.cache = {}
        self.closed = False

    def poll(self):
        with self.lock:
            if self.closed:
                return self.summary()
            s = self.settings
            feed_key = tuple(
                s[k]
                for k in (
                    "source",
                    "receiver_url",
                    "latitude",
                    "longitude",
                    "radius_km",
                )
            )
            with _FEED_LOCK:
                cached = _FEEDS.get(feed_key)
                interval = 30 if s["source"] == "receiver" else 60
                if cached and time.monotonic() - cached[0] < interval:
                    rows, error, feed = deepcopy(cached[1])
                else:
                    result = adsb.nearby(
                        s["source"],
                        s["receiver_url"],
                        s["latitude"],
                        s["longitude"],
                        float(s["radius_km"]),
                        self.folder,
                        adsb.user_agent(s["contact"]),
                    )
                    _FEEDS[feed_key] = (time.monotonic(), deepcopy(result))
                    rows, error, feed = result
                    if len(_FEEDS) > 64:
                        _FEEDS.pop(next(iter(_FEEDS)))
            self.rows, self.error, self.feed = rows, error, feed
            self.updated = time.time()
            if not error:
                self.history.observe(rows, self.updated)
                sightings.ledger(self.folder).note(
                    rows, sheet.SIGHT_ID, sheet.SIGHT_NAME
                )
            self.cache.clear()
            for key, options in list(self.profiles.items()):
                self._render(key, options, preview=False)
            self._clean_cache()
            return self.summary()

    def summary(self):
        airborne = [r for r in self.rows if not r["ground"]]
        nearest = airborne[0] if airborne else {}
        return {
            "count": len(airborne),
            "nearest": {
                k: nearest[k]
                for k in ("cs", "reg", "typ", "km", "alt", "gs")
                if k in nearest
            },
            "error": self.error,
            "feed": self.feed,
            "updated": self.updated,
        }

    def snapshot(self, profile, options, preview=False, allow_register=True):
        profile = profile_id(profile)
        options = options_of(options)
        with self.lock:
            if self.closed:
                raise ValueError("Integration is shutting down")
            if not preview:
                if not allow_register and self.profiles.get(profile) != options:
                    raise ValueError(
                        "An administrator must register this card configuration first"
                    )
                if profile not in self.profiles and len(self.profiles) >= 12:
                    raise ValueError(
                        "At most twelve saved cards per integration; remove an unused profile"
                    )
                if self.profiles.get(profile) != options:
                    self.profiles[profile] = deepcopy(options)
                    save(self.folder / "profiles.json", self.profiles)
                    self.cache.pop(profile, None)
                cached = self.cache.get(profile)
                if cached and time.time() - cached[0] < 15:
                    return deepcopy(cached[1])
            return self._render(profile, options, preview)

    def _render(self, profile, options, preview):
        o = deepcopy(options)
        widget = o.pop("view")
        o["view"] = o.pop("viewpoint", "side")
        s = self.settings
        o.update(
            latitude=s["latitude"],
            longitude=s["longitude"],
            location={"timezone": s["timezone"]},
            source=s["source"],
            radius_km=s["radius_km"],
            receiver_url=s["receiver_url"],
        )
        ctx = {
            "data_dir": str(self.folder),
            "preview": preview,
            "profile_id": profile,
            "artwork": self.artwork,
            "observations": lambda: (deepcopy(self.rows), self.error, self.feed),
            "history": lambda: self.history.window(
                profile, options["snapshot_minutes"] * 60, time.time(), preview=preview
            ),
        }
        data = sheet.fetch(o, s, ctx, widget)
        ctx["art_session"].finish(ctx)
        data["observed_at"] = self.updated
        if self.error:
            data.setdefault("notices", []).append(self.error)
        if not preview:
            self.cache[profile] = (time.time(), deepcopy(data))
        return data

    def manage(self, action, key="", version=0):
        with self.lock:
            if action == "remove_profile":
                profile_id(key)
                self.profiles.pop(key, None)
                self.history.windows.pop(key, None)
                self.history.persist()
                self.cache.pop(key, None)
                save(self.folder / "profiles.json", self.profiles)
                return {"ok": True}
            if action == "status":
                result = self.artwork.status()
                painted = {
                    i.get("meta", {}).get("reg")
                    for k, i in self.artwork.items.items()
                    if self.artwork.path(k)
                }
                result["catalogue"] = sightings.stats(
                    self.folder, lambda reg: reg in painted
                )
                result["profiles"] = [
                    {"id": k, "view": v["view"]} for k, v in self.profiles.items()
                ]
                return result
            result = self.artwork.action(action, key, version)
            self.cache.clear()
            return result

    def metadata(self):
        p = sheet.P

        def choices(values):
            return {k: (v[0] if isinstance(v, tuple) else v) for k, v in values.items()}

        return {
            "styles": {k: v[0] for k, v in p.STYLES.items()},
            "models": {k: v["label"] for k, v in p.MODELS.items()},
            "backdrops": choices(p.BACKDROPS),
            "viewpoints": choices(p.VIEWS),
            "visitors": {k: v[0] for k, v in p.UFOS.items()}
            if hasattr(p, "UFOS")
            else {},
            "build": {
                k: {
                    "label": v[0],
                    "default": v[1],
                    "choices": {x[0]: x[1] for x in v[2]},
                }
                for k, v in p.BUILDER.items()
            },
        }

    def _clean_cache(self):
        # Evict re-fetchable network/resize cache. User artwork is never silently deleted.
        roots = [
            self.folder / k
            for k in ("img", "live", "routes", "photos", "logos", "weather")
        ]
        files = [
            f for root in roots if root.exists() for f in root.rglob("*") if f.is_file()
        ]
        sizes = [(f.stat().st_mtime, f.stat().st_size, f) for f in files]
        total = sum(size for _, size, _ in sizes)
        limit = self.settings["cache_mb"] * 1024 * 1024 // 2
        for _, size, file in sorted(sizes):
            if total <= limit:
                break
            file.unlink(missing_ok=True)
            total -= size

    def close(self):
        with self.lock:
            self.closed = True
            self.history.persist()
            sightings.ledger(self.folder).save()
        self.artwork.close()
