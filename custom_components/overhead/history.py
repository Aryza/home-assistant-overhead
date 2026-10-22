"""Two-day observations and persisted scheduled per-card windows."""

from copy import deepcopy
from .storage import load, save


class History:
    def __init__(self, path):
        self.path = path
        state = load(path, {})
        self.points = state.get("points", [])
        self.windows = state.get("windows", {})

    def persist(self):
        save(self.path, {"points": self.points, "windows": self.windows})

    def observe(self, rows, now):
        self.points = [p for p in self.points if p[0] >= now - 172800]
        self.points.extend([now, deepcopy(r)] for r in rows)
        # Bound memory for unusually busy receivers, retaining the newest observations.
        self.points = self.points[-100000:]
        self.persist()

    def window(self, profile, interval, now, preview=False):
        old = self.windows.get(profile)
        if old and now < old["end"] + interval:
            return deepcopy(old["rows"]), old["start"], old["end"]
        start = old["end"] if old else now - 3600
        seen = {}
        for ts, row in self.points:
            if not start <= ts <= now:
                continue
            key = row.get("hex") or row.get("reg") or row.get("cs")
            if not key:
                continue
            if key not in seen:
                seen[key] = {
                    **deepcopy(row),
                    "seen_first": ts,
                    "seen_last": ts,
                    "closest_at": ts,
                }
            else:
                previous = seen[key]
                if row["km"] < previous["km"]:
                    seen[key] = {
                        **deepcopy(row),
                        "seen_first": previous["seen_first"],
                        "closest_at": ts,
                    }
                seen[key]["seen_last"] = ts
        rows = sorted(seen.values(), key=lambda r: r["km"])
        if not preview:
            self.windows[profile] = {"start": start, "end": now, "rows": rows}
            self.persist()
        return deepcopy(rows), start, now
