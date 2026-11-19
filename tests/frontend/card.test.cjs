const { test, before, after, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { createPreviewServer } = require("../../scripts/card_preview.cjs");
let browser, server, url, page;
const button = name => page.locator(`volcano-hybrid-card button.${name}`);
const stateText = () => page.locator("volcano-hybrid-card .temperatures").textContent();
const lit = role => page.locator(`volcano-hybrid-card .${role}-icon`).evaluate(el => getComputedStyle(el).opacity === "1");
before(async () => {
  server = createPreviewServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  url = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true, ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}) });
});
after(async () => { await browser?.close(); await new Promise(resolve => server.close(resolve)); });
beforeEach(async () => {
  page = await browser.newPage({ viewport: { width: 820, height: 850 } });
  await page.goto(url);
  await page.waitForFunction(() => window.demo && !demo.card.shadowRoot.querySelector("button.heat").disabled);
});
afterEach(async () => { await page.close(); });

test("renamed entities resolve from only a device; current and target have the correct colours", async () => {
  assert.match(await stateText(), /Current temperature: 180. Target temperature: 180 degrees Celsius/);
  assert.deepEqual(await page.locator("volcano-hybrid-card g.current").evaluate(el => getComputedStyle(el).fill), "rgb(255, 133, 12)");
  assert.equal(await page.locator("volcano-hybrid-card g.target").evaluate(el => getComputedStyle(el).fill), "rgb(244, 245, 240)");
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
});
test("both temperature buttons use the resolved number and honour the bounds", async () => {
  await button("increase").click();
  await button("decrease").click();
  assert.deepEqual(await page.evaluate(() => demo.calls), [
    { domain: "number", service: "set_value", data: { entity_id: "number.renamed_target", value: 181 } },
    { domain: "number", service: "set_value", data: { entity_id: "number.renamed_target", value: 180 } },
  ]);
  await page.evaluate(() => demo.update("target", "230"));
  assert.equal(await button("increase").isDisabled(), true);
  await page.evaluate(() => demo.update("target", "40"));
  assert.equal(await button("decrease").isDisabled(), true);
});
test("device Fahrenheit moves one displayed degree on every press", async () => {
  await page.evaluate(() => demo.setDeviceUnit("F"));
  assert.match(await stateText(), /356 degrees Fahrenheit/);
  await button("increase").click();
  const call = await page.evaluate(() => demo.calls[0]);
  assert.equal(call.data.value, 180.5556);
  assert.match(await stateText(), /Target temperature: 357 degrees Fahrenheit/);
  assert.equal(await button("increase").isDisabled(), false);
  await button("decrease").click();
  await button("decrease").click();
  await button("increase").click();
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [180.5556, 180, 179.4444, 180]);
  assert.match(await stateText(), /Target temperature: 356 degrees Fahrenheit/);
});
test("mixed entity units convert once and HA defaults never override the physical device", async () => {
  await page.evaluate(() => {
    demo.hass.config.unit_system.temperature = "°F";
    demo.update("current", "356", { unit_of_measurement: "°F" });
  });
  assert.match(await stateText(), /Current temperature: 180. Target temperature: 180 degrees Celsius/);
  await page.evaluate(() => demo.setDeviceUnit("F"));
  assert.match(await stateText(), /Current temperature: 356. Target temperature: 356 degrees Fahrenheit/);
});
test("Fahrenheit number entities receive Fahrenheit commands", async () => {
  await page.evaluate(() => {
    demo.card.setConfig({ device: "volcano-one", temperature_unit: "F" });
    demo.setDeviceUnit("F");
    demo.update("target", "356", { unit_of_measurement: "°F", min: 104, max: 446, step: 1.8 });
  });
  await button("increase").click();
  assert.equal(await page.evaluate(() => demo.calls[0].data.value), 357);
  assert.match(await stateText(), /Target temperature: 357 degrees Fahrenheit/);
  assert.equal(await button("decrease").isDisabled(), false);
  await button("decrease").click();
  assert.equal(await page.evaluate(() => demo.calls[1].data.value), 356);
});
test("heat and air toggle on and off for exactly the selected device", async () => {
  for (const role of ["heat", "air"]) {
    assert.equal(await lit(role), false);
    await button(role).click();
    assert.equal(await button(role).getAttribute("aria-pressed"), "true");
    assert.equal(await lit(role), true);
    await button(role).click();
    assert.equal(await button(role).getAttribute("aria-pressed"), "false");
    assert.equal(await lit(role), false);
  }
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => [call.service, call.data.device_id])), [
    ["heat_on", "volcano-one"], ["heat_off", "volcano-one"], ["pump_on", "volcano-one"], ["pump_off", "volcano-one"],
  ]);
});
test("Bluetooth indicates an established HA connection; stale heat and air icons disappear offline", async () => {
  await page.evaluate(() => { demo.update("heat", "ON"); demo.update("air", "ON"); });
  assert.equal(await lit("bluetooth"), true);
  for (const state of ["CONNECTING", "DISCONNECTED", "unavailable", "unknown"]) {
    await page.evaluate(state => demo.update("connection", state, { connection_requested: true }), state);
    for (const role of ["bluetooth", "heat", "air"]) {
      assert.equal(await page.locator(`volcano-hybrid-card .${role}-icon`).evaluate(el => getComputedStyle(el).opacity), "0");
    }
  }
  await page.evaluate(() => demo.update("connection", "CONNECTED"));
  for (const role of ["bluetooth", "heat", "air"]) assert.equal(await lit(role), true);
  await page.evaluate(() => { demo.update("heat", "unknown"); demo.update("air", "unavailable"); });
  for (const role of ["heat", "air"]) assert.equal(await lit(role), false);
});
test("screen symbols fit in one column and the power button follows its symbol at desktop and phone widths", async () => {
  for (const width of [820, 360]) {
    await page.setViewportSize({ width, height: 850 });
    const boxes = await page.evaluate(() => {
      const root = demo.card.shadowRoot;
      const box = selector => root.querySelector(selector).getBoundingClientRect().toJSON();
      return {
        icons: ["bluetooth", "power", "air", "heat"].map(role => box(`.${role}-icon`)),
        screen: box(".face > rect"), power: box("button.power"), current: box("g.current"),
      };
    });
    for (let i = 0; i < boxes.icons.length; i++) {
      const icon = boxes.icons[i];
      assert.ok(icon.top > boxes.screen.top && icon.bottom < boxes.screen.bottom);
      assert.ok(icon.left > boxes.screen.left && icon.right < boxes.current.left);
      if (i) assert.ok(icon.top > boxes.icons[i - 1].bottom);
    }
    const power = boxes.icons[1];
    assert.ok(boxes.power.left < power.left && boxes.power.right > power.right);
    assert.ok(boxes.power.top < power.top && boxes.power.bottom > power.bottom);
    // Click the visible symbol, rather than relying on the overlay's own centre.
    await page.mouse.click(power.x + power.width / 2, power.y + power.height / 2);
    assert.equal(await page.evaluate(() => demo.calls.at(-1).service), "disconnect");
    await page.evaluate(() => demo.update("connection", "CONNECTED"));
  }
});
test("status text is vertically centred for single and wrapped messages", async () => {
  for (const width of [820, 360]) {
    await page.setViewportSize({ width, height: 850 });
    await page.evaluate(() => demo.update("connection", "DISCONNECTED"));
    for (const longMessage of [false, true]) {
      if (longMessage) {
        await page.evaluate(() => { demo.registry[0].disabled_by = "user"; demo.registryChanged(); });
        await page.waitForFunction(() => demo.card.shadowRoot.querySelector(".status").textContent.includes("missing"));
      }
      const spacing = await page.locator("volcano-hybrid-card .status").evaluate(el => {
        const range = document.createRange();
        range.selectNodeContents(el);
        const text = range.getBoundingClientRect();
        const box = el.getBoundingClientRect();
        return { top: text.top - box.top, bottom: box.bottom - text.bottom, lines: range.getClientRects().length, overflow: el.scrollWidth > el.clientWidth };
      });
      assert.ok(Math.abs(spacing.top - spacing.bottom) <= 1, JSON.stringify(spacing));
      assert.equal(spacing.overflow, false);
      if (width === 360 && longMessage) assert.ok(spacing.lines > 1);
    }
    await page.evaluate(() => { demo.registry[0].disabled_by = null; demo.registryChanged(); });
    await page.waitForFunction(() => demo.card.shadowRoot.querySelector(".status").textContent.includes("disconnected"));
  }
});
test("offline controls cannot send commands; power reconnects without waiting for heat", async () => {
  await page.evaluate(() => demo.update("connection", "DISCONNECTED"));
  for (const key of ["heat", "air", "increase", "decrease"]) assert.equal(await button(key).isDisabled(), true);
  assert.match(await stateText(), /Current temperature: unavailable. Target temperature: unavailable/);
  await button("power").click();
  assert.deepEqual(await page.evaluate(() => demo.calls[0]), {
    domain: "volcano_integration", service: "connect", data: { device_id: "volcano-one", wait_until_connected: false },
  });
  await button("power").click();
  assert.equal(await page.evaluate(() => demo.calls[1].service), "disconnect");
});
test("unknown readings and unknown actuator states never become zero or an ON command", async () => {
  await page.evaluate(() => { demo.update("current", "unknown"); demo.update("target", "unavailable"); demo.update("heat", "unknown"); });
  assert.match(await stateText(), /Current temperature: unavailable. Target temperature: unavailable/);
  assert.equal(await button("heat").isDisabled(), true);
  assert.equal(await button("increase").isDisabled(), true);
});

test("power cancels retries while the disconnected device is in backoff", async () => {
  await page.evaluate(() => demo.update("connection", "DISCONNECTED", { connection_requested: true }));
  assert.match(await button("power").getAttribute("aria-label"), /Cancel/);
  await button("power").click();
  assert.equal(await page.evaluate(() => demo.calls[0].service), "disconnect");
  assert.equal(await button("power").getAttribute("aria-label"), "Connect Bluetooth");
});
test("power uses the shared shutdown action and keeps failures visible", async () => {
  await page.evaluate(() => {
    demo.update("heat", "ON"); demo.update("air", "ON");
    demo.failure = "Volcano did not confirm that heat and air are off. Bluetooth is still connected.";
  });
  assert.match(await button("power").getAttribute("aria-label"), /Turn off heat and air/);
  await button("power").click();
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /did not confirm/);
  assert.equal(await lit("bluetooth"), true);
  assert.equal(await lit("heat"), true);
  assert.equal(await lit("air"), true);
  await page.evaluate(() => { demo.failure = null; demo.pause = true; });
  await button("power").click();
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "Turning off heat and air…");
  await page.evaluate(() => demo.resume());
  await page.waitForFunction(() => !demo.card.shadowRoot.querySelector(".bluetooth-icon").classList.contains("active"));
  assert.deepEqual(await page.evaluate(() => demo.calls), [
    { domain: "volcano_integration", service: "disconnect", data: { device_id: "volcano-one" } },
    { domain: "volcano_integration", service: "disconnect", data: { device_id: "volcano-one" } },
  ]);
  assert.equal(await lit("bluetooth"), false);
});
test("failed commands surface their error without pretending the heater turned on", async () => {
  await page.evaluate(() => { demo.failure = "Bluetooth write failed"; });
  await button("heat").click();
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Bluetooth write failed/);
  assert.equal(await button("heat").getAttribute("aria-pressed"), "false");
  assert.equal(await lit("heat"), false);
});
test("buttons wait for an actual status update and prevent repeated in-flight toggles", async () => {
  await page.evaluate(() => { demo.confirm = false; });
  await button("heat").click();
  assert.equal(await button("heat").isDisabled(), true);
  assert.equal(await button("heat").getAttribute("aria-pressed"), "false");
  assert.equal(await lit("heat"), false);
  await page.evaluate(() => demo.update("heat", "ON"));
  assert.equal(await button("heat").isDisabled(), false);
  assert.equal(await button("heat").getAttribute("aria-pressed"), "true");
  assert.equal(await lit("heat"), true);
});
test("target changes stay adjustable while feedback waits for the device", async () => {
  await page.evaluate(() => { demo.confirm = false; });
  await button("increase").click();
  assert.equal(await button("increase").isDisabled(), false);
  assert.equal(await button("heat").isDisabled(), true);
  assert.match(await stateText(), /Target temperature: 181/);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "Setting target to 181 °C…");
  await page.evaluate(() => demo.update("target", "181"));
  await page.waitForFunction(() => !demo.card._targetRequest);
  assert.equal(await button("heat").isDisabled(), false);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});
test("unconfirmed commands time out with an error and disconnection clears waiting state", async () => {
  await page.clock.install();
  await page.evaluate(() => { demo.confirm = false; });
  await button("air").click();
  await page.clock.runFor(5100);
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /No status confirmation/);
  assert.equal(await button("air").getAttribute("aria-pressed"), "false");
  await button("heat").click();
  await page.evaluate(() => demo.update("connection", "DISCONNECTED"));
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Bluetooth disconnected/);
});
test("changing device configuration cannot send a command to the previous device", async () => {
  await page.evaluate(() => {
    for (const [id, state] of Object.entries(demo.hass.states)) demo.hass.states[`${id}_2`] = structuredClone(state);
    demo.card.setConfig({ device: "volcano-two" });
  });
  await button("increase").click();
  assert.equal(await page.evaluate(() => demo.calls[0].data.entity_id), "number.renamed_target_2");
});
test("registry failures are visible and retryable, and repeated resource loading is safe", async () => {
  await page.evaluate(async () => {
    demo.registryFailure = true;
    demo.registryChanged();
    await import("/card.js?v=another-resource");
  });
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Could not load device controls/);
  await page.evaluate(() => { demo.registryFailure = false; });
  await button("power").click();
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
  assert.equal(await page.evaluate(() => window.customCards.filter(card => card.type === "volcano-hybrid-card").length), 1);
});
test("registry updates follow entity renames and disabled entities", async () => {
  await page.evaluate(() => {
    const target = demo.registry.find(entry => entry.entity_id === demo.ids.target);
    demo.hass.states["number.new_name"] = demo.hass.states[demo.ids.target];
    target.entity_id = "number.new_name";
    demo.registryChanged();
  });
  await button("increase").click();
  assert.equal(await page.evaluate(() => demo.calls[0].data.entity_id), "number.new_name");
  await page.evaluate(() => { demo.registry[0].disabled_by = "user"; demo.registryChanged(); });
  await page.waitForFunction(() => demo.card.shadowRoot.querySelector(".status").textContent.includes("missing"));
});
test("remounting cleans registry listeners and reconnects them once", async () => {
  assert.equal(await page.evaluate(() => demo.subscriptions), 1);
  await page.evaluate(() => demo.card.remove());
  assert.equal(await page.evaluate(() => demo.subscriptions), 0);
  await page.evaluate(() => document.querySelector("main").append(demo.card));
  assert.equal(await page.evaluate(() => demo.subscriptions), 1);
});
test("visual editor needs only a device, and preserves unrelated card options", async () => {
  const result = await page.evaluate(async () => {
    let loadedForm = false;
    window.loadCardHelpers = async () => ({ createCardElement: () => ({ constructor: { getConfigElement: async () => {
      loadedForm = true;
      customElements.define("ha-form", class extends HTMLElement {});
    } } }) });
    const editor = await customElements.get("volcano-hybrid-card").getConfigElement();
    editor.setConfig({ type: "custom:volcano-hybrid-card", device: "volcano-one", temperature_unit: "F", colors: { current_temperature: "#abcdef" }, grid_options: { columns: 12 } });
    editor.hass = demo.hass;
    const form = editor.shadowRoot.querySelector("ha-form");
    let changed;
    editor.addEventListener("config-changed", event => { changed = event.detail.config; });
    form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { device: "volcano-two", temperature_unit: "F" } } }));
    return { loadedForm, schema: form.schema, changed, stub: customElements.get("volcano-hybrid-card").getStubConfig(demo.hass) };
  });
  assert.equal(result.schema[0].selector.device.filter.integration, "volcano_integration");
  assert.equal(result.schema.length, 10);
  assert.equal(result.loadedForm, true);
  assert.deepEqual(result.stub, { device: "volcano-one" });
  assert.equal(result.changed.device, "volcano-two");
  assert.deepEqual(result.changed.grid_options, { columns: 12 });
  assert.deepEqual(result.changed.colors, { current_temperature: "#abcdef" });
  assert.equal(result.changed.temperature_unit, undefined);
});
test("old card overrides are ignored and no card unit switch remains", async () => {
  await page.evaluate(() => demo.card.setConfig({ device: "volcano-one", temperature_unit: "F" }));
  await page.waitForFunction(() => !demo.card.shadowRoot.querySelector("button.increase").disabled);
  assert.match(await stateText(), /180 degrees Celsius/);
  assert.equal(await button("units").count(), 0);
});
test("an unknown device unit disables temperature changes without guessing", async () => {
  await page.evaluate(() => demo.setDeviceUnit(null));
  assert.equal(await button("increase").isDisabled(), true);
  assert.equal(await button("decrease").isDisabled(), true);
  assert.equal(await button("heat").isDisabled(), false);
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /temperature unit unavailable/);
  assert.equal(await page.locator("volcano-hybrid-card .unit.current").textContent(), "");
});
test("Fahrenheit limits use the physical unit with a Celsius number entity", async () => {
  await page.evaluate(() => { demo.setDeviceUnit("F"); demo.update("target", "229.4"); });
  await button("increase").click();
  assert.match(await stateText(), /446 degrees Fahrenheit/);
  assert.equal(await button("increase").isDisabled(), true);
  await page.evaluate(() => demo.update("target", "40.6"));
  await button("decrease").click();
  assert.match(await stateText(), /104 degrees Fahrenheit/);
  assert.equal(await button("decrease").isDisabled(), true);
});
test("colour editor previews changes, survives rerenders and resets without losing card options", async () => {
  const result = await page.evaluate(() => {
    const editor = document.createElement("volcano-hybrid-card-editor");
    const original = { device: "volcano-one", grid_options: { columns: 12 } };
    editor.setConfig(original); editor.hass = demo.hass;
    document.querySelector("main").append(editor);
    let changed;
    editor.addEventListener("config-changed", event => {
      changed = event.detail.config; demo.card.setConfig(changed); editor.setConfig(changed);
    });
    const input = editor.shadowRoot.querySelector('input[name="current_temperature"]');
    input.value = "#33ccff";
    input.dispatchEvent(new Event("input"));
    const fill = getComputedStyle(demo.card.shadowRoot.querySelector("g.current")).fill;
    const sameInput = input === editor.shadowRoot.querySelector('input[name="current_temperature"]');
    const count = editor.shadowRoot.querySelectorAll('input[type="color"]').length;
    editor.shadowRoot.querySelector(".reset-colours").click();
    return { fill, sameInput, count, changed, reset: input.value, defaultFill: getComputedStyle(demo.card.shadowRoot.querySelector("g.current")).fill };
  });
  assert.equal(result.fill, "rgb(51, 204, 255)");
  assert.equal(result.sameInput, true);
  assert.equal(result.count, 28);
  assert.deepEqual(result.changed, { device: "volcano-one", grid_options: { columns: 12 } });
  assert.equal(result.reset, "#ff850c");
  assert.equal(result.defaultFill, "rgb(255, 133, 12)");
});
test("colour overrides reach screen, buttons, icons and status; invalid values are rejected", async () => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const result = await page.evaluate(() => {
    demo.card.setConfig({ device: "volcano-one", colors: {
      screen_top: "#123456", button_background: "#223344", icons: "#55aaff", status_text: "#bbccdd",
    } });
    const root = demo.card.shadowRoot;
    const values = [getComputedStyle(root.querySelector("stop")).stopColor, getComputedStyle(root.querySelector(".key")).fill,
      getComputedStyle(root.querySelector(".bluetooth-icon")).stroke, getComputedStyle(root.querySelector(".status")).color];
    const errors = [];
    for (const colors of ["red", [], { current_temperature: "url(https://example.com)" }, { invalid: "#112233" }]) {
      try { demo.card.setConfig({ device: "volcano-one", colors }); } catch { errors.push(true); }
    }
    return { values, errors };
  });
  assert.deepEqual(result.values, ["rgb(18, 52, 86)", "rgb(34, 51, 68)", "rgb(85, 170, 255)", "rgb(187, 204, 221)"]);
  assert.equal(result.errors.length, 4);
});
test("phone layout stays within the viewport and keyboard controls work", async () => {
  await page.setViewportSize({ width: 360, height: 720 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await button("heat").focus();
  await page.keyboard.press("Enter");
  assert.equal(await button("heat").getAttribute("aria-pressed"), "true");
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-panel-phone.png` });
});
test("desktop panel screenshot", async () => {
  if (process.env.SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-panel-preview.png`, fullPage: true });
    await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-hybrid-panel.png` });
  }
});


test("explicit Celsius fallback enables controls until the device reports its unit", async () => {
  await page.evaluate(() => {
    demo.setDeviceUnit(null);
    demo.hass.config.unit_system.temperature = "°F";
    demo.update("target", "356", { unit_of_measurement: "°F", min: 104, max: 446, temperature_unit_fallback: "C" });
  });
  assert.match(await stateText(), /Target temperature: 180 degrees Celsius/);
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Device unit not reported; using °C/);
  assert.equal(await button("increase").isDisabled(), false);
  assert.equal(await button("decrease").isDisabled(), false);
  await button("increase").click();
  assert.equal(await page.evaluate(() => demo.calls[0].data.value), 357.8);
  assert.match(await stateText(), /Target temperature: 181 degrees Celsius/);
  await page.evaluate(() => {
    demo.setDeviceUnit("F");
    demo.update("target", "356", { temperature_unit_fallback: null });
  });
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
  assert.match(await stateText(), /Target temperature: 356 degrees Fahrenheit/);
  await button("increase").click();
  assert.equal(await page.evaluate(() => demo.calls[1].data.value), 357);
  assert.match(await stateText(), /Target temperature: 357 degrees Fahrenheit/);
});

async function holdButton(name) {
  const box = await button(name).boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
}

for (const direction of ["increase", "decrease"]) {
  test(`mouse hold repeats ${direction} and release adds no extra step`, async () => {
    await page.clock.install();
    await holdButton(direction);
    assert.equal(await page.evaluate(() => demo.calls.length), 1);
    await page.clock.runFor(900);
    const values = await page.evaluate(() => demo.calls.map(call => call.data.value));
    assert.ok(values.length >= 4);
    values.forEach((value, index) => assert.equal(value, 180 + (direction === "increase" ? 1 : -1) * (index + 1)));
    await page.mouse.up();
    await page.clock.runFor(2000);
    assert.equal(await page.evaluate(() => demo.calls.length), values.length);
    assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
  });
}

test("holding during a slow service previews the final target and sends only that target next", async () => {
  await page.clock.install();
  await page.evaluate(() => {
    demo.pause = true;
    const send = demo.hass.callService;
    demo.inFlight = 0; demo.maxInFlight = 0;
    demo.hass.callService = async (...args) => {
      demo.maxInFlight = Math.max(demo.maxInFlight, ++demo.inFlight);
      try { await send(...args); } finally { demo.inFlight--; }
    };
  });
  await holdButton("increase");
  await page.clock.runFor(1000);
  await page.mouse.up();
  const selected = await page.evaluate(() => demo.card._targetRequest.value);
  assert.ok(selected > 185);
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  assert.equal(await button("increase").isDisabled(), false);
  assert.equal(await button("heat").isDisabled(), true);
  assert.match(await stateText(), new RegExp(`Target temperature: ${selected}`));
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), `Setting target to ${selected} °C…`);
  if (process.env.SCREENSHOT_DIR) {
    await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-hold-pending.png` });
  }
  await page.evaluate(() => { demo.pause = false; demo.resume(); });
  await page.waitForFunction(() => !demo.card._targetRequest && !demo.card._busy);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [181, selected]);
  assert.equal(await page.evaluate(() => demo.maxInFlight), 1);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});

test("rapid taps coalesce behind confirmation and can reverse back to the original target", async () => {
  await page.evaluate(() => { demo.confirm = false; });
  await button("increase").click();
  await button("increase").click();
  await button("decrease").click();
  await button("decrease").click();
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  assert.match(await stateText(), /Target temperature: 180/);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "Setting target to 180 °C…");
  await page.evaluate(() => demo.update("target", "181"));
  await page.waitForFunction(() => demo.calls.length === 2);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [181, 180]);
  await page.evaluate(() => demo.update("target", "180"));
  await page.waitForFunction(() => !demo.card._targetRequest);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});

test("Fahrenheit hold previews whole degrees and converts the coalesced target once", async () => {
  await page.clock.install();
  await page.evaluate(() => { demo.setDeviceUnit("F"); demo.pause = true; });
  await holdButton("increase");
  await page.clock.runFor(800);
  const selected = await page.evaluate(() => demo.card._targetRequest.value);
  assert.ok(selected >= 360);
  assert.match(await stateText(), new RegExp(`Target temperature: ${selected} degrees Fahrenheit`));
  await page.mouse.up();
  await page.evaluate(() => { demo.pause = false; demo.resume(); });
  await page.waitForFunction(() => !demo.card._targetRequest);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [180.5556, Number(((selected - 32) * 5 / 9).toFixed(4))]);
  assert.match(await stateText(), new RegExp(`Target temperature: ${selected} degrees Fahrenheit`));
});

for (const [direction, temperature, expected] of [["increase", "229", 230], ["decrease", "41", 40]]) {
  test(`holding ${direction} stops at the temperature limit`, async () => {
    await page.clock.install();
    await page.evaluate(value => demo.update("target", value), temperature);
    await holdButton(direction);
    await page.clock.runFor(3000);
    await page.mouse.up();
    assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [expected]);
    assert.equal(await button(direction).isDisabled(), true);
    assert.equal(await page.evaluate(() => demo.card._hold), null);
  });
}

for (const ending of ["touchEnd", "touchCancel"]) {
  test(`real touch hold repeats and ${ending} stops it without a duplicate click`, async () => {
    await page.clock.install();
    await page.setViewportSize({ width: 360, height: 720 });
    const session = await page.context().newCDPSession(page);
    await session.send("Emulation.setTouchEmulationEnabled", { enabled: true });
    const box = await button("increase").boundingBox();
    await session.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: box.x + box.width / 2, y: box.y + box.height / 2 }] });
    await page.clock.runFor(900);
    const count = await page.evaluate(() => demo.calls.length);
    assert.ok(count >= 4);
    await session.send("Input.dispatchTouchEvent", { type: ending, touchPoints: [] });
    await page.clock.runFor(2000);
    assert.equal(await page.evaluate(() => demo.calls.length), count);
    assert.equal(await page.evaluate(() => demo.card._hold), null);
    await session.detach();
  });
}

for (const interruption of ["blur", "hidden", "capture_lost", "pointer_cancel", "move_away"]) {
  test(`holding stops after ${interruption}`, async () => {
    await page.clock.install();
    await holdButton("increase");
    await page.clock.runFor(650);
    if (interruption === "move_away") await page.mouse.move(0, 0);
    else await page.evaluate(kind => {
      if (kind === "blur") window.dispatchEvent(new Event("blur"));
      if (kind === "hidden") {
        Object.defineProperty(document, "hidden", { value: true, configurable: true });
        document.dispatchEvent(new Event("visibilitychange"));
      }
      const hold = demo.card._hold;
      if (kind === "capture_lost") hold.button.releasePointerCapture(hold.pointerId);
      if (kind === "pointer_cancel") hold.button.dispatchEvent(new PointerEvent("pointercancel", { pointerId: hold.pointerId }));
    }, interruption);
    // A capture release is delivered on the next pointer event by Chromium.
    if (interruption === "capture_lost") await page.mouse.move(400, 10);
    const count = await page.evaluate(() => demo.calls.length);
    await page.clock.runFor(2000);
    await page.mouse.up();
    assert.equal(await page.evaluate(() => demo.calls.length), count);
    assert.equal(await page.evaluate(() => demo.card._hold), null);
  });
}

for (const change of ["disconnect", "unit", "entity", "rename", "config", "remove", "connection"]) {
  test(`${change} cancels held and queued changes while an old command finishes`, async () => {
    await page.clock.install();
    await page.evaluate(() => { demo.pause = true; });
    await holdButton("increase");
    await page.clock.runFor(800);
    await page.evaluate(kind => {
      if (kind === "disconnect") demo.update("connection", "DISCONNECTED");
      if (kind === "unit") demo.setDeviceUnit("F");
      if (kind === "entity") {
        demo.registry.find(entry => entry.entity_id === demo.ids.target).disabled_by = "user";
        demo.registryChanged();
      }
      if (kind === "rename") {
        demo.hass.states["number.new_name"] = demo.hass.states[demo.ids.target];
        demo.registry.find(entry => entry.entity_id === demo.ids.target).entity_id = "number.new_name";
        demo.registryChanged();
      }
      if (kind === "config") demo.card.setConfig({ device: "volcano-two" });
      if (kind === "remove") demo.card.remove();
      if (kind === "connection") {
        demo.hass.connection = { ...demo.hass.connection };
        demo.card.hass = demo.hass;
      }
    }, change);
    await page.clock.runFor(1000);
    await page.mouse.up();
    await page.evaluate(() => { demo.pause = false; demo.resume(); });
    await page.clock.runFor(6000);
    assert.equal(await page.evaluate(() => demo.calls.length), 1);
    assert.equal(await page.evaluate(() => Boolean(demo.card._hold || demo.card._targetRequest || demo.card._pending)), false);
    assert.equal(await page.locator("volcano-hybrid-card .status").count() > 0 ? await page.locator("volcano-hybrid-card .status").evaluate(el => el.classList.contains("error")) : false, false);
  });
}

test("a failed temperature write stops repeating and restores the actual target", async () => {
  await page.clock.install();
  await page.evaluate(() => { demo.failure = "Bluetooth write failed"; });
  await holdButton("increase");
  await page.clock.runFor(3000);
  await page.mouse.up();
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  assert.match(await stateText(), /Target temperature: 180/);
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Bluetooth write failed/);
  assert.equal(await page.evaluate(() => Boolean(demo.card._hold || demo.card._targetRequest)), false);
});

test("unconfirmed temperature writes stop a hold and discard the unsent target", async () => {
  await page.clock.install();
  await page.evaluate(() => { demo.confirm = false; });
  await holdButton("increase");
  await page.clock.runFor(6000);
  await page.mouse.up();
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  assert.match(await stateText(), /Target temperature: 180/);
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /No status confirmation/);
  await page.evaluate(() => demo.update("target", "181"));
  await page.clock.runFor(2000);
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
});

test("power discards queued temperatures while waiting for target confirmation", async () => {
  await page.evaluate(() => { demo.confirm = false; });
  await button("increase").click();
  await button("increase").click();
  await page.evaluate(() => { demo.confirm = true; });
  await button("power").click();
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.service)), ["set_value", "disconnect"]);
  await page.evaluate(() => demo.update("target", "181"));
  assert.equal(await page.evaluate(() => Boolean(demo.card._targetRequest)), false);
});

test("keyboard temperature clicks adjust once and right clicks do not adjust", async () => {
  await button("increase").focus();
  await page.keyboard.press("Enter");
  await button("decrease").focus();
  await page.keyboard.press("Space");
  await button("increase").click({ button: "right" });
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [181, 180]);
});


test("an old service response cannot clear a new device's pending command", async () => {
  await page.evaluate(() => { demo.pause = true; });
  await button("increase").click();
  await page.evaluate(() => {
    demo.resumeFirst = demo.resume;
    for (const [id, state] of Object.entries(demo.hass.states)) demo.hass.states[`${id}_2`] = structuredClone(state);
    demo.card.setConfig({ device: "volcano-two" });
  });
  await button("decrease").click();
  await page.evaluate(() => { demo.resumeSecond = demo.resume; demo.resumeFirst(); });
  assert.equal(await button("heat").isDisabled(), true);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "Setting target to 179 °C…");
  await page.evaluate(() => { demo.pause = false; demo.resumeSecond(); });
  await page.waitForFunction(() => !demo.card._busy && !demo.card._targetRequest);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data)), [
    { entity_id: "number.renamed_target", value: 181 },
    { entity_id: "number.renamed_target_2", value: 179 },
  ]);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});

async function enableExtras(options = {}) {
  await page.evaluate(options => demo.card.setConfig({ device: "volcano-one", show_brightness: true,
    show_auto_shutoff: true, show_vibration: true, show_stop_all: true, ...options }), options);
  await page.waitForFunction(() => !demo.card._loading);
}

test("extra controls are opt-in, independently configurable, and below the original panel", async () => {
  assert.equal(await page.locator("volcano-hybrid-card .extras").isVisible(), false);
  for (const [option, row] of [["brightness", "brightness"], ["auto_shutoff", "shutoff"], ["vibration", "vibration"], ["stop_all", "stop"]]) {
    await page.evaluate(option => demo.card.setConfig({ device: "volcano-one", [`show_${option}`]: true }), option);
    assert.equal(await page.locator(`volcano-hybrid-card .${row}-row`).isVisible(), true);
    assert.equal(await page.locator("volcano-hybrid-card .extra-row:visible").count(), 1);
  }
  await enableExtras();
  const panel = await page.locator("volcano-hybrid-card .panel").boundingBox();
  const extras = await page.locator("volcano-hybrid-card .extras").boundingBox();
  assert.ok(extras.y >= panel.y + panel.height);
  assert.equal(await page.evaluate(() => demo.card.getCardSize()), 7);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});

test("YAML options validate percentages, booleans and explicit script/automation targets", async () => {
  const result = await page.evaluate(() => {
    const invalid = [{ temperature_acceleration: -1 }, { temperature_acceleration: 301 }, { temperature_acceleration: "100" },
      { temperature_acceleration: 1.5 }, { show_vibration: "false" }, { stop_all_entities: "script.test" },
      { stop_all_entities: ["all"] }, { stop_all_entities: ["switch.test"] }, { stop_all_entities: [null] }];
    const rejected = invalid.filter(config => {
      try { demo.card.setConfig({ device: "volcano-one", ...config }); return false; } catch { return true; }
    }).length;
    const selected = Array.from({ length: 100 }, (_, i) => `script.workflow_${i}`);
    const config = { device: "volcano-one", temperature_acceleration: 0, stop_all_entities: [...selected, selected[0]] };
    demo.card.setConfig(config);
    return { rejected, count: demo.card._config.stop_all_entities.length, original: config.stop_all_entities.length };
  });
  assert.deepEqual(result, { rejected: 9, count: 100, original: 101 });
});

test("visual settings round-trip YAML, defaults, unlimited stop selection and existing colours", async () => {
  const result = await page.evaluate(() => {
    const editor = document.createElement("volcano-hybrid-card-editor");
    editor.setConfig({ device: "volcano-one", colors: { icons: "#aabbcc" }, grid_options: { columns: 6 } }); editor.hass = demo.hass;
    const form = editor.shadowRoot.querySelector("ha-form");
    const defaults = structuredClone(form.data);
    let changed;
    editor.addEventListener("config-changed", event => { changed = event.detail.config; });
    form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data,
      show_stop_all: true, show_brightness: true, temperature_acceleration: 200, stop_all_entities: ["script.bag", "automation.timer"] } } }));
    editor.setConfig(changed);
    return { defaults, changed, data: form.data, selector: form.schema.at(-1).selector,
      helper: form.computeHelper({ name: "stop_all_entities" }) };
  });
  assert.equal(result.defaults.temperature_acceleration, 100);
  assert.equal(result.defaults.show_stop_all, false);
  assert.deepEqual(result.defaults.stop_all_entities, []);
  assert.equal(result.changed.temperature_acceleration, 200);
  assert.equal(result.data.show_brightness, true);
  assert.deepEqual(result.changed.colors, { icons: "#aabbcc" });
  assert.deepEqual(result.changed.grid_options, { columns: 6 });
  assert.deepEqual(result.selector.entity, { multiple: true, filter: { domain: ["script", "automation"] } });
  assert.match(result.helper, /Automations stay enabled/);
});

test("hold acceleration increases the repeat rate, with a steady 0% option and a sensible default", async () => {
  await page.clock.install();
  const counts = [];
  for (const acceleration of [0, 100, 300, null]) {
    await page.evaluate(acceleration => {
      demo.calls.length = 0; demo.confirm = false;
      demo.card.setConfig({ device: "volcano-one", ...(acceleration === null ? {} : { temperature_acceleration: acceleration }) });
      demo.update("target", "100");
    }, acceleration);
    await page.waitForFunction(() => !demo.card._loading);
    await holdButton("increase");
    await page.clock.runFor(2400);
    counts.push(await page.evaluate(() => demo.card._targetRequest.value - 100));
    await page.mouse.up();
  }
  assert.ok(counts[0] >= 16 && counts[0] <= 20);
  assert.ok(counts[1] > counts[0]);
  assert.ok(counts[2] > counts[1]);
  assert.ok(Math.abs(counts[3] - counts[1]) <= 1);
});

test("brightness slider previews without writes, commits on release, and +/- respects zero and 100", async () => {
  await enableExtras();
  const slider = page.locator("volcano-hybrid-card #brightness");
  await slider.evaluate(input => { input.value = "42"; input.dispatchEvent(new Event("input")); });
  await page.evaluate(() => demo.update("current", "181"));
  assert.equal(await slider.inputValue(), "42");
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
  assert.equal(await page.locator("volcano-hybrid-card .brightness-value").textContent(), "42%");
  await slider.dispatchEvent("change");
  await button("brightness-increase").click();
  await button("brightness-decrease").click();
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data)), [
    { entity_id: "number.renamed_brightness", value: 42 }, { entity_id: "number.renamed_brightness", value: 43 }, { entity_id: "number.renamed_brightness", value: 42 },
  ]);
  await page.evaluate(() => demo.update("brightness", "0"));
  assert.equal(await button("brightness-decrease").isDisabled(), true);
  assert.equal(await slider.isDisabled(), false);
  await page.evaluate(() => demo.update("brightness", "100"));
  assert.equal(await button("brightness-increase").isDisabled(), true);
});

test("auto shutoff preserves editing during updates and validates the entity's limits and units", async () => {
  await enableExtras();
  const input = page.locator("volcano-hybrid-card #shutoff");
  await input.fill("90");
  await page.evaluate(() => demo.update("current", "181"));
  assert.equal(await input.inputValue(), "90");
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
  await input.press("Tab");
  assert.deepEqual(await page.evaluate(() => demo.calls[0]), { domain: "number", service: "set_value", data: { entity_id: "number.renamed_shutoff", value: 90 } });
  for (const value of ["0", "361", "90.5", ""]) {
    await input.fill(value); await input.press("Tab");
    assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Choose auto shutoff/);
  }
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  await page.evaluate(() => demo.update("shutoff", "3600", { min: 1800, max: 21600, step: 60, unit_of_measurement: "s" }));
  await input.fill("5400"); await input.press("Enter");
  assert.equal(await page.evaluate(() => demo.calls.at(-1).data.value), 5400);
  assert.equal(await page.locator("volcano-hybrid-card .shutoff-unit").textContent(), "s");
});

test("vibration waits for real state confirmation and displays failures without changing the toggle", async () => {
  await enableExtras();
  await page.evaluate(() => { demo.confirm = false; });
  const toggle = button("vibration-toggle");
  await toggle.click();
  assert.deepEqual(await page.evaluate(() => demo.calls[0]), { domain: "switch", service: "turn_on", data: { entity_id: "switch.renamed_vibration" } });
  assert.equal(await toggle.getAttribute("aria-checked"), "false");
  assert.equal(await toggle.isDisabled(), true);
  await page.evaluate(() => demo.update("vibration", "on"));
  assert.equal(await toggle.getAttribute("aria-checked"), "true");
  await page.evaluate(() => { demo.failure = "Permission denied"; });
  await toggle.click();
  assert.equal(await toggle.getAttribute("aria-checked"), "true");
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Permission denied/);
});

test("missing optional entities never break main controls and unavailable settings cannot send commands", async () => {
  await enableExtras();
  await page.evaluate(() => {
    for (const role of ["brightness", "shutoff", "vibration"]) demo.registry.find(entry => entry.entity_id === demo.ids[role]).disabled_by = "user";
    demo.registryChanged();
  });
  await page.waitForFunction(() => !demo.card._loading);
  assert.equal(await button("increase").isDisabled(), false);
  assert.equal(await button("heat").isDisabled(), false);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
  assert.equal(await button("vibration-toggle").isDisabled(), true);
  assert.equal(await page.locator("volcano-hybrid-card #shutoff").isDisabled(), true);
  assert.equal(await page.locator("volcano-hybrid-card #brightness").isDisabled(), true);
  assert.equal(await page.locator("volcano-hybrid-card .brightness-value").textContent(), "Unavailable");
});

test("Stop all targets only configured scripts and automations, then turns off both outputs without disconnecting", async () => {
  await enableExtras({ stop_all_entities: ["script.bag", "automation.timer", "script.cool", "script.bag"] });
  await page.evaluate(() => {
    for (const id of ["script.bag", "automation.timer", "script.cool", "script.unrelated"]) demo.hass.states[id] = { state: "on", attributes: {} };
    demo.update("heat", "ON"); demo.update("air", "ON");
  });
  await button("stop-all").click();
  await page.waitForFunction(() => !demo.card._busy);
  assert.deepEqual(await page.evaluate(() => demo.calls), [
    { domain: "volcano_integration", service: "stop_automation_runs", data: { entity_id: "automation.timer" } },
    { domain: "script", service: "turn_off", data: { entity_id: "script.bag" } },
    { domain: "script", service: "turn_off", data: { entity_id: "script.cool" } },
    { domain: "volcano_integration", service: "heat_off", data: { device_id: "volcano-one" } },
    { domain: "volcano_integration", service: "pump_off", data: { device_id: "volcano-one" } },
  ]);
  assert.equal(await page.evaluate(() => demo.hass.states["script.unrelated"].state), "on");
  assert.equal(await page.evaluate(() => demo.hass.states[demo.ids.connection].state), "CONNECTED");
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});

test("Stop all attempts every selected target and both OFF actions even after failures", async () => {
  await enableExtras({ stop_all_entities: ["script.denied", "automation.timer", "script.missing"] });
  await page.evaluate(() => {
    demo.hass.states["script.denied"] = { state: "on", attributes: {} };
    demo.hass.states["automation.timer"] = { state: "on", attributes: {} };
    demo.failures = { "script.denied": "Permission denied", heat_off: "Bluetooth failed" };
    demo.update("heat", "ON"); demo.update("air", "ON");
  });
  await button("stop-all").click();
  await page.waitForFunction(() => !demo.card._busy);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.service)), ["stop_automation_runs", "turn_off", "heat_off", "pump_off"]);
  const status = await page.locator("volcano-hybrid-card .status").textContent();
  assert.match(status, /Could not stop everything/);
  assert.match(status, /script.denied: Permission denied/);
  assert.match(status, /script.missing: unavailable/);
  assert.match(status, /Heat: Bluetooth failed/);
  assert.equal(await page.evaluate(() => demo.hass.states[demo.ids.air].state), "OFF");
  assert.equal(await button("stop-all").isDisabled(), false);
});

test("Stop all cancels queued temperature steps and waits for the in-flight write before OFF actions", async () => {
  await enableExtras();
  await page.clock.install();
  await page.evaluate(() => { demo.pause = true; });
  await holdButton("increase");
  await page.clock.runFor(900);
  await page.mouse.up();
  await button("stop-all").click();
  assert.equal(await page.evaluate(() => Boolean(demo.card._targetRequest || demo.card._hold)), false);
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  assert.equal(await button("stop-all").isDisabled(), true);
  await page.evaluate(() => { demo.pause = false; demo.resume(); });
  await page.waitForFunction(() => !demo.card._busy);
  await page.clock.runFor(6000);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.service)), ["set_value", "heat_off", "pump_off"]);
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
});

test("Stop all waits for heat/air status and reports missing confirmation", async () => {
  await enableExtras();
  await page.clock.install();
  await page.evaluate(() => { demo.update("heat", "ON"); demo.update("air", "ON"); demo.confirm = false; });
  await button("stop-all").click();
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Waiting for heat and air status/);
  await page.clock.runFor(5500);
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /No status confirmation/);
});

test("Stop all still stops selected workflows when Bluetooth is offline", async () => {
  await enableExtras({ stop_all_entities: ["script.bag"] });
  await page.evaluate(() => {
    demo.hass.states["script.bag"] = { state: "on", attributes: {} };
    demo.update("connection", "DISCONNECTED");
    demo.failures = { heat_off: "Not connected", pump_off: "Not connected" };
  });
  await button("stop-all").click();
  await page.waitForFunction(() => !demo.card._busy);
  assert.equal(await page.evaluate(() => demo.hass.states["script.bag"].state), "off");
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Not connected/);
  assert.equal(await page.evaluate(() => demo.calls.length), 3);
});

test("Stop all finishes for the original device when the card is reconfigured or removed", async () => {
  await enableExtras({ stop_all_entities: ["script.bag"] });
  await page.evaluate(() => { demo.hass.states["script.bag"] = { state: "on", attributes: {} }; demo.pause = true; });
  await button("stop-all").click();
  await page.waitForFunction(() => Boolean(demo.resume));
  await page.evaluate(() => {
    demo.card.setConfig({ device: "volcano-two", show_stop_all: true }); demo.card.remove();
    demo.pause = false; demo.resume();
  });
  await page.waitForFunction(() => demo.calls.length === 3);
  assert.deepEqual(await page.evaluate(() => demo.calls.slice(1).map(call => call.data.device_id)), ["volcano-one", "volcano-one"]);
  assert.equal(await page.evaluate(() => Boolean(demo.card._pending)), false);
});

test("all extra controls fit desktop and phone layouts and inherit card colours", async () => {
  await enableExtras({ stop_all_entities: ["script.bag", "automation.timer"] });
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-extras-desktop.png` });
  await page.setViewportSize({ width: 360, height: 800 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const result = await page.evaluate(() => {
    const root = demo.card.shadowRoot;
    const card = demo.card.getBoundingClientRect();
    return [...root.querySelectorAll(".extras button, .extras input")].every(el => {
      const bounds = el.getBoundingClientRect(); return bounds.left >= card.left && bounds.right <= card.right;
    });
  });
  assert.equal(result, true);
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-extras-phone.png` });
});


test("Stop all cancels current automation runs before their scripts and leaves automations enabled", async () => {
  await enableExtras({ stop_all_entities: ["script.bag", "automation.timer"] });
  await page.evaluate(() => {
    for (const id of ["script.bag", "automation.timer"]) demo.hass.states[id] = { state: "on", attributes: { current: 2 } };
    demo.pause = true;
  });
  await button("stop-all").click();
  await page.waitForFunction(() => Boolean(demo.resume));
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.entity_id)), ["automation.timer"]);
  await page.evaluate(() => { demo.pause = false; demo.resume(); });
  await page.waitForFunction(() => !demo.card._busy);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.service)), ["stop_automation_runs", "turn_off", "heat_off", "pump_off"]);
});


for (const state of ["on", "off"]) {
  test(`Stop all preserves an automation's ${state} state while stopping its current runs`, async () => {
    await enableExtras({ stop_all_entities: ["automation.timer", "script.bag"] });
    await page.evaluate(state => {
      demo.hass.states["automation.timer"] = { state, attributes: { current: 2 } };
      demo.hass.states["script.bag"] = { state: "on", attributes: {} };
    }, state);
    await button("stop-all").click();
    await page.waitForFunction(() => !demo.card._busy);
    assert.equal(await page.evaluate(() => demo.hass.states["automation.timer"].state), state);
    assert.equal(await page.evaluate(() => demo.hass.states["automation.timer"].attributes.current), 0);
    assert.equal(await page.evaluate(() => demo.hass.states["script.bag"].state), "off");
    assert.equal(await page.evaluate(() => demo.calls.some(call => call.domain === "automation")), false);
    assert.match(await page.locator("volcano-hybrid-card .stop-note").textContent(), /stops 1 automation/);
  });
}

const scriptButton = entity => page.locator(`volcano-hybrid-card .script-run[data-entity="${entity}"]`);
async function enableScriptButtons(options = {}) {
  await page.evaluate(options => {
    for (const [id, name] of [["script.session", "Fill balloon"], ["script.cool", "Cool down"], ["script.cleanup", "Clean up"]]) {
      demo.hass.states[id] = { state: "off", attributes: { friendly_name: name, current: 0 } };
    }
    demo.hass.states["automation.timer"] = { state: "on", attributes: { friendly_name: "Timer" } };
    demo.card.setConfig({ device: "volcano-one", show_script_buttons: true,
      stop_all_entities: ["script.session", "automation.timer", "script.cool", "script.cleanup"], ...options });
  }, options);
  await page.waitForFunction(() => !demo.card._loading);
}

test("script buttons reuse related scripts, show by default in list order and don't change Stop all membership", async () => {
  await enableScriptButtons({ show_script_buttons: false });
  assert.equal(await page.locator("volcano-hybrid-card .scripts-row").isVisible(), false);
  await enableScriptButtons();
  assert.deepEqual(await page.locator("volcano-hybrid-card .script-name").allTextContents(), ["Fill balloon", "Cool down", "Clean up"]);
  await enableScriptButtons({ script_buttons: [{ entity: "script.cool" }, { entity: "script.session", show: false }] });
  assert.deepEqual(await page.locator("volcano-hybrid-card .script-name").allTextContents(), ["Cool down", "Clean up"]);
  assert.deepEqual(await page.evaluate(() => demo.card._config.stop_all_entities), ["script.session", "automation.timer", "script.cool", "script.cleanup"]);
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
});

test("script button YAML rejects invalid mappings and clones configuration without mutating it", async () => {
  const result = await page.evaluate(() => {
    const invalid = [null, "script.foo", ["script.foo"], [null], [{ entity: "all" }], [{ entity: "automation.foo" }],
      [{ entity: "script.foo", show: "false" }], [{ entity: "script.foo", other: true }], [{ entity: "script.foo" }, { entity: "script.foo" }]];
    const rejected = invalid.filter(script_buttons => {
      try { demo.card.setConfig({ device: "volcano-one", script_buttons }); return false; } catch { return true; }
    }).length;
    const original = { device: "volcano-one", show_script_buttons: true, stop_all_entities: ["script.foo"],
      script_buttons: [{ entity: "script.foo", show: false }] };
    demo.card.setConfig(original);
    original.script_buttons[0].show = true;
    let booleanRejected = false;
    try { demo.card.setConfig({ device: "volcano-one", show_script_buttons: "true" }); } catch { booleanRejected = true; }
    return { rejected, booleanRejected, show: demo.card._config.script_buttons[0].show };
  });
  assert.deepEqual(result, { rejected: 9, booleanRejected: true, show: false });
});

test("script buttons start only the chosen script, show real running state, and don't need Bluetooth", async () => {
  await enableScriptButtons();
  await page.evaluate(() => demo.update("connection", "DISCONNECTED"));
  await scriptButton("script.session").click();
  assert.deepEqual(await page.evaluate(() => demo.calls), [{ domain: "script", service: "turn_on", data: { entity_id: "script.session" } }]);
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Running · Stop");
  assert.equal(await scriptButton("script.session").isDisabled(), false);
  assert.equal(await scriptButton("script.cool").isDisabled(), false);
  await page.evaluate(() => { demo.hass.states["script.session"].state = "off"; demo.hass.states["script.session"].attributes.current = 0; demo.card.hass = demo.hass; });
  assert.equal(await scriptButton("script.session").isDisabled(), false);
  await scriptButton("script.session").focus();
  await page.keyboard.press("Enter");
  assert.equal(await page.evaluate(() => demo.calls.length), 2);
});

test("a script's pending start blocks duplicate taps and Stop all waits for it before stopping hidden and visible scripts", async () => {
  await enableScriptButtons({ show_stop_all: true, script_buttons: [{ entity: "script.cleanup", show: false }] });
  await page.evaluate(() => { demo.pause = true; });
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Starting…");
  assert.equal(await scriptButton("script.session").isDisabled(), true);
  await page.evaluate(() => { demo.card._runScript("script.session"); demo.card._runScript("script.cleanup"); });
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  await button("stop-all").click();
  assert.equal(await scriptButton("script.cool").isDisabled(), true);
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  await page.evaluate(() => { demo.pause = false; demo.resume(); });
  await page.waitForFunction(() => !demo.card._stopping);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => [call.service, call.data.entity_id || call.data.device_id])), [
    ["turn_on", "script.session"], ["stop_automation_runs", "automation.timer"],
    ["turn_off", "script.session"], ["turn_off", "script.cool"], ["turn_off", "script.cleanup"],
    ["heat_off", "volcano-one"], ["pump_off", "volcano-one"],
  ]);
  assert.equal(await page.evaluate(() => demo.hass.states["automation.timer"].state), "on");
  assert.equal(await scriptButton("script.session").isDisabled(), false);
});

test("script permission errors are visible and retryable; unavailable and queued scripts cannot be started", async () => {
  await enableScriptButtons();
  await page.evaluate(() => {
    demo.failures = { "script.session": "Permission denied" };
    demo.hass.states["script.cool"].state = "unavailable";
    demo.hass.states["script.cleanup"].attributes.current = 2;
    demo.card.hass = demo.hass;
  });
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Permission denied");
  assert.equal(await scriptButton("script.session").isDisabled(), false);
  assert.equal(await scriptButton("script.cool").locator(".script-state").textContent(), "Unavailable");
  assert.equal(await scriptButton("script.cleanup").locator(".script-state").textContent(), "Running · Stop");
  assert.equal(await scriptButton("script.cool").isDisabled(), true);
  assert.equal(await scriptButton("script.cleanup").isDisabled(), false);
  await page.evaluate(() => { demo.failures = {}; });
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Running · Stop");
});

test("script starts wait for HA state; fast completed scripts are confirmed by last_triggered", async () => {
  await enableScriptButtons();
  await page.clock.install();
  await page.evaluate(() => { demo.confirm = false; });
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").isDisabled(), true);
  await page.evaluate(() => {
    demo.hass.states["script.session"].attributes.last_triggered = "2026-10-25T12:00:00Z";
    demo.card.hass = demo.hass;
  });
  assert.equal(await scriptButton("script.session").isDisabled(), false);
  await scriptButton("script.cool").click();
  await page.clock.runFor(5100);
  assert.equal(await scriptButton("script.cool").locator(".script-state").textContent(), "Start sent; status not confirmed.");
  assert.equal(await scriptButton("script.cool").isDisabled(), false);
  assert.equal(await page.evaluate(() => demo.calls.length), 2);
});

test("removed scripts and late start failures cannot change a newly configured card", async () => {
  await enableScriptButtons();
  await page.evaluate(() => {
    demo.hass.callService = async () => new Promise((resolve, reject) => { demo.rejectStart = reject; });
  });
  await scriptButton("script.session").click();
  await page.evaluate(() => {
    demo.card.setConfig({ device: "volcano-one", show_script_buttons: true, stop_all_entities: ["script.cool"],
      script_buttons: [{ entity: "script.session" }, { entity: "script.cool" }] });
    demo.rejectStart(new Error("Old request failed"));
  });
  await page.waitForFunction(() => !demo.card._loading);
  assert.deepEqual(await page.locator("volcano-hybrid-card .script-name").allTextContents(), ["Cool down"]);
  assert.equal(await scriptButton("script.cool").locator(".script-state").textContent(), "Run script");
  assert.equal(await page.evaluate(() => demo.card._scriptErrors.size), 0);
});

async function createScriptEditor() {
  await page.evaluate(() => {
    const editor = window.scriptEditor = document.createElement("volcano-hybrid-card-editor");
    editor.setConfig({ ...demo.card._config, colors: { icons: "#aabbcc" }, grid_options: { columns: 6 } });
    editor.hass = demo.hass;
    editor.addEventListener("config-changed", event => {
      window.editedConfig = structuredClone(event.detail.config);
      demo.card.setConfig(event.detail.config); editor.setConfig(event.detail.config);
    });
    document.querySelector("main").append(editor);
  });
}
const editorRow = entity => page.locator(`volcano-hybrid-card-editor .script-editor-row[data-entity="${entity}"]`);

test("editor supports individual visibility, select all, ordering and YAML round-trips without changing Stop all", async () => {
  await enableScriptButtons();
  await createScriptEditor();
  const all = page.locator("volcano-hybrid-card-editor .script-select-all input");
  assert.equal(await all.isChecked(), true);
  await editorRow("script.cool").locator("input").uncheck();
  assert.equal(await all.evaluate(el => el.indeterminate), true);
  assert.deepEqual(await page.locator("volcano-hybrid-card .script-name").allTextContents(), ["Fill balloon", "Clean up"]);
  await editorRow("script.cleanup").locator(".move-up").click();
  await editorRow("script.cleanup").locator(".move-up").click();
  assert.deepEqual(await page.locator("volcano-hybrid-card .script-name").allTextContents(), ["Clean up", "Fill balloon"]);
  assert.equal(await editorRow("script.cleanup").locator(".move-up").isDisabled(), true);
  assert.equal(await editorRow("script.cool").locator(".move-down").isDisabled(), true);
  await all.check();
  assert.deepEqual(await page.locator("volcano-hybrid-card .script-name").allTextContents(), ["Clean up", "Fill balloon", "Cool down"]);
  await all.uncheck();
  assert.equal(await page.locator("volcano-hybrid-card .script-run").count(), 0);
  assert.equal(await page.locator("volcano-hybrid-card .scripts-empty").isVisible(), true);
  assert.deepEqual(await page.evaluate(() => editedConfig), {
    device: "volcano-one", show_script_buttons: true,
    stop_all_entities: ["script.session", "automation.timer", "script.cool", "script.cleanup"],
    colors: { icons: "#aabbcc" }, grid_options: { columns: 6 },
    script_buttons: [{ entity: "script.cleanup", show: false }, { entity: "script.session", show: false }, { entity: "script.cool", show: false }],
  });
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
});

test("editor reacts to related-list changes and show toggle, retaining order and adding new scripts at the end", async () => {
  await enableScriptButtons({ script_buttons: [{ entity: "script.cool", show: false }, { entity: "script.session" }] });
  await createScriptEditor();
  await page.evaluate(() => {
    const form = scriptEditor.shadowRoot.querySelector("ha-form");
    form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, stop_all_entities: ["script.session", "script.new", "script.cool"] } } }));
  });
  assert.deepEqual(await page.locator("volcano-hybrid-card-editor .script-editor-id").allTextContents(), ["script.cool", "script.session", "script.new"]);
  assert.equal(await editorRow("script.new").locator("input").isChecked(), true);
  assert.equal(await editorRow("script.cool").locator("input").isChecked(), false);
  await page.evaluate(() => {
    const form = scriptEditor.shadowRoot.querySelector("ha-form");
    form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, show_script_buttons: false } } }));
  });
  assert.equal(await page.locator("volcano-hybrid-card-editor .script-buttons-editor").isVisible(), false);
  assert.equal(await page.locator("volcano-hybrid-card .scripts-row").isVisible(), false);
  await page.evaluate(() => {
    const form = scriptEditor.shadowRoot.querySelector("ha-form");
    form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, show_script_buttons: true } } }));
  });
  assert.equal(await editorRow("script.cool").locator("input").isChecked(), false);
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
});

test("empty selection and missing entities are clear; names are literal text and updates retain button focus", async () => {
  await enableScriptButtons({ stop_all_entities: ["automation.timer"] });
  await createScriptEditor();
  assert.equal(await page.locator("volcano-hybrid-card-editor .script-select-all input").isDisabled(), true);
  assert.equal(await page.locator("volcano-hybrid-card-editor .script-editor-empty").isVisible(), true);
  await enableScriptButtons({ stop_all_entities: ["script.session", "script.missing"] });
  await page.evaluate(() => {
    demo.hass.states["script.session"].attributes.friendly_name = '<img src=x onerror="window.badName=true">';
    demo.card.hass = demo.hass;
  });
  await scriptButton("script.session").focus();
  await page.evaluate(() => demo.update("current", "181"));
  assert.equal(await scriptButton("script.session").evaluate(el => el.getRootNode().activeElement === el), true);
  assert.equal(await scriptButton("script.session").locator("img").count(), 0);
  assert.equal(await page.evaluate(() => Boolean(window.badName)), false);
  assert.equal(await scriptButton("script.missing").isDisabled(), true);
});

test("script buttons and their editor fit narrow screens with long names", async () => {
  await enableScriptButtons({ show_stop_all: true, show_brightness: true, show_auto_shutoff: true, show_vibration: true });
  await page.evaluate(() => {
    demo.hass.states["script.session"].attributes.friendly_name = "A long Volcano session name that wraps over several lines";
    demo.hass.states["script.cool"].state = "on";
    demo.card.hass = demo.hass;
  });
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-scripts-desktop.png` });
  await page.setViewportSize({ width: 360, height: 1050 });
  await createScriptEditor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  for (const host of ["volcano-hybrid-card", "volcano-hybrid-card-editor"]) {
    assert.equal(await page.locator(host).evaluate(el => {
      const bounds = el.getBoundingClientRect();
      return [...el.shadowRoot.querySelectorAll(".script-run, .script-editor-row, .script-editor-row button")].every(node => {
        const rect = node.getBoundingClientRect(); return rect.left >= bounds.left && rect.right <= bounds.right;
      });
    }), true);
  }
  if (process.env.SCREENSHOT_DIR) {
    await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-scripts-phone.png` });
    await page.locator("volcano-hybrid-card-editor .script-buttons-editor").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-scripts-editor.png` });
  }
});

const presetButton = temperature => page.locator(`volcano-hybrid-card .temperature-preset[data-celsius="${temperature}"]`);
const temperatureDialog = () => page.locator("volcano-hybrid-card .temperature-dialog");
const temperatureInput = () => page.locator("volcano-hybrid-card #temperature-entry");
async function enablePresets(options = {}) {
  await page.evaluate(options => demo.card.setConfig({ device: "volcano-one", show_temperature_presets: true, ...options }), options);
  await page.waitForFunction(() => !demo.card._loading);
}

test("running script button stops only that script, leaves outputs alone and can run it again", async () => {
  await enableScriptButtons();
  await page.evaluate(() => {
    demo.hass.states["script.session"].state = "on"; demo.hass.states["script.session"].attributes.current = 3;
    demo.hass.states["script.cool"].state = "on";
    demo.update("heat", "ON"); demo.update("air", "ON");
  });
  assert.equal(await scriptButton("script.session").getAttribute("aria-label"), "Stop: Fill balloon");
  await scriptButton("script.session").click();
  assert.deepEqual(await page.evaluate(() => demo.calls), [{ domain: "script", service: "turn_off", data: { entity_id: "script.session" } }]);
  assert.equal(await page.evaluate(() => demo.hass.states["script.session"].attributes.current), 0);
  assert.equal(await page.evaluate(() => demo.hass.states["script.cool"].state), "on");
  assert.equal(await page.evaluate(() => demo.hass.states[demo.ids.heat].state), "ON");
  assert.equal(await page.evaluate(() => demo.hass.states[demo.ids.air].state), "ON");
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Run script");
  await scriptButton("script.session").click();
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.service)), ["turn_off", "turn_on"]);
});

test("individual script stop remains available during device commands and failed stops stay visible", async () => {
  await enableScriptButtons();
  await page.evaluate(() => {
    demo.hass.states["script.session"].state = "on"; demo.update("heat", "ON");
    demo.confirm = false; demo.failures = { "script.session": "Stop permission denied" };
  });
  await button("heat").click();
  assert.equal(await scriptButton("script.session").isDisabled(), false);
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Stop permission denied");
  assert.equal(await page.evaluate(() => demo.hass.states["script.session"].state), "on");
  assert.equal(await scriptButton("script.session").isDisabled(), false);
});

test("individual script stop blocks duplicate requests and requires stopped state confirmation", async () => {
  await enableScriptButtons();
  await page.clock.install();
  await page.evaluate(() => { demo.hass.states["script.session"].state = "on"; demo.card.hass = demo.hass; demo.confirm = false; });
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Stopping…");
  await page.evaluate(() => demo.card._stopScript("script.session"));
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  await page.clock.runFor(5100);
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Stop sent; status not confirmed.");
  await page.evaluate(() => { demo.confirm = true; });
  await scriptButton("script.session").click();
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Run script");
});

for (const deviceUnit of ["C", "F"]) {
  for (const entityUnit of ["C", "F"]) {
    test(`presets and typed temperature follow device ${deviceUnit} with HA entity ${entityUnit}`, async () => {
      await enablePresets();
      await page.evaluate(({ deviceUnit, entityUnit }) => {
        demo.setDeviceUnit(deviceUnit);
        demo.hass.config.unit_system.temperature = deviceUnit === "C" ? "°F" : "°C";
        const f = entityUnit === "F";
        demo.update("target", f ? "356" : "180", { unit_of_measurement: `°${entityUnit}`, min: f ? 104 : 40, max: f ? 446 : 230 });
      }, { deviceUnit, entityUnit });
      assert.equal(await presetButton(185).locator(".preset-value").textContent(), deviceUnit === "F" ? "365 °F" : "185 °C");
      await presetButton(185).click();
      assert.deepEqual(await page.evaluate(() => demo.calls[0]), {
        domain: "number", service: "set_value", data: { entity_id: "number.renamed_target", value: entityUnit === "F" ? 365 : 185 },
      });
      assert.equal(await presetButton(185).getAttribute("aria-pressed"), "true");
      await button("target-edit").click();
      assert.equal(await temperatureInput().inputValue(), deviceUnit === "F" ? "365" : "185");
      assert.equal(await temperatureInput().getAttribute("min"), deviceUnit === "F" ? "104" : "40");
      assert.equal(await temperatureInput().getAttribute("max"), deviceUnit === "F" ? "446" : "230");
      await temperatureInput().fill(deviceUnit === "F" ? "361" : "191");
      await temperatureInput().press("Enter");
      assert.equal(await temperatureDialog().isVisible(), false);
      const expected = deviceUnit === "F" ? (entityUnit === "F" ? 361 : 182.7778) : (entityUnit === "F" ? 375.8 : 191);
      assert.equal(await page.evaluate(() => demo.calls[1].data.value), expected);
      assert.match(await stateText(), new RegExp(`Target temperature: ${deviceUnit === "F" ? 361 : 191} degrees`));
      assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
    });
  }
}

test("default preset range is 170–230 C by 5 or equivalent 338–446 F by 9; main buttons remain one degree", async () => {
  await enablePresets();
  assert.deepEqual(await page.locator("volcano-hybrid-card .preset-value").allTextContents(), Array.from({ length: 13 }, (_, i) => `${170 + i * 5} °C`));
  await presetButton(230).click();
  assert.equal(await page.evaluate(() => demo.calls.at(-1).data.value), 230);
  assert.equal(await button("increase").isDisabled(), true);
  await page.evaluate(() => demo.setDeviceUnit("F"));
  assert.deepEqual(await page.locator("volcano-hybrid-card .preset-value").allTextContents(), Array.from({ length: 13 }, (_, i) => `${338 + i * 9} °F`));
  await presetButton(170).click();
  assert.equal(await page.evaluate(() => demo.calls.at(-1).data.value), 170);
  await button("increase").click();
  assert.match(await stateText(), /Target temperature: 339 degrees Fahrenheit/);
  assert.equal(await page.evaluate(() => demo.calls.at(-1).data.value), 170.5556);
});

test("typed temperatures reject blanks, fractions and values beyond device bounds without sending a command", async () => {
  await button("target-edit").click();
  for (const value of ["", "170.6", "39", "231", "240"]) {
    await temperatureInput().fill(value);
    await temperatureDialog().locator('button[type="submit"]').click();
    assert.equal(await temperatureDialog().isVisible(), true);
    assert.match(await page.locator("volcano-hybrid-card .temperature-entry-error").textContent(), /whole number from 40 to 230 °C/);
  }
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
  await temperatureInput().fill("40");
  await temperatureInput().press("Enter");
  assert.equal(await page.evaluate(() => demo.calls[0].data.value), 40);
  await page.evaluate(() => demo.setDeviceUnit("F"));
  await button("target-edit").click();
  await temperatureInput().fill("447");
  await temperatureInput().press("Enter");
  assert.match(await page.locator("volcano-hybrid-card .temperature-entry-error").textContent(), /104 to 446 °F/);
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
});

test("cancel and Escape preserve target; updates preserve a typed draft", async () => {
  await button("target-edit").click();
  await temperatureInput().fill("205");
  await page.evaluate(() => { demo.update("current", "181"); demo.update("target", "190"); });
  assert.equal(await temperatureInput().inputValue(), "205");
  await button("temperature-cancel").click();
  assert.equal(await temperatureDialog().isVisible(), false);
  assert.equal(await button("target-edit").evaluate(el => el.getRootNode().activeElement === el), true);
  await button("target-edit").click();
  assert.equal(await temperatureInput().inputValue(), "190");
  await page.keyboard.press("Escape");
  assert.equal(await temperatureDialog().isVisible(), false);
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
});

for (const change of ["unit", "entity_unit", "disconnect", "device", "remove"]) {
  test(`a ${change} change cancels typed entry without reinterpreting the value`, async () => {
    await button("target-edit").click();
    await temperatureInput().fill("200");
    await page.evaluate(change => {
      if (change === "unit") demo.setDeviceUnit("F");
      if (change === "entity_unit") demo.update("target", "356", { unit_of_measurement: "°F", min: 104, max: 446 });
      if (change === "disconnect") demo.update("connection", "DISCONNECTED");
      if (change === "device") demo.card.setConfig({ device: "volcano-two" });
      if (change === "remove") demo.card.remove();
      demo.card._submitTemperatureEntry();
    }, change);
    assert.equal(await page.evaluate(() => demo.card.shadowRoot.querySelector("dialog").open), false);
    assert.equal(await page.evaluate(() => demo.calls.length), 0);
  });
}

test("presets coalesce with rapid typed changes and preserve error/confirmation feedback", async () => {
  await enablePresets();
  await page.evaluate(() => { demo.pause = true; });
  await presetButton(190).click();
  await presetButton(205).click();
  await button("target-edit").click();
  await temperatureInput().fill("212");
  await temperatureInput().press("Enter");
  assert.match(await stateText(), /Target temperature: 212 degrees Celsius/);
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  await page.evaluate(() => { demo.pause = false; demo.resume(); });
  await page.waitForFunction(() => demo.calls.length === 2 && !demo.card._busy);
  assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.data.value)), [190, 212]);
  await page.evaluate(() => { demo.failure = "Bluetooth write failed"; });
  await presetButton(230).click();
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Bluetooth write failed/);
  assert.match(await stateText(), /Target temperature: 212 degrees Celsius/);
});

test("presets and entry respect unknown units, offline state, fallback and narrower number bounds", async () => {
  await enablePresets();
  await page.evaluate(() => demo.setDeviceUnit(null));
  assert.equal(await button("target-edit").isDisabled(), true);
  assert.equal(await presetButton(185).isDisabled(), true);
  await page.evaluate(() => demo.update("target", "180", { temperature_unit_fallback: "C", max: 200 }));
  assert.equal(await presetButton(185).isDisabled(), false);
  assert.equal(await presetButton(205).isDisabled(), true);
  await button("target-edit").click();
  assert.equal(await temperatureInput().getAttribute("max"), "200");
  await page.keyboard.press("Escape");
  await page.evaluate(() => demo.update("connection", "DISCONNECTED"));
  assert.equal(await button("target-edit").isDisabled(), true);
  assert.equal(await presetButton(185).isDisabled(), true);
});

test("preset YAML rejects unsupported temperatures, units, fractions, duplicates and invalid booleans", async () => {
  const result = await page.evaluate(() => {
    const invalid = [null, "180", [180], [null], [{ temperature: 240 }], [{ temperature: 165 }],
      [{ temperature: 172 }], [{ temperature: 180.5 }], [{ temperature: "180" }],
      [{ temperature: 180, unit: "F" }], [{ temperature: 180, show: "false" }], [{ temperature: 180, name: 5 }],
      [{ temperature: 180 }, { temperature: 180 }]];
    const rejected = invalid.filter(temperature_presets => {
      try { demo.card.setConfig({ device: "volcano-one", temperature_presets }); return false; } catch { return true; }
    }).length;
    let collapseRejected = false;
    try { demo.card.setConfig({ device: "volcano-one", collapse_extras: "true" }); } catch { collapseRejected = true; }
    return { rejected, collapseRejected };
  });
  assert.deepEqual(result, { rejected: 13, collapseRejected: true });
});

test("preset editor names, individual visibility, Select all and collapse option survive YAML round-trip", async () => {
  await enablePresets({ temperature_presets: [{ temperature: 195, name: "Finish" }, { temperature: 180 }] });
  await createScriptEditor();
  const row = temperature => page.locator(`volcano-hybrid-card-editor .preset-editor-row[data-celsius="${temperature}"]`);
  const all = page.locator("volcano-hybrid-card-editor .preset-select-all input");
  assert.deepEqual(await page.locator("volcano-hybrid-card .preset-value").allTextContents(), ["195 °C", "180 °C"]);
  assert.equal(await all.evaluate(el => el.indeterminate), true);
  await row(180).locator('input[type="text"]').fill("Start");
  assert.equal(await presetButton(180).locator(".preset-name").textContent(), "Start");
  await row(195).locator('input[type="checkbox"]').uncheck();
  assert.equal(await presetButton(195).count(), 0);
  await all.check();
  assert.equal(await page.locator("volcano-hybrid-card .temperature-preset").count(), 13);
  await all.uncheck();
  assert.equal(await page.locator("volcano-hybrid-card .presets-empty").isVisible(), true);
  await row(180).locator('input[type="checkbox"]').check();
  assert.equal(await presetButton(180).locator(".preset-name").textContent(), "Start");
  await page.evaluate(() => {
    const form = scriptEditor.shadowRoot.querySelector("ha-form");
    form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, collapse_extras: true } } }));
  });
  assert.equal(await page.evaluate(() => editedConfig.collapse_extras), true);
  assert.deepEqual(await page.evaluate(() => editedConfig.colors), { icons: "#aabbcc" });
  assert.deepEqual(await page.evaluate(() => editedConfig.grid_options), { columns: 6 });
  assert.equal(await page.evaluate(() => demo.calls.length), 0);
});

test("extra controls collapse without affecting actions; state updates preserve expansion and show running count", async () => {
  await enableScriptButtons({ collapse_extras: true, show_temperature_presets: true, show_stop_all: true });
  assert.equal(await page.locator("volcano-hybrid-card .extras").isVisible(), false);
  assert.equal(await button("extras-toggle").getAttribute("aria-expanded"), "false");
  assert.equal(await page.evaluate(() => demo.card.getCardSize()), 4);
  await button("extras-toggle").click();
  assert.equal(await page.locator("volcano-hybrid-card .extras").isVisible(), true);
  await scriptButton("script.session").click();
  await page.evaluate(() => demo.update("current", "181"));
  assert.equal(await button("extras-toggle").getAttribute("aria-expanded"), "true");
  await button("extras-toggle").click();
  assert.match(await button("extras-toggle").textContent(), /1 script running/);
  assert.equal(await page.evaluate(() => demo.hass.states["script.session"].state), "on");
  assert.equal(await page.evaluate(() => demo.calls.length), 1);
  await button("extras-toggle").focus(); await page.keyboard.press("Enter");
  await scriptButton("script.session").click();
  assert.equal(await button("extras-toggle").textContent(), "Extra controls");
  await page.evaluate(() => demo.card.setConfig({ device: "volcano-one", collapse_extras: true }));
  assert.equal(await button("extras-toggle").isVisible(), false);
  assert.equal(await page.locator("volcano-hybrid-card .extras").isVisible(), false);
});

test("new controls fit phone and desktop, display literal preset names and keep modal within viewport", async () => {
  await enableScriptButtons({ show_brightness: true, show_auto_shutoff: true, show_vibration: true, show_stop_all: true,
    show_temperature_presets: true, collapse_extras: true, temperature_presets: [
      { temperature: 170, name: "Warm up" }, { temperature: 185, name: "Session" }, { temperature: 200 }, { temperature: 215 }, { temperature: 230 },
    ] });
  await page.evaluate(() => { demo.hass.states["script.session"].state = "on"; demo.card.hass = demo.hass; });
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-controls-collapsed.png` });
  await button("extras-toggle").click();
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-controls-desktop.png` });
  await page.setViewportSize({ width: 360, height: 1000 });
  await page.evaluate(() => demo.setDeviceUnit("F"));
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-controls-fahrenheit-phone.png` });
  await createScriptEditor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.SCREENSHOT_DIR) await page.locator("volcano-hybrid-card-editor .preset-editor").screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-preset-editor.png` });
  await button("target-edit").click();
  const bounds = await temperatureDialog().boundingBox();
  assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 360);
  if (process.env.SCREENSHOT_DIR) await temperatureDialog().screenshot({ path: `${process.env.SCREENSHOT_DIR}/volcano-temperature-entry.png` });
  await page.keyboard.press("Escape");
  await enablePresets({ temperature_presets: [{ temperature: 180, name: '<img src=x onerror="window.badPreset=true">' }] });
  assert.equal(await presetButton(180).locator("img").count(), 0);
  assert.equal(await page.evaluate(() => Boolean(window.badPreset)), false);
});

for (const reset of ["config", "remount", "connection"]) {
  test(`Stop all keeps every control blocked after a ${reset} reset`, async () => {
    await enableScriptButtons({ show_stop_all: true, show_brightness: true, show_auto_shutoff: true, show_vibration: true, show_temperature_presets: true });
    await page.evaluate(() => {
      demo.update("heat", "ON"); demo.update("air", "ON");
      const original = demo.hass.callService;
      demo.hass.callService = async (...args) => {
        if (args[1] === "pump_off") await new Promise(resolve => { demo.finishStop = resolve; });
        return original(...args);
      };
    });
    await button("stop-all").click();
    await page.waitForFunction(() => Boolean(demo.finishStop));
    await page.evaluate(reset => {
      if (reset === "config") demo.card.setConfig({ ...demo.card._config, colors: { icons: "#aabbcc" } });
      if (reset === "remount") { const parent = demo.card.parentNode; demo.card.remove(); parent.append(demo.card); }
      if (reset === "connection") { demo.hass = { ...demo.hass, connection: { ...demo.hass.connection } }; demo.card.hass = demo.hass; }
    }, reset);
    await page.waitForFunction(() => !demo.card._loading);
    for (const name of ["heat", "air", "power", "increase", "decrease", "target-edit", "vibration-toggle", "brightness-increase", "stop-all"]) {
      assert.equal(await button(name).isDisabled(), true, name);
    }
    assert.equal(await page.locator("volcano-hybrid-card #brightness").isDisabled(), true);
    assert.equal(await page.locator("volcano-hybrid-card #shutoff").isDisabled(), true);
    assert.equal(await scriptButton("script.session").isDisabled(), true);
    assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "Stopping…");
    const callsBefore = await page.evaluate(() => demo.calls.length);
    await page.evaluate(async () => {
      await demo.card._action("heat"); await demo.card._action("air"); await demo.card._action("power");
      await demo.card._setSetting("brightness", 42); await demo.card._setSetting("shutoff", 123);
      await demo.card._setSetting("vibration", true); await demo.card._runScript("script.session");
      demo.card._adjustTemperature("increase");
    });
    assert.equal(await page.evaluate(() => demo.calls.length), callsBefore);
    await page.evaluate(() => demo.finishStop());
    await page.waitForFunction(() => !demo.card._stopping);
    assert.deepEqual(await page.evaluate(() => [demo.hass.states[demo.ids.heat].state, demo.hass.states[demo.ids.air].state]), ["OFF", "OFF"]);
    assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
    assert.equal(await button("heat").isEnabled(), true);
  });
}

for (const failure of ["write", "confirmation"]) {
  test(`Stop all retains its ${failure} failure after editing the card`, async () => {
    await enableExtras();
    await page.clock.install();
    await page.evaluate(failure => {
      demo.update("heat", "ON"); demo.update("air", "ON");
      if (failure === "write") demo.failures = { pump_off: "Air command failed" };
      else demo.confirm = false;
      const original = demo.hass.callService;
      demo.hass.callService = async (...args) => {
        if (args[1] === "pump_off") await new Promise(resolve => { demo.finishStop = resolve; });
        return original(...args);
      };
    }, failure);
    await button("stop-all").click();
    await page.waitForFunction(() => Boolean(demo.finishStop));
    await page.evaluate(() => demo.card.setConfig({ ...demo.card._config, colors: { icons: "#aabbcc" } }));
    await page.waitForFunction(() => !demo.card._loading);
    await page.evaluate(() => demo.finishStop());
    await page.waitForFunction(() => !demo.card._busy);
    if (failure === "confirmation") {
      assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Waiting for heat and air status/);
      await page.clock.runFor(5100);
    }
    assert.match(await page.locator("volcano-hybrid-card .status").textContent(), failure === "write" ? /Air command failed/ : /No status confirmation/);
  });
}

test("hour-based shutoff confirmation rejects a value one minute short", async () => {
  await enableExtras();
  await page.evaluate(() => {
    demo.update("shutoff", "2", { min: 0, max: 6, step: 1, unit_of_measurement: "h",
      native_value: 120, native_min_value: 30, native_max_value: 360, native_step: 1, native_unit_of_measurement: "min" });
    demo.confirm = false;
  });
  const input = page.locator("volcano-hybrid-card #shutoff");
  assert.equal(await input.getAttribute("min"), "0.5");
  assert.equal(Number(await input.getAttribute("step")), 1 / 60);
  await input.fill("2.05"); await input.press("Enter");
  await page.evaluate(() => demo.update("shutoff", "2", { native_value: 122 }));
  assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Waiting for auto shutoff status/);
  await page.evaluate(() => demo.update("shutoff", "2", { native_value: 123 }));
  assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
  assert.equal(await input.inputValue(), "2.05");
});

for (const outcome of ["running", "finished"]) {
  test(`a later external ${outcome} script clears a failed start message`, async () => {
    await enableScriptButtons();
    await page.evaluate(() => { demo.failure = "Permission denied"; });
    await scriptButton("script.session").click();
    assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Permission denied");
    await page.evaluate(() => demo.update("current", "181"));
    assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Permission denied");
    await page.evaluate(outcome => {
      const state = demo.hass.states["script.session"];
      state.state = outcome === "running" ? "on" : "off";
      state.attributes.current = outcome === "running" ? 1 : 0;
      state.attributes.last_triggered = "2026-11-19T12:00:00Z";
      demo.card.hass = demo.hass;
    }, outcome);
    assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), outcome === "running" ? "Running · Stop" : "Run script");
    assert.equal(await scriptButton("script.session").evaluate(el => el.classList.contains("failed")), false);
  });
}

test("a failed script stop stays visible until a later state confirms it stopped", async () => {
  await enableScriptButtons();
  await page.evaluate(() => {
    demo.hass.states["script.session"].state = "on";
    demo.hass.states["script.session"].attributes.current = 1;
    demo.card.hass = demo.hass; demo.failure = "Stop permission denied";
  });
  await scriptButton("script.session").click();
  await page.evaluate(() => demo.update("current", "181"));
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Stop permission denied");
  await page.evaluate(() => {
    demo.hass.states["script.session"].state = "off";
    demo.hass.states["script.session"].attributes.current = 0;
    demo.card.hass = demo.hass;
  });
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Run script");
});

test("a late start confirmation clears a script timeout message", async () => {
  await enableScriptButtons();
  await page.clock.install();
  await page.evaluate(() => { demo.confirm = false; });
  await scriptButton("script.session").click();
  await page.clock.runFor(5100);
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Start sent; status not confirmed.");
  await page.evaluate(() => { demo.hass.states["script.session"].state = "on"; demo.card.hass = demo.hass; });
  assert.equal(await scriptButton("script.session").locator(".script-state").textContent(), "Running · Stop");
});


for (const outcome of ["confirmed", "timeout"]) {
  test(`Stop all confirmation survives a card reset until ${outcome}`, async () => {
    await enableExtras();
    await page.clock.install();
    await page.evaluate(() => { demo.confirm = false; demo.update("heat", "ON"); demo.update("air", "ON"); });
    await button("stop-all").click();
    assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /Waiting for heat and air status/);
    await page.evaluate(() => demo.card.setConfig({ ...demo.card._config, colors: { icons: "#aabbcc" } }));
    await page.waitForFunction(() => !demo.card._loading);
    assert.equal(await button("heat").isDisabled(), true);
    assert.equal(await button("power").isDisabled(), true);
    assert.equal(await button("stop-all").isDisabled(), true);
    await page.evaluate(() => demo.card._action("heat"));
    assert.deepEqual(await page.evaluate(() => demo.calls.map(call => call.service)), ["heat_off", "pump_off"]);
    if (outcome === "confirmed") {
      await page.evaluate(() => { demo.update("heat", "OFF"); demo.update("air", "OFF"); });
      assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
      await page.clock.runFor(5100);
      assert.equal(await page.locator("volcano-hybrid-card .status").textContent(), "");
    } else {
      await page.clock.runFor(5100);
      assert.match(await page.locator("volcano-hybrid-card .status").textContent(), /No status confirmation/);
    }
    assert.equal(await button("stop-all").isEnabled(), true);
  });
}
