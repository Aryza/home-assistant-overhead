import io
import threading
from PIL import Image
import pytest
from overhead_test.artwork import Artwork
from overhead_test.storage import save


def picture(job):
    out = io.BytesIO()
    Image.new("RGB", (20, 10), "white").save(out, "PNG")
    return out.getvalue(), {"credit": "test", "reg": job.payload.get("reg", "TEST")}


SETTINGS = {
    "fal_api_key": "test-key",
    "generation_enabled": True,
    "gen_daily_usd": 0.04,
    "gen_parallel": 1,
    "timezone": "UTC",
}
PAYLOAD = {"model": "nano_banana", "reg": "TEST"}


def test_preview_holds_then_explicit_generation_and_versions(tmp_path):
    a = Artwork(tmp_path, {**SETTINGS, "gen_daily_usd": 0.08}, make=picture)
    session = a.open({"preview": True}, SETTINGS)
    assert session.request("TEST_poster", PAYLOAD).state == "held"
    assert a.status()["used_cents"] == 0
    a.action("paint")
    a.wait()
    assert a.path("TEST_poster").exists()
    assert a.status()["used_cents"] == 4
    assert a.open({"preview": False}, SETTINGS).request("TEST_poster", PAYLOAD).ready
    a.action("repaint", "TEST_poster")
    a.wait()
    assert len(a.status()["items"][0]["versions"]) == 1
    a.action("restore", "TEST_poster", 0)
    a.action("delete", "TEST_poster")
    assert not a.path("TEST_poster")
    a.close()


def test_budget_atomic_and_deduplicated(tmp_path):
    gate = threading.Event()
    calls = []

    def make(job):
        calls.append(job.payload["reg"])
        gate.wait(2)
        return picture(job)

    a = Artwork(tmp_path, SETTINGS, make=make)
    s = a.open({"preview": False}, SETTINGS)
    for _ in range(5):
        s.request("a", PAYLOAD)
    result = s.request("b", PAYLOAD)
    assert result.state == "budget"
    gate.set()
    a.wait()
    assert len(calls) == 1
    assert a.status()["used_cents"] == 4
    a.close()


def test_interrupted_submission_does_not_retry_and_no_credentials_returned(tmp_path):
    save(
        tmp_path / "artwork.json",
        {
            "items": {"a": {"state": "running", "payload": PAYLOAD}},
            "days": {"2026-10-22": 4},
        },
    )
    a = Artwork(tmp_path, SETTINGS, make=picture)
    assert a.state("a") == "uncertain"
    assert (
        a.open({"preview": False}, SETTINGS).request("a", PAYLOAD).state == "uncertain"
    )
    assert "test-key" not in str(a.status())
    a.close()


def test_disabled_generation_cannot_be_started_and_purge_keeps_spend(tmp_path):
    a = Artwork(tmp_path, {**SETTINGS, "generation_enabled": False}, make=picture)
    a.open({"preview": True}, SETTINGS).request("a", PAYLOAD)
    with pytest.raises(ValueError):
        a.action("paint")
    a.close()
    a = Artwork(tmp_path, SETTINGS, make=picture)
    a.action("paint")
    a.wait()
    a.action("purge")
    assert a.status()["used_cents"] == 4
    assert not a.status()["items"]
    a.close()


def test_style_changes_drop_unused_held_jobs_for_that_profile_only(tmp_path):
    a = Artwork(tmp_path, SETTINGS, make=picture)
    one = a.open({"preview": True, "profile_id": "one"}, SETTINGS)
    one.request("old", PAYLOAD)
    one.finish({})
    two = a.open({"preview": True, "profile_id": "two"}, SETTINGS)
    two.request("other", PAYLOAD)
    two.finish({})
    new = a.open({"preview": True, "profile_id": "one"}, SETTINGS)
    new.request("new", PAYLOAD)
    new.finish({})
    assert a.state("old") == "none"
    assert a.state("other") == "held"
    assert a.state("new") == "held"
    a.close()


def test_fal_uses_model_schema_and_accepts_official_image_host(monkeypatch):
    import json
    from overhead_test.fal import Fal
    from overhead_test.vendor import net

    calls = []

    def http(url, *args, **kwargs):
        calls.append((url, args, kwargs))
        if url.startswith("https://fal.run/"):
            return json.dumps(
                {"images": [{"url": "https://fal.media/example.png"}]}
            ).encode(), None
        return b"image", None

    monkeypatch.setattr(net, "http", http)
    assert (
        Fal("secret").generate(
            "flux_kontext", "draw", refs=["https://example.org/photo.jpg"]
        )
        == b"image"
    )
    body = json.loads(calls[0][2]["body"])
    assert body["image_url"] == "https://example.org/photo.jpg"
    assert calls[1][1] == ()  # The fal API key is not sent to the image CDN.


def test_complete_painted_render_pipeline_without_paid_calls(tmp_path, monkeypatch):
    """Run actual upstream prompts, worker, image cut-out and sheet integration."""
    from overhead_test.engine import Engine
    from overhead_test.vendor import adsb
    from overhead_test.fal import Fal
    from PIL import ImageDraw

    im = Image.new("RGB", (400, 250), "white")
    ImageDraw.Draw(im).ellipse(
        (70, 90, 330, 160), fill="white", outline="navy", width=6
    )
    out = io.BytesIO()
    im.save(out, "PNG")
    raw = out.getvalue()
    monkeypatch.setattr(Fal, "generate", lambda *a, **kw: raw)
    rows = adsb._rows(
        [
            {
                "hex": "abc",
                "flight": "TEST123",
                "r": "D-TEST",
                "t": "A320",
                "lat": 54.01,
                "lon": 12.01,
                "alt_baro": 5000,
            }
        ],
        54,
        12,
        25,
    )
    monkeypatch.setattr(adsb, "nearby", lambda *a: (rows, None, "test"))
    monkeypatch.setattr(adsb, "route_of", lambda *a: {})
    monkeypatch.setattr(
        adsb,
        "photo_of",
        lambda *a: {
            "src": "https://example.org/photo.jpg",
            "by": "test photographer",
            "link": "https://example.org/photo",
        },
    )
    monkeypatch.setattr(adsb, "brand_of", lambda *a: {})
    monkeypatch.setattr(adsb, "sky_now", lambda *a: ("dusk", "cloud"))
    monkeypatch.setattr(adsb.N, "cached_get", lambda *a, **kw: raw)
    engine = Engine(
        tmp_path, {**SETTINGS, "latitude": 54, "longitude": 12, "gen_daily_usd": 1}
    )
    engine.poll()
    for view in ("plate", "cluster", "scene"):
        options = {
            "view": view,
            "pictures": "paintings",
            "backdrop": "live" if view == "scene" else "none",
        }
        engine.snapshot(view, options)
        engine.artwork.wait()
        engine.cache.clear()
        rendered = engine.snapshot(view, options)
        assert rendered["aircraft"][0]["pic"]["kind"] == "painting"
        assert rendered["aircraft"][0]["pic"]["src"].startswith("data:image/")
        if view == "scene":
            assert rendered["sky"]["time"] == "dusk"
    assert (
        engine.artwork.status()["used_cents"] == 8
    )  # Plate and Cluster share an airframe/style key.
    engine.close()


def test_restore_invalidates_whole_image_display_cache(tmp_path):
    calls = []

    def make(job):
        out = io.BytesIO()
        color = "red" if not calls else "blue"
        calls.append(color)
        Image.new("RGB", (60, 40), color).save(out, "PNG")
        return out.getvalue(), {"reg": "TEST"}

    a = Artwork(tmp_path, {**SETTINGS, "gen_daily_usd": 1}, make=make)
    a.open({"preview": False}, SETTINGS).request("color", PAYLOAD)
    a.wait()
    first = a.image("color", px=60)
    a.action("repaint", "color")
    a.wait()
    second = a.image("color", px=60)
    assert first != second
    a.action("restore", "color", 0)
    assert a.image("color", px=60) == first
    a.close()


def test_budget_work_resumes_next_day_but_failed_work_never_retries(
    tmp_path, monkeypatch
):
    a = Artwork(tmp_path, SETTINGS, make=picture)
    monkeypatch.setattr(a, "day", lambda: "day1")
    session = a.open({"preview": False}, SETTINGS)
    session.request("one", PAYLOAD)
    a.wait()
    assert session.request("two", PAYLOAD).state == "budget"
    monkeypatch.setattr(a, "day", lambda: "day2")
    assert session.request("two", PAYLOAD).state in ("queued", "running", "ready")
    a.wait()
    a.items["failed"] = {"state": "failed", "payload": PAYLOAD}
    assert session.request("failed", PAYLOAD).state == "failed"
    a.close()


def test_closing_cancels_queued_work_without_submitting_it(tmp_path):
    gate = threading.Event()
    started = threading.Event()
    calls = []

    def make(job):
        calls.append(job.payload["reg"])
        started.set()
        gate.wait(2)
        return picture(job)

    a = Artwork(tmp_path, {**SETTINGS, "gen_daily_usd": 1}, make=make)
    s = a.open({"preview": False}, SETTINGS)
    s.request("running", {**PAYLOAD, "reg": "RUNNING"})
    assert started.wait(1)
    s.request("queued", {**PAYLOAD, "reg": "QUEUED"})
    closer = threading.Thread(target=a.close)
    closer.start()
    import time

    time.sleep(0.03)
    gate.set()
    closer.join(3)
    assert calls == ["RUNNING"]
    assert a.state("queued") == "cancelled"
    assert a.status()["used_cents"] == 4


def test_saved_painting_survives_missing_photo_metadata(tmp_path, monkeypatch):
    from overhead_test.engine import Engine
    from overhead_test.vendor import adsb

    rows = adsb._rows(
        [
            {
                "hex": "saved",
                "flight": "SAVED1",
                "r": "D-SAVED",
                "t": "A320",
                "lat": 55.01,
                "lon": 12.01,
                "alt_baro": 5000,
            }
        ],
        55,
        12,
        25,
    )
    monkeypatch.setattr(adsb, "nearby", lambda *a: (rows, None, "test"))
    monkeypatch.setattr(adsb, "route_of", lambda *a: {})
    monkeypatch.setattr(
        adsb, "photo_of", lambda *a: {"src": "https://example.org/photo.jpg"}
    )
    monkeypatch.setattr(adsb, "brand_of", lambda *a: {})
    e = Engine(tmp_path, {**SETTINGS, "latitude": 55, "longitude": 12})
    e.artwork.make = picture
    e.poll()
    opts = {"view": "scene", "pictures": "paintings", "backdrop": "sky"}
    e.snapshot("saved", opts)
    e.artwork.wait()
    e.cache.clear()
    assert e.snapshot("saved", opts)["aircraft"][0]["pic"]["kind"] == "painting"
    monkeypatch.setattr(adsb, "photo_of", lambda *a: {})
    e.cache.clear()
    assert e.snapshot("saved", opts)["aircraft"][0]["pic"]["kind"] == "painting"
    e.close()
