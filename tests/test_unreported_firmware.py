"""Acknowledged commands when notify-only firmware has not sent any state."""

import asyncio
from types import SimpleNamespace

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_integration.const import (
    DOMAIN,
    REGISTER2_UUID,
    UUID_HEAT_OFF,
    UUID_PUMP_NOTIFICATIONS,
    UUID_PUMP_OFF,
)

from .conftest import connect_manager
from .test_firmware_capabilities import notification_only


def set_properties(peripheral, uuid, properties):
    original = peripheral.services.get_characteristic
    peripheral.services.get_characteristic = lambda requested: (
        (None if properties is None else SimpleNamespace(uuid=uuid, properties=properties))
        if requested == uuid
        else original(requested)
    )


@pytest.fixture
def short_confirmation(monkeypatch):
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.03
    )


@pytest.mark.parametrize("previous_connection", [False, True])
async def test_disconnect_without_status_requires_acknowledgements_and_warns(
    hass, manager, peripheral, short_confirmation, previous_connection, caplog
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)
    if previous_connection:
        peripheral.notification_callback(None, bytes.fromhex("2020"))
        await manager.stop()
        await connect_manager(manager)
        peripheral.disconnect.reset_mock()
    assert manager.state.heat_state is None and manager.state.pump_state is None
    await asyncio.wait_for(manager.async_user_disconnect(), 1)
    writes = peripheral.write_gatt_char.await_args_list
    assert [call.args[0].uuid for call in writes] == [UUID_HEAT_OFF, UUID_PUMP_OFF]
    assert all(call.kwargs["response"] is True for call in writes)
    assert not manager.connected and not manager.connection_requested
    peripheral.disconnect.assert_awaited_once()
    notifications = hass.data["persistent_notification"]
    assert len(notifications) == 1
    notification = notifications[f"{DOMAIN}_{manager._config_entry_id}_shutdown_unconfirmed"]
    assert "Both OFF commands were acknowledged" in notification["message"]
    assert "Check that heat and air are off" in notification["message"]
    assert "Bluetooth has been disconnected" in caplog.text


@pytest.mark.parametrize("uuid", [UUID_HEAT_OFF, UUID_PUMP_OFF])
async def test_disconnect_without_status_rejects_writes_without_response(
    hass, manager, peripheral, short_confirmation, uuid
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    set_properties(peripheral, uuid, ["write-without-response"])
    await connect_manager(manager)
    with pytest.raises(HomeAssistantError, match="did not confirm.*still connected"):
        await asyncio.wait_for(manager.async_user_disconnect(), 1)
    assert manager.connected
    assert peripheral.write_gatt_char.await_count == 2
    peripheral.disconnect.assert_not_awaited()
    assert not hass.data.get("persistent_notification")


@pytest.mark.parametrize("failed_uuid", [UUID_HEAT_OFF, UUID_PUMP_OFF])
async def test_disconnect_without_status_still_attempts_both_outputs_on_write_failure(
    hass, manager, peripheral, short_confirmation, failed_uuid
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == failed_uuid:
            raise BleakError("Write refused")
        await peripheral.write(characteristic, data, **kwargs)

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError, match="Could not turn off.*still connected"):
        await manager.async_user_disconnect()
    assert peripheral.write_gatt_char.await_count == 2
    peripheral.disconnect.assert_not_awaited()
    assert not hass.data.get("persistent_notification")


@pytest.mark.parametrize("status", [bytes(2), bytes.fromhex("2020"), b"\x00"])
async def test_first_status_during_off_writes_takes_precedence_over_acknowledgements(
    hass, manager, peripheral, short_confirmation, status
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == UUID_PUMP_OFF:
            peripheral.notification_callback(None, status)

    peripheral.write_gatt_char.side_effect = write
    if status == bytes(2):
        await manager.async_user_disconnect()
        peripheral.disconnect.assert_awaited_once()
    else:
        with pytest.raises(HomeAssistantError, match="did not confirm.*still connected"):
            await manager.async_user_disconnect()
        assert manager.connected
        peripheral.disconnect.assert_not_awaited()
    assert not hass.data.get("persistent_notification")


async def test_disconnect_acknowledgements_cannot_hide_link_loss(
    hass, manager, peripheral, short_confirmation
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == UUID_PUMP_OFF:
            peripheral.drop()

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError, match="Bluetooth was lost"):
        await manager.async_user_disconnect()
    assert not manager.connection_requested
    assert not hass.data.get("persistent_notification")


@pytest.mark.parametrize("unit", ["C", "F"])
async def test_select_existing_unreported_unit_accepts_acknowledgement(
    hass, integration, peripheral, short_confirmation, unit
):
    notification_only(peripheral, REGISTER2_UUID)
    raw_unit = bytes(2) if unit == "C" else bytes.fromhex("0002")
    peripheral.values[REGISTER2_UUID] = raw_unit
    await connect_manager(integration)
    assert integration.state.temperature_unit is None
    registry = er.async_get(hass)
    select_id = registry.async_get_entity_id(
        "select", DOMAIN, "volcano_temperature_unit_AA:BB:CC:DD:EE:FF"
    )
    target_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    await asyncio.wait_for(
        hass.services.async_call(
            "select", "select_option", {"entity_id": select_id, "option": f"°{unit}"}, blocking=True
        ),
        1,
    )
    peripheral.write_gatt_char.assert_awaited_once()
    assert peripheral.write_gatt_char.await_args.kwargs["response"] is True
    assert peripheral.values[REGISTER2_UUID] == raw_unit
    async with integration._io_lock:
        await integration._read_temperature_unit()
    assert hass.states.get(select_id).state == f"°{unit}"
    assert hass.states.get(target_id).attributes["device_temperature_unit"] == unit
    assert hass.states.get(target_id).attributes["temperature_unit_fallback"] is None
    # A real report overrides the acknowledged command, including after polling.
    opposite = "F" if unit == "C" else "C"
    peripheral.notification_callbacks[REGISTER2_UUID](
        None, bytes.fromhex("0002") if opposite == "F" else bytes(2)
    )
    async with integration._io_lock:
        await integration._read_temperature_unit()
    assert hass.states.get(select_id).state == f"°{opposite}"
    await integration.stop()
    await connect_manager(integration)
    assert integration.state.temperature_unit is None
    assert integration.state.temperature_unit_fallback == "C"


async def test_acknowledged_unit_is_discarded_on_reconnect_without_any_notification(
    manager, peripheral, short_confirmation
):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(manager)
    await manager.set_temperature_unit("F")
    assert manager.state.temperature_unit == "F"
    await manager.stop()
    await connect_manager(manager)
    assert manager.state.temperature_unit is None
    assert manager.state.temperature_unit_fallback == "C"


@pytest.mark.parametrize(
    "failure", ["no_response", "opposite_notification", "malformed", "write_error"]
)
async def test_unreported_unit_does_not_accept_unacknowledged_or_contradictory_writes(
    manager, peripheral, short_confirmation, failure
):
    notification_only(peripheral, REGISTER2_UUID)
    if failure == "no_response":
        set_properties(peripheral, REGISTER2_UUID, ["notify", "write-without-response"])
    await connect_manager(manager)

    async def write(characteristic, data, **kwargs):
        if failure == "write_error":
            raise BleakError("Write refused")
        await peripheral.write(characteristic, data, **kwargs)
        if failure in ("opposite_notification", "malformed"):
            peripheral.notification_callbacks[REGISTER2_UUID](
                None, bytes(2) if failure == "opposite_notification" else b"\x00"
            )

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError):
        await asyncio.wait_for(manager.set_temperature_unit("F"), 1)
    assert manager.state.temperature_unit != "F"


@pytest.mark.parametrize("properties", [None, ["write"], ["notify", "write"], ["read", "write"]])
async def test_unit_selector_availability_follows_device_capabilities(
    hass, integration, peripheral, properties
):
    original = peripheral.services.get_characteristic
    set_properties(peripheral, REGISTER2_UUID, properties)
    await connect_manager(integration)
    select_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, "volcano_temperature_unit_AA:BB:CC:DD:EE:FF"
    )
    available = properties is not None and ("notify" in properties or "read" in properties)
    assert (hass.states.get(select_id).state != "unavailable") == available
    if not available:
        # HA ignores unavailable entities before their command handler is called.
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select_id, "option": "°F"}, blocking=True
        )
        peripheral.write_gatt_char.assert_not_awaited()
    await integration.stop()
    assert hass.states.get(select_id).state == "unavailable"
    peripheral.services.get_characteristic = original
    await connect_manager(integration)
    assert hass.states.get(select_id).state == "°C"
