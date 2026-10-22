/* Overhead for Home Assistant — AGPL-3.0-or-later. See UPSTREAM.md. */
import { render, esc } from "./overhead.js";

const VERSION = "1.0.0";
const UI_KEYS = new Set([
  "type",
  "entry_id",
  "profile_id",
  "height",
  "aspect_ratio",
]);
const safeImage = (value) =>
  typeof value === "string" &&
  /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(value)
    ? value
    : "";
const safeLink = (value) => {
  try {
    const u = new URL(value);
    return u.protocol === "https:" ? u.href : "";
  } catch {
    return "";
  }
};
const style = `:host{display:block}ha-card{display:block;overflow:hidden;background:var(--card-background-color,#fff);color:var(--primary-text-color,#24333b)}.frame{height:100%;min-height:200px}.message{padding:28px;font:15px/1.5 var(--paper-font-body1_-_font-family,system-ui)}.message strong{display:block;font-size:19px}.management{padding:20px;font:14px/1.5 system-ui}.management h2{margin:0 0 6px;font-size:22px}.management p{margin:6px 0 14px}.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin:15px 0}button,select,input,textarea{font:inherit}button{border:1px solid var(--divider-color,#ccd2d5);border-radius:7px;background:var(--card-background-color,#fff);color:inherit;padding:8px 12px;cursor:pointer}button:disabled{opacity:.5;cursor:default}.artwork{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:12px}.art{border:1px solid var(--divider-color,#dde1e4);border-radius:8px;padding:12px;min-width:0}.art img{width:100%;height:135px;object-fit:contain;background:#f3ead6}.art h3{font-size:14px;margin:7px 0;overflow-wrap:anywhere}.art small{display:block;overflow-wrap:anywhere}.art a{color:var(--primary-color,#1671b8)}.art select{max-width:100%}.stats{display:flex;gap:15px;flex-wrap:wrap;padding:10px 0}.status{color:var(--secondary-text-color,#66757b)}details{margin-top:18px}ul{padding-left:20px}`;

export class OverheadCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._seq = 0;
    this._drawSeq = 0;
    this._busy = false;
    this._observer = new ResizeObserver(() => {
      clearTimeout(this._resize);
      this._resize = setTimeout(() => {
        if (this._data) this._draw(this._data);
      }, 150);
    });
  }
  static getConfigElement() {
    return document.createElement("overhead-card-editor");
  }
  static getStubConfig() {
    return {
      type: "custom:overhead-card",
      profile_id: "overhead_" + crypto.randomUUID().slice(0, 8),
      view: "photo",
    };
  }
  setConfig(config) {
    if (
      !["photo", "plate", "cluster", "scene", "management"].includes(
        config.view || "photo",
      )
    )
      throw new Error("Choose photo, plate, cluster, scene or management");
    if (
      config.view !== "management" &&
      !/^[A-Za-z0-9_-]{1,64}$/.test(config.profile_id || "")
    )
      throw new Error("Set a unique profile_id, for example living_room");
    const height = Number(config.height || 420),
      ratio = Number(config.aspect_ratio || 0);
    if (
      !Number.isFinite(height) ||
      height < 200 ||
      height > 1400 ||
      !Number.isFinite(ratio) ||
      ratio < 0 ||
      ratio > 5
    )
      throw new Error(
        "Height must be 200–1400 px and aspect_ratio must be 0–5",
      );
    this._config = { ...config, view: config.view || "photo" };
    this._seq++;
    this._drawSeq++;
    this._data = null;
    clearTimeout(this._timer);
    this._ensureFrame();
    this._refresh();
  }
  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._refresh();
    }
  }
  connectedCallback() {
    this._observer.observe(this);
    this._refresh();
  }
  disconnectedCallback() {
    clearTimeout(this._timer);
    clearTimeout(this._resize);
    this._observer.disconnect();
    this._seq++;
    this._drawSeq++;
    this._started = false;
  }
  getCardSize() {
    return this._config?.view === "management" ? 10 : 8;
  }
  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto", min_rows: 4 };
  }
  _ensureFrame() {
    if (!this._config) return;
    if (!this.shadowRoot.querySelector(".frame"))
      this.shadowRoot.innerHTML = `<style>${style}</style><ha-card><div class="frame" aria-live="polite"></div></ha-card>`;
    const card = this.shadowRoot.querySelector("ha-card");
    card.style.height =
      this._config.view === "management"
        ? "auto"
        : this._config.aspect_ratio
          ? "auto"
          : `${this._config.height || 420}px`;
    card.style.aspectRatio =
      this._config.view === "management"
        ? "auto"
        : String(this._config.aspect_ratio || "auto");
    if (!this.shadowRoot.querySelector(".frame").childNodes.length)
      this._message("Overhead", "Loading aircraft…");
  }
  _message(title, text) {
    this._ensureFrameBase();
    this.shadowRoot.querySelector(".frame").innerHTML =
      `<div class="message"><strong>${esc(title)}</strong>${esc(text)}</div>`;
  }
  _ensureFrameBase() {
    if (!this.shadowRoot.querySelector(".frame"))
      this.shadowRoot.innerHTML = `<style>${style}</style><ha-card><div class="frame" aria-live="polite"></div></ha-card>`;
  }
  _preview() {
    let n = this;
    while (n) {
      if (
        n.localName &&
        /hui-(card-preview|dialog-edit-card|dialog-create-card)/.test(
          n.localName,
        )
      )
        return true;
      n = n.parentNode || n.host;
    }
    return this.preview === true;
  }
  async _entry(config = this._config) {
    if (config.entry_id) return config.entry_id;
    const entries = await this._hass.callWS({ type: "overhead/entries" });
    if (entries.length !== 1)
      throw new Error(
        entries.length
          ? "Choose an Overhead integration in the card editor."
          : "Add Overhead in Settings → Devices & services first.",
      );
    return entries[0].entry_id;
  }
  async _refresh() {
    clearTimeout(this._timer);
    if (!this.isConnected || !this._config || !this._hass) return;
    if (this._busy) {
      this._timer = setTimeout(() => this._refresh(), 250);
      return;
    }
    this._busy = true;
    const seq = this._seq;
    const config = structuredClone(this._config);
    const preview = this._preview();
    let delay = 60000;
    try {
      const entry = await this._entry(config);
      if (seq !== this._seq || !this.isConnected) return;
      if (config.view === "management") {
        const d = await this._hass.callWS({
          type: "overhead/manage",
          entry_id: entry,
          action: "status",
        });
        if (seq === this._seq && this.isConnected) this._management(d, entry);
        delay = 15000;
      } else {
        const options = Object.fromEntries(
          Object.entries(config).filter(([k]) => !UI_KEYS.has(k)),
        );
        const d = await this._hass.callWS({
          type: "overhead/snapshot",
          entry_id: entry,
          profile_id: config.profile_id,
          options,
          preview,
        });
        if (seq === this._seq && this.isConnected) {
          this._data = d;
          await this._draw(d);
        }
        if (d.live_refresh_s)
          delay = Math.max(10000, Number(d.live_refresh_s) * 1000);
      }
    } catch (err) {
      if (seq === this._seq && this.isConnected) {
        this._data = null;
        this._drawSeq++;
        this._message("Overhead", err.message || String(err));
      }
      delay = 15000;
    } finally {
      this._busy = false;
      if (this.isConnected)
        this._timer = setTimeout(
          () => this._refresh(),
          seq === this._seq ? delay : 0,
        );
    }
  }
  async _draw(data) {
    if (!this.isConnected) return;
    const seq = ++this._drawSeq;
    const d = structuredClone(data);
    for (const a of [...(d.aircraft || []), ...(d.ufo ? [d.ufo] : [])]) {
      if (a.pic) a.pic.src = safeImage(a.pic.src);
      a.logo = safeImage(a.logo);
    }
    // Keep the original renderer offscreen until its async image/layout work completes.
    const staging = document
      .createElement("div")
      .attachShadow({ mode: "open" });
    await render(
      staging,
      {
        data: d,
        cell: {
          size: "md",
          w: this.clientWidth,
          h: this.shadowRoot.querySelector("ha-card").clientHeight,
        },
      },
      this._config.view,
    );
    if (seq !== this._drawSeq || !this.isConnected) return;
    this.shadowRoot.querySelector(".frame").innerHTML = staging.innerHTML;
  }
  _management(d, entry) {
    const c = d.catalogue || {},
      admin = !!this._hass.user?.is_admin;
    this._collectionData = d;
    this._collectionEntry = entry;
    const styles = [
      ...new Set(
        (d.items || []).map((a) => a.style || a.meta?.style).filter(Boolean),
      ),
    ].sort();
    const profiles = [
      ...new Set((d.items || []).flatMap((a) => a.profiles || [])),
    ].sort();
    const filter = this._collectionFilter || {};
    const items = (d.items || [])
      .filter(
        (a) =>
          (!filter.style || (a.style || a.meta?.style) === filter.style) &&
          (!filter.profile || (a.profiles || []).includes(filter.profile)),
      )
      .map(
        (a) =>
          `<article class="art">${safeImage(a.thumb) ? `<img src="${a.thumb}" alt="${esc(a.title)}">` : ""}<h3>${esc(a.title)}</h3><small>${esc(a.state)}${a.meta?.style ? " · " + esc(a.meta.style) : ""}</small><small>${esc(a.meta?.credit || "")}</small>${safeLink(a.meta?.photo_link) ? `<a href="${esc(safeLink(a.meta.photo_link))}" target="_blank" rel="noopener noreferrer">Original photograph</a>` : ""}<small>${esc(a.why || "")}</small>${admin ? `<div class="toolbar"><button data-action="repaint" data-key="${esc(a.key)}">Repaint</button><button data-action="delete" data-key="${esc(a.key)}">Delete</button></div>${a.versions?.length ? `<select aria-label="Earlier version" data-key="${esc(a.key)}"><option value="">Earlier versions…</option>${a.versions.map((v, i) => `<option value="${i}">${esc(new Date(v * 1000).toLocaleString())}</option>`).join("")}</select>` : ""}` : ""}</article>`,
      )
      .join("");
    this.shadowRoot.querySelector(".frame").innerHTML =
      `<div class="management"><h2>Overhead collection</h2><p class="status">${d.generation_enabled ? "AI generation enabled" : "AI generation disabled"} · Estimated use $${(d.used_cents / 100).toFixed(2)} / $${(d.cap_cents / 100).toFixed(2)} today</p><div class="stats"><span><b>${c.airframes || 0}</b> airframes seen</span><span><b>${c.painted || 0}</b> painted</span><span><b>${Math.round((c.next_painted || 0) * 100)}%</b> estimated next-pass coverage</span><span><b>${c.estimate || 0}</b> estimated airframes (Chao1)</span></div><p class="status">${c.passes || 0} passes · ${Math.round((c.painted_passes_share || 0) * 100)}% of passes painted · ${d.total || 0} saved or requested paintings</p><div class="toolbar"><button data-action="refresh">Refresh</button>${admin ? '<button data-action="paint">Paint now</button><button data-action="purge">Purge artwork</button>' : ""}</div><div class="toolbar"><label>Style <select data-filter="style"><option value="">All styles</option>${styles.map((s) => `<option value="${esc(s)}"${filter.style === s ? " selected" : ""}>${esc(s)}</option>`).join("")}</select></label><label>Dashboard card <select data-filter="profile"><option value="">All cards</option>${profiles.map((p) => `<option value="${esc(p)}"${filter.profile === p ? " selected" : ""}>${esc(p)}</option>`).join("")}</select></label></div><div class="action-status" role="status"></div><div class="artwork">${items || "<p>No paintings yet. Choose Paintings on a Plate, Cluster or Scene card to collect subjects.</p>"}</div><details><summary>Saved dashboard cards</summary><ul>${(d.profiles || []).map((p) => `<li>${esc(p.id)} · ${esc(p.view)} ${admin ? `<button data-action="remove_profile" data-key="${esc(p.id)}">Remove</button>` : ""}</li>`).join("")}</ul></details><details><summary>Most frequently seen</summary><ul>${(c.top || []).map((r) => `<li>${esc(r.name)} · ${r.passes} passes${r.painted ? " · painted" : ""}</li>`).join("")}</ul></details></div>`;
    this.shadowRoot.querySelectorAll("[data-filter]").forEach((s) =>
      s.addEventListener("change", () => {
        this._collectionFilter = {
          ...this._collectionFilter,
          [s.dataset.filter]: s.value,
        };
        this._management(d, entry);
      }),
    );
    this.shadowRoot
      .querySelectorAll("button[data-action]")
      .forEach((b) =>
        b.addEventListener("click", () =>
          this._action(entry, b.dataset.action, b.dataset.key || ""),
        ),
      );
    this.shadowRoot.querySelectorAll("select[data-key]").forEach((s) =>
      s.addEventListener("change", () => {
        if (s.value !== "")
          this._action(entry, "restore", s.dataset.key, Number(s.value));
      }),
    );
  }
  async _action(entry, action, key, version = 0) {
    if (action === "refresh") {
      this._refresh();
      return;
    }
    const prompts = {
      purge:
        "Delete every saved painting and version? Daily spend reservations will remain.",
      delete: "Delete this painting and its versions?",
      repaint:
        "Submit another paid painting? Check fal.ai first if the earlier request failed.",
      remove_profile:
        "Remove this saved card profile? Its dashboard card can register it again when opened.",
    };
    if (prompts[action] && !window.confirm(prompts[action])) return;
    const buttons = this.shadowRoot.querySelectorAll("button,select");
    buttons.forEach((b) => (b.disabled = true));
    try {
      await this._hass.callWS({
        type: "overhead/manage",
        entry_id: entry,
        action,
        key,
        version,
      });
      await this._refresh();
    } catch (err) {
      const s = this.shadowRoot.querySelector(".action-status");
      if (s) s.textContent = err.message || String(err);
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  }
}

class OverheadCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._meta = {};
    this._entries = [];
  }
  setConfig(c) {
    this._config = { view: "photo", ...c };
    this._render();
  }
  set hass(h) {
    this._hass = h;
    if (!this._loading) {
      this._loading = true;
      this._load();
    }
  }
  async _load() {
    try {
      this._entries = await this._hass.callWS({ type: "overhead/entries" });
      const id = this._config?.entry_id || this._entries[0]?.entry_id;
      if (id)
        this._meta = await this._hass.callWS({
          type: "overhead/metadata",
          entry_id: id,
        });
      this._render();
    } catch (e) {
      this._error = e.message || String(e);
      this._render();
    }
  }
  _select(key, label, choices) {
    const value = this._config[key] ?? "";
    return `<label>${esc(label)}<select data-key="${key}">${Object.entries(
      choices,
    )
      .map(
        ([v, t]) =>
          `<option value="${esc(v)}"${String(value) === v ? " selected" : ""}>${esc(t)}</option>`,
      )
      .join("")}</select></label>`;
  }
  _input(key, label, type = "text") {
    return `<label>${esc(label)}<input type="${type}" data-key="${key}" value="${esc(this._config[key] ?? "")}"></label>`;
  }
  _render() {
    if (!this._config) return;
    const c = this._config,
      m = this._meta;
    let html =
      this._select("entry_id", "Overhead location", {
        "": "Automatic (one integration)",
        ...Object.fromEntries(this._entries.map((e) => [e.entry_id, e.name])),
      }) +
      this._select("view", "View", {
        photo: "Photo",
        plate: "Plate",
        cluster: "Cluster",
        scene: "Scene",
        management: "Artwork management",
      });
    if (c.view !== "management") {
      html +=
        this._input("profile_id", "Unique card ID") +
        this._input("title", "Title") +
        this._select("pictures", "Pictures", {
          photos: "Photographs",
          paintings: "AI paintings",
        }) +
        this._select("period", "Traffic window", {
          now: "In the air now",
          since: "Since the previous snapshot",
        }) +
        this._input(
          "snapshot_minutes",
          "Snapshot interval (minutes)",
          "number",
        ) +
        this._select("order", "Sort", {
          nearest: "Nearest",
          lowest: "Lowest",
          highest: "Highest",
          largest: "Largest",
          fastest: "Fastest",
        });
      html +=
        this._select("style", "Painting style", {
          ...(m.styles || { poster: "Vintage poster" }),
          builder: "Build my own",
          custom: "My own prompt",
        }) +
        this._select(
          "backdrop",
          "Backdrop",
          m.backdrops || { none: "None", live: "Current sky" },
        ) +
        this._select(
          "viewpoint",
          "Aircraft viewpoint",
          m.viewpoints || { side: "Side" },
        ) +
        this._select(
          "model",
          "Painting model",
          m.models || { nano_banana: "Nano Banana" },
        );
      if (c.style === "builder")
        for (const [key, b] of Object.entries(m.build || {}))
          html += this._select("build_" + key, b.label, b.choices);
      if (c.style === "custom")
        html += this._input("custom_style", "Custom painting prompt");
      html +=
        this._select("font", "Typeface", {
          fell: "IM Fell English",
          archivo: "Archivo Narrow",
          georgia: "Georgia",
          page: "Dashboard font",
        }) +
        this._select("paper", "Paper", {
          cream: "Cream",
          white: "White",
          aged: "Aged",
          blueprint: "Blueprint",
          sky: "Sky",
        }) +
        this._select("look", "Plate layout", {
          plate: "Ruled plate",
          pass: "Boarding pass",
          tiles: "Tiles",
          poster: "Poster",
          split: "Split",
        }) +
        this._input("height", "Card height (pixels)", "number");
      html += `<details><summary>All presentation options</summary><p>Use the documented card options for labels, UFO visitors, custom style details and color modes.</p><textarea aria-label="Additional presentation options" rows="6">${esc(JSON.stringify(Object.fromEntries(Object.entries(c).filter(([k]) => !["type", "entry_id", "profile_id", "view"].includes(k))), null, 2))}</textarea><button class="apply">Apply options</button></details>`;
    }
    this.shadowRoot.innerHTML = `<style>:host{display:block;font:14px system-ui}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}label{display:flex;flex-direction:column;gap:6px}input,select,textarea,button{font:inherit;color:var(--primary-text-color,#222);background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#aaa);border-radius:6px;padding:9px;min-width:0}details{grid-column:1/-1}textarea{display:block;width:100%;box-sizing:border-box}p{line-height:1.5}.error{color:var(--error-color,#b00)}</style><p>Live aircraft and saved paintings. Configure feeds, photo contact and AI generation in the integration options.</p><section>${html}</section><p class="error">${esc(this._error || "")}</p>`;
    this.shadowRoot.querySelectorAll("[data-key]").forEach((el) =>
      el.addEventListener("change", () => {
        const k = el.dataset.key;
        const next = { ...this._config };
        if (el.value === "") delete next[k];
        else next[k] = el.type === "number" ? Number(el.value) : el.value;
        this._emit(next);
        if (k === "view" || k === "style") this._render();
        if (k === "entry_id") this._load();
      }),
    );
    this.shadowRoot.querySelector(".apply")?.addEventListener("click", () => {
      try {
        const more = JSON.parse(
          this.shadowRoot.querySelector("textarea").value,
        );
        if (!more || Array.isArray(more) || typeof more !== "object")
          throw new Error("Enter a JSON object");
        this._emit({
          ...more,
          type: "custom:overhead-card",
          entry_id: c.entry_id,
          profile_id: c.profile_id,
          view: c.view,
        });
        this._error = "";
        this._render();
      } catch (e) {
        this._error = e.message;
        this.shadowRoot.querySelector(".error").textContent = this._error;
      }
    });
  }
  _emit(config) {
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
if (!customElements.get("overhead-card"))
  customElements.define("overhead-card", OverheadCard);
if (!customElements.get("overhead-card-editor"))
  customElements.define("overhead-card-editor", OverheadCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "overhead-card"))
  window.customCards.push({
    type: "overhead-card",
    name: "Overhead",
    description:
      "Aircraft overhead: photos, plates, clusters and painted scenes",
    preview: true,
  });
console.info(
  `Overhead ${VERSION} · adapted from dmellok/tesserae-widget-overhead`,
);
