"""Regression tests for connection lifecycle, command failures and workflow waits."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError

from custom_components.volcano_integration.const import (
    BT_STATUS_CONNECTING,
    REGISTER3_UUID,
    UUID_AUTO_SHUT_OFF_SETTING,
    UUID_FIRMWARE_VERSION,
    UUID_HEATER_SETPOINT,
    UUID_HOURS_OF_OPERATION,
    UUID_LED_BRIGHTNESS,
    UUID_MINUTES_OF_OPERATION,
    UUID_TEMP,
)

from .conftest import connect_manager, drain


async def test_no_duplicate_workers(manager, ble):
    await asyncio.gather(manager.async_user_connect(), manager.async_user_connect())
    await manager.wait_until_connected(timeout=2)
    assert ble.await_count == 1
    assert manager.state.target_temperature == 170
    assert manager.state.pump_state is False


async def test_disconnect_during_connection(manager, ble, peripheral):
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    ble.side_effect = blocked
    await manager.async_user_connect()
    await started.wait()
    await asyncio.wait_for(manager.async_user_disconnect(), 1)
    assert not manager.connection_requested
    assert manager._run_task is None
    await drain()
    assert ble.await_count == 1


async def test_capped_backoff_and_stop_while_unavailable(manager, monkeypatch, caplog):
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.async_ble_device_from_address",
        lambda *a, **k: None,
    )
    delays = []
    enough_attempts = asyncio.Event()

    async def wait_retry(delay):
        delays.append(delay)
        if len(delays) == 8:
            enough_attempts.set()
            await asyncio.Event().wait()
        await asyncio.sleep(0)

    monkeypatch.setattr(manager, "_wait_retry", wait_retry)
    await manager.async_user_connect()
    await enough_attempts.wait()
    await asyncio.wait_for(manager.stop(), 1)
    assert delays == [5, 10, 20, 40, 80, 160, 300, 300]
    assert not manager.connection_requested
    assert not [r for r in caplog.records if r.levelno >= 30]


async def test_not_ready_until_notifications_are_subscribed(manager, peripheral):
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked(*args):
        started.set()
        await release.wait()

    peripheral.start_notify.side_effect = blocked
    await manager.async_user_connect()
    await started.wait()
    assert manager.state.bt_status == BT_STATUS_CONNECTING
    assert not manager.connected
    release.set()
    await manager.wait_until_connected(timeout=2)
    assert manager.connected


async def test_initialization_failure_releases_client(manager, peripheral):
    peripheral.start_notify.side_effect = BleakError("Subscription failed")
    await manager.async_user_connect()
    await drain()
    assert not manager.connected
    await manager.stop()
    peripheral.disconnect.assert_awaited_once()


async def test_stop_during_disconnect_still_releases_client(manager, peripheral):
    await connect_manager(manager)
    started, release = asyncio.Event(), asyncio.Event()

    async def blocked_disconnect():
        started.set()
        await release.wait()
        peripheral.is_connected = False

    peripheral.disconnect.side_effect = blocked_disconnect
    peripheral.drop()
    await started.wait()
    stop_task = asyncio.create_task(manager.stop())
    await drain()
    release.set()
    await asyncio.wait_for(stop_task, 1)
    assert not peripheral.is_connected
    assert manager._client is None


@pytest.mark.parametrize("error", [BleakError("Lost link"), EOFError("Transport closed")])
async def test_failed_write_raises_and_clears_stale_readings(manager, peripheral, error):
    await connect_manager(manager)
    peripheral.write_gatt_char.side_effect = error
    with pytest.raises(HomeAssistantError, match="command failed"):
        await manager.set_heater_temperature(190)
    assert manager.state.current_temperature is None
    assert manager.state.target_temperature is None


async def test_commands_when_disconnected_raise(manager):
    with pytest.raises(HomeAssistantError, match="not connected"):
        await manager.set_heater_temperature(190)


async def test_wait_requires_a_new_sample(manager, peripheral):
    await connect_manager(manager)
    await manager.set_heater_temperature(170)
    sequence = manager._temperature_sequence
    waiter = asyncio.create_task(
        manager.wait_for_temperature(170, manager._generation, sequence, timeout=1)
    )
    await drain()
    assert not waiter.done()
    async with manager._io_lock:
        await manager._read_temperature()
    await waiter


@pytest.mark.parametrize("late_response", [False, True])
async def test_wait_aborts_when_connection_drops(manager, peripheral, late_response):
    await connect_manager(manager)
    await manager.set_heater_temperature(200)
    waiter = asyncio.create_task(
        manager.wait_for_temperature(200, manager._generation, manager._temperature_sequence)
    )
    await drain()
    if late_response:

        async def read_after_drop(uuid):
            peripheral.drop()
            return (2000).to_bytes(2, "little")

        peripheral.read_gatt_char.side_effect = read_after_drop
        async with manager._io_lock:
            await manager._read_temperature()
    else:
        peripheral.drop()
    with pytest.raises(HomeAssistantError, match="disconnected"):
        await waiter


async def test_wait_aborts_when_another_command_changes_target(manager):
    await connect_manager(manager)
    await manager.set_heater_temperature(200)
    waiter = asyncio.create_task(
        manager.wait_for_temperature(200, manager._generation, manager._temperature_sequence)
    )
    await drain()
    await manager.set_heater_temperature(190)
    with pytest.raises(HomeAssistantError, match="target changed"):
        await waiter


@pytest.mark.parametrize("readback_offset", [0, 1])
async def test_wait_uses_whole_degree_write_and_detects_real_readback_change(
    manager, peripheral, readback_offset
):
    """Model firmware that stores whole degrees instead of echoing the write."""
    await connect_manager(manager)
    wrote = asyncio.Event()
    original_write = peripheral.write_gatt_char.side_effect

    async def firmware_write(characteristic, data, **kwargs):
        if characteristic.uuid == UUID_HEATER_SETPOINT:
            raw = int.from_bytes(data, "little")
            stored = (raw + 5) // 10
            peripheral.values[UUID_HEATER_SETPOINT] = (stored * 10).to_bytes(2, "little")
            wrote.set()
        else:
            await original_write(characteristic, data, **kwargs)

    peripheral.write_gatt_char.side_effect = firmware_write
    waiter = asyncio.create_task(manager.set_heater_temperature(170.6, wait=True))
    try:
        await wrote.wait()
        await drain()
        assert manager.state.target_temperature == 171
        peripheral.values[UUID_HEATER_SETPOINT] = ((171 + readback_offset) * 10).to_bytes(
            2, "little"
        )
        async with manager._io_lock:
            await manager._read_setpoint()
        await drain()
        if readback_offset:
            with pytest.raises(HomeAssistantError, match="target changed"):
                await waiter
            return
        assert not waiter.done()
        # Still wait for a fresh sample at the rounded target, not just 170.6.
        peripheral.values[UUID_TEMP] = (1709).to_bytes(2, "little")
        async with manager._io_lock:
            await manager._read_temperature()
        await drain()
        assert not waiter.done()
        peripheral.values[UUID_TEMP] = (1710).to_bytes(2, "little")
        async with manager._io_lock:
            await manager._read_temperature()
        await asyncio.wait_for(waiter, 1)
    finally:
        if not waiter.done():
            waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


async def test_timeout_is_an_action_failure(manager):
    await connect_manager(manager)
    await manager.set_heater_temperature(200)
    with pytest.raises(HomeAssistantError, match="Timed out"):
        await manager.wait_for_temperature(
            200, manager._generation, manager._temperature_sequence, timeout=0.01
        )


async def test_connect_timeout_is_an_action_failure(manager, monkeypatch):
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.async_ble_device_from_address",
        lambda *a, **k: None,
    )
    await manager.async_user_connect()
    with pytest.raises(HomeAssistantError, match="Timed out"):
        await manager.wait_until_connected(timeout=0.01)


async def test_manual_setpoint_read_updates_shared_state(manager, peripheral):
    await connect_manager(manager)
    peripheral.values[UUID_HEATER_SETPOINT] = (1900).to_bytes(2, "little")
    async with manager._io_lock:
        await manager._read_setpoint()
    assert manager.state.target_temperature == 190


async def test_old_client_callbacks_are_ignored(manager, peripheral):
    await connect_manager(manager)
    manager._on_disconnect(object())
    manager._notification(object(), bytes.fromhex("0030"))
    assert manager.connected
    assert manager.state.pump_state is False


async def test_malformed_notification_becomes_unknown(manager, peripheral):
    await connect_manager(manager)
    peripheral.notification_callback(None, b"\x23")
    assert manager.state.heat_state is None
    assert manager.state.pump_state is None
    assert manager.state.raw_status == "23"


async def test_read_and_write_are_serialized(manager, peripheral):
    await connect_manager(manager)
    started, release = asyncio.Event(), asyncio.Event()
    original_read = peripheral.read_gatt_char.side_effect

    async def blocked_read(uuid):
        if uuid == UUID_TEMP:
            started.set()
            await release.wait()
        return await original_read(uuid)

    peripheral.read_gatt_char.side_effect = blocked_read

    async def poll():
        async with manager._io_lock:
            await manager._read_temperature()

    poll_task = asyncio.create_task(poll())
    await started.wait()
    command = asyncio.create_task(manager.set_heater_temperature(190))
    await drain()
    peripheral.write_gatt_char.assert_not_awaited()
    release.set()
    await asyncio.gather(poll_task, command)
    assert manager.state.target_temperature == 190


async def test_vibration_preserves_other_bits_and_reads_confirmation(manager, peripheral):
    await connect_manager(manager)
    peripheral.values[REGISTER3_UUID] = bytes.fromhex("aa55")
    await manager.set_vibration(True)
    assert peripheral.values[REGISTER3_UUID] == bytes.fromhex("aa51")
    assert manager.state.vibration is True
    peripheral.write_gatt_char.side_effect = AsyncMock()
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await manager.set_vibration(False)
    assert manager.state.vibration is True


async def test_reconnect_resolves_a_new_proxy(manager, peripheral, ble, monkeypatch):
    first_proxy_device, second_proxy_device = object(), object()
    lookup = Mock(side_effect=[first_proxy_device, second_proxy_device])
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.async_ble_device_from_address",
        lookup,
    )
    monkeypatch.setattr(manager, "_wait_retry", AsyncMock())
    await connect_manager(manager)
    assert ble.call_args.args[1] is first_proxy_device
    peripheral.drop()
    await manager.wait_until_connected(timeout=2)
    assert ble.call_args.args[1] is second_proxy_device
    assert lookup.call_args.kwargs == {"connectable": True}


async def test_transport_eof_during_poll_retries(manager, peripheral, monkeypatch):
    await connect_manager(manager)
    retry_started = asyncio.Event()

    async def wait_retry(delay):
        retry_started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "_wait_retry", wait_retry)
    peripheral.read_gatt_char.side_effect = EOFError("Bluetooth transport closed")
    await asyncio.wait_for(retry_started.wait(), 2)
    assert manager.connection_requested
    assert not manager.connected
    assert manager.state.current_temperature is None
    peripheral.disconnect.assert_awaited_once()


async def test_settings_and_counters_refresh_without_reconnecting(manager, peripheral, monkeypatch):
    module = "custom_components.volcano_integration.bluetooth_coordinator"
    monkeypatch.setattr(f"{module}.TEMP_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(f"{module}.SETTINGS_POLL_INTERVAL", 0.01, raising=False)
    await connect_manager(manager)
    peripheral.values.update(
        {
            UUID_LED_BRIGHTNESS: (55).to_bytes(2, "little"),
            UUID_AUTO_SHUT_OFF_SETTING: (3600).to_bytes(2, "little"),
            UUID_HOURS_OF_OPERATION: (12).to_bytes(2, "little"),
            UUID_MINUTES_OF_OPERATION: (34).to_bytes(2, "little"),
            REGISTER3_UUID: bytes.fromhex("0004"),
        }
    )
    refreshed = asyncio.Event()

    def on_update():
        if manager.state.minutes_of_operation == 34:
            refreshed.set()

    unsubscribe = manager.async_add_listener(on_update)
    try:
        await asyncio.wait_for(refreshed.wait(), 1)
    finally:
        unsubscribe()
    assert manager.state.led_brightness == 55
    assert manager.state.auto_shut_off_setting == 60
    assert manager.state.hours_of_operation == 12
    assert manager.state.vibration is False
    assert manager._generation == 1
    assert (
        sum(
            call.args == (UUID_FIRMWARE_VERSION,)
            for call in peripheral.read_gatt_char.call_args_list
        )
        == 1
    )
    peripheral.drop()
    assert manager.state.hours_of_operation is None
    assert manager.state.minutes_of_operation is None
