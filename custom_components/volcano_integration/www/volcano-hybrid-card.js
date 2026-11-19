/* Volcano Hybrid panel. Bundled locally; no framework, CDN, fonts or build step. */
const DOMAIN = "volcano_integration";
const HOLD_DELAY = 400;
const HOLD_INTERVAL = 120;
const HOLD_SEND_INTERVAL = 300;
const PRESET_TEMPERATURES = Array.from({ length: 13 }, (_, index) => 170 + index * 5);
const EXTRA_OPTIONS = {
  show_brightness: "Show brightness",
  show_auto_shutoff: "Show auto shutoff",
  show_vibration: "Show vibration",
  show_stop_all: "Show Stop all",
  show_script_buttons: "Show script buttons",
  show_temperature_presets: "Show temperature presets",
};
const DEFAULT_OPTIONS = {
  temperature_acceleration: 100,
  ...Object.fromEntries(Object.keys(EXTRA_OPTIONS).map(key => [key, false])),
  stop_all_entities: [],
  collapse_extras: false,
};
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
  if (result.temperature_acceleration !== undefined &&
      (!Number.isInteger(result.temperature_acceleration) || result.temperature_acceleration < 0 || result.temperature_acceleration > 300)) {
    throw new Error("Temperature acceleration must be a whole percentage from 0 to 300.");
  }
  for (const key of [...Object.keys(EXTRA_OPTIONS), "collapse_extras"]) {
    if (result[key] !== undefined && typeof result[key] !== "boolean") throw new Error(`${key} must be true or false.`);
  }
  if (result.stop_all_entities !== undefined) {
    if (!Array.isArray(result.stop_all_entities) || result.stop_all_entities.some(id =>
      typeof id !== "string" || !/^(script|automation)\.[a-z0-9_]+$/.test(id))) {
      throw new Error("Stop all entities must be a list of script or automation entity IDs.");
    }
    result.stop_all_entities = [...new Set(result.stop_all_entities)];
  }
  if (result.script_buttons !== undefined) {
    if (!Array.isArray(result.script_buttons) || result.script_buttons.some(item =>
      !item || typeof item !== "object" || Array.isArray(item) ||
      typeof item.entity !== "string" || !/^script\.[a-z0-9_]+$/.test(item.entity) ||
      (item.show !== undefined && typeof item.show !== "boolean") ||
      Object.keys(item).some(key => !["entity", "show"].includes(key)))) {
      throw new Error("Script buttons must be a list of script entity/show mappings; show must be true or false.");
    }
    if (new Set(result.script_buttons.map(item => item.entity)).size !== result.script_buttons.length) {
      throw new Error("Each script button must appear only once.");
    }
    result.script_buttons = result.script_buttons.map(item => ({ ...item }));
  }
  if (result.temperature_presets !== undefined) {
    if (!Array.isArray(result.temperature_presets) || result.temperature_presets.some(item =>
      !item || typeof item !== "object" || Array.isArray(item) || !PRESET_TEMPERATURES.includes(item.temperature) ||
      (item.show !== undefined && typeof item.show !== "boolean") ||
      (item.name !== undefined && (typeof item.name !== "string" || item.name.length > 60)) ||
      Object.keys(item).some(key => !["temperature", "name", "show"].includes(key)))) {
      throw new Error("Temperature presets use Celsius from 170 to 230 in steps of 5, with an optional name and show boolean.");
    }
    if (new Set(result.temperature_presets.map(item => item.temperature)).size !== result.temperature_presets.length) {
      throw new Error("Each preset temperature must appear only once.");
    }
    result.temperature_presets = result.temperature_presets.map(item => ({ ...item }));
  }
  return result;
}

function temperaturePresets(config) {
  const selected = config.temperature_presets ?? PRESET_TEMPERATURES.map(temperature => ({ temperature }));
  const listed = new Set(selected.map(item => item.temperature));
  return [...selected, ...PRESET_TEMPERATURES.filter(temperature => !listed.has(temperature)).map(temperature => ({ temperature, show: false }))]
    .map(item => ({ ...item, show: item.show !== false }));
}

function scriptButtons(config) {
  const scripts = (config.stop_all_entities || []).filter(id => id.startsWith("script."));
  const ordered = (config.script_buttons || []).filter(item => scripts.includes(item.entity));
  const listed = new Set(ordered.map(item => item.entity));
  return [...ordered, ...scripts.filter(entity => !listed.has(entity)).map(entity => ({ entity }))]
    .map(item => ({ entity: item.entity, show: item.show !== false }));
}

const ROLES = {
  current: ["sensor", "current_temperature"],
  target: ["number", "heater_temperature_setpoint"],
  heat: ["sensor", "heat_status"],
  air: ["sensor", "pump_status"],
  connection: ["sensor", "bt_status"],
};
const OPTIONAL_ROLES = {
  brightness: ["number", "led_brightness_number"],
  shutoff: ["number", "auto_shutoff_minutes"],
  vibration: ["switch", "vibration"],
};
const SETTING_LABELS = { brightness: "brightness", shutoff: "auto shutoff", vibration: "vibration", outputs: "heat and air" };
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

function renderDigits(element, value) {
  const text = Number.isFinite(value) ? String(Math.round(value)).padStart(3, " ") : "---";
  const displayed = text.slice(-3);
  if (element.dataset.value === displayed) return;
  // Keep the SVG nodes alive during holds and incoming HA state updates.
  if (!element.childElementCount) {
    element.innerHTML = Array.from({ length: 3 }, (_, index) =>
      `<g transform="translate(${index * 44} 0)">${Object.values(SEGMENT_PATHS).map(path =>
        `<path d="${path}" opacity="0.035"/>`).join("")}</g>`).join("");
  }
  [...displayed].forEach((digit, index) => {
    if (element.dataset.value?.[index] === digit) return;
    const active = digit === "-" ? "g" : digit === " " ? "" : SEGMENTS[Number(digit)] || "";
    Object.keys(SEGMENT_PATHS).forEach((key, segmentIndex) => {
      const segment = element.children[index].children[segmentIndex];
      const opacity = active.includes(key) ? "1" : "0.035";
      if (segment.getAttribute("opacity") !== opacity) segment.setAttribute("opacity", opacity);
    });
  });
  element.dataset.value = displayed;
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
  .decrease, .increase { top:15.151515%; touch-action:none; user-select:none; -webkit-touch-callout:none; }
  .heat, .air { top:54.545455%; }
  .power { left:29%; top:32.575758%; width:8.666667%; height:16.666667%; }
  .target-edit { left:38%; top:54%; width:31%; height:32%; }
  .target-edit:hover:not(:disabled) { background:color-mix(in srgb,var(--hover) 4%,transparent); }
  dialog { box-sizing:border-box; width:min(340px,calc(100vw - 32px)); max-width:calc(100vw - 32px);
    padding:24px; border:1px solid var(--button_border); border-radius:16px; background:var(--card_background);
    color:var(--button_text); font:14px/1.5 system-ui,sans-serif; box-shadow:0 12px 40px #0007; }
  dialog::backdrop { background:#0008; }
  dialog label { display:block; margin-bottom:16px; font-size:16px; font-weight:600; }
  .temperature-entry { display:flex; align-items:center; gap:12px; }
  .temperature-entry input { min-width:0; width:100%; box-sizing:border-box; padding:10px 12px;
    border:1px solid var(--button_border); border-radius:8px; background:var(--button_background);
    color:var(--button_text); font:28px system-ui,sans-serif; }
  .temperature-entry input:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
  .temperature-entry-unit { font-size:24px; }
  .temperature-entry-range { color:var(--status_text); font-size:12px; }
  .temperature-entry-error { color:var(--status_error); overflow-wrap:anywhere; }
  .temperature-entry-error:empty { display:none; }
  .temperature-entry-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:20px; }
  .temperature-entry-actions button { position:static; padding:10px 16px; background:var(--button_background); font:inherit; }
  .temperature-entry-actions button[type=submit] { background:var(--active_background); color:var(--active_text); }
  .extras-toggle { position:static; display:flex; align-items:center; justify-content:space-between;
    width:calc(100% - 40px); margin:0 20px 12px; padding:12px 14px; min-height:44px;
    color:var(--status_text); background:var(--status_background); font:13px/1.4 system-ui,sans-serif; text-align:left; gap:12px; }
  .extras-toggle span { overflow-wrap:anywhere; }
  .extras-toggle svg { width:16px; height:16px; flex-shrink:0; fill:none; stroke:currentColor; stroke-width:2; }
  .extras-toggle[aria-expanded=true] svg { transform:rotate(180deg); }
  .status { min-height:20px; margin:0; padding:8px 18px; font:12px/20px system-ui,sans-serif;
    white-space:normal; overflow-wrap:anywhere;
    text-align:center; color:var(--status_text); background:var(--status_background); }
  .status:empty { display:none; }
  .status.error { color:var(--status_error); }
  [hidden] { display:none !important; }
  .extras { container-type:inline-size; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px;
    margin:0 20px 20px; padding:16px; border:1px solid color-mix(in srgb,var(--button_border) 12%,transparent);
    border-radius:14px; background:color-mix(in srgb,var(--status_background) 45%,var(--card_background));
    color:var(--button_text); font:13px/1.4 Arial,sans-serif; }
  .extra-row { min-width:0; }
  .brightness-row, .stop-row, .scripts-row, .presets-row { grid-column:1/-1; }
  .setting-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:4px; }
  .setting-label { display:flex; align-items:center; gap:7px; min-width:0; font-size:12px; font-weight:500; }
  .setting-icon { width:16px; height:16px; flex-shrink:0; fill:none; stroke:var(--status_text);
    stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
  .setting-value { color:var(--status_text); font-size:12px; font-variant-numeric:tabular-nums; }
  .brightness-value { color:var(--active_text); font-size:13px; font-weight:600; }
  .setting-note { display:block; color:var(--status_text); font-size:11px; line-height:1.5; }
  .adjuster { display:flex; align-items:center; gap:12px; }
  .extras button { position:static; display:flex; align-items:center; justify-content:center; flex-shrink:0;
    height:40px; padding:0 12px; border:1px solid transparent; border-radius:9px;
    background:color-mix(in srgb,var(--button_border) 6%,transparent); color:var(--button_text); font:inherit; }
  .extras button:hover:not(:disabled) { background:color-mix(in srgb,var(--hover) 12%,var(--button_background)); }
  .extras button:active:not(:disabled) { background:color-mix(in srgb,var(--pressed) 18%,var(--button_background)); }
  .extras button:disabled, .extras input:disabled { opacity:.4; }
  .extras .brightness-decrease, .extras .brightness-increase { width:36px; height:36px; padding:0; font-size:22px; }
  .extras input { accent-color:var(--active_border); min-width:0; }
  .extras input:focus-visible { outline:2px solid var(--focus); outline-offset:3px; }
  .extras input[type=range] { appearance:none; -webkit-appearance:none; flex:1; width:100%; height:36px;
    margin:0; padding:0; background:transparent; cursor:pointer; }
  .extras input[type=range]::-webkit-slider-runnable-track { height:4px; border-radius:4px;
    background:linear-gradient(to right,var(--active_border) var(--brightness-position,0%),
      color-mix(in srgb,var(--button_border) 20%,transparent) var(--brightness-position,0%)); }
  .extras input[type=range]::-webkit-slider-thumb { appearance:none; -webkit-appearance:none; width:14px;
    height:14px; margin-top:-5px; border:0; border-radius:50%; background:var(--active_border); }
  .extras input[type=range]::-moz-range-track { height:4px; border-radius:4px; background:color-mix(in srgb,var(--button_border) 20%,transparent); }
  .extras input[type=range]::-moz-range-progress { height:4px; border-radius:4px; background:var(--active_border); }
  .extras input[type=range]::-moz-range-thumb { width:14px; height:14px; border:0; border-radius:50%; background:var(--active_border); }
  .setting-tile { display:flex; flex-direction:column; justify-content:space-between; gap:12px; padding:12px;
    border-radius:10px; background:color-mix(in srgb,var(--button_border) 5%,transparent); }
  .extras:has(.shutoff-row[hidden]) .vibration-row, .extras:has(.vibration-row[hidden]) .shutoff-row { grid-column:1/-1; }
  .shutoff-controls, .vibration-controls { display:flex; align-items:center; gap:8px; min-height:30px; }
  .shutoff-value { appearance:textfield; -moz-appearance:textfield; width:64px; box-sizing:border-box;
    padding:0; border:0; border-radius:3px; background:transparent; color:var(--button_text);
    font:500 24px/30px Arial,sans-serif; font-variant-numeric:tabular-nums; }
  .shutoff-value::-webkit-inner-spin-button, .shutoff-value::-webkit-outer-spin-button { -webkit-appearance:none; margin:0; }
  .shutoff-note, .vibration-note { margin-top:3px; }
  .extras .vibration-toggle { position:relative; width:46px; height:28px; padding:0; border-radius:20px;
    background:color-mix(in srgb,var(--button_border) 23%,var(--button_background)); }
  .vibration-toggle::after { content:""; position:absolute; width:20px; height:20px; left:3px; top:3px;
    border-radius:50%; background:var(--button_text); transition:transform .15s; }
  .extras .vibration-toggle[aria-checked=true] { background:var(--active_border); }
  .vibration-toggle[aria-checked=true]::after { transform:translateX(18px); }
  .vibration-state { color:var(--status_text); font-size:12px; }
  .extras .stop-all { width:100%; gap:9px; font-weight:600; border-color:color-mix(in srgb,var(--active_border) 40%,transparent);
    color:var(--active_text); background:color-mix(in srgb,var(--active_background) 35%,transparent); }
  .stop-all svg { width:12px; height:12px; fill:currentColor; }
  .stop-row .setting-note { text-align:center; margin-top:7px; }
  .presets-row > .setting-label { margin-bottom:10px; }
  .preset-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(70px,1fr)); gap:8px; }
  .extras .temperature-preset { height:auto; min-height:44px; padding:10px 6px; flex-direction:column; gap:4px;
    border-color:color-mix(in srgb,var(--button_border) 10%,transparent); font-variant-numeric:tabular-nums; }
  .temperature-preset .preset-name { font-size:11px; overflow-wrap:anywhere; }
  .temperature-preset .preset-value { white-space:nowrap; font-weight:600; }
  .extras .temperature-preset[aria-pressed=true] { color:var(--active_text); background:var(--active_background); border-color:var(--active_border); }
  .script-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .scripts-row > .setting-label { margin-bottom:10px; }
  .extras .script-run { height:auto; min-height:60px; width:100%; justify-content:flex-start; gap:10px;
    padding:12px; text-align:left; border-color:color-mix(in srgb,var(--button_border) 10%,transparent); }
  .script-run svg { width:18px; height:18px; flex-shrink:0; fill:var(--active_text); }
  .script-copy { display:flex; flex-direction:column; min-width:0; gap:4px; }
  .script-name { font-size:13px; font-weight:600; overflow-wrap:anywhere; }
  .script-state { color:var(--status_text); font-size:11px; overflow-wrap:anywhere; }
  .extras .script-run.running { opacity:1; border-color:color-mix(in srgb,var(--active_border) 45%,transparent);
    background:color-mix(in srgb,var(--active_background) 35%,transparent); }
  .script-run.running .script-state { color:var(--active_text); }
  .script-run.running .script-state::before { content:""; display:inline-block; width:6px; height:6px;
    margin-right:6px; border-radius:50%; background:currentColor; }
  .script-run.failed .script-state { color:var(--status_error); }
  @container(max-width:300px) { .script-grid { grid-template-columns:1fr; } }
  @container(max-width:235px) { .setting-tile { grid-column:1/-1; } }
  @media(max-width:450px) { .extras { margin:0 12px 12px; padding:12px; gap:10px; }
    .extras-toggle { margin:0 12px 12px; width:calc(100% - 24px); } }
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
      <button class="decrease" aria-label="Decrease target temperature" title="Decrease target temperature (hold to repeat)"></button>
      <button class="increase" aria-label="Increase target temperature" title="Increase target temperature (hold to repeat)"></button>
      <button class="heat" aria-label="Toggle heat" aria-pressed="false" title="Toggle heat"></button>
      <button class="air" aria-label="Toggle air" aria-pressed="false" title="Toggle air"></button>
      <button class="power" aria-label="Connect Bluetooth" title="Connect Bluetooth"></button>
      <button class="target-edit" aria-label="Set target temperature" title="Tap to enter target temperature"></button>
      <span class="sr-only temperatures"></span>
    </div>
    <p class="status" role="status" aria-live="polite"></p>
    <dialog class="temperature-dialog" aria-labelledby="temperature-entry-label">
      <form novalidate>
        <label id="temperature-entry-label" for="temperature-entry">Target temperature</label>
        <div class="temperature-entry"><input id="temperature-entry" type="number" inputmode="numeric" step="1" required aria-describedby="temperature-entry-range temperature-entry-error"><span class="temperature-entry-unit"></span></div>
        <p class="temperature-entry-range" id="temperature-entry-range"></p>
        <p class="temperature-entry-error" id="temperature-entry-error" role="alert"></p>
        <div class="temperature-entry-actions"><button type="button" class="temperature-cancel">Cancel</button><button type="submit">Set temperature</button></div>
      </form>
    </dialog>
    <button class="extras-toggle" type="button" aria-expanded="false" aria-controls="extra-controls" hidden><span>Extra controls</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
    <div class="extras" id="extra-controls" hidden>
      <div class="extra-row presets-row" hidden><span class="setting-label">Temperature presets</span><div class="preset-grid"></div><span class="presets-empty setting-note" hidden>No presets selected. Choose them in the card editor.</span></div>
      <div class="extra-row brightness-row" hidden>
        <div class="setting-heading">
          <label class="setting-label" for="brightness"><svg class="setting-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2V4M12 20V22M2 12H4M20 12H22M5 5L6.5 6.5M17.5 17.5L19 19M5 19L6.5 17.5M17.5 6.5L19 5"/></svg>Brightness</label>
          <span class="brightness-value setting-value"></span>
        </div>
        <div class="adjuster">
          <button class="brightness-decrease" aria-label="Decrease display brightness">−</button>
          <input id="brightness" type="range" min="0" max="100" step="1" aria-label="Display brightness">
          <button class="brightness-increase" aria-label="Increase display brightness">+</button>
        </div>
      </div>
      <div class="extra-row shutoff-row setting-tile" hidden>
        <label class="setting-label" for="shutoff"><svg class="setting-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="14" r="8"/><path d="M9 2H15M12 2V6M18 7L20 5M12 10V14L15 16"/></svg>Auto shutoff</label>
        <div><div class="shutoff-controls"><input id="shutoff" class="shutoff-value" type="number" aria-label="Auto shutoff"><span class="shutoff-unit setting-value"></span></div><span class="shutoff-note setting-note" hidden></span></div>
      </div>
      <div class="extra-row vibration-row setting-tile" hidden>
        <span class="setting-label"><svg class="setting-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="4" width="8" height="16" rx="2"/><path d="M4 7L2 10 4 13 2 16M20 7L22 10 20 13 22 16"/></svg>Vibration</span>
        <div><div class="vibration-controls"><button class="vibration-toggle" role="switch" aria-label="Vibration" aria-checked="false"></button><span class="vibration-state">Off</span></div><span class="vibration-note setting-note" hidden></span></div>
      </div>
      <div class="extra-row scripts-row" hidden>
        <span class="setting-label">Scripts</span>
        <div class="script-grid"></div>
        <span class="scripts-empty setting-note" hidden>No script buttons selected. Choose scripts in the card editor.</span>
      </div>
      <div class="extra-row stop-row" hidden>
        <button class="stop-all"><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2"/></svg>Stop all</button>
        <span class="stop-note setting-note"></span>
      </div>
    </div>
  </ha-card>
`;

class VolcanoHybridCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>${PANEL}`;
    this._entities = {};
    this._generation = 0;
    this._serviceCalls = new Set();
    this._scriptRequests = new Map();
    this._scriptErrors = new Map();
    this._scriptNodes = new Map();
    this._presetNodes = new Map();
    this._stopRepeat = () => this._stopHold();
    this._visibilityChanged = () => { if (document.hidden) this._stopHold(); };
    for (const action of ["decrease", "increase", "heat", "air", "power"]) {
      const button = this.shadowRoot.querySelector(`button.${action}`);
      if (action === "decrease" || action === "increase") {
        button.addEventListener("pointerdown", event => this._startHold(event, action));
        for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
          button.addEventListener(type, event => {
            if (event.pointerId === this._hold?.pointerId) this._stopHold();
          });
        }
        button.addEventListener("pointermove", event => {
          if (event.pointerId !== this._hold?.pointerId) return;
          const box = button.getBoundingClientRect();
          if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) this._stopHold();
        });
        button.addEventListener("contextmenu", event => event.preventDefault());
        // Pointer presses act on down; ignore their follow-up click. Keyboard
        // and assistive-technology clicks still make one normal adjustment.
        button.addEventListener("click", event => { if (event.detail === 0) this._adjustTemperature(action); });
      } else {
        button.addEventListener("click", () => this._action(action));
      }
    }
    this._bindExtraControls();
  }

  _bindExtraControls() {
    const root = this.shadowRoot;
    root.querySelector(".target-edit").addEventListener("click", () => this._openTemperatureEntry());
    const dialog = root.querySelector(".temperature-dialog");
    dialog.addEventListener("close", () => { if (!dialog.open) this._temperatureDraft = null; });
    dialog.querySelector("form").addEventListener("submit", event => { event.preventDefault(); this._submitTemperatureEntry(); });
    root.querySelector(".temperature-cancel").addEventListener("click", () => this._closeTemperatureEntry());
    root.querySelector(".extras-toggle").addEventListener("click", () => { this._extrasExpanded = !this._extrasExpanded; this._renderExtras(); });
    const brightness = root.querySelector("#brightness");
    brightness.addEventListener("input", () => {
      this._brightnessDraft = brightness.value;
      root.querySelector(".brightness-value").textContent = `${brightness.value}%`;
      this._setBrightnessFill(brightness);
    });
    brightness.addEventListener("change", () => {
      this._brightnessDraft = null;
      this._setSetting("brightness", brightness.value);
    });
    for (const [key, delta] of [["decrease", -1], ["increase", 1]]) {
      root.querySelector(`.brightness-${key}`).addEventListener("click", () => {
        const setting = this._numberSetting("brightness");
        if (setting) this._setSetting("brightness", setting.value + delta * setting.step);
      });
    }
    const shutoff = root.querySelector("#shutoff");
    shutoff.addEventListener("input", () => {
      this._shutoffDraft = shutoff.value;
      shutoff.style.width = `${Math.max(3, shutoff.value.length)}ch`;
    });
    shutoff.addEventListener("change", () => { this._shutoffDraft = null; this._setSetting("shutoff", shutoff.value); });
    shutoff.addEventListener("keydown", event => { if (event.key === "Enter") shutoff.blur(); });
    root.querySelector(".vibration-toggle").addEventListener("click", () => this._setSetting("vibration", this._state("vibration")?.state !== "on"));
    root.querySelector(".stop-all").addEventListener("click", () => this._stopAll());
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
  getCardSize() {
    if (this._config?.collapse_extras && !this._extrasExpanded) return 4;
    const scriptRows = this._config?.show_script_buttons ? Math.ceil(scriptButtons(this._config).filter(item => item.show).length / 2) : 0;
    return 3 + Object.keys(EXTRA_OPTIONS).filter(key => this._config?.[key]).length + Math.max(0, scriptRows - 1);
  }
  getGridOptions() { return { columns: 12, rows: "auto", min_columns: 6 }; }

  setConfig(config) {
    if (config.device != null && typeof config.device !== "string") throw new Error("Select one Volcano device.");
    const nextConfig = cardConfig(config);
    this._resetActions();
    if (this._config?.device !== nextConfig.device || this._config?.collapse_extras !== nextConfig.collapse_extras) {
      this._extrasExpanded = !nextConfig.collapse_extras;
    }
    this._config = nextConfig;
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
    const changedConnection = this._connection !== hass.connection;
    this._connection = hass.connection;
    const changedRegistry = hass.entities && this._hass?.entities !== hass.entities;
    this._hass = hass;
    if (changedConnection) { this._resetActions(); this._entities = {}; this._unsubscribe(); }
    if (changedConnection || changedRegistry) this._resolve();
    if (this.isConnected) this._subscribe();
    this._render();
  }
  get hass() { return this._hass; }

  connectedCallback() {
    window.addEventListener("blur", this._stopRepeat);
    document.addEventListener("visibilitychange", this._visibilityChanged);
    this._subscribe();
    this._resolve();
  }
  disconnectedCallback() {
    window.removeEventListener("blur", this._stopRepeat);
    document.removeEventListener("visibilitychange", this._visibilityChanged);
    this._unsubscribe();
    this._generation++;
    this._resetActions();
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
      this._entities = Object.fromEntries(Object.entries({ ...ROLES, ...OPTIONAL_ROLES }).map(([role, [domain, key]]) => [role,
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

  _startHold(event, action) {
    const button = event.currentTarget;
    if (event.button !== 0 || !event.isPrimary || button.disabled || this._hold) return;
    event.preventDefault();
    button.focus({ preventScroll: true });
    button.setPointerCapture(event.pointerId);
    this._lastTargetSend = null;
    const hold = this._hold = { button, pointerId: event.pointerId, started: performance.now() };
    const repeat = () => {
      if (this._hold !== hold) return;
      this._adjustTemperature(action);
      const elapsed = Math.max(0, performance.now() - hold.started - HOLD_DELAY);
      const acceleration = this._config.temperature_acceleration ?? DEFAULT_OPTIONS.temperature_acceleration;
      const interval = Math.max(60, HOLD_INTERVAL / (1 + elapsed / 2000 * acceleration / 100));
      if (this._hold === hold) hold.timer = setTimeout(repeat, interval);
    };
    this._adjustTemperature(action);
    if (this._hold === hold) hold.timer = setTimeout(repeat, HOLD_DELAY);
  }

  _stopHold() {
    const hold = this._hold;
    this._hold = null;
    if (!hold) return;
    clearTimeout(hold.timer);
    if (hold.button.hasPointerCapture(hold.pointerId)) hold.button.releasePointerCapture(hold.pointerId);
    clearTimeout(this._targetSendTimer);
    this._targetSendTimer = null;
    // Send the final selection as soon as the current write is confirmed.
    if (this._targetRequest) queueMicrotask(() => this._sendTemperature());
  }

  _cancelTemperature() {
    this._stopHold();
    this._targetRequest = null;
    clearTimeout(this._targetSendTimer);
    this._targetSendTimer = null;
    if (this._pending?.role === "target") {
      clearTimeout(this._confirmationTimer);
      this._pending = null;
    }
  }

  _resetActions() {
    this._closeTemperatureEntry();
    for (const request of this._scriptRequests.values()) clearTimeout(request.timer);
    this._scriptRequests.clear();
    this._scriptErrors.clear();
    this._brightnessDraft = null;
    this._shutoffDraft = null;
    this._cancelTemperature();
    clearTimeout(this._confirmationTimer);
    this._pending = null;
    this._commandToken = null;
    this._busy = false;
  }

  _temperatureContext() {
    const state = this._state("target");
    const displayUnit = this._unit();
    const sourceUnit = unit(state?.attributes.unit_of_measurement);
    const { min, max } = state?.attributes || {};
    if (!this.isConnected || !this._connected() || !this._config?.device || this._registryError ||
        reading(state, displayUnit) == null || !Number.isFinite(min) || !Number.isFinite(max) || min > max) return null;
    return { device: this._config.device, entity: this._entities.target, displayUnit, sourceUnit, min, max };
  }

  _validTargetRequest(request) {
    const context = this._temperatureContext();
    return context && Object.entries(context).every(([key, value]) => request[key] === value);
  }

  _temperatureBlocked() {
    return Boolean(this._stopping || (this._busy && !this._targetRequest) || (this._pending && this._pending.role !== "target"));
  }

  _temperatureLimits(context) {
    return {
      min: Math.ceil(Math.max(convert(context.min, context.sourceUnit, context.displayUnit), convert(40, "C", context.displayUnit))),
      max: Math.floor(Math.min(convert(context.max, context.sourceUnit, context.displayUnit), convert(230, "C", context.displayUnit))),
    };
  }

  _setTarget(value) {
    const context = this._temperatureContext();
    if (!context || this._temperatureBlocked()) return false;
    const { min, max } = this._temperatureLimits(context);
    if (!Number.isInteger(value) || value < min || value > max) return false;
    this._targetRequest ||= context;
    this._targetRequest.value = value;
    this._error = "";
    this._render();
    return true;
  }

  _adjustTemperature(action) {
    const context = this._temperatureContext();
    if (!context || this._temperatureBlocked()) return;
    const target = this._targetRequest?.value ?? Math.round(reading(this._state("target"), context.displayUnit));
    const { min, max } = this._temperatureLimits(context);
    const value = Math.max(min, Math.min(max, target + (action === "increase" ? 1 : -1)));
    if (value !== target) this._setTarget(value);
  }

  _openTemperatureEntry() {
    const context = this._temperatureContext();
    if (!context || this._temperatureBlocked()) return;
    this._stopHold();
    this._temperatureDraft = context;
    const root = this.shadowRoot, { min, max } = this._temperatureLimits(context);
    const input = root.querySelector("#temperature-entry");
    Object.assign(input, { min, max, value: this._targetRequest?.value ?? Math.round(reading(this._state("target"), context.displayUnit)) });
    root.querySelector(".temperature-entry-unit").textContent = `°${context.displayUnit}`;
    root.querySelector(".temperature-entry-range").textContent = `${min}–${max} °${context.displayUnit} · whole degrees`;
    root.querySelector(".temperature-entry-error").textContent = "";
    root.querySelector(".temperature-dialog").showModal();
    input.focus(); input.select();
  }

  _closeTemperatureEntry() {
    this._temperatureDraft = null;
    const dialog = this.shadowRoot.querySelector(".temperature-dialog");
    if (dialog.open) dialog.close();
  }

  _submitTemperatureEntry() {
    const draft = this._temperatureDraft;
    if (!draft || !this._validTargetRequest(draft)) { this._closeTemperatureEntry(); return; }
    const input = this.shadowRoot.querySelector("#temperature-entry");
    const value = Number(input.value), { min, max } = this._temperatureLimits(draft);
    if (input.value.trim() === "" || !Number.isInteger(value) || value < min || value > max) {
      this.shadowRoot.querySelector(".temperature-entry-error").textContent = `Enter a whole number from ${min} to ${max} °${draft.displayUnit}.`;
      input.focus(); return;
    }
    if (this._setTarget(value)) this._closeTemperatureEntry();
  }

  _waitForConfirmation(confirmation) {
    clearTimeout(this._confirmationTimer);
    this._pending = confirmation;
    this._confirmationTimer = setTimeout(() => {
      if (this._pending !== confirmation) return;
      this._pending = null;
      this._cancelTemperature();
      this._error = "No status confirmation yet. Check the device before trying again.";
      this._render();
    }, 5000);
  }

  async _sendTemperature() {
    const request = this._targetRequest;
    if (!request || this._stopping || this._busy || this._pending || !this._validTargetRequest(request)) return;
    if (Math.round(reading(this._state("target"), request.displayUnit)) === request.value) {
      this._targetRequest = null;
      this._render();
      return;
    }
    // Preview every step, but coalesce held repeats to avoid flooding HA and BLE.
    // Taps and the final value on release still send immediately.
    const delay = this._hold && this._lastTargetSend != null
      ? HOLD_SEND_INTERVAL - (performance.now() - this._lastTargetSend) : 0;
    if (delay > 0) {
      this._targetSendTimer ??= setTimeout(() => {
        this._targetSendTimer = null;
        this._sendTemperature();
      }, delay);
      return;
    }
    clearTimeout(this._targetSendTimer);
    this._targetSendTimer = null;
    this._lastTargetSend = performance.now();
    const converted = convert(request.value, request.displayUnit, request.sourceUnit);
    const value = Math.max(request.min, Math.min(request.max, Number(converted.toFixed(4))));
    const token = this._commandToken = {};
    this._busy = true;
    this._busyMessage = "Sending…";
    this._render();
    try {
      await this._callService("number", "set_value", { entity_id: request.entity, value });
      if (this._commandToken !== token || this._targetRequest !== request || !this._validTargetRequest(request)) return;
      this._waitForConfirmation({ role: "target", expected: value });
    } catch (error) {
      if (this._commandToken === token && this._targetRequest === request) {
        this._cancelTemperature();
        this._error = error.message || "Command failed. Check the Bluetooth connection.";
      }
    } finally {
      if (this._commandToken === token) {
        this._commandToken = null;
        this._busy = false;
        this._render();
      }
    }
  }

  _render() {
    if (!this._config) return;
    const stop = this._stopping;
    if (stop?.confirming && ["heat", "air"].every(role => this._hass?.states[stop.entities[role]]?.state === "OFF")) {
      clearTimeout(stop.timer);
      this._stopping = null;
    }
    const connected = this._connected();
    const displayUnit = this._unit();
    if (this._temperatureDraft && !this._validTargetRequest(this._temperatureDraft)) {
      this._closeTemperatureEntry();
      this._error = "Temperature settings or connection changed. Tap the target to enter it again.";
    }
    const current = connected ? reading(this._state("current"), displayUnit) : null;
    if (this._targetRequest && !this._validTargetRequest(this._targetRequest)) this._cancelTemperature();
    const target = connected ? this._targetRequest?.value ?? reading(this._state("target"), displayUnit) : null;
    const pendingState = this._pending?.role === "shutoff" ? this._numberSetting("shutoff")?.value
      : this._pending && this._state(this._pending.role)?.state;
    const tolerance = this._pending?.role === "target" ? 0.11
      : Math.min(0.11, (this._numberSetting(this._pending?.role)?.step ?? 0) / 2);
    const confirmed = this._pending?.role === "outputs"
      ? this._state("heat")?.state === "OFF" && this._state("air")?.state === "OFF"
      : ["target", "brightness", "shutoff"].includes(this._pending?.role)
        ? pendingState != null && pendingState !== "" && Number.isFinite(Number(pendingState)) && Math.abs(Number(pendingState) - this._pending.expected) < tolerance
        : this._pending && pendingState === this._pending.expected;
    if (confirmed || !connected) {
      clearTimeout(this._confirmationTimer);
      this._pending = null;
    }
    const root = this.shadowRoot;
    root.querySelector(".panel").classList.toggle("offline", !connected);
    root.querySelector(".panel").classList.toggle("heat-off", connected && this._state("heat")?.state === "OFF");
    renderDigits(root.querySelector("g.current"), current);
    renderDigits(root.querySelector("g.target"), target);
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
      button.disabled = !connected || !this._known(role) || Boolean(this._stopping || this._busy || this._pending || this._targetRequest);
    }
    const attrs = this._state("target")?.attributes;
    const min = convert(attrs?.min, unit(attrs?.unit_of_measurement), displayUnit);
    const max = convert(attrs?.max, unit(attrs?.unit_of_measurement), displayUnit);
    const blocked = this._temperatureBlocked();
    root.querySelector(".target-edit").disabled = !this._temperatureContext() || blocked;
    root.querySelector(".decrease").disabled = !connected || target == null || min == null || target <= min || Boolean(blocked);
    root.querySelector(".increase").disabled = !connected || target == null || max == null || target >= max || Boolean(blocked);
    if (this._hold?.button.disabled) this._stopHold();
    const power = root.querySelector("button.power");
    const connecting = this._connecting();
    const powerLabel = connected ? "Turn off heat and air, then disconnect Bluetooth" : connecting ? "Cancel Bluetooth connection" : "Connect Bluetooth";
    power.setAttribute("aria-label", powerLabel);
    power.title = powerLabel;
    power.disabled = !this._config.device || Boolean(this._stopping || this._busy) || (!this._entities.connection && !this._registryError);
    let status = "";
    if (!this._config.device) status = "Select your Volcano device in the card editor.";
    else if (this._registryError) status = this._registryError;
    else if (this._loading) status = "Finding device controls…";
    else if (Object.keys(ROLES).some(role => !this._entities[role])) status = "Device controls are missing. Select a Volcano Hybrid and enable its temperature, heat, air and Bluetooth entities.";
    else if (this._stopping) status = this._stopping.confirming ? "Waiting for heat and air status…" : "Stopping…";
    else if (this._error) status = this._error;
    else if (this._targetRequest) status = `Setting target to ${this._targetRequest.value} °${this._targetRequest.displayUnit}…`;
    else if (this._busy) status = this._busyMessage;
    else if (this._pending) status = `Waiting for ${this._pending.role === "target" ? "target temperature" : SETTING_LABELS[this._pending.role] || this._pending.role} status…`;
    else if (connecting) status = "Connecting… Tap power to cancel.";
    else if (!connected) status = "Bluetooth disconnected · Tap power to connect";
    else if (!displayUnit) status = "Device temperature unit unavailable. Reconnect the Volcano to read its setting.";
    else if (!this._deviceUnit()) status = "Device unit not reported; using °C.";
    const statusElement = root.querySelector(".status");
    statusElement.textContent = status;
    statusElement.classList.toggle("error", Boolean(this._error || this._registryError));
    this._renderExtras();
    if (this._targetRequest && !this._busy && !this._pending) queueMicrotask(() => this._sendTemperature());
  }

  async _callService(domain, service, data, hass = this._hass) {
    const call = hass.callService(domain, service, data);
    this._serviceCalls.add(call);
    try { return await call; } finally { this._serviceCalls.delete(call); }
  }

  _numberSetting(role) {
    const state = this._state(role);
    if (!this._connected() || !state || ["", "unknown", "unavailable"].includes(state.state)) return null;
    const { unit_of_measurement = "" } = state.attributes;
    let { min, max, step = 1 } = state.attributes;
    let value = Number(state.state);
    if (role === "shutoff" && state.attributes.native_unit_of_measurement === "min") {
      const factor = { "µs": 60000000, ms: 60000, s: 60, min: 1, h: 1 / 60, d: 1 / 1440 }[unit_of_measurement];
      const native = ["native_value", "native_min_value", "native_max_value", "native_step"].map(key => state.attributes[key]);
      if (factor && native.every(Number.isFinite)) [value, min, max, step] = native.map(number => number * factor);
    }
    if (![value, min, max, step].every(Number.isFinite) || min > max || step <= 0) return null;
    return { value, min, max, step, unit: unit_of_measurement };
  }

  _setBrightnessFill(slider) {
    const min = Number(slider.min), max = Number(slider.max);
    const percent = max > min ? Math.max(0, Math.min(100, (Number(slider.value) - min) / (max - min) * 100)) : 0;
    slider.style.setProperty("--brightness-position", `${percent}%`);
  }

  _renderExtras() {
    const root = this.shadowRoot;
    const busy = Boolean(this._stopping || this._busy || this._pending || this._targetRequest);
    const hasExtras = Object.keys(EXTRA_OPTIONS).some(key => this._config[key]);
    const expanded = !this._config.collapse_extras || this._extrasExpanded;
    root.querySelector(".extras").hidden = !hasExtras || !expanded;
    const toggleExtras = root.querySelector(".extras-toggle");
    toggleExtras.hidden = !hasExtras || !this._config.collapse_extras;
    toggleExtras.setAttribute("aria-expanded", String(Boolean(expanded)));
    const runningScripts = (this._config.stop_all_entities || []).filter(id => id.startsWith("script.") && this._scriptRunning(id)).length;
    toggleExtras.querySelector("span").textContent = `Extra controls${runningScripts ? ` · ${runningScripts} script${runningScripts === 1 ? "" : "s"} running` : ""}`;
    for (const [role, option] of [["brightness", "brightness"], ["shutoff", "auto_shutoff"], ["vibration", "vibration"], ["stop", "stop_all"], ["scripts", "script_buttons"], ["presets", "temperature_presets"]]) {
      root.querySelector(`.${role}-row`).hidden = !this._config[`show_${option}`];
    }
    const brightness = this._numberSetting("brightness");
    const slider = root.querySelector("#brightness");
    if (!brightness || busy) this._brightnessDraft = null;
    if (brightness) {
      Object.assign(slider, { min: brightness.min, max: brightness.max, step: brightness.step,
        value: this._brightnessDraft ?? brightness.value });
    }
    this._setBrightnessFill(slider);
    slider.disabled = !brightness || busy;
    root.querySelector(".brightness-value").textContent = brightness ? `${this._brightnessDraft ?? brightness.value}%` : "Unavailable";
    root.querySelector(".brightness-decrease").disabled = !brightness || busy || brightness.value <= brightness.min;
    root.querySelector(".brightness-increase").disabled = !brightness || busy || brightness.value >= brightness.max;
    const shutoff = this._numberSetting("shutoff");
    const input = root.querySelector("#shutoff");
    if (!shutoff || busy) this._shutoffDraft = null;
    if (shutoff) Object.assign(input, { min: shutoff.min, max: shutoff.max, step: shutoff.step });
    input.value = this._shutoffDraft ?? shutoff?.value ?? "";
    input.style.width = `${Math.max(3, input.value.length)}ch`;
    input.disabled = !shutoff || busy;
    root.querySelector(".shutoff-unit").textContent = shutoff?.unit || "";
    input.title = shutoff ? `${shutoff.min}–${shutoff.max} ${shutoff.unit}` : "Unavailable";
    root.querySelector(".shutoff-note").hidden = Boolean(shutoff);
    root.querySelector(".shutoff-note").textContent = shutoff ? "" : "Unavailable";
    const vibration = this._connected() && ["on", "off"].includes(this._state("vibration")?.state);
    const toggle = root.querySelector(".vibration-toggle");
    const on = vibration && this._state("vibration").state === "on";
    toggle.disabled = !vibration || busy;
    toggle.setAttribute("aria-checked", String(Boolean(on)));
    root.querySelector(".vibration-state").textContent = vibration ? on ? "On" : "Off" : "—";
    root.querySelector(".vibration-note").hidden = Boolean(vibration);
    root.querySelector(".vibration-note").textContent = vibration ? "" : "Unavailable";
    const selected = this._config.stop_all_entities || [];
    root.querySelector(".stop-all").disabled = !this._config.device || Boolean(this._stopping) || (!this._connected() && !selected.length);
    const scripts = selected.filter(id => id.startsWith("script.")).length;
    const automations = selected.length - scripts;
    const targets = [];
    if (scripts) targets.push(`stops ${scripts} script${scripts === 1 ? "" : "s"}`);
    if (automations) targets.push(`stops ${automations} automation${automations === 1 ? "" : "s"}`);
    root.querySelector(".stop-note").textContent = targets.length ? `Also ${targets.join(" and ")}` : "";
    root.querySelector(".stop-note").hidden = !targets.length;
    this._renderScripts();
    this._renderPresets();
  }

  _renderScripts() {
    const grid = this.shadowRoot.querySelector(".script-grid");
    const selected = this._config.show_script_buttons ? scriptButtons(this._config).filter(item => item.show) : [];
    const ids = new Set(selected.map(item => item.entity));
    for (const [id, button] of this._scriptNodes) {
      if (!ids.has(id)) { button.remove(); this._scriptNodes.delete(id); }
    }
    this.shadowRoot.querySelector(".scripts-empty").hidden = Boolean(selected.length);
    selected.forEach(({ entity }, index) => {
      let button = this._scriptNodes.get(entity);
      if (!button) {
        button = document.createElement("button");
        button.type = "button"; button.className = "script-run"; button.dataset.entity = entity;
        button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4.5v15l12-7.5Z"/></svg><span class="script-copy"><span class="script-name"></span><span class="script-state" aria-live="polite"></span></span>';
        button.addEventListener("click", () => {
          if (this._scriptRunning(entity)) this._stopScript(entity);
          else this._runScript(entity);
        });
        this._scriptNodes.set(entity, button);
      }
      if (grid.children[index] !== button) grid.insertBefore(button, grid.children[index] || null);
      const state = this._hass?.states[entity];
      const name = state?.attributes.friendly_name || entity;
      const available = state && ["on", "off"].includes(state.state);
      const running = this._scriptRunning(entity);
      const request = this._scriptRequests.get(entity);
      if (request?.acknowledged && this._scriptActionConfirmed(entity, request)) {
        clearTimeout(request.timer); this._scriptRequests.delete(entity);
      }
      const pending = this._scriptRequests.get(entity);
      const failure = this._scriptErrors.get(entity);
      if (failure && this._scriptActionConfirmed(entity, failure)) this._scriptErrors.delete(entity);
      const error = this._scriptErrors.get(entity)?.message;
      const label = !available ? "Unavailable" : pending ? pending.stop ? "Stopping…" : "Starting…"
        : error || (running ? "Running · Stop" : "Run script");
      button.querySelector(".script-name").textContent = name;
      button.querySelector(".script-state").textContent = label;
      button.querySelector("svg path").setAttribute("d", running ? "M6 6H18V18H6Z" : "M8 4.5v15l12-7.5Z");
      button.setAttribute("aria-label", `${running ? "Stop" : "Run"}: ${name}`);
      button.title = `${name} · ${label}`;
      button.classList.toggle("running", running);
      button.classList.toggle("failed", Boolean(error && !pending));
      button.disabled = !available || Boolean(pending || this._stopping) ||
        (!running && Boolean(this._busy || this._pending || this._targetRequest)) || !this._hass;
    });
  }

  _scriptRunning(entity) {
    const state = this._hass?.states[entity];
    return Boolean(state && ["on", "off"].includes(state.state) && (state.state === "on" || Number(state.attributes.current) > 0));
  }

  _scriptActionConfirmed(entity, action) {
    const state = this._hass?.states[entity];
    if (!state || !["on", "off"].includes(state.state)) return false;
    const running = this._scriptRunning(entity);
    return action.stop ? !running : running || Boolean(
      state.attributes.last_triggered && state.attributes.last_triggered !== action.lastTriggered
    );
  }

  _runScript(entity) { return this._scriptAction(entity, false); }
  _stopScript(entity) { return this._scriptAction(entity, true); }

  async _scriptAction(entity, stop) {
    if (!this.isConnected || !this._config?.show_script_buttons || this._stopping ||
        (!stop && (this._busy || this._pending || this._targetRequest)) || this._scriptRequests.has(entity) ||
        !scriptButtons(this._config).some(item => item.entity === entity && item.show)) return;
    const state = this._hass?.states[entity];
    if (!state || !["on", "off"].includes(state.state) || this._scriptRunning(entity) !== stop) return;
    const request = { stop, lastTriggered: state.attributes.last_triggered };
    this._scriptRequests.set(entity, request); this._scriptErrors.delete(entity);
    this._renderScripts();
    try {
      // turn_on starts without waiting for the script to finish. turn_off
      // cancels its current and queued runs; the script remains runnable.
      await this._callService("script", stop ? "turn_off" : "turn_on", { entity_id: entity });
      if (this._scriptRequests.get(entity) !== request) return;
      request.acknowledged = true;
      request.timer = setTimeout(() => {
        if (this._scriptRequests.get(entity) !== request) return;
        this._scriptRequests.delete(entity);
        this._scriptErrors.set(entity, { stop, lastTriggered: request.lastTriggered, message: `${stop ? "Stop" : "Start"} sent; status not confirmed.` });
        this._renderScripts();
      }, 5000);
    } catch (error) {
      if (this._scriptRequests.get(entity) === request) {
        this._scriptRequests.delete(entity);
        this._scriptErrors.set(entity, { stop, lastTriggered: request.lastTriggered, message: error.message || `Could not ${stop ? "stop" : "start"} script.` });
      }
    } finally { this._renderScripts(); }
  }

  _renderPresets() {
    const grid = this.shadowRoot.querySelector(".preset-grid");
    const selected = this._config.show_temperature_presets ? temperaturePresets(this._config).filter(item => item.show) : [];
    const keys = new Set(selected.map(item => item.temperature));
    for (const [key, button] of this._presetNodes) {
      if (!keys.has(key)) { button.remove(); this._presetNodes.delete(key); }
    }
    this.shadowRoot.querySelector(".presets-empty").hidden = Boolean(selected.length);
    const displayUnit = this._unit(), context = this._temperatureContext();
    const limits = context && this._temperatureLimits(context);
    const target = this._targetRequest?.value ?? reading(this._state("target"), displayUnit);
    selected.forEach((preset, index) => {
      let button = this._presetNodes.get(preset.temperature);
      if (!button) {
        button = document.createElement("button"); button.type = "button";
        button.className = "temperature-preset"; button.dataset.celsius = String(preset.temperature);
        button.innerHTML = '<span class="preset-name"></span><span class="preset-value"></span>';
        button.addEventListener("click", () => {
          if (!this._config.show_temperature_presets || !temperaturePresets(this._config).some(item => item.temperature === preset.temperature && item.show)) return;
          const unit = this._unit();
          if (unit) this._setTarget(Math.round(convert(preset.temperature, "C", unit)));
        });
        this._presetNodes.set(preset.temperature, button);
      }
      if (grid.children[index] !== button) grid.insertBefore(button, grid.children[index] || null);
      const value = displayUnit ? Math.round(convert(preset.temperature, "C", displayUnit)) : null;
      const label = value == null ? "—" : `${value} °${displayUnit}`;
      button.querySelector(".preset-name").textContent = preset.name || "";
      button.querySelector(".preset-name").hidden = !preset.name;
      button.querySelector(".preset-value").textContent = label;
      button.setAttribute("aria-label", `Set target to ${label}${preset.name ? ` (${preset.name})` : ""}`);
      button.setAttribute("aria-pressed", String(this._connected() && value != null && target != null && Math.round(target) === value));
      button.disabled = !limits || value == null || value < limits.min || value > limits.max || this._temperatureBlocked();
    });
  }

  async _setSetting(role, rawValue) {
    if (this._stopping || this._busy || this._pending || this._targetRequest || !this._connected()) { this._render(); return; }
    const option = role === "shutoff" ? "auto_shutoff" : role;
    if (!this._config[`show_${option}`]) return;
    const entity = this._entities[role];
    let domain, service, data, expected;
    if (role === "vibration") {
      if (!["on", "off"].includes(this._state(role)?.state)) return;
      domain = "switch"; service = rawValue ? "turn_on" : "turn_off";
      data = { entity_id: entity }; expected = rawValue ? "on" : "off";
    } else {
      const setting = this._numberSetting(role);
      if (!setting) return;
      const value = Number(rawValue);
      const steps = (value - setting.min) / setting.step;
      if (String(rawValue).trim() === "" || !Number.isFinite(value) || value < setting.min || value > setting.max || Math.abs(steps - Math.round(steps)) > 0.0001) {
        this._error = `Choose ${SETTING_LABELS[role]} from ${setting.min} to ${setting.max} ${setting.unit}, in steps of ${setting.step}.`;
        this._render(); return;
      }
      if (value === setting.value) { this._render(); return; }
      domain = "number"; service = "set_value"; data = { entity_id: entity, value }; expected = value;
    }
    const token = this._commandToken = {};
    this._busy = true; this._busyMessage = `Setting ${SETTING_LABELS[role]}…`; this._error = "";
    this._render();
    try {
      await this._callService(domain, service, data);
      if (this._commandToken === token && this.isConnected && this._entities[role] === entity) this._waitForConfirmation({ role, expected });
    } catch (error) {
      if (this._commandToken === token) this._error = error.message || "Setting failed. Check the Bluetooth connection.";
    } finally {
      if (this._commandToken === token) { this._commandToken = null; this._busy = false; this._render(); }
    }
  }

  async _stopAll() {
    if (!this._config?.show_stop_all || !this._config.device || this._stopping) return;
    const hass = this._hass, device = this._config.device;
    const selected = [...(this._config.stop_all_entities || [])];
    if (!this._connected() && !selected.length) return;
    const inFlight = [...this._serviceCalls];
    this._resetActions();
    // Shutdown survives configuration, connection and DOM resets.
    const token = this._stopping = { device, entities: { ...this._entities } };
    this._busy = true; this._busyMessage = "Stopping…"; this._error = "";
    this._render();
    const errors = [];
    const attempt = async (label, domain, service, data) => {
      try { await this._callService(domain, service, data, hass); }
      catch (error) { errors.push(`${label}: ${error.message || "stop failed"}`); }
    };
    // Finish any command already sent before switching the outputs off. Queued
    // targets were discarded above, and old responses cannot start new writes.
    await Promise.allSettled(inFlight);
    // Cancel current automation actions before scripts they may have started.
    // Their triggers stay attached; future triggers can start a new run.
    for (const domain of ["automation", "script"]) {
      await Promise.all(selected.filter(entity => entity.startsWith(`${domain}.`)).map(async entity => {
        if (!hass.states[entity] || ["unknown", "unavailable"].includes(hass.states[entity].state)) {
          errors.push(`${entity}: unavailable`); return;
        }
        await attempt(entity, domain === "automation" ? DOMAIN : "script",
          domain === "automation" ? "stop_automation_runs" : "turn_off", { entity_id: entity });
      }));
    }
    // Try both outputs even if a script, automation or the first OFF write fails.
    await attempt("Heat", DOMAIN, "heat_off", { device_id: device });
    await attempt("Air", DOMAIN, "pump_off", { device_id: device });
    if (this._stopping !== token) return;
    this._busy = false;
    if (errors.length) {
      this._stopping = null;
      if (this._config?.device === device) this._error = `Could not stop everything. ${errors.join("; ")}`;
    } else {
      // Keep the guard and deadline independent of ordinary card action resets.
      // Confirm the original device even if the editor selects another one.
      token.confirming = true;
      token.timer = setTimeout(() => {
        if (this._stopping !== token) return;
        this._stopping = null;
        if (this._config?.device === device) this._error = "No status confirmation yet. Check the device before trying again.";
        this._render();
      }, 5000);
    }
    this._render();
  }

  async _action(action) {
    if (action === "decrease" || action === "increase") { this._adjustTemperature(action); return; }
    if (this._stopping || this._busy || !this._config?.device) return;
    if (this._registryError) { await this._resolve(); return; }
    const device = this._config.device;
    const connected = this._connected();
    let service, data, confirmation;
    if (action === "power") {
      this._cancelTemperature();
      service = connected || this._connecting() ? "disconnect" : "connect";
      data = { device_id: device, ...(service === "connect" ? { wait_until_connected: false } : {}) };
    } else if (["heat", "air"].includes(action)) {
      if (!connected || !this._known(action) || this._pending || this._targetRequest) return;
      const on = this._state(action).state === "ON";
      service = `${action === "air" ? "pump" : "heat"}_${on ? "off" : "on"}`;
      data = { device_id: device };
      confirmation = { role: action, expected: on ? "OFF" : "ON" };
    } else return;
    const token = this._commandToken = {};
    this._busy = true;
    this._busyMessage = action === "power" && connected ? "Turning off heat and air…" : "Sending…";
    this._error = "";
    this._render();
    try {
      await this._callService(DOMAIN, service, data);
      if (this._commandToken !== token || !this.isConnected) return;
      if (confirmation) this._waitForConfirmation(confirmation);
    } catch (error) {
      if (this._commandToken === token) this._error = error.message || "Command failed. Check the Bluetooth connection.";
    } finally {
      if (this._commandToken === token) {
        this._commandToken = null;
        this._busy = false;
        this._render();
      }
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
        { name: "temperature_acceleration", selector: { number: { min: 0, max: 300, step: 10, unit_of_measurement: "%", mode: "slider" } } },
        ...Object.keys(EXTRA_OPTIONS).map(name => ({ name, selector: { boolean: {} } })),
        { name: "collapse_extras", selector: { boolean: {} } },
        { name: "stop_all_entities", selector: { entity: { multiple: true, filter: { domain: ["script", "automation"] } } } },
      ];
      this._form.computeLabel = schema => ({ device: "Volcano device", temperature_acceleration: "Temperature button acceleration",
        ...EXTRA_OPTIONS, collapse_extras: "Collapse extra controls", stop_all_entities: "Related scripts and automations" })[schema.name] || schema.name;
      this._form.computeHelper = schema => ({
        temperature_acceleration: "100% is the default. Higher values speed up a hold sooner; 0% keeps a steady repeat rate.",
        collapse_extras: "Start with the extra controls folded away. Tap Extra controls to open them; the Hybrid panel stays visible.",
        show_temperature_presets: "170–230 °C in 5 °C steps. Choose buttons and optional names below. Fahrenheit displays the same temperatures in 9 °F steps.",
        show_script_buttons: "Show buttons for scripts from the list below. Choose which ones and their order beneath the list.",
        stop_all_entities: "Used by Stop all and the script buttons. Optional, with no limit. Stop all cancels current script and automation runs, then turns off heat and air. Automations stay enabled and can run again on their next trigger. Bluetooth stays connected.",
      })[schema.name];
      this._form.addEventListener("value-changed", event => {
        event.stopPropagation();
        const values = event.detail.value;
        const updates = Object.fromEntries(this._form.schema.filter(field => Object.hasOwn(values, field.name)).map(field =>
          [field.name, values[field.name] ?? DEFAULT_OPTIONS[field.name]]));
        this._config = cardConfig({ ...this._config, ...updates });
        this._render();
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
        .script-buttons-editor, .preset-editor { margin:16px 0; padding:16px; border:1px solid var(--divider-color,#ddd); border-radius:12px; }
        [hidden] { display:none !important; }
        h3 { margin:0; font-size:16px; font-weight:500; }
        .script-buttons-editor p, .preset-editor p { margin:8px 0 14px; }
        .script-buttons-editor input { width:18px; height:18px; accent-color:var(--primary-color,#03a9f4); }
        .script-select-all { justify-content:flex-start; padding:8px 0 14px; }
        .script-editor-row { display:flex; align-items:center; gap:8px; padding:10px 0; border-top:1px solid var(--divider-color,#ddd); }
        .script-editor-row label { justify-content:flex-start; min-width:0; flex:1; cursor:pointer; }
        .script-editor-copy { display:flex; flex-direction:column; gap:3px; min-width:0; overflow-wrap:anywhere; }
        .script-editor-id { font-size:11px; color:var(--secondary-text-color); }
        .script-editor-row button { flex-shrink:0; margin:0; padding:0; width:36px; height:36px; font-size:20px; }
        .script-editor-row button:disabled { opacity:.3; cursor:default; }
        .preset-editor-row { display:flex; align-items:center; gap:10px; padding:8px 0; border-top:1px solid var(--divider-color,#ddd); }
        .preset-editor input[type=checkbox] { width:18px; height:18px; accent-color:var(--primary-color,#03a9f4); }
        .preset-editor-row label { justify-content:flex-start; gap:8px; white-space:nowrap; cursor:pointer; }
        .preset-editor-row input[type=text] { box-sizing:border-box; flex:1; width:0; min-width:0; height:36px; padding:6px 8px;
          color:var(--primary-text-color); font:inherit; cursor:text; }
        .preset-select-all { justify-content:flex-start; padding:8px 0 14px; }
        button:focus-visible, input:focus-visible { outline:2px solid var(--primary-color,#03a9f4); outline-offset:2px; }
        @media(max-width:450px) { .colours { grid-template-columns:1fr; } }`;
      this.shadowRoot.append(style);
      const note = document.createElement("p");
      note.textContent = "Temperatures follow the Volcano’s °C / °F setting. Change it under Configuration on the device page.";
      this.shadowRoot.append(note);
      this._scriptEditor = document.createElement("section");
      this._scriptEditor.className = "script-buttons-editor";
      this._scriptEditor.innerHTML = '<h3>Script buttons</h3><p>Choose which buttons appear and use the arrows to change their order. Hidden scripts still belong to Stop all.</p><label class="script-select-all"><input type="checkbox">Select all</label><div class="script-editor-list"></div><p class="script-editor-empty">Add scripts to Related scripts and automations above.</p>';
      this._scriptEditor.querySelector(".script-select-all input").addEventListener("change", event => {
        this._updateScriptButtons(items => items.map(item => ({ ...item, show: event.target.checked })));
      });
      this._scriptEditorNodes = new Map();
      this.shadowRoot.append(this._scriptEditor);
      this._presetEditor = document.createElement("section");
      this._presetEditor.className = "preset-editor";
      this._presetEditor.innerHTML = '<h3>Temperature presets</h3><p>Choose temperatures and optional names. Values here are in °C; the card converts them to °F when the Volcano uses Fahrenheit.</p><label class="preset-select-all"><input type="checkbox">Select all</label><div class="preset-editor-list"></div>';
      this._presetEditor.querySelector(".preset-select-all input").addEventListener("change", event => {
        this._updatePresets(items => items.map(item => ({ ...item, show: event.target.checked })));
      });
      for (const temperature of PRESET_TEMPERATURES) {
        const row = document.createElement("div"); row.className = "preset-editor-row"; row.dataset.celsius = String(temperature);
        row.innerHTML = '<label><input type="checkbox"><span></span></label><input type="text" maxlength="60" placeholder="Name (optional)">';
        row.querySelector("label span").textContent = `${temperature} °C`;
        row.querySelector('input[type="text"]').setAttribute("aria-label", `Name for ${temperature} °C preset`);
        row.querySelector('input[type="checkbox"]').addEventListener("change", event => {
          this._updatePresets(items => items.map(item => item.temperature === temperature ? { ...item, show: event.target.checked } : item));
        });
        row.querySelector('input[type="text"]').addEventListener("input", event => {
          this._updatePresets(items => items.map(item => item.temperature === temperature ? { ...item, name: event.target.value } : item));
        });
        this._presetEditor.querySelector(".preset-editor-list").append(row);
      }
      this.shadowRoot.append(this._presetEditor);
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
      reset.type = "button"; reset.className = "reset-colours";
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
    this._form.data = { ...DEFAULT_OPTIONS, ...this._config };
    this._renderScriptEditor();
    this._renderPresetEditor();
    for (const [key, [, , fallback]] of Object.entries(COLOURS)) {
      this.shadowRoot.querySelector(`input[name="${key}"]`).value = this._config.colors?.[key] || fallback;
    }
  }
  _updatePresets(update) {
    this._config = cardConfig({ ...this._config, temperature_presets: update(temperaturePresets(this._config)) });
    this._render(); this._changed();
  }

  _renderPresetEditor() {
    this._presetEditor.hidden = !this._config.show_temperature_presets;
    const items = temperaturePresets(this._config);
    const all = this._presetEditor.querySelector(".preset-select-all input");
    all.checked = items.every(item => item.show);
    all.indeterminate = items.some(item => item.show) && !all.checked;
    const list = this._presetEditor.querySelector(".preset-editor-list");
    items.forEach((item, index) => {
      const row = list.querySelector(`[data-celsius="${item.temperature}"]`);
      if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
      row.querySelector('input[type="checkbox"]').checked = item.show;
      const input = row.querySelector('input[type="text"]');
      if (input.value !== (item.name || "")) input.value = item.name || "";
    });
  }

  _updateScriptButtons(update) {
    this._config = cardConfig({ ...this._config, script_buttons: update(scriptButtons(this._config)) });
    this._render(); this._changed();
  }

  _renderScriptEditor() {
    this._scriptEditor.hidden = !this._config.show_script_buttons;
    const items = scriptButtons(this._config);
    const all = this._scriptEditor.querySelector(".script-select-all input");
    all.checked = items.length > 0 && items.every(item => item.show);
    all.indeterminate = items.some(item => item.show) && !all.checked;
    all.disabled = !items.length;
    this._scriptEditor.querySelector(".script-editor-empty").hidden = Boolean(items.length);
    const list = this._scriptEditor.querySelector(".script-editor-list");
    const ids = new Set(items.map(item => item.entity));
    for (const [entity, row] of this._scriptEditorNodes) {
      if (!ids.has(entity)) { row.remove(); this._scriptEditorNodes.delete(entity); }
    }
    items.forEach(({ entity, show }, index) => {
      let row = this._scriptEditorNodes.get(entity);
      if (!row) {
        row = document.createElement("div"); row.className = "script-editor-row"; row.dataset.entity = entity;
        row.innerHTML = '<label><input type="checkbox"><span class="script-editor-copy"><span class="script-editor-name"></span><span class="script-editor-id"></span></span></label><button type="button" class="move-up">↑</button><button type="button" class="move-down">↓</button>';
        row.querySelector("input").addEventListener("change", event => {
          this._updateScriptButtons(items => items.map(item => item.entity === entity ? { ...item, show: event.target.checked } : item));
        });
        for (const [direction, delta] of [["up", -1], ["down", 1]]) {
          row.querySelector(`.move-${direction}`).addEventListener("click", event => {
            this._updateScriptButtons(items => {
              const from = items.findIndex(item => item.entity === entity), to = from + delta;
              if (from >= 0 && to >= 0 && to < items.length) [items[from], items[to]] = [items[to], items[from]];
              return items;
            });
            if (!event.currentTarget.disabled) event.currentTarget.focus();
            else row.querySelector("input").focus();
          });
        }
        this._scriptEditorNodes.set(entity, row);
      }
      if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
      const name = this._hass.states[entity]?.attributes.friendly_name || entity;
      row.querySelector(".script-editor-name").textContent = name;
      row.querySelector(".script-editor-id").textContent = entity;
      row.querySelector("input").checked = show;
      row.querySelector("input").setAttribute("aria-label", `Show ${name}`);
      for (const direction of ["up", "down"]) {
        const button = row.querySelector(`.move-${direction}`);
        button.disabled = direction === "up" ? index === 0 : index === items.length - 1;
        button.setAttribute("aria-label", `Move ${name} ${direction}`);
        button.title = `Move ${direction}`;
      }
    });
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
