from pathlib import Path
import sys
import types
import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "overhead"
# Import the pure modules without importing the Home Assistant lifecycle module.
pkg = types.ModuleType("overhead_test")
pkg.__path__ = [str(ROOT)]
sys.modules.setdefault("overhead_test", pkg)
from overhead_test.history import History
from overhead_test.validation import settings_of, options_of


def row(km=5, key="abc"):
    return {"hex": key, "reg": key.upper(), "cs": key.upper(), "km": km}


def test_closest_approach_and_preview_do_not_advance(tmp_path):
    h = History(tmp_path / "history.json")
    h.observe([row(10)], 10000)
    h.observe([row(2)], 10060)
    h.observe([row(8)], 10120)
    rows, start, end = h.window("living", 3600, 10120, preview=False)
    assert rows[0]["km"] == 2
    assert rows[0]["closest_at"] == 10060
    assert rows[0]["seen_first"] == 10000
    assert rows[0]["seen_last"] == 10120
    h.observe([row(1)], 10200)
    assert h.window("living", 3600, 10200, preview=True) == (rows, start, end)
    restored = History(tmp_path / "history.json")
    assert restored.window("living", 3600, 10200) == (rows, start, end)
    newer, start2, end2 = restored.window("living", 3600, 13720)
    assert start2 == end
    assert newer[0]["km"] == 1
    assert end2 == 13720


def test_profiles_are_independent_and_preview_does_not_register(tmp_path):
    h = History(tmp_path / "history.json")
    h.observe([row()], 10000)
    h.window("preview", 3600, 10000, preview=True)
    assert "preview" not in h.windows
    a = h.window("a", 3600, 10000)
    b = h.window("b", 3600, 10100)
    assert a[2] != b[2]


def test_retention(tmp_path):
    h = History(tmp_path / "history.json")
    h.observe([row()], 10000)
    h.observe([row(key="new")], 200000)
    rows, *_ = h.window("a", 3600, 200000)
    assert [r["hex"] for r in rows] == ["new"]


def test_settings_validate_zero_coordinates_and_block_bad_sources():
    s = settings_of({"latitude": 0, "longitude": 0})
    assert s["latitude"] == s["longitude"] == 0
    for invalid in (
        {"latitude": float("nan")},
        {"longitude": 181},
        {"source": "x"},
        {"source": "receiver", "receiver_url": "file:///tmp/x"},
    ):
        with pytest.raises(ValueError):
            settings_of(invalid)


def test_client_cannot_override_credentials_location_or_source():
    with pytest.raises(ValueError):
        options_of({"fal_api_key": "x"})
    with pytest.raises(ValueError):
        options_of({"receiver_url": "http://evil"})
    assert (
        options_of({"view": "scene", "period": "since", "snapshot_minutes": 60})["view"]
        == "scene"
    )


def test_engine_views_and_no_paid_preview(tmp_path, monkeypatch):
    from overhead_test.engine import Engine
    from overhead_test.vendor import adsb

    raw = [
        {
            "hex": "abc",
            "flight": "TEST1",
            "r": "D-TEST",
            "t": "A320",
            "lat": 52.01,
            "lon": 13.01,
            "alt_baro": 5000,
            "gs": 200,
        }
    ]
    rows = adsb._rows(raw, 52, 13, 25)
    monkeypatch.setattr(adsb, "nearby", lambda *a: (rows, None, "test feed"))
    monkeypatch.setattr(adsb, "route_of", lambda *a: {})
    monkeypatch.setattr(adsb, "photo_of", lambda *a: {})
    monkeypatch.setattr(adsb, "brand_of", lambda *a: {})
    e = Engine(tmp_path, {"latitude": 52, "longitude": 13})
    e.poll()
    for view in ("photo", "plate", "cluster", "scene"):
        data = e.snapshot(view, {"view": view}, preview=True)
        assert data["widget"] == view
        assert data["aircraft"][0]["reg"] == "D-TEST"
    assert not e.profiles
    e.snapshot("living", {"view": "cluster"})
    assert "living" in e.profiles
    with pytest.raises(ValueError):
        e.snapshot("other", {}, allow_register=False)
    e.close()


def test_public_feed_fallback_and_bad_data(tmp_path, monkeypatch):
    from overhead_test.vendor import adsb

    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if "adsb.lol" in url:
            return None, "unreachable"
        return {
            "ac": [
                {
                    "hex": "a",
                    "r": "D-TEST",
                    "lat": 52.01,
                    "lon": 13.01,
                    "alt_baro": 1000,
                }
            ]
        }, None

    monkeypatch.setattr(adsb.N, "get_json", get)
    rows, error, feed = adsb.nearby("adsb_lol", "", 52, 13, 25, tmp_path, "test")
    assert not error and rows[0]["reg"] == "D-TEST"
    assert "fi" in feed.lower()
    assert len(calls) == 2


def test_invalid_aircraft_values_are_ignored():
    from overhead_test.vendor import adsb

    bad = [
        {"lat": float("nan"), "lon": 13},
        {"lat": 91, "lon": 13},
        {
            "lat": 52,
            "lon": 13,
            "alt_baro": float("inf"),
            "gs": float("inf"),
            "track": float("nan"),
        },
    ]
    rows = adsb._rows(bad, 52, 13, 25)
    assert len(rows) == 1
    assert rows[0]["gs"] == 0
    assert rows[0]["trk"] == 0


def test_stale_cache_is_labeled_and_not_recorded_as_new_traffic(tmp_path, monkeypatch):
    from overhead_test.vendor import adsb
    from overhead_test.storage import save

    url = adsb.FEEDS[0][1].format(lat="52.0000", lon="13.0000", nm=14)
    cache = tmp_path / "live" / (adsb.N.slug(url) + ".json")
    save(
        cache,
        {
            "at": 1,
            "feed": "old",
            "data": {"ac": [{"lat": 52.01, "lon": 13.01, "alt_baro": 1000}]},
        },
    )
    monkeypatch.setattr(adsb, "_ask_feeds", lambda *a: (None, "unreachable", ""))
    rows, error, feed = adsb.nearby("adsb_lol", "", 52, 13, 25, tmp_path, "test")
    assert rows and error and "stale" in error.lower()


def test_identical_locations_share_poll(tmp_path, monkeypatch):
    from overhead_test.engine import Engine
    from overhead_test.vendor import adsb

    calls = []
    monkeypatch.setattr(
        adsb, "nearby", lambda *a: (calls.append(1) or [], None, "test")
    )
    one = Engine(tmp_path / "one", {"latitude": 51.2, "longitude": 12.1})
    two = Engine(tmp_path / "two", {"latitude": 51.2, "longitude": 12.1})
    one.poll()
    two.poll()
    assert len(calls) == 1
    one.close()
    two.close()


def test_changing_observation_location_resets_old_history(tmp_path):
    from overhead_test.engine import Engine

    first = Engine(tmp_path, {"latitude": 56, "longitude": 12})
    first.history.observe([row()], 10000)
    first.history.window("card", 3600, 10000)
    first.close()
    moved = Engine(tmp_path, {"latitude": 57, "longitude": 12})
    assert moved.history.points == []
    assert moved.history.windows == {}
    moved.close()
