/* Volcano Hybrid panel. Bundled locally; no framework, CDN, fonts or build step. */
const DOMAIN = "volcano_integration";
const COLOURS = {
  panel_top: ["Panel", "Top", "#373a36"],
  panel_bottom: ["Panel", "Bottom", "#242724"],
  card_background: ["Panel", "Background", "#292b29"],
  card_border: ["Panel", "Border", "#454744"],
  shadow: ["Panel", "Shadow", "#000000"],
  screen_top: ["Display", "Background top", "#696e65"],
  screen_bottom: ["Display", "Background bottom", "#52594f"],
  screen_bezel: ["Display", "Bezel", "#151a15"],
  screen_border: ["Display", "Border", "#81867b"],
  current_temperature: ["Display", "Current temperature", "#ff850c"],
  target_temperature: ["Display", "Target temperature", "#f4f5f0"],
  icons: ["Display", "Icons", "#f5f6f0"],
  icon_glow: ["Display", "Icon glow", "#eeeeee"],
  button_background: ["Buttons", "Background", "#30332f"],
  button_border: ["Buttons", "Border", "#c4c9c0"],
  button_text: ["Buttons", "Text", "#f1f2ef"],
  button_symbols: ["Buttons", "Plus / minus", "#f5f5f0"],
  active_background: ["Buttons", "On background", "#583716"],
  active_border: ["Buttons", "On border", "#ff850c"],
  active_text: ["Buttons", "On text", "#ff9c33"],
  offline_border: ["Buttons", "Disconnected border", "#858884"],
  offline_text: ["Buttons", "Disconnected text", "#92958f"],
  hover: ["Buttons", "Hover", "#ffffff"],
  pressed: ["Buttons", "Pressed", "#ffffff"],
  focus: ["Buttons", "Keyboard focus", "#ffb55f"],
  status_background: ["Status", "Background", "#181a19"],
  status_text: ["Status", "Text", "#c5c8c5"],
  status_error: ["Status", "Error text", "#ffb68c"],
};

function cardConfig(config) {
  const { temperature_unit, ...result } = config; // Retired card override: always follow the device.
  if (result.colors != null) {
    if (typeof result.colors !== "object" || Array.isArray(result.colors)) throw new Error("Colours must be a mapping of colour names to #RRGGBB values.");
    for (const [key, value] of Object.entries(result.colors)) {
      if (!Object.hasOwn(COLOURS, key) || typeof value !== "string" || !/^#[0-9a-f]{6}$/i.test(value)) {
        throw new Error(`Invalid card colour: ${key}. Use a supported colour name and #RRGGBB value.`);
      }
    }
    result.colors = { ...result.colors };
  }
  return result;
}
const ROLES = {
  current: ["sensor", "current_temperature"],
  target: ["number", "heater_temperature_setpoint"],
  heat: ["sensor", "heat_status"],
  air: ["sensor", "pump_status"],
  connection: ["sensor", "bt_status"],
};
const SEGMENTS = ["abcedf", "bc", "abged", "abgcd", "fgbc", "afgcd", "afgecd", "abc", "abcdefg", "abfgcd"];
const SEGMENT_PATHS = {
  a: "M7 2H27L31 6 27 10H7L3 6Z",
  b: "M29 11 33 7 31 29 27 32 24 28 26 14Z",
  c: "M27 34 31 37 29 58 25 61 22 57 24 38Z",
  d: "M4 60H24L28 64 24 68H4L0 64Z",
  e: "M2 35 6 38 4 57 0 61-3 57-1 39Z",
  f: "M4 8 8 12 6 28 2 32-1 28 1 12Z",
  g: "M5 30H25L29 34 25 38H5L1 34Z",
};

function digits(value) {
  const text = Number.isFinite(value) ? String(Math.round(value)).padStart(3, " ") : "---";
  return [...text].slice(-3).map((digit, index) => {
    const active = digit === "-" ? "g" : SEGMENTS[Number(digit)] || "";
    return `<g transform="translate(${index * 44} 0)">${Object.entries(SEGMENT_PATHS).map(([key, path]) =>
      `<path d="${path}" opacity="${digit !== " " && active.includes(key) ? 1 : 0.035}"/>`).join("")}</g>`;
  }).join("");
}

function unit(value) {
  return value === "°F" || value === "F" ? "F" : value === "°C" || value === "C" ? "C" : null;
}

function convert(value, from, to) {
  if (!Number.isFinite(value) || !from || !to) return null;
  return from === to ? value : to === "F" ? value * 9 / 5 + 32 : (value - 32) * 5 / 9;
}

function reading(state, to) {
  if (!state || ["unknown", "unavailable", ""].includes(state.state)) return null;
  return convert(Number(state.state), unit(state.attributes.unit_of_measurement), to);
}

function isVolcano(device) {
  return device.identifiers?.some(([domain]) => domain === DOMAIN);
}

const STYLE = `
  :host { display:block; min-width:0; }
  ha-card { display:block; overflow:hidden; background:var(--card_background); border:1px solid var(--card_border);
    border-radius:16px; box-shadow:0 3px 12px color-mix(in srgb,var(--shadow) 13.333333%,transparent); }
  .panel { position:relative; width:100%; isolation:isolate; background:linear-gradient(160deg,var(--panel_top),var(--panel_bottom)); }
  svg.face { display:block; width:100%; height:auto; }
  .key { fill:var(--button_background); stroke:var(--button_border); stroke-width:1.5; transition:fill .15s,stroke .15s; }
  .key.active { fill:var(--active_background); stroke:var(--active_border); }
  .key-label { fill:var(--button_text); font:700 17px Arial,sans-serif; letter-spacing:1px; text-anchor:middle; }
  .key-label.active { fill:var(--active_text); }
  .temperature { filter:drop-shadow(0 0 1px currentColor); }
  .current { color:var(--current_temperature); fill:var(--current_temperature); }
  .target { color:var(--target_temperature); fill:var(--target_temperature); }
  .heat-off .target { opacity:.65; }
  .unit { font:700 31px Arial,sans-serif; text-anchor:end; }
  .screen-icon { fill:none; stroke:var(--icons); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; opacity:0; }
  .bluetooth-icon { stroke-linecap:square; stroke-linejoin:miter; }
  .power-icon { stroke-width:3.5; opacity:.35; }
  .air-icon { fill:var(--icons); stroke:none; }
  .screen-icon.active { opacity:1; filter:drop-shadow(0 0 1px color-mix(in srgb,var(--icon_glow) 40%,transparent)); }
  button { position:absolute; display:block; padding:0; margin:0; border:0; border-radius:8px;
    background:transparent; color:inherit; cursor:pointer; touch-action:manipulation; -webkit-tap-highlight-color:transparent; }
  button:hover:not(:disabled) { background:color-mix(in srgb,var(--hover) 7.058824%,transparent); }
  button:active:not(:disabled) { background:color-mix(in srgb,var(--pressed) 12.54902%,transparent); }
  button:focus-visible { outline:3px solid var(--focus); outline-offset:3px; background:color-mix(in srgb,var(--hover) 7.058824%,transparent); }
  button:disabled { cursor:default; }
  .decrease, .increase, .heat, .air { width:13.333333%; height:30.303030%; border-radius:10%; }
  .decrease, .heat { left:10.833333%; }
  .increase, .air { right:10.833333%; }
  .decrease, .increase { top:15.151515%; }
  .heat, .air { top:54.545455%; }
  .power { left:29%; top:32.575758%; width:8.666667%; height:16.666667%; }
  .status { min-height:20px; margin:0; padding:8px 18px; font:12px/20px system-ui,sans-serif;
    white-space:normal; overflow-wrap:anywhere;
    text-align:center; color:var(--status_text); background:var(--status_background); }
  .status:empty { display:none; }
  .status.error { color:var(--status_error); }
  .sr-only { position:absolute; width:1px; height:1px; padding:0; overflow:hidden; clip-path:inset(50%); white-space:nowrap; }
  .offline .temperature { opacity:.3; filter:none; }
  .offline .key { stroke:var(--offline_border); }
  .offline .key-label { fill:var(--offline_text); }
  @media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
`;

const PANEL = `
  <ha-card>
    <div class="panel offline">
      <svg class="face" viewBox="0 0 600 264" aria-hidden="true">
        <defs>
          <linearGradient id="screen" x1="0" y1="0" x2="0" y2="1">
            <stop stop-color="var(--screen_top)"/><stop offset="1" stop-color="var(--screen_bottom)"/>
          </linearGradient>
        </defs>
        <rect x="173" y="27" width="254" height="210" rx="3" fill="var(--screen_bezel)" stroke="var(--screen_border)" stroke-opacity=".4"/>
        <rect x="175" y="29" width="250" height="206" rx="2" fill="url(#screen)"/>
        <g class="temperature current" transform="translate(237 48) scale(.93)"></g>
        <g class="temperature target" transform="translate(237 151) scale(.93)"></g>
        <text class="unit current" x="405" y="72">°C</text>
        <text class="unit target" x="405" y="175">°C</text>
        <g class="screen-icon bluetooth-icon" transform="translate(200 60)">
          <path d="M-7-8 8 7 0 14V-14L8-7-7 8"/>
        </g>
        <g class="screen-icon power-icon" transform="translate(200 108)">
          <path d="M-5-9A12 12 0 1 0 5-9M0-13V0"/>
        </g>
        <g class="screen-icon air-icon" transform="translate(200 154)">
          <path d="M-14-13H14L11-6H-11ZM-10-2H10L7 5H-7ZM-6 9H6L4 16H-4Z"/>
        </g>
        <g class="screen-icon heat-icon" transform="translate(200 204)">
          <path d="M0-15C2-8 11-5 11 3A11 11 0 0 1-11 3C-11-1-9-5-6-8L-4-2C0-5 1-10 0-15Z"/>
        </g>
        <rect class="key" x="65" y="40" width="80" height="80" rx="8"/>
        <path d="M89 80H121" fill="none" stroke="var(--button_symbols)" stroke-width="4" stroke-linecap="round"/>
        <rect class="key" x="455" y="40" width="80" height="80" rx="8"/>
        <path d="M479 80H511M495 64V96" fill="none" stroke="var(--button_symbols)" stroke-width="4" stroke-linecap="round"/>
        <rect class="key heat-key" x="65" y="144" width="80" height="80" rx="8"/>
        <rect class="key air-key" x="455" y="144" width="80" height="80" rx="8"/>
        <text class="key-label heat-label" x="105" y="190">HEAT</text>
        <text class="key-label air-label" x="495" y="190">AIR</text>
      </svg>
      <button class="decrease" aria-label="Decrease target temperature" title="Decrease target temperature"></button>
      <button class="increase" aria-label="Increase target temperature" title="Increase target temperature"></button>
      <button class="heat" aria-label="Toggle heat" aria-pressed="false" title="Toggle heat"></button>
      <button class="air" aria-label="Toggle air" aria-pressed="false" title="Toggle air"></button>
      <button class="power" aria-label="Connect Bluetooth" title="Connect Bluetooth"></button>
      <span class="sr-only temperatures"></span>
    </div>
    <p class="status" role="status" aria-live="polite"></p>
  </ha-card>
`;

class VolcanoHybridCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>${PANEL}`;
    this._entities = {};
    this._generation = 0;
    for (const action of ["decrease", "increase", "heat", "air", "power"]) {
      this.shadowRoot.querySelector(`button.${action}`).addEventListener("click", () => this._action(action));
    }
  }

  static async getConfigElement() {
    // HA lazy-loads ha-form. Load its own button editor before using the form,
    // including when this is the first card editor opened after a fresh login.
    if (!customElements.get("ha-form")) {
      const helpers = await window.loadCardHelpers();
      const button = await helpers.createCardElement({ type: "button" });
      await button.constructor.getConfigElement();
    }
    return document.createElement("volcano-hybrid-card-editor");
  }
  static getStubConfig(hass) {
    const device = Object.values(hass.devices || {}).find(isVolcano);
    return { device: device?.id || "" };
  }
  getCardSize() { return 3; }
  getGridOptions() { return { columns: 12, rows: "auto", min_columns: 6 }; }

  setConfig(config) {
    if (config.device != null && typeof config.device !== "string") throw new Error("Select one Volcano device.");
    this._config = cardConfig(config);
    for (const [key, [, , fallback]] of Object.entries(COLOURS)) {
      this.style.setProperty(`--${key}`, this._config.colors?.[key] || fallback);
    }
    this._entities = {};
    this._loading = false;
    this._registryError = "";
    this._error = "";
    this._pending = null;
    clearTimeout(this._confirmationTimer);
    this._resolve();
    this._render();
  }

  set hass(hass) {
    const changedConnection = this._hass?.connection !== hass.connection;
    const changedRegistry = hass.entities && this._hass?.entities !== hass.entities;
    this._hass = hass;
    if (changedConnection) { this._entities = {}; this._unsubscribe(); }
    if (changedConnection || changedRegistry) this._resolve();
    if (this.isConnected) this._subscribe();
    this._render();
  }
  get hass() { return this._hass; }

  connectedCallback() { this._subscribe(); this._resolve(); }
  disconnectedCallback() {
    this._unsubscribe();
    this._generation++;
    clearTimeout(this._confirmationTimer);
    this._pending = null;
  }

  _subscribe() {
    if (!this._hass?.connection || this._subscription) return;
    const connection = this._hass.connection;
    // A promise also marks subscription-in-progress, preventing duplicate listeners.
    const subscription = connection.subscribeEvents(() => this._resolve(), "entity_registry_updated");
    this._subscription = subscription;
    subscription.then(unsubscribe => {
      if (this._subscription !== subscription || !this.isConnected) unsubscribe();
      else this._unsubscribeRegistry = unsubscribe;
    }).catch(() => { if (this._subscription === subscription) this._subscription = null; });
  }

  _unsubscribe() {
    this._unsubscribeRegistry?.();
    this._unsubscribeRegistry = null;
    this._subscription = null;
  }

  async _resolve() {
    const generation = ++this._generation;
    if (!this._hass || !this._config?.device || !this.isConnected) return;
    this._loading = true;
    try {
      const registry = await this._hass.callWS({ type: "config/entity_registry/list" });
      if (generation !== this._generation) return;
      const entries = registry.filter(entry => entry.device_id === this._config.device && entry.platform === DOMAIN && !entry.disabled_by);
      this._entities = Object.fromEntries(Object.entries(ROLES).map(([role, [domain, key]]) => [role,
        entries.find(entry => entry.entity_id.startsWith(`${domain}.`) && entry.unique_id?.startsWith(`volcano_${key}_`))?.entity_id,
      ]));
      this._registryError = "";
    } catch (error) {
      if (generation !== this._generation) return;
      this._registryError = `Could not load device controls: ${error.message || "connection unavailable"}. Tap power to retry.`;
    } finally {
      if (generation === this._generation) { this._loading = false; this._render(); }
    }
  }

  _state(role) { return this._hass?.states[this._entities[role]]; }
  _deviceUnit() { return unit(this._state("current")?.attributes.device_temperature_unit) || unit(this._state("target")?.attributes.device_temperature_unit); }
  _unit() { return this._deviceUnit() || unit(this._state("target")?.attributes.temperature_unit_fallback); }
  _connected() { return this._state("connection")?.state === "CONNECTED"; }
  _connecting() {
    const connection = this._state("connection");
    return !this._connected() && (connection?.state === "CONNECTING" || connection?.attributes?.connection_requested === true);
  }
  _known(role) { return ["ON", "OFF"].includes(this._state(role)?.state); }

  _render() {
    if (!this._config) return;
    const connected = this._connected();
    const displayUnit = this._unit();
    const current = connected ? reading(this._state("current"), displayUnit) : null;
    const target = connected ? reading(this._state("target"), displayUnit) : null;
    const pendingState = this._pending && this._state(this._pending.role)?.state;
    const confirmed = this._pending?.role === "target"
      ? Number.isFinite(Number(pendingState)) && Math.abs(Number(pendingState) - this._pending.expected) < 0.11
      : this._pending && pendingState === this._pending.expected;
    if (confirmed || !connected) {
      clearTimeout(this._confirmationTimer);
      this._pending = null;
    }
    const root = this.shadowRoot;
    root.querySelector(".panel").classList.toggle("offline", !connected);
    root.querySelector(".panel").classList.toggle("heat-off", connected && this._state("heat")?.state === "OFF");
    root.querySelector("g.current").innerHTML = digits(current);
    root.querySelector("g.target").innerHTML = digits(target);
    root.querySelectorAll(".unit").forEach(element => { element.textContent = displayUnit ? `°${displayUnit}` : ""; });
    root.querySelector(".temperatures").textContent = `Current temperature: ${current == null ? "unavailable" : Math.round(current)}. Target temperature: ${target == null ? "unavailable" : Math.round(target)}${displayUnit ? ` degrees ${displayUnit === "C" ? "Celsius" : "Fahrenheit"}` : ". Device temperature unit unavailable"}.`;
    root.querySelector(".power-icon").classList.toggle("active", connected);
    root.querySelector(".bluetooth-icon").classList.toggle("active", connected);
    for (const role of ["heat", "air"]) {
      const active = connected && this._state(role)?.state === "ON";
      root.querySelector(`.${role}-key`).classList.toggle("active", active);
      root.querySelector(`.${role}-label`).classList.toggle("active", active);
      root.querySelector(`.${role}-icon`).classList.toggle("active", active);
      const button = root.querySelector(`button.${role}`);
      button.setAttribute("aria-pressed", String(active));
      button.disabled = !connected || !this._known(role) || Boolean(this._busy || this._pending);
    }
    const attrs = this._state("target")?.attributes;
    const min = convert(attrs?.min, unit(attrs?.unit_of_measurement), displayUnit);
    const max = convert(attrs?.max, unit(attrs?.unit_of_measurement), displayUnit);
    root.querySelector(".decrease").disabled = !connected || target == null || min == null || target <= min || Boolean(this._busy || this._pending);
    root.querySelector(".increase").disabled = !connected || target == null || max == null || target >= max || Boolean(this._busy || this._pending);
    const power = root.querySelector("button.power");
    const connecting = this._connecting();
    const powerLabel = connected ? "Turn off heat and air, then disconnect Bluetooth" : connecting ? "Cancel Bluetooth connection" : "Connect Bluetooth";
    power.setAttribute("aria-label", powerLabel);
    power.title = powerLabel;
    power.disabled = !this._config.device || Boolean(this._busy) || (!this._entities.connection && !this._registryError);
    let status = "";
    if (!this._config.device) status = "Select your Volcano device in the card editor.";
    else if (this._registryError) status = this._registryError;
    else if (this._loading) status = "Finding device controls…";
    else if (Object.values(ROLES).length !== Object.values(this._entities).filter(Boolean).length) status = "Device controls are missing. Select a Volcano Hybrid and enable its temperature, heat, air and Bluetooth entities.";
    else if (this._error) status = this._error;
    else if (this._busy) status = this._busyMessage;
    else if (this._pending) status = `Waiting for ${this._pending.role === "target" ? "target temperature" : this._pending.role} status…`;
    else if (connecting) status = "Connecting… Tap power to cancel.";
    else if (!connected) status = "Bluetooth disconnected · Tap power to connect";
    else if (!displayUnit) status = "Device temperature unit unavailable. Reconnect the Volcano to read its setting.";
    else if (!this._deviceUnit()) status = "Device unit not reported; using °C.";
    const statusElement = root.querySelector(".status");
    statusElement.textContent = status;
    statusElement.classList.toggle("error", Boolean(this._error || this._registryError));
  }

  async _action(action) {
    if (this._busy || !this._config?.device) return;
    if (this._registryError) { await this._resolve(); return; }
    const device = this._config.device;
    const generation = this._generation;
    const connected = this._connected();
    const domain = action === "decrease" || action === "increase" ? "number" : DOMAIN;
    let service, data;
    let confirmation;
    if (action === "power") {
      service = connected || this._connecting() ? "disconnect" : "connect";
      data = { device_id: device, ...(service === "connect" ? { wait_until_connected: false } : {}) };
    } else if (["heat", "air"].includes(action)) {
      if (!connected || !this._known(action) || this._pending) return;
      const on = this._state(action).state === "ON";
      service = `${action === "air" ? "pump" : "heat"}_${on ? "off" : "on"}`;
      data = { device_id: device };
      confirmation = { role: action, expected: on ? "OFF" : "ON" };
    } else {
      if (!connected || this._pending) return;
      const state = this._state("target");
      const displayUnit = this._unit();
      const target = reading(state, displayUnit);
      const sourceUnit = unit(state?.attributes.unit_of_measurement);
      if (target == null || !Number.isFinite(state.attributes.min) || !Number.isFinite(state.attributes.max)) return;
      const value = convert(Math.round(target) + (action === "increase" ? 1 : -1), displayUnit, sourceUnit);
      service = "set_value";
      data = { entity_id: this._entities.target, value: Math.max(state.attributes.min, Math.min(state.attributes.max, Number(value.toFixed(4)))) };
      if (Math.abs(data.value - Number(state.state)) < 0.0001) return;
      confirmation = { role: "target", expected: data.value };
    }
    this._busy = true;
    this._busyMessage = action === "power" && connected ? "Turning off heat and air…" : "Sending…";
    this._error = "";
    this._render();
    try {
      await this._hass.callService(domain, service, data);
      if (device !== this._config.device || generation !== this._generation || !this.isConnected) return;
      if (confirmation) {
        this._pending = confirmation;
        this._confirmationTimer = setTimeout(() => {
          this._pending = null;
          this._error = "No status confirmation yet. Check the device before trying again.";
          this._render();
        }, 5000);
      }
    } catch (error) {
      if (device === this._config.device) this._error = error.message || "Command failed. Check the Bluetooth connection.";
    } finally {
      this._busy = false;
      this._render();
    }
  }
}

class VolcanoHybridCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }
  setConfig(config) { this._config = cardConfig(config); this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.schema = [
        { name: "device", required: true, selector: { device: { filter: { integration: DOMAIN } } } },
      ];
      this._form.computeLabel = () => "Volcano device";
      this._form.addEventListener("value-changed", event => {
        event.stopPropagation();
        this._config = { ...this._config, device: event.detail.value.device };
        this._changed();
      });
      this.shadowRoot.append(this._form);
      const style = document.createElement("style");
      style.textContent = `:host { display:block; color:var(--primary-text-color); }
        p { font-size:14px; line-height:1.5; color:var(--secondary-text-color); }
        details { border-top:1px solid var(--divider-color,#ddd); padding:12px 0; }
        summary { cursor:pointer; font-weight:500; }
        .colours { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px 20px; padding-top:16px; }
        label { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:14px; }
        input { width:42px; height:32px; flex-shrink:0; padding:2px; border:1px solid var(--divider-color,#ccc); border-radius:6px; background:none; cursor:pointer; }
        button { display:block; margin:12px 0; padding:10px 16px; border:1px solid var(--divider-color,#ccc); border-radius:8px; background:none; color:var(--primary-color,#03a9f4); font:inherit; cursor:pointer; }
        @media(max-width:450px) { .colours { grid-template-columns:1fr; } }`;
      this.shadowRoot.append(style);
      const note = document.createElement("p");
      note.textContent = "Temperatures follow the Volcano’s °C / °F setting. Change it under Configuration on the device page.";
      this.shadowRoot.append(note);
      const groups = {};
      for (const [key, [group, label]] of Object.entries(COLOURS)) {
        if (!groups[group]) {
          const details = document.createElement("details");
          const summary = document.createElement("summary");
          summary.textContent = `${group === "Buttons" ? "Button" : group} colours`;
          const grid = document.createElement("div");
          grid.className = "colours";
          details.append(summary, grid);
          this.shadowRoot.append(details);
          groups[group] = grid;
        }
        const row = document.createElement("label");
        row.append(document.createTextNode(label));
        const input = document.createElement("input");
        input.type = "color";
        input.name = key;
        input.addEventListener("input", () => {
          this._config = { ...this._config, colors: { ...this._config.colors, [key]: input.value } };
          this._changed();
        });
        row.append(input);
        groups[group].append(row);
      }
      const reset = document.createElement("button");
      reset.type = "button";
      reset.textContent = "Reset colours";
      reset.addEventListener("click", () => {
        const { colors, ...config } = this._config;
        this._config = config;
        this._render();
        this._changed();
      });
      this.shadowRoot.append(reset);
    }
    this._form.hass = this._hass;
    this._form.data = { device: this._config.device };
    for (const [key, [, , fallback]] of Object.entries(COLOURS)) {
      this.shadowRoot.querySelector(`input[name="${key}"]`).value = this._config.colors?.[key] || fallback;
    }
  }
  _changed() {
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("volcano-hybrid-card")) customElements.define("volcano-hybrid-card", VolcanoHybridCard);
if (!customElements.get("volcano-hybrid-card-editor")) customElements.define("volcano-hybrid-card-editor", VolcanoHybridCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "volcano-hybrid-card")) window.customCards.push({
  type: "volcano-hybrid-card",
  name: "Volcano Hybrid",
  description: "The Hybrid control panel. Select your Volcano device; controls are discovered automatically.",
  preview: true,
  documentationURL: "https://github.com/Chuffnugget/volcano_integration#hybrid-dashboard-card",
});
