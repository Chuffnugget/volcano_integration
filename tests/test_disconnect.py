"""A deliberate disconnect must stop both outputs before releasing Bluetooth."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_integration.const import (
    DOMAIN,
    UUID_HEAT_OFF,
    UUID_PUMP_NOTIFICATIONS,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
)

from .conftest import connect_manager, drain


async def test_outputs_are_written_and_confirmed_before_disconnect(manager, peripheral):
    peripheral.values[UUID_PUMP_NOTIFICATIONS] = bytes.fromhex("2020")
    await connect_manager(manager)
    events = []

    async def write(characteristic, data, **kwargs):
        events.append((characteristic.uuid, data))
        await peripheral.write(characteristic, data, **kwargs)

    async def read(uuid):
        if uuid == UUID_PUMP_NOTIFICATIONS:
            events.append("status")
        return await peripheral.read(uuid)

    async def close():
        assert peripheral.values[UUID_PUMP_NOTIFICATIONS] == bytes(2)
        events.append("disconnect")
        await peripheral.close()

    peripheral.write_gatt_char.side_effect = write
    peripheral.read_gatt_char.side_effect = read
    peripheral.disconnect.side_effect = close
    await manager.async_user_disconnect()
    assert events == [
        (UUID_HEAT_OFF, b"\x00"),
        (UUID_PUMP_OFF, b"\x00"),
        "status",
        "disconnect",
    ]
    assert not manager.connection_requested
    assert manager._run_task is None


@pytest.mark.parametrize("control", ["action", "button"])
async def test_both_ha_disconnect_controls_stop_outputs(hass, integration, peripheral, control):
    peripheral.values[UUID_PUMP_NOTIFICATIONS] = bytes.fromhex("2020")
    await connect_manager(integration)
    if control == "action":
        await hass.services.async_call(DOMAIN, "disconnect", {}, blocking=True)
    else:
        entity_id = er.async_get(hass).async_get_entity_id(
            "button", DOMAIN, "volcano_disconnect_button_AA:BB:CC:DD:EE:FF"
        )
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    assert peripheral.values[UUID_PUMP_NOTIFICATIONS] == bytes(2)
    assert not peripheral.is_connected
    assert not integration.connection_requested


@pytest.mark.parametrize("failed_uuid", [UUID_HEAT_OFF, UUID_PUMP_OFF])
async def test_failed_off_write_still_attempts_other_output_and_keeps_connection(
    manager, peripheral, failed_uuid
):
    peripheral.values[UUID_PUMP_NOTIFICATIONS] = bytes.fromhex("2020")
    await connect_manager(manager)

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == failed_uuid:
            raise BleakError("Write refused")
        await peripheral.write(characteristic, data, **kwargs)

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError, match="Could not turn off.*still connected"):
        await manager.async_user_disconnect()
    assert [call.args[0].uuid for call in peripheral.write_gatt_char.await_args_list] == [
        UUID_HEAT_OFF,
        UUID_PUMP_OFF,
    ]
    peripheral.disconnect.assert_not_awaited()
    assert manager.connected
    peripheral.write_gatt_char.side_effect = peripheral.write
    await manager.async_user_disconnect()
    assert not manager.connected


@pytest.mark.parametrize("status", [bytes.fromhex("2020"), b"\x00"])
async def test_unconfirmed_outputs_leave_bluetooth_open(manager, peripheral, monkeypatch, status):
    await connect_manager(manager)
    peripheral.values[UUID_PUMP_NOTIFICATIONS] = status
    # Neither cached OFF states nor successful writes prove the device is now off.
    manager._publish(heat_state=False, pump_state=False)
    peripheral.write_gatt_char.side_effect = AsyncMock()
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.IO_TIMEOUT", 0.02
    )
    with pytest.raises(HomeAssistantError, match="did not confirm.*still connected"):
        await asyncio.wait_for(manager.async_user_disconnect(), 1)
    peripheral.disconnect.assert_not_awaited()
    assert manager.connected


async def test_missing_status_characteristic_does_not_silently_disconnect(manager, peripheral):
    await connect_manager(manager)
    peripheral.services.get_characteristic = lambda uuid: (
        None if uuid == UUID_PUMP_NOTIFICATIONS else peripheral.characteristic(uuid)
    )
    with pytest.raises(HomeAssistantError, match="status is unavailable.*still connected"):
        await manager.async_user_disconnect()
    peripheral.disconnect.assert_not_awaited()
    assert manager.connected


async def test_new_on_notification_wins_over_stale_off_read(manager, peripheral):
    await connect_manager(manager)
    first_read, release = asyncio.Event(), asyncio.Event()

    async def read(uuid):
        if uuid != UUID_PUMP_NOTIFICATIONS:
            return await peripheral.read(uuid)
        if not first_read.is_set():
            peripheral.notification_callback(None, bytes.fromhex("2020"))
            first_read.set()
            return bytes(2)
        await release.wait()
        return bytes(2)

    peripheral.read_gatt_char.side_effect = read
    task = asyncio.create_task(manager.async_user_disconnect())
    try:
        await asyncio.wait_for(first_read.wait(), 1)
        await drain()
        assert not task.done()
        peripheral.disconnect.assert_not_awaited()
    finally:
        release.set()
        await asyncio.wait_for(task, 1)
    peripheral.disconnect.assert_awaited_once()


async def test_on_command_cannot_slip_between_off_commands_and_disconnect(manager, peripheral):
    await connect_manager(manager)
    started, release = asyncio.Event(), asyncio.Event()

    async def write(characteristic, data, **kwargs):
        if characteristic.uuid == UUID_HEAT_OFF:
            started.set()
            await release.wait()
        await peripheral.write(characteristic, data, **kwargs)

    peripheral.write_gatt_char.side_effect = write
    disconnect = asyncio.create_task(manager.async_user_disconnect())
    try:
        await asyncio.wait_for(started.wait(), 1)
        pump_on = asyncio.create_task(manager.write_gatt_command(UUID_PUMP_ON, b"\x01"))
        await drain()
        assert not pump_on.done()
    finally:
        release.set()
    await asyncio.wait_for(disconnect, 1)
    with pytest.raises(HomeAssistantError, match="not connected"):
        await pump_on
    assert [call.args[0].uuid for call in peripheral.write_gatt_char.await_args_list] == [
        UUID_HEAT_OFF,
        UUID_PUMP_OFF,
    ]


async def test_simultaneous_disconnects_only_stop_outputs_once(manager, peripheral):
    await connect_manager(manager)
    await asyncio.gather(manager.async_user_disconnect(), manager.async_user_disconnect())
    assert peripheral.write_gatt_char.await_count == 2
    peripheral.disconnect.assert_awaited_once()


async def test_link_loss_during_output_shutdown_reports_error_and_cancels_retries(
    manager, peripheral, ble
):
    await connect_manager(manager)

    async def write(*args, **kwargs):
        peripheral.drop()
        raise BleakError("Lost link")

    peripheral.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError, match="Bluetooth was lost"):
        await manager.async_user_disconnect()
    assert not manager.connection_requested
    assert manager._run_task is None
    assert manager.state.heat_state is None
    assert manager.state.pump_state is None
    await drain()
    assert ble.await_count == 1


async def test_disconnected_cancel_never_claims_to_have_turned_outputs_off(manager, peripheral):
    await manager.async_user_disconnect()
    peripheral.write_gatt_char.assert_not_awaited()
    assert manager.state.heat_state is None
    assert manager.state.pump_state is None
