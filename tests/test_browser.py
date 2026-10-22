"""Browser checks use the real card, original renderer and deterministic data."""

from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import threading
import pytest
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def web_server():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_four_views_resize_empty_error_and_management(web_server):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 900})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        response = await page.goto(web_server + "/demo/index.html")
        assert response.status == 200
        await page.wait_for_function(
            "document.querySelectorAll('overhead-card').length === 5"
        )
        await page.wait_for_function(
            "[...document.querySelectorAll('overhead-card')].slice(0,4).every(c=>c.shadowRoot.querySelector('.oh'))"
        )
        for view in ("photo", "plate", "cluster", "scene"):
            card = page.locator(f"overhead-card[data-view={view}]")
            assert await card.locator(".oh").is_visible()
            assert "DLH247" in await card.locator(".oh").inner_text()
        screenshots = ROOT / "docs" / "previews"
        screenshots.mkdir(exist_ok=True)
        await page.screenshot(path=str(screenshots / "desktop.png"), full_page=True)
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(200)
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        await page.screenshot(path=str(screenshots / "phone.png"), full_page=True)
        await page.evaluate("window.mode='empty';window.cards[0]._refresh()")
        await page.wait_for_function(
            "document.querySelector('overhead-card').shadowRoot.textContent.includes('Nothing in the air')"
        )
        await page.evaluate("window.mode='error';window.cards[0]._refresh()")
        await page.wait_for_function(
            "document.querySelector('overhead-card').shadowRoot.textContent.includes('Feed unavailable')"
        )
        assert not errors
        await browser.close()


@pytest.mark.asyncio
async def test_editor_preview_config_changes_and_reconnect(web_server):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 900, "height": 800})
        await page.goto(web_server + "/demo/index.html")
        await page.wait_for_function(
            "window.cards?.[0]?.shadowRoot.querySelector('.oh')"
        )
        await page.evaluate(
            "window.cards[0].setConfig({...window.cards[0]._config,view:'plate'})"
        )
        await page.wait_for_function(
            "window.cards[0].shadowRoot.querySelector('.oh.plate')"
        )
        await page.evaluate("""() => {
          const dialog=document.createElement('hui-dialog-edit-card');
          const shadow=dialog.attachShadow({mode:'open'});
          const card=document.createElement('overhead-card');
          card.setConfig({type:'custom:overhead-card',entry_id:'demo',profile_id:'editor_preview',view:'photo'});
          const original=window.cards[0]._hass;
          card.hass={...original,async callWS(msg){window.lastPreview=msg.preview;return original.callWS(msg)}};
          shadow.append(card);document.body.append(dialog);window.previewCard=card;
        }""")
        await page.wait_for_function("window.lastPreview===true")
        await page.evaluate("""() => {
          const card=window.cards[0];window.originalHass=card._hass;
          card._hass={...card._hass,callWS:async()=>{throw new Error('Disconnected')}};
          card._refresh();
        }""")
        await page.wait_for_function(
            "window.cards[0].shadowRoot.textContent.includes('Disconnected')"
        )
        await page.evaluate(
            "window.cards[0]._hass=window.originalHass;window.cards[0]._refresh()"
        )
        await page.wait_for_function(
            "window.cards[0].shadowRoot.querySelector('.oh.plate')"
        )
        editor = page.locator("overhead-card-editor")
        await page.evaluate("""() => {
          const editor=document.createElement('overhead-card-editor');
          editor.setConfig({type:'custom:overhead-card',profile_id:'test_editor',view:'photo'});
          editor.hass=window.originalHass;
          editor.addEventListener('config-changed',event=>window.editedConfig=event.detail.config);
          document.body.append(editor);
        }""")
        await editor.locator("select[data-key=view]").select_option("scene")
        await page.wait_for_function("window.editedConfig?.view==='scene'")
        await browser.close()


@pytest.mark.asyncio
async def test_entry_resolution_race_never_sends_new_options_to_old_entry(web_server):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(web_server + "/demo/index.html")
        await page.wait_for_function("window.cards?.length===5")
        await page.evaluate("""() => {
          window.sentSnapshots=[];
          const gate=new Promise(resolve=>window.resolveEntry=resolve);
          const original=window.cards[0]._hass;
          const card=document.createElement('overhead-card');
          card.setConfig({type:'custom:overhead-card',profile_id:'old_profile',view:'photo'});
          card.hass={...original,async callWS(msg){
            if(msg.type==='overhead/entries'){window.resolvingEntry=true;return gate;}
            if(msg.type==='overhead/snapshot')window.sentSnapshots.push(structuredClone(msg));
            return original.callWS(msg);
          }};
          document.body.append(card);window.raceCard=card;
        }""")
        await page.wait_for_function("window.resolvingEntry")
        await page.evaluate(
            "window.raceCard.setConfig({type:'custom:overhead-card',entry_id:'new',profile_id:'new_profile',view:'scene'});window.resolveEntry([{entry_id:'old',name:'Old'}])"
        )
        await page.wait_for_function("window.sentSnapshots.some(s=>s.entry_id==='new')")
        assert await page.evaluate(
            "window.sentSnapshots.every(s=>s.profile_id!=='new_profile'||s.entry_id==='new')"
        )
        await browser.close()
