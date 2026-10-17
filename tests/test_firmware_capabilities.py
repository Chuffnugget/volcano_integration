"""Firmware variants with notification-only status and unavailable display units."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_integration.bluetooth_coordinator import METADATA_READS
from custom_components.volcano_integration.const import (
    DOMAIN,
    REGISTER2_UUID,
    UUID_FIRMWARE_VERSION,
    UUID_HEAT_OFF,
    UUID_HEAT_ON,
    UUID_HEATER_SETPOINT,
    UUID_PUMP_NOTIFICATIONS,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
)

from .conftest import connect_manager, drain


def notification_only(peripheral, uuid):
    original = peripheral.services.get_characteristic
    peripheral.services.get_characteristic = lambda requested: (
        SimpleNamespace(uuid=uuid, properties=["notify", "write"])
        if requested == uuid
        else original(requested)
    )


@pytest.mark.parametrize("when", ["during_write", "after_write"])
async def test_disconnect_accepts_fresh_notification_without_read_support(
    manager, peripheral, when
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    peripheral.values[UUID_PUMP_NOTIFICATIONS] = bytes.fromhex("2020")
    await connect_manager(manager)
    peripheral.notification_callback(None, bytes.fromhex("2020"))
    written = asyncio.Event()

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == UUID_PUMP_OFF:
            written.set()
            if when == "during_write":
                peripheral.notification_callback(None, bytes(2))

    peripheral.write_gatt_char.side_effect = write
    task = asyncio.create_task(manager.async_user_disconnect())
    try:
        await asyncio.wait_for(written.wait(), 1)
        if when == "after_write":
            await drain()
            assert not task.done()
            peripheral.disconnect.assert_not_awaited()
            peripheral.notification_callback(None, bytes(2))
        await asyncio.wait_for(task, 1)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not manager.connection_requested
    peripheral.disconnect.assert_awaited_once()
    assert UUID_PUMP_NOTIFICATIONS not in [
        call.args[0] for call in peripheral.read_gatt_char.await_args_list
    ]


@pytest.mark.parametrize("fresh_status", [b"\x00", bytes.fromhex("2020")])
async def test_notify_only_disconnect_rejects_new_unknown_or_on_status(
    manager, peripheral, monkeypatch, fresh_status
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)
    peripheral.notification_callback(None, bytes(2))

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == UUID_PUMP_OFF:
            peripheral.notification_callback(None, fresh_status)

    peripheral.write_gatt_char.side_effect = write
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.02
    )
    with pytest.raises(HomeAssistantError, match="did not confirm.*still connected"):
        await asyncio.wait_for(manager.async_user_disconnect(), 1)
    assert manager.connected
    peripheral.disconnect.assert_not_awaited()


async def test_notify_only_disconnect_reports_link_loss_while_waiting(manager, peripheral):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)
    written = asyncio.Event()

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == UUID_PUMP_OFF:
            written.set()

    peripheral.write_gatt_char.side_effect = write
    task = asyncio.create_task(manager.async_user_disconnect())
    try:
        await asyncio.wait_for(written.wait(), 1)
        peripheral.drop()
        with pytest.raises(HomeAssistantError, match="Bluetooth was lost"):
            await asyncio.wait_for(task, 1)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not manager.connection_requested


async def test_unit_notifications_survive_polling_on_notify_only_register(manager, peripheral):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(manager)
    assert manager.supports_temperature_unit
    assert manager.state.temperature_unit is None
    callback = peripheral.notification_callbacks[REGISTER2_UUID]
    callback(None, bytes.fromhex("0002"))
    async with manager._io_lock:
        await manager._read_temperature_unit()
    assert manager.state.temperature_unit == "F"
    callback(None, bytes(2))
    async with manager._io_lock:
        await manager._read_temperature_unit()
    assert manager.state.temperature_unit == "C"
    await manager.stop()
    assert manager.state.temperature_unit is None


@pytest.mark.parametrize("properties", [None, ["write"], ["notify", "write"]])
@pytest.mark.parametrize("ha_unit", ["°C", "°F"])
async def test_number_falls_back_to_wire_celsius_without_claiming_device_unit(
    hass, integration, peripheral, properties, ha_unit
):
    original = peripheral.characteristic
    peripheral.services.get_characteristic = lambda uuid: (
        (None if properties is None else SimpleNamespace(uuid=uuid, properties=properties))
        if uuid == REGISTER2_UUID
        else original(uuid)
    )
    target_id = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    er.async_get(hass).async_update_entity_options(
        target_id, "number", {"unit_of_measurement": ha_unit}
    )
    await drain()
    await connect_manager(integration)
    assert integration.supports_temperature_unit == (properties == ["notify", "write"])
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": target_id, "value": 180 if ha_unit == "°C" else 356},
        blocking=True,
    )
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1800).to_bytes(4, "little")
    assert hass.states.get(target_id).attributes["device_temperature_unit"] is None
    assert hass.states.get(target_id).attributes["temperature_unit_fallback"] == "C"


async def test_device_fahrenheit_rounding_and_action_celsius_contract(
    hass, integration, peripheral
):
    peripheral.values[REGISTER2_UUID] = bytes.fromhex("0002")
    await connect_manager(integration)
    target_id = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": target_id, "value": 177}, blocking=True
    )
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1772).to_bytes(4, "little")
    await hass.services.async_call(
        DOMAIN, "set_temperature", {"temperature": 177, "wait_until_reached": False}, blocking=True
    )
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1770).to_bytes(4, "little")


async def test_real_registry_lookup_uses_this_config_entry(hass, entry, integration, peripheral):
    await connect_manager(integration)
    registry = dr.async_get(hass)
    owner, method = (
        (registry, "async_get_device_by_identifier")
        if hasattr(registry, "async_get_device_by_identifier")
        else (dr, "async_entries_for_config_entry")
    )
    peripheral.values[UUID_FIRMWARE_VERSION] = b"2.1"
    with patch.object(owner, method, wraps=getattr(owner, method)) as lookup:
        async with integration._io_lock:
            await integration._read_fields(METADATA_READS)
        if owner is registry:
            lookup.assert_called_once_with((DOMAIN, entry.data["bt_address"]), entry.entry_id)
        else:
            lookup.assert_called_once_with(registry, entry.entry_id)
    device = dr.async_entries_for_config_entry(registry, entry.entry_id)[0]
    assert device.sw_version == "2.1"


async def test_notify_only_already_off_disconnect_needs_no_repeated_notification(
    manager, peripheral
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)
    peripheral.notification_callback(None, bytes(2))
    # Successful off writes do not generate any notifications on this firmware.
    await asyncio.wait_for(manager.async_user_disconnect(), 1)
    assert [call.args[0].uuid for call in peripheral.write_gatt_char.await_args_list] == [
        UUID_HEAT_OFF,
        UUID_PUMP_OFF,
    ]
    peripheral.disconnect.assert_awaited_once()
    assert not manager.connection_requested


@pytest.mark.parametrize("reason", ["cached_state", "previous_connection", "heat_on", "air_on"])
async def test_notify_only_disconnect_cannot_reuse_unconfirmed_or_obsolete_off(
    manager, peripheral, monkeypatch, reason
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    original = peripheral.services.get_characteristic
    # Without acknowledged writes, only a valid current-session status can allow release.
    peripheral.services.get_characteristic = lambda uuid: (
        SimpleNamespace(uuid=uuid, properties=["write-without-response"])
        if uuid in (UUID_HEAT_OFF, UUID_PUMP_OFF)
        else original(uuid)
    )
    await connect_manager(manager)
    if reason == "cached_state":
        manager._publish(heat_state=False, pump_state=False)
    else:
        peripheral.notification_callback(None, bytes(2))
        if reason == "previous_connection":
            await manager.stop()
            await connect_manager(manager)
            peripheral.disconnect.reset_mock()
        else:
            await manager.write_gatt_command(UUID_HEAT_ON if reason == "heat_on" else UUID_PUMP_ON)
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.02
    )
    with pytest.raises(HomeAssistantError, match="did not confirm.*still connected"):
        await asyncio.wait_for(manager.async_user_disconnect(), 1)
    peripheral.disconnect.assert_not_awaited()
    assert manager.connected


@pytest.mark.parametrize("failed_uuid", [UUID_HEAT_OFF, UUID_PUMP_OFF])
async def test_notify_only_already_off_still_requires_both_successful_writes(
    manager, peripheral, failed_uuid
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)
    peripheral.notification_callback(None, bytes(2))

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == failed_uuid:
            raise BleakError("Write refused")
        await peripheral.write(characteristic, data, **kwargs)

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError, match="Could not turn off.*still connected"):
        await manager.async_user_disconnect()
    assert peripheral.write_gatt_char.await_count == 2
    peripheral.disconnect.assert_not_awaited()


async def test_notify_only_unit_fallback_replaced_by_device_and_reset_on_reconnect(
    hass, integration, peripheral
):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(integration)
    registry = er.async_get(hass)
    target_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    current_id = registry.async_get_entity_id(
        "sensor", DOMAIN, "volcano_current_temperature_AA:BB:CC:DD:EE:FF"
    )
    for entity_id in (current_id, target_id):
        assert hass.states.get(entity_id).attributes["temperature_unit_fallback"] == "C"
        assert hass.states.get(entity_id).attributes["device_temperature_unit"] is None
    peripheral.notification_callbacks[REGISTER2_UUID](None, bytes.fromhex("0002"))
    for entity_id in (current_id, target_id):
        assert hass.states.get(entity_id).attributes["temperature_unit_fallback"] is None
        assert hass.states.get(entity_id).attributes["device_temperature_unit"] == "F"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": target_id, "value": 177}, blocking=True
    )
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1772).to_bytes(4, "little")
    await integration.stop()
    assert integration.state.temperature_unit_fallback is None
    await connect_manager(integration)
    assert integration.state.temperature_unit is None
    assert integration.state.temperature_unit_fallback == "C"


async def test_malformed_unit_notification_does_not_restore_fallback_during_polling(
    hass, integration, peripheral
):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(integration)
    peripheral.notification_callbacks[REGISTER2_UUID](None, b"\x02")
    async with integration._io_lock:
        await integration._read_temperature_unit()
    target_id = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    assert hass.states.get(target_id).attributes["temperature_unit_fallback"] is None
    with pytest.raises(HomeAssistantError, match="unit is unknown"):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": target_id, "value": 180}, blocking=True
        )
    peripheral.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("uuid", [UUID_HEAT_ON, UUID_PUMP_ON])
async def test_off_notification_during_on_command_cannot_confirm_later_disconnect(
    manager, peripheral, monkeypatch, uuid
):
    notification_only(peripheral, UUID_PUMP_NOTIFICATIONS)
    await connect_manager(manager)

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == uuid:
            peripheral.notification_callback(None, bytes(2))
        await peripheral.write(characteristic, data, **kwargs)

    peripheral.write_gatt_char.side_effect = write
    await manager.write_gatt_command(uuid)
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.02
    )
    with pytest.raises(HomeAssistantError, match="did not confirm.*still connected"):
        await asyncio.wait_for(manager.async_user_disconnect(), 1)
    peripheral.disconnect.assert_not_awaited()


@pytest.mark.parametrize("unit", ["C", "F"])
@pytest.mark.parametrize("initial_known", [False, True])
@pytest.mark.parametrize("notify_when", ["during_write", "after_write"])
async def test_notify_only_unit_selector_waits_for_confirmation(
    hass, integration, peripheral, unit, initial_known, notify_when
):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(integration)
    notify = peripheral.notification_callbacks[REGISTER2_UUID]
    if initial_known:
        notify(None, bytes.fromhex("0002") if unit == "C" else bytes(2))
    registry = er.async_get(hass)
    select_id = registry.async_get_entity_id(
        "select", DOMAIN, "volcano_temperature_unit_AA:BB:CC:DD:EE:FF"
    )
    target_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    written = asyncio.Event()
    response = bytes(2) if unit == "C" else bytes.fromhex("0002")

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == REGISTER2_UUID:
            if notify_when == "during_write":
                notify(None, response)
            written.set()

    peripheral.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        hass.services.async_call(
            "select", "select_option", {"entity_id": select_id, "option": f"°{unit}"}, blocking=True
        )
    )
    try:
        await asyncio.wait_for(written.wait(), 1)
        if notify_when == "after_write":
            await drain()
            assert not task.done()
            # A callback from a different Bluetooth client cannot confirm this write.
            integration._unit_notification(object(), response)
            await drain()
            assert not task.done()
            notify(None, response)
        await asyncio.wait_for(task, 1)
        assert integration.connected
        assert hass.states.get(select_id).state == f"°{unit}"
        assert hass.states.get(target_id).attributes["device_temperature_unit"] == unit
        assert hass.states.get(target_id).attributes["temperature_unit_fallback"] is None
        assert REGISTER2_UUID not in [
            call.args[0] for call in peripheral.read_gatt_char.await_args_list
        ]
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("unit", ["C", "F"])
async def test_notify_only_unit_already_selected_needs_no_repeat_notification(
    manager, peripheral, unit
):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(manager)
    peripheral.notification_callbacks[REGISTER2_UUID](
        None, bytes(2) if unit == "C" else bytes.fromhex("0002")
    )
    await asyncio.wait_for(manager.set_temperature_unit(unit), 1)
    peripheral.write_gatt_char.assert_awaited_once()
    assert manager.state.temperature_unit == unit
    assert manager.connected


@pytest.mark.parametrize("response", [None, bytes(2), b"\x02"])
async def test_notify_only_unit_timeout_keeps_connection_and_releases_commands(
    manager, peripheral, monkeypatch, response
):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(manager)
    peripheral.notification_callbacks[REGISTER2_UUID](None, bytes(2))
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.02
    )

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == REGISTER2_UUID and response is not None:
            peripheral.notification_callbacks[REGISTER2_UUID](None, response)

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError, match="did not confirm the temperature unit"):
        await asyncio.wait_for(manager.set_temperature_unit("F"), 1)
    assert manager.connected
    assert manager.state.temperature_unit != "F"
    peripheral.disconnect.assert_not_awaited()
    await asyncio.wait_for(manager.set_led_brightness(45), 1)
    assert manager.state.led_brightness == 45


@pytest.mark.parametrize("interruption", ["link_loss", "stop", "shutdown", "cancel"])
async def test_notify_only_unit_wait_can_be_interrupted(manager, peripheral, interruption):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(manager)
    written = asyncio.Event()

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == REGISTER2_UUID:
            written.set()

    peripheral.write_gatt_char.side_effect = write
    task = asyncio.create_task(manager.set_temperature_unit("F"))
    try:
        await asyncio.wait_for(written.wait(), 1)
        await drain()
        assert not task.done()
        if interruption == "link_loss":
            peripheral.drop()
        elif interruption == "stop":
            await asyncio.wait_for(manager.stop(), 1)
        elif interruption == "shutdown":
            await asyncio.wait_for(manager.async_shutdown(), 1)
        else:
            task.cancel()
        expected = asyncio.CancelledError if interruption == "cancel" else HomeAssistantError
        with pytest.raises(expected):
            await asyncio.wait_for(task, 1)
        if interruption == "cancel":
            assert manager.connected
            await asyncio.wait_for(manager.set_led_brightness(45), 1)
        else:
            assert not manager.connected
            assert manager.state.temperature_unit is None
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_notify_only_unit_changes_wait_their_turn(manager, peripheral):
    notification_only(peripheral, REGISTER2_UUID)
    await connect_manager(manager)
    written = asyncio.Queue()

    async def write(characteristic, data, **kwargs):
        await peripheral.write(characteristic, data, **kwargs)
        if characteristic.uuid == REGISTER2_UUID:
            written.put_nowait(bytes(peripheral.values[REGISTER2_UUID]))

    peripheral.write_gatt_char.side_effect = write
    first = asyncio.create_task(manager.set_temperature_unit("F"))
    second = None
    try:
        assert await asyncio.wait_for(written.get(), 1) == bytes.fromhex("0002")
        second = asyncio.create_task(manager.set_temperature_unit("C"))
        await drain()
        assert written.empty()
        assert not first.done() and not second.done()
        peripheral.notification_callbacks[REGISTER2_UUID](None, bytes.fromhex("0002"))
        await asyncio.wait_for(first, 1)
        assert await asyncio.wait_for(written.get(), 1) == bytes(2)
        assert not second.done()
        peripheral.notification_callbacks[REGISTER2_UUID](None, bytes(2))
        await asyncio.wait_for(second, 1)
        assert manager.state.temperature_unit == "C"
    finally:
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
