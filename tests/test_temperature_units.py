"""Physical display units, bit commands and HA temperature conversion."""

import asyncio

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.volcano_integration.const import DOMAIN, REGISTER2_UUID, UUID_HEATER_SETPOINT
from custom_components.volcano_integration.protocol import (
    decode_temperature,
    decode_temperature_unit,
    encode_temperature,
    encode_temperature_unit,
)

from .conftest import connect_manager, drain


def test_official_unit_register_vectors():
    assert decode_temperature_unit(bytes.fromhex("0010")) == "C"
    assert decode_temperature_unit(bytes.fromhex("0012")) == "F"
    assert encode_temperature_unit("F") == bytes.fromhex("00020100")
    assert encode_temperature_unit("C") == bytes.fromhex("00020000")
    with pytest.raises(ValueError):
        encode_temperature_unit("K")


def test_every_whole_fahrenheit_target_survives_wire_rounding():
    previous = None
    for fahrenheit in range(104, 447):
        celsius = decode_temperature(encode_temperature(fahrenheit, "F"))
        assert round(celsius * 9 / 5 + 32) == fahrenheit
        if previous is not None:
            assert celsius > previous
        previous = celsius
    assert encode_temperature(350, "F") == bytes.fromhex("e7060000")  # 176.7 °C
    assert encode_temperature(104, "F") == (400).to_bytes(4, "little")
    assert encode_temperature(446, "F") == (2300).to_bytes(4, "little")


@pytest.mark.parametrize("value", [103.9, 446.1, float("nan"), float("inf")])
def test_fahrenheit_validation_precedes_rounding(value):
    with pytest.raises(ValueError):
        encode_temperature(value, "F")


async def test_unit_select_preserves_bits_and_updates_card_attributes(
    hass, integration, peripheral
):
    registry = er.async_get(hass)
    select_id = registry.async_get_entity_id(
        "select", DOMAIN, "volcano_temperature_unit_AA:BB:CC:DD:EE:FF"
    )
    current_id = registry.async_get_entity_id(
        "sensor", DOMAIN, "volcano_current_temperature_AA:BB:CC:DD:EE:FF"
    )
    target_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    assert hass.states.get(select_id).state == "unavailable"
    peripheral.values[REGISTER2_UUID] = bytes.fromhex("0010")
    await connect_manager(integration)
    assert hass.states.get(select_id).state == "°C"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "°F"}, blocking=True
    )
    assert peripheral.values[REGISTER2_UUID] == bytes.fromhex("0012")
    assert hass.states.get(select_id).state == "°F"
    for entity_id in (current_id, target_id):
        assert hass.states.get(entity_id).attributes["device_temperature_unit"] == "F"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select_id, "option": "°C"}, blocking=True
    )
    assert peripheral.values[REGISTER2_UUID] == bytes.fromhex("0010")
    peripheral.write_gatt_char.side_effect = None
    with pytest.raises(HomeAssistantError, match="did not confirm"):
        await integration.set_temperature_unit("F")
    assert hass.states.get(select_id).state == "°C"
    await integration.stop()
    assert hass.states.get(select_id).state == "unavailable"
    assert integration.state.temperature_unit is None


async def test_physical_notifications_and_polling_update_unit(manager, peripheral, monkeypatch):
    monkeypatch.setattr(
        "custom_components.volcano_integration.bluetooth_coordinator.TEMP_POLL_INTERVAL", 0.001
    )
    await connect_manager(manager)
    assert manager.state.temperature_unit == "C"
    peripheral.notification_callbacks[REGISTER2_UUID](None, bytes.fromhex("0002"))
    assert manager.state.temperature_unit == "F"
    async with asyncio.timeout(1):
        while manager.state.temperature_unit != "C":
            await manager._changed.wait()


async def test_unit_notification_wins_over_stale_read(manager, peripheral):
    await connect_manager(manager)
    original = peripheral.read_gatt_char.side_effect

    async def stale_read(uuid):
        data = await original(uuid)
        if uuid == REGISTER2_UUID:
            peripheral.notification_callbacks[uuid](None, bytes.fromhex("0002"))
        return data

    peripheral.read_gatt_char.side_effect = stale_read
    async with manager._io_lock:
        await manager._read_temperature_unit()
    assert manager.state.temperature_unit == "F"
    manager._unit_notification(object(), bytes(2))
    assert manager.state.temperature_unit == "F"
    await manager.stop()
    peripheral.notification_callbacks[REGISTER2_UUID](None, bytes.fromhex("0002"))
    assert manager.state.temperature_unit is None


async def test_unit_polling_works_when_notifications_are_unsupported(manager, peripheral):
    original = peripheral.notify

    async def notify(uuid, callback):
        if uuid == REGISTER2_UUID:
            raise BleakError("Notifications unavailable")
        await original(uuid, callback)

    peripheral.start_notify.side_effect = notify
    peripheral.values[REGISTER2_UUID] = bytes.fromhex("0002")
    await connect_manager(manager)
    assert manager.state.temperature_unit == "F"
    assert manager.connected


@pytest.mark.parametrize("payload", [None, b"\x02"])
async def test_missing_or_malformed_unit_is_unknown(hass, integration, peripheral, payload):
    if payload is None:
        original = peripheral.characteristic
        peripheral.services.get_characteristic = lambda uuid: (
            None if uuid == REGISTER2_UUID else original(uuid)
        )
    else:
        peripheral.values[REGISTER2_UUID] = payload
    await connect_manager(integration)
    assert integration.state.temperature_unit is None
    target_id = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    with pytest.raises(HomeAssistantError, match="unit is unknown"):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": target_id, "value": 180}, blocking=True
        )
    peripheral.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("entity_unit", ["°C", "°F"])
async def test_number_uses_device_fahrenheit_regardless_of_ha_entity_unit(
    hass, integration, peripheral, entity_unit
):
    registry = er.async_get(hass)
    target_id = registry.async_get_entity_id(
        "number", DOMAIN, "volcano_heater_temperature_setpoint_AA:BB:CC:DD:EE:FF"
    )
    registry.async_update_entity_options(target_id, "number", {"unit_of_measurement": entity_unit})
    await drain()
    peripheral.values[REGISTER2_UUID] = bytes.fromhex("0002")
    await connect_manager(integration)
    value = 350 if entity_unit == "°F" else (350 - 32) * 5 / 9
    await hass.services.async_call(
        "number", "set_value", {"entity_id": target_id, "value": value}, blocking=True
    )
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1767).to_bytes(4, "little")
    assert integration.state.target_temperature == 176.7
    # Existing automation actions keep their Celsius contract, even in device F mode.
    await hass.services.async_call(
        DOMAIN, "set_temperature", {"temperature": 180, "wait_until_reached": False}, blocking=True
    )
    assert peripheral.values[UUID_HEATER_SETPOINT] == (1800).to_bytes(4, "little")
