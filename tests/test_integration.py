"""Exercise actual Home Assistant service dispatch, entity updates and unload."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_integration import async_unload_entry
from custom_components.volcano_integration.const import DOMAIN


async def test_service_updates_existing_setpoint_entity(hass, entry, integration):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unavailable"
    await hass.services.async_call(DOMAIN, "connect", {}, blocking=True)
    await hass.services.async_call(
        DOMAIN,
        "set_temperature",
        {
            "temperature": 190,
            "wait_until_reached": False,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert float(state.state) == 190
    assert state.attributes["device_class"] == "temperature"
    assert state.attributes["unit_of_measurement"] == "°C"
    assert entry.unique_id == "AA:BB:CC:DD:EE:FF"


async def test_failed_action_propagates_through_ha(hass, integration):
    with pytest.raises(HomeAssistantError, match="not connected"):
        await hass.services.async_call(DOMAIN, "pump_on", {}, blocking=True)


async def test_all_original_entity_unique_ids_survive(hass, integration):
    registry = er.async_get(hass)
    expected = {
        "sensor": [
            "current_temperature",
            "heat_status",
            "pump_status",
            "bt_status",
            "ble_firmware_version",
            "serial_number",
            "firmware_version",
            "led_brightness",
            "hours_of_operation",
            "minutes_of_operation",
        ],
        "number": ["heater_temperature_setpoint", "led_brightness_number", "auto_shutoff_minutes"],
        "button": [
            "connect_button",
            "disconnect_button",
            "pump_on_button",
            "pump_off_button",
            "heat_on_button",
            "heat_off_button",
        ],
    }
    for platform, keys in expected.items():
        for key in keys:
            assert registry.async_get_entity_id(
                platform, DOMAIN, f"volcano_{key}_AA:BB:CC:DD:EE:FF"
            )


async def test_two_entries_require_target_and_unload_does_not_remove_services(
    hass, entry, integration
):
    second = MockConfigEntry(
        domain=DOMAIN, title="Second Volcano", version=2, data={"bt_address": "11:22:33:44:55:66"}
    )
    second.add_to_hass(hass)
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        assert await hass.config_entries.async_setup(second.entry_id)
    manager_two = hass.data[DOMAIN][second.entry_id]
    with pytest.raises(ServiceValidationError, match="Select a loaded"):
        await hass.services.async_call(DOMAIN, "pump_on", {}, blocking=True)
    first_device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    with (
        patch.object(integration, "write_gatt_command", new_callable=AsyncMock) as first_write,
        patch.object(manager_two, "write_gatt_command", new_callable=AsyncMock) as second_write,
    ):
        await hass.services.async_call(
            DOMAIN, "pump_on", {"device_id": first_device.id}, blocking=True
        )
        first_write.assert_awaited_once()
        second_write.assert_not_awaited()
        assert await hass.config_entries.async_unload(second.entry_id)
        assert hass.services.has_service(DOMAIN, "pump_on")
        await hass.services.async_call(DOMAIN, "pump_off", {}, blocking=True)
        assert first_write.await_count == 2


async def test_unload_failure_keeps_runtime(hass, entry, integration):
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=False):
        assert await async_unload_entry(hass, entry) is False
    assert hass.data[DOMAIN][entry.entry_id] is integration


async def test_shutdown_and_unload_release_listeners(hass, entry, integration):
    assert len(integration._listeners) == 21
    await hass.services.async_call(DOMAIN, "connect", {}, blocking=True)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert integration._run_task is None
    assert not integration._listeners


async def test_legacy_lowercase_address_connects_without_changing_entity_ids(hass, entry, ble):
    address = "aa:bb:cc:dd:ee:ff"
    hass.config_entries.async_update_entry(entry, data={**entry.data, "bt_address": address})
    with (
        patch("homeassistant.setup.async_process_deps_reqs", return_value=True),
        patch(
            "custom_components.volcano_integration.bluetooth_coordinator.async_ble_device_from_address",
            side_effect=lambda hass, lookup_address, **kwargs: (
                object() if lookup_address == address.upper() else None
            ),
        ),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
        manager = hass.data[DOMAIN][entry.entry_id]
        try:
            await manager.async_user_connect()
            await manager.wait_until_connected(timeout=0.5)
            assert er.async_get(hass).async_get_entity_id(
                "sensor", DOMAIN, f"volcano_current_temperature_{address}"
            )
            assert entry.data["bt_address"] == address
            assert entry.unique_id == address.upper()
        finally:
            await hass.config_entries.async_unload(entry.entry_id)
