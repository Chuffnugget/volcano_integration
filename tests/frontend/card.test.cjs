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
test("target changes wait for their state update, then release the controls", async () => {
  await page.evaluate(() => { demo.confirm = false; });
  await button("increase").click();
  assert.equal(await button("increase").isDisabled(), true);
  assert.match(await stateText(), /Target temperature: 180/);
  await page.evaluate(() => demo.update("target", "181"));
  assert.equal(await button("increase").isDisabled(), false);
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
  assert.equal(result.schema.length, 1);
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
    editor.shadowRoot.querySelector("button").click();
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
