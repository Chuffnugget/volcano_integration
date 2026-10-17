"""Use real Home Assistant entities/services with a deterministic BLE peripheral."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_integration.bluetooth_coordinator import VolcanoBTManager
from custom_components.volcano_integration.const import (
    DOMAIN,
    HEATER_ENABLED_MASK,
    PUMP_ENABLED_MASK,
    REGISTER2_UUID,
    REGISTER3_UUID,
    UUID_AUTO_SHUT_OFF_SETTING,
    UUID_BLE_FIRMWARE_VERSION,
    UUID_FIRMWARE_VERSION,
    UUID_HEAT_OFF,
    UUID_HEAT_ON,
    UUID_HEATER_SETPOINT,
    UUID_LED_BRIGHTNESS,
    UUID_PUMP_NOTIFICATIONS,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
    UUID_SERIAL_NUMBER,
    UUID_TEMP,
)


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    """Allow HA to load this custom component."""


@pytest.fixture(autouse=True)
def frontend_setup():
    """Keep BLE tests independent of HTTP; frontend tests exercise real HA resources."""
    with patch("custom_components.volcano_integration.async_setup_frontend") as setup:
        yield setup


class FakePeripheral:
    """Model wire values, command failures and delayed notification setup."""

    def __init__(self):
        self.is_connected = True
        self.values = {
            UUID_TEMP: (1700).to_bytes(2, "little"),
            UUID_HEATER_SETPOINT: (1700).to_bytes(2, "little"),
            UUID_PUMP_NOTIFICATIONS: bytes.fromhex("2306"),
            UUID_LED_BRIGHTNESS: bytes.fromhex("1400"),
            UUID_AUTO_SHUT_OFF_SETTING: (1800).to_bytes(2, "little"),
            REGISTER3_UUID: bytes(2),
            REGISTER2_UUID: bytes(2),
            UUID_BLE_FIRMWARE_VERSION: b"1.2\x00",
            UUID_FIRMWARE_VERSION: b"1.9\x00",
            UUID_SERIAL_NUMBER: b"VH123456\x00",
        }
        self.services = SimpleNamespace(get_characteristic=self.characteristic)
        self.read_gatt_char = AsyncMock(side_effect=self.read)
        self.write_gatt_char = AsyncMock(side_effect=self.write)
        self.start_notify = AsyncMock(side_effect=self.notify)
        self.disconnect = AsyncMock(side_effect=self.close)
        self.callback = None
        self.notification_callback = None
        self.notification_callbacks = {}

    def characteristic(self, uuid):
        return SimpleNamespace(uuid=uuid, properties=["read", "write", "notify"])

    async def read(self, uuid):
        return bytearray(self.values.get(uuid, bytes(2)))

    async def write(self, characteristic, data, **kwargs):
        if characteristic.uuid in (REGISTER2_UUID, REGISTER3_UUID):
            command = int.from_bytes(data, "little")
            current = int.from_bytes(self.values[characteristic.uuid], "little")
            mask = command & 0xFFFF
            current = current | mask if command & 0x10000 else current & ~mask
            self.values[characteristic.uuid] = current.to_bytes(2, "little")
        else:
            self.values[characteristic.uuid] = data
        output_commands = {
            UUID_HEAT_ON: (HEATER_ENABLED_MASK, True),
            UUID_HEAT_OFF: (HEATER_ENABLED_MASK, False),
            UUID_PUMP_ON: (PUMP_ENABLED_MASK, True),
            UUID_PUMP_OFF: (PUMP_ENABLED_MASK, False),
        }
        if characteristic.uuid in output_commands:
            mask, enabled = output_commands[characteristic.uuid]
            status = int.from_bytes(self.values[UUID_PUMP_NOTIFICATIONS], "little")
            status = status | mask if enabled else status & ~mask
            self.values[UUID_PUMP_NOTIFICATIONS] = status.to_bytes(2, "little")

    async def notify(self, uuid, callback):
        self.notification_callbacks[uuid] = callback
        if uuid == UUID_PUMP_NOTIFICATIONS:
            self.notification_callback = callback

    async def close(self):
        self.is_connected = False
        if self.callback:
            self.callback(self)

    def drop(self):
        self.is_connected = False
        self.callback(self)


@pytest.fixture
def peripheral():
    return FakePeripheral()


@pytest.fixture
def ble(monkeypatch, peripheral):
    module = "custom_components.volcano_integration.bluetooth_coordinator"
    monkeypatch.setattr(f"{module}.async_ble_device_from_address", lambda *a, **k: object())

    async def connect(*args, **kwargs):
        peripheral.is_connected = True
        peripheral.callback = kwargs["disconnected_callback"]
        return peripheral

    connector = AsyncMock(side_effect=connect)
    monkeypatch.setattr(f"{module}.establish_connection", connector)
    return connector


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Volcano",
        version=2,
        data={"bt_address": "AA:BB:CC:DD:EE:FF", "device_name": "S&B VOLCANO"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def manager(hass, ble, entry):
    manager = VolcanoBTManager(hass, entry.data["bt_address"], config_entry_id=entry.entry_id)
    yield manager
    await manager.stop()


@pytest.fixture
async def integration(hass, entry, ble):
    with patch("homeassistant.setup.async_process_deps_reqs", return_value=True):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
        yield hass.data[DOMAIN][entry.entry_id]
        if entry.entry_id in hass.data[DOMAIN]:
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def connect_manager(manager):
    await manager.async_user_connect()
    await manager.wait_until_connected(timeout=2)
    return manager


async def drain():
    """Yield to manager and service tasks without real Bluetooth delays."""
    for _ in range(10):
        await asyncio.sleep(0)
