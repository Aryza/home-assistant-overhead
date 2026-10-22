"""Atomic local state. Never hide a failed artwork budget write."""

import json
import os
from pathlib import Path


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(value, f, separators=(",", ":"), allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
