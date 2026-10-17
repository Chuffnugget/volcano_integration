/* Test-only Home Assistant facade. Never included in the HACS release. */
export function setup(card, options = {}) {
  const keys = { current: "current_temperature", target: "heater_temperature_setpoint", heat: "heat_status", air: "pump_status", connection: "bt_status" };
  const ids = { current: "sensor.renamed_current", target: "number.renamed_target", heat: "sensor.renamed_heat", air: "sensor.renamed_air", connection: "sensor.renamed_bluetooth" };
  const registry = Object.entries(ids).map(([role, entity_id]) => ({
    entity_id, device_id: "volcano-one", platform: "volcano_integration", unique_id: `volcano_${keys[role]}_aa:bb:cc:dd:ee:ff`, disabled_by: null,
  }));
  registry.push(...registry.map(entry => ({ ...entry, device_id: "volcano-two", entity_id: `${entry.entity_id}_2`, unique_id: entry.unique_id.replace("aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66") })));
  const callbacks = new Set();
  const calls = [];
  let subscriptions = 0;
  const hass = {
    states: {
      [ids.current]: { state: "180", attributes: { unit_of_measurement: "°C", device_temperature_unit: "C" } },
      [ids.target]: { state: "180", attributes: { unit_of_measurement: "°C", device_temperature_unit: "C", min: 40, max: 230, step: 1 } },
      [ids.heat]: { state: "OFF", attributes: {} },
      [ids.air]: { state: "OFF", attributes: {} },
      [ids.connection]: { state: "CONNECTED", attributes: {} },
    },
    config: { unit_system: { temperature: "°C" } },
    devices: { "volcano-one": { id: "volcano-one", identifiers: [["volcano_integration", "aa:bb:cc:dd:ee:ff"]] } },
    connection: { subscribeEvents: async callback => {
      callbacks.add(callback); subscriptions++;
      return () => { if (callbacks.delete(callback)) subscriptions--; };
    } },
    callWS: async () => {
      if (demo.registryFailure) throw new Error("Registry offline");
      return registry;
    },
    callService: async (domain, service, data) => {
      calls.push({ domain, service, data });
      if (demo.failure) throw new Error(demo.failure);
      if (demo.pause) await new Promise(resolve => { demo.resume = resolve; });
      if (!demo.confirm) return;
      if (service === "set_value") {
        const state = hass.states[data.entity_id];
        // HA converts to native Celsius; the integration rounds in the device's unit.
        const fahrenheit = state.attributes.unit_of_measurement === "°F";
        const native = fahrenheit ? (data.value - 32) * 5 / 9 : data.value;
        const celsius = state.attributes.device_temperature_unit === "F"
          ? Math.round((Math.round(native * 9 / 5 + 32) - 32) * 5 / 9 * 10) / 10 : Math.round(native);
        const value = fahrenheit ? Number((celsius * 9 / 5 + 32).toFixed(4)) : celsius;
        state.state = String(value);
      }
      if (service.startsWith("heat_")) hass.states[ids.heat].state = service.endsWith("on") ? "ON" : "OFF";
      if (service.startsWith("pump_")) hass.states[ids.air].state = service.endsWith("on") ? "ON" : "OFF";
      if (service === "connect" || service === "disconnect") {
        if (service === "disconnect" && hass.states[ids.connection].state === "CONNECTED") {
          hass.states[ids.heat].state = "OFF";
          hass.states[ids.air].state = "OFF";
        }
        hass.states[ids.connection].state = service === "connect" ? "CONNECTED" : "DISCONNECTED";
        hass.states[ids.connection].attributes.connection_requested = service === "connect";
      }
      card.hass = hass;
    },
  };
  const demo = { card, hass, ids, registry, calls, confirm: true,
    get subscriptions() { return subscriptions; },
    update(role, state, attributes) {
      hass.states[ids[role]] = { ...hass.states[ids[role]], state, attributes: { ...hass.states[ids[role]].attributes, ...attributes } };
      card.hass = hass;
    },
    setDeviceUnit(unit) {
      for (const role of ["current", "target"]) hass.states[ids[role]].attributes.device_temperature_unit = unit;
      card.hass = hass;
    },
    registryChanged() { callbacks.forEach(callback => callback({})); },
  };
  card.setConfig({ type: "custom:volcano-hybrid-card", device: "volcano-one", ...options });
  card.hass = hass;
  return demo;
}
