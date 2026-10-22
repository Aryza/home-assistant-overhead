"""Persistent bounded artwork queue and upstream-compatible render sessions."""

import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from .storage import load, save

UNLIMITED = 10**9


class ArtworkError(Exception):
    """A generation could not finish; never automatically retry paid submissions."""


class Artwork:
    name = "paintings"

    def __init__(self, folder, settings, make=None):
        self.root = Path(folder)
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.lock = threading.RLock()
        self.closed = False
        self.pool = ThreadPoolExecutor(
            max_workers=int(settings.get("gen_parallel", 1)),
            thread_name_prefix="overhead-art",
        )
        self.futures = set()
        self.future_keys = {}
        state = load(self.root / "artwork.json", {})
        self.items, self.days = state.get("items", {}), state.get("days", {})
        self.make = make
        for item in self.items.values():
            if item["state"] in ("running", "queued"):
                item.update(
                    state="uncertain",
                    why="Interrupted submission; inspect your fal.ai account before explicitly repainting.",
                )
        self._save()

    def _save(self):
        save(self.root / "artwork.json", {"items": self.items, "days": self.days})

    def day(self):
        return datetime.now(ZoneInfo(self.settings.get("timezone", "UTC"))).strftime(
            "%Y-%m-%d"
        )

    def cap(self, settings=None):
        # Zero means no new paid work, unlike upstream's unlimited zero.
        return round(float(self.settings.get("gen_daily_usd", 1)) * 100)

    def budget_used(self, *_):
        return self.days.get(self.day(), 0)

    def folder(self, *_):
        p = self.root / "paintings"
        p.mkdir(exist_ok=True)
        return p

    def _key(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,220}", key):
            raise ValueError("Invalid artwork key")
        return key

    def path(self, key, *_):
        self._key(key)
        p = self.folder() / f"{key}.png"
        return p if p.exists() else None

    def meta(self, key, *_):
        with self.lock:
            return deepcopy(self.items.get(key, {}).get("meta", {}))

    def state(self, key, *_):
        with self.lock:
            return self.items.get(key, {}).get("state", "none")

    def note_error(self, key, *_, **kwargs):
        with self.lock:
            if key in self.items:
                self.items[key]["why"] = "Could not prepare the image cut-out"
                self._save()

    def open(self, ctx, settings=None, **_):
        session = Session(
            self, bool(ctx.get("preview", True)), ctx.get("profile_id", "")
        )
        ctx["art_session"] = session
        return session

    def request(self, key, payload, title="", want=True, preview=True):
        self._key(key)
        with self.lock:
            if key not in self.items:
                if len(self.items) >= 2000:
                    return SimpleNamespace(
                        key=key,
                        state="full",
                        ready=False,
                        why="Artwork catalogue limit reached",
                        meta={},
                    )
                self.items[key] = {
                    "state": "held",
                    "payload": deepcopy(payload),
                    "title": title[:200],
                    "meta": {},
                    "versions": [],
                    "created": time.time(),
                }
                self._save()
            item = self.items[key]
            if (
                item["state"] in ("held", "budget", "storage")
                and want
                and not preview
                and self.settings.get("generation_enabled")
            ):
                self._submit(key)
            return SimpleNamespace(
                key=key,
                state=item["state"],
                ready=bool(self.path(key)),
                why=item.get("why", ""),
                meta=deepcopy(item.get("meta", {})),
            )

    def _submit(self, key):
        if self.closed:
            raise ValueError("Integration is shutting down")
        if not self.settings.get("generation_enabled") or not self.settings.get(
            "fal_api_key"
        ):
            raise ValueError("Enable generation and configure your fal.ai key first")
        item = self.items[key]
        if item["state"] in ("queued", "running", "uncertain"):
            return
        from .vendor.paint import cost_cents

        cost = cost_cents(item["payload"].get("model", "nano_banana"))
        day = self.day()
        if self.days.get(day, 0) + cost > self.cap():
            item.update(state="budget", why="Daily estimated artwork limit reached")
            self._save()
            return
        stored = sum(p.stat().st_size for p in self.folder().iterdir() if p.is_file())
        allowance = float(self.settings.get("cache_mb", 512)) * 1024 * 1024 / 2
        if stored + (len(self.futures) + 1) * 24 * 1024 * 1024 > allowance:
            item.update(
                state="storage",
                why="Artwork storage allowance reached; delete artwork or increase the allowance",
            )
            self._save()
            return
        if len(self.futures) >= 24:
            item.update(
                state="held", why="Queue full; try Paint now after current jobs finish"
            )
            self._save()
            return
        # Reserve and fsync BEFORE submitting; uncertain/failed calls retain the reservation.
        self.days[day] = self.days.get(day, 0) + cost
        item.update(state="queued", why="", reserved_day=day, reserved_cents=cost)
        self._save()
        f = self.pool.submit(self._run, key)
        self.futures.add(f)
        self.future_keys[f] = key
        f.add_done_callback(self._done)

    def _done(self, future):
        with self.lock:
            self.futures.discard(future)
            key = self.future_keys.pop(future, None)
            if future.cancelled() and key:
                self._cancel(key)

    def _cancel(self, key):
        item = self.items[key]
        if item["state"] != "queued":
            return
        day = item.pop("reserved_day", "")
        cents = item.pop("reserved_cents", 0)
        self.days[day] = max(0, self.days.get(day, 0) - cents)
        item.update(
            state="cancelled",
            why="Cancelled before submission during shutdown; use Paint now to request it again",
        )
        self._save()

    def _run(self, key):
        from .vendor import paint
        from .fal import Fal

        with self.lock:
            item = self.items[key]
            if self.closed:
                self._cancel(key)
                return
            item["state"] = "running"
            self._save()
            payload = deepcopy(item["payload"])
        try:
            job = SimpleNamespace(
                payload=payload,
                data_dir=self.root,
                fal=Fal(self.settings["fal_api_key"]),
            )
            raw, meta = (self.make or paint.make)(job)
            # Validate/normalize provider output before keeping it.
            from PIL import Image
            import io

            im = Image.open(io.BytesIO(raw))
            im.thumbnail((2400, 2400))
            out = io.BytesIO()
            im.save(out, "PNG")
            with self.lock:
                target = self.folder() / f"{key}.png"
                temporary = target.with_suffix(".tmp")
                with temporary.open("wb") as file:
                    import os

                    file.write(out.getvalue())
                    file.flush()
                    os.fsync(file.fileno())
                temporary.replace(target)
                for pattern in (f"{key}__cut*", f"{key}__display*"):
                    for derived in self.folder().glob(pattern):
                        derived.unlink(missing_ok=True)
                item.update(state="ready", meta=meta, why="")
                self._save()
        except Exception as exc:
            with self.lock:
                # A timeout may have been billed. Manual repaint is the sole resubmission path.
                item.update(
                    state="failed",
                    why=f"Generation failed ({type(exc).__name__}); check fal.ai before repainting.",
                )
                self._save()

    def image(self, key, px=700, levels="colour", cut=False, variant=""):
        from .vendor import net

        with self.lock:
            p = (
                self.folder() / f"{self._key(key)}__{variant}.png"
                if cut
                else self.path(key)
            )
            if not p or not p.exists():
                return ""
            raw = p.read_bytes()
        if cut:
            from PIL import Image
            import io

            im = Image.open(io.BytesIO(raw)).convert("RGBA")
            im.thumbnail((px, px))
            if levels != "colour":
                alpha = im.getchannel("A")
                im = im.convert("L").convert("RGBA")
                im.putalpha(alpha)
            out = io.BytesIO()
            im.save(out, "PNG")
            return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()
        return net.render(
            raw,
            px,
            levels=levels,
            cache=self.folder() / f"{key}__display{px}_{levels}.jpg",
        )

    def status(self):
        with self.lock:
            rows = []
            for index, (key, item) in enumerate(
                sorted(self.items.items(), key=lambda kv: -kv[1].get("created", 0))
            ):
                rows.append(
                    {
                        "key": key,
                        "state": item["state"],
                        "title": item.get("title", key),
                        "why": item.get("why", ""),
                        "meta": deepcopy(item.get("meta", {})),
                        "versions": [v["at"] for v in item.get("versions", [])],
                        "profiles": item.get("profiles", []),
                        "style": item.get("payload", {}).get("style", ""),
                        "thumb": self.image(key, px=240) if index < 100 else "",
                    }
                )
            return {
                "items": rows,
                "total": len(self.items),
                "states": dict(Counter(i["state"] for i in self.items.values())),
                "used_cents": self.budget_used(),
                "cap_cents": self.cap(),
                "generation_enabled": bool(self.settings.get("generation_enabled")),
            }

    def action(self, action, key="", version=0):
        with self.lock:
            if action == "paint":
                if not self.settings.get("generation_enabled"):
                    raise ValueError(
                        "Enable generation in the integration options first"
                    )
                for k, item in self.items.items():
                    if item["state"] in ("held", "budget", "storage", "cancelled"):
                        self._submit(k)
            elif action in ("purge", "delete", "repaint", "restore"):
                if any(
                    i["state"] in ("running", "queued") for i in self.items.values()
                ):
                    raise ValueError("Wait for artwork jobs to finish first")
                if action == "purge":
                    for p in self.folder().iterdir():
                        if p.is_file():
                            p.unlink()
                    self.items.clear()
                else:
                    self._key(key)
                    item = self.items.get(key)
                    if not item:
                        raise ValueError("Artwork not found")
                    if action == "delete":
                        for p in self.folder().glob(f"{key}.*"):
                            p.unlink()
                        for p in self.folder().glob(f"{key}__*"):
                            p.unlink()
                        del self.items[key]
                    elif action == "repaint":
                        if self.path(key):
                            stamp = time.time_ns()
                            dest = self.folder() / f"{key}__v{stamp}.png"
                            dest.write_bytes(self.path(key).read_bytes())
                            item.setdefault("versions", []).append(
                                {
                                    "file": dest.name,
                                    "meta": deepcopy(item.get("meta", {})),
                                    "at": time.time(),
                                }
                            )
                        item["state"] = "held"
                        self._submit(key)
                    else:
                        versions = item.get("versions", [])
                        if not 0 <= version < len(versions):
                            raise ValueError("Version not found")
                        v = versions[version]
                        (self.folder() / f"{key}.png").write_bytes(
                            (self.folder() / v["file"]).read_bytes()
                        )
                        item.update(state="ready", meta=deepcopy(v["meta"]))
                    if action in ("repaint", "restore"):
                        for pattern in (f"{key}__cut*", f"{key}__display*"):
                            for p in self.folder().glob(pattern):
                                p.unlink(missing_ok=True)
            else:
                raise ValueError("Unknown artwork action")
            self._save()
        return {"ok": True}

    def wait(self):
        with self.lock:
            pending = list(self.futures)
        wait(pending)

    def close(self):
        with self.lock:
            self.closed = True
        self.pool.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            self._save()


class Session:
    def __init__(self, collection, preview, profile=""):
        self.c = collection
        self.profile = profile
        self.asked = set()
        self.preview = preview
        self.data_dir = collection.root
        self.key = collection.settings.get("fal_api_key", "")
        self.states = Counter()
        self.started = 0

    def request(self, key, payload, *, title="", want=True):
        got = self.c.request(key, payload, title, want, self.preview)
        self.asked.add(key)
        if self.profile:
            with self.c.lock:
                item = self.c.items.get(key)
                if item is not None and self.profile not in item.setdefault(
                    "profiles", []
                ):
                    item["profiles"].append(self.profile)
                    self.c._save()
        self.states[got.state] += 1
        return got

    def url(self, key, **kwargs):
        return self.c.image(key, **kwargs)

    def live(self):
        pending = self.states["queued"] + self.states["running"]
        return {"live_refresh_s": 10 if pending else 0, "live_pending": pending}

    def notes(self):
        return (
            ["AI generation is disabled; cached artwork and photographs are available."]
            if not self.c.settings.get("generation_enabled") and self.states["held"]
            else []
        )

    def status(self):
        return [f"{v} artwork {k}" for k, v in self.states.items() if k != "ready"]

    def finish(self, *_args, **_kwargs):
        if not self.profile:
            return
        with self.c.lock:
            changed = False
            for key, item in list(self.c.items.items()):
                if (
                    item["state"] in ("held", "budget", "storage")
                    and self.profile in item.get("profiles", [])
                    and key not in self.asked
                ):
                    item["profiles"].remove(self.profile)
                    if not item["profiles"]:
                        del self.c.items[key]
                    changed = True
            if changed:
                self.c._save()
