"""Recover missing GATT services and route actions without deprecated registry reads."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from bleak.exc import BleakCharacteristicNotFoundError
from bleak_retry_connector import BleakClientWithServiceCache
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

from custom_components.volcano_integration.const import (
    DOMAIN,
    REGISTER2_UUID,
    UUID_HEATER_SETPOINT,
    UUID_PUMP_NOTIFICATIONS,
    UUID_TEMP,
)

from .conftest import connect_manager


async def test_targeted_actions_do_not_read_deprecated_device_entries(hass, entry, integration):
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    guard = (
        patch.object(
            dr.DeviceEntry,
            "config_entries",
            new_callable=PropertyMock,
            side_effect=AssertionError("Deprecated config_entries read"),
        )
        if hasattr(device, "config_entry_id")
        else nullcontext()
    )
    with guard:
        for service in ("connect", "heat_off", "disconnect"):
            await hass.services.async_call(DOMAIN, service, {"device_id": device.id}, blocking=True)


@pytest.mark.parametrize("missing", [UUID_TEMP, UUID_PUMP_NOTIFICATIONS])
async def test_missing_required_characteristic_clears_cache_then_reconnects(
    manager, peripheral, ble, monkeypatch, missing
):
    cached = True
    original = peripheral.characteristic
    peripheral.services.get_characteristic = lambda uuid: (
        None if cached and uuid == missing else original(uuid)
    )

    async def clear_cache():
        nonlocal cached
        assert not manager.connected
        peripheral.read_gatt_char.assert_not_awaited()
        cached = False
        return True

    peripheral.clear_cache = AsyncMock(side_effect=clear_cache)
    monkeypatch.setattr(manager, "_wait_retry", AsyncMock())
    await connect_manager(manager)
    assert manager.connected
    assert manager.state.current_temperature == 170
    peripheral.clear_cache.assert_awaited_once()
    peripheral.disconnect.assert_awaited_once()
    assert ble.await_count == 2
    assert ble.call_args_list[0].args[0] is BleakClientWithServiceCache
    assert ble.call_args_list[0].kwargs["use_services_cache"] is True
    assert ble.call_args_list[1].kwargs["use_services_cache"] is False


async def test_unit_change_followed_by_lost_services_recovers_in_fahrenheit(
    manager, peripheral, ble, monkeypatch
):
    await connect_manager(manager)
    await manager.set_temperature_unit("F")
    assert peripheral.values[REGISTER2_UUID] == bytes.fromhex("0002")
    original = peripheral.read_gatt_char.side_effect
    cached = True

    async def stale_read(uuid):
        if cached and uuid == UUID_TEMP:
            raise BleakCharacteristicNotFoundError(uuid)
        return await original(uuid)

    async def clear_cache():
        nonlocal cached
        cached = False
        return True

    peripheral.read_gatt_char.side_effect = stale_read
    peripheral.clear_cache = AsyncMock(side_effect=clear_cache)
    monkeypatch.setattr(manager, "_wait_retry", AsyncMock())
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.TEMP_POLL_INTERVAL", 0.001
    )
    # Wake the existing poll immediately; the missing characteristic appears on reconnect.
    peripheral.drop()
    await manager.wait_until_connected(timeout=2)
    assert manager.state.temperature_unit == "F"
    assert ble.await_count == 3
    peripheral.clear_cache.assert_awaited_once()
    await manager.set_heater_temperature(350, unit="F")
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1767).to_bytes(4, "little")


@pytest.mark.parametrize("cache_error", [TimeoutError(), OSError("Adapter disappeared")])
async def test_cache_clear_failure_keeps_retry_worker_alive(
    manager, peripheral, ble, monkeypatch, cache_error
):
    original = peripheral.read_gatt_char.side_effect
    first = True

    async def stale_read(uuid):
        nonlocal first
        if first and uuid == UUID_TEMP:
            first = False
            raise BleakCharacteristicNotFoundError(uuid)
        return await original(uuid)

    peripheral.read_gatt_char.side_effect = stale_read
    peripheral.clear_cache = AsyncMock(side_effect=cache_error)
    monkeypatch.setattr(manager, "_wait_retry", AsyncMock())
    await connect_manager(manager)
    assert manager.connected
    assert ble.call_args.kwargs["use_services_cache"] is False


async def test_stop_cancels_cache_clear_and_releases_connection(manager, peripheral):
    started = asyncio.Event()

    async def clear_cache():
        started.set()
        await asyncio.Event().wait()

    peripheral.read_gatt_char.side_effect = BleakCharacteristicNotFoundError(UUID_TEMP)
    peripheral.clear_cache = AsyncMock(side_effect=clear_cache)
    await manager.async_user_connect()
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(manager.stop(), 1)
    assert not manager.connection_requested
    assert manager._run_task is None
    peripheral.disconnect.assert_awaited_once()


async def test_permanently_missing_characteristic_keeps_backoff_and_cannot_become_ready(
    manager, peripheral, monkeypatch
):
    retrying = asyncio.Event()
    peripheral.services.get_characteristic = lambda uuid: None
    peripheral.clear_cache = AsyncMock(return_value=True)

    async def wait_retry(delay):
        assert delay == 5
        retrying.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "_wait_retry", wait_retry)
    await manager.async_user_connect()
    await asyncio.wait_for(retrying.wait(), 1)
    assert not manager.connected
    assert manager.connection_requested
    with pytest.raises(HomeAssistantError, match="Timed out"):
        await manager.wait_until_connected(timeout=0.01)
    peripheral.read_gatt_char.assert_not_awaited()
    peripheral.clear_cache.assert_awaited_once()
