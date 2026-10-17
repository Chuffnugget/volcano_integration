"""Set up the Volcano integration and preserve its public service names."""

import asyncio
import logging
from functools import partial

import voluptuous as vol
from homeassistant.auth.permissions.const import CAT_ENTITIES, POLICY_CONTROL
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryError,
    ServiceValidationError,
    Unauthorized,
    UnknownUser,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .bluetooth_coordinator import VolcanoBTManager
from .const import (
    CONNECT_WAIT_TIMEOUT,
    DOMAIN,
    MAX_BRIGHTNESS,
    MAX_SHUTOFF_MINUTES,
    MIN_BRIGHTNESS,
    MIN_SHUTOFF_MINUTES,
    UUID_HEAT_OFF,
    UUID_HEAT_ON,
    UUID_PUMP_OFF,
    UUID_PUMP_ON,
)
from .protocol import normalize_setpoint

_LOGGER = logging.getLogger(__name__)
type VolcanoConfigEntry = ConfigEntry[VolcanoBTManager]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.SWITCH, Platform.SELECT]
TARGET_SCHEMA = {vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string])}
SERVICE_SCHEMAS = {
    "connect": vol.Schema(
        {
            **TARGET_SCHEMA,
            vol.Optional("wait_until_connected", default=True): cv.boolean,
            vol.Optional("timeout", default=CONNECT_WAIT_TIMEOUT): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=900)
            ),
        }
    ),
    "disconnect": vol.Schema(TARGET_SCHEMA),
    "set_temperature": vol.Schema(
        {
            **TARGET_SCHEMA,
            vol.Required("temperature"): vol.All(vol.Coerce(float), normalize_setpoint),
            vol.Optional("wait_until_reached", default=True): cv.boolean,
        }
    ),
    "set_led_brightness": vol.Schema(
        {
            **TARGET_SCHEMA,
            vol.Required("brightness", default=20): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_BRIGHTNESS, max=MAX_BRIGHTNESS)
            ),
        }
    ),
    "set_auto_shutoff_setting": vol.Schema(
        {
            **TARGET_SCHEMA,
            vol.Required("minutes", default=30): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SHUTOFF_MINUTES, max=MAX_SHUTOFF_MINUTES)
            ),
        }
    ),
}
COMMANDS = {
    "pump_on": (UUID_PUMP_ON, b"\x01"),
    "pump_off": (UUID_PUMP_OFF, b"\x00"),
    "heat_on": (UUID_HEAT_ON, b"\x01"),
    "heat_off": (UUID_HEAT_OFF, b"\x00"),
}
SERVICE_ENTITIES = {
    "connect": (Platform.BUTTON, "connect_button"),
    "disconnect": (Platform.BUTTON, "disconnect_button"),
    "heat_on": (Platform.BUTTON, "heat_on_button"),
    "heat_off": (Platform.BUTTON, "heat_off_button"),
    "pump_on": (Platform.BUTTON, "pump_on_button"),
    "pump_off": (Platform.BUTTON, "pump_off_button"),
    "set_temperature": (Platform.NUMBER, "heater_temperature_setpoint"),
    "set_led_brightness": (Platform.NUMBER, "led_brightness_number"),
    "set_auto_shutoff_setting": (Platform.NUMBER, "auto_shutoff_minutes"),
}


def _resolve_manager(hass: HomeAssistant, call: ServiceCall) -> VolcanoBTManager:
    managers = hass.data.get(DOMAIN, {})
    device_ids = call.data.get("device_id")
    if device_ids is not None:
        if len(device_ids) != 1:
            raise ServiceValidationError("Select exactly one Volcano device")
        device = dr.async_get(hass).async_get(device_ids[0])
        matches = [
            manager
            for entry_id, manager in managers.items()
            if device is not None and entry_id in device.config_entries
        ]
    else:
        matches = list(managers.values())
    if len(matches) != 1:
        raise ServiceValidationError(
            "Select a loaded Volcano device; a target can only be omitted when exactly one is loaded"
        )
    return matches[0]


async def _async_check_control_permission(
    hass: HomeAssistant, call: ServiceCall, manager: VolcanoBTManager
) -> None:
    """Apply the corresponding entity's permissions to this device's action."""
    if call.context.user_id is None:
        # Automations and other internal calls may not have a user context.
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None:
        raise UnknownUser(context=call.context, permission=POLICY_CONTROL)
    platform, key = SERVICE_ENTITIES[call.service]
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"volcano_{key}_{manager.bt_address}"
    )
    if (
        not user.is_active
        or entity_id is None
        or not user.permissions.check_entity(entity_id, POLICY_CONTROL)
    ):
        raise Unauthorized(
            context=call.context,
            entity_id=entity_id,
            perm_category=CAT_ENTITIES,
            permission=POLICY_CONTROL,
        )


async def _handle_service(hass: HomeAssistant, call: ServiceCall) -> None:
    manager = _resolve_manager(hass, call)
    await _async_check_control_permission(hass, call, manager)
    if call.service == "connect":
        await manager.async_user_connect()
        if call.data["wait_until_connected"]:
            await manager.wait_until_connected(timeout=call.data["timeout"])
    elif call.service == "disconnect":
        await manager.async_user_disconnect()
    elif call.service in COMMANDS:
        uuid, payload = COMMANDS[call.service]
        await manager.write_gatt_command(uuid, payload)
    elif call.service == "set_temperature":
        await manager.set_heater_temperature(
            call.data["temperature"], wait=call.data["wait_until_reached"]
        )
    elif call.service == "set_led_brightness":
        await manager.set_led_brightness(call.data["brightness"])
    elif call.service == "set_auto_shutoff_setting":
        await manager.set_auto_shutoff_setting(call.data["minutes"])


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Keep optional frontend imports and failures outside device setup."""
    from .frontend import async_setup_frontend as setup_frontend

    await setup_frontend(hass)


async def _async_setup_optional_frontend(hass: HomeAssistant) -> None:
    try:
        await async_setup_frontend(hass)
    except Exception:
        _LOGGER.warning(
            "Could not register the Volcano Hybrid card; Bluetooth controls remain available",
            exc_info=True,
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register domain services once, independently of individual entries."""
    await _async_setup_optional_frontend(hass)
    hass.data.setdefault(DOMAIN, {})
    for service in (*SERVICE_SCHEMAS, *COMMANDS):
        hass.services.async_register(
            DOMAIN,
            service,
            partial(_handle_service, hass),
            schema=SERVICE_SCHEMAS.get(service, vol.Schema(TARGET_SCHEMA)),
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VolcanoConfigEntry) -> bool:
    """Expose entities immediately; connection remains an explicit user action."""
    address = entry.data["bt_address"]
    managers = hass.data.setdefault(DOMAIN, {})
    if any(manager.bt_address.upper() == address.upper() for manager in managers.values()):
        raise ConfigEntryError(
            "This Volcano already has a loaded entry. Remove the duplicate integration entry."
        )
    if entry.unique_id is None:
        # Preserve the existing address and entity IDs while adding deduplication.
        hass.config_entries.async_update_entry(entry, unique_id=address.upper())
    manager = VolcanoBTManager(hass, address, config_entry_id=entry.entry_id)
    entry.runtime_data = manager
    # This index only routes domain services across loaded entries.
    managers[entry.entry_id] = manager
    try:
        # Reserve this address before any await so concurrent legacy duplicates
        # cannot both load. Restore the resource after the final device was removed.
        await _async_setup_optional_frontend(hass)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except (Exception, asyncio.CancelledError):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await manager.async_shutdown()
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        del entry.runtime_data
        raise

    async def shutdown(event) -> None:
        await manager.async_shutdown()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VolcanoConfigEntry) -> bool:
    """Only remove this entry after Home Assistant successfully unloads it."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    manager = hass.data[DOMAIN].pop(entry.entry_id)
    await manager.async_shutdown()
    del entry.runtime_data
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove automatic card resources only after the final configured device."""
    ir.async_delete_issue(hass, DOMAIN, f"legacy_entry_{entry.entry_id}")
    if any(other.entry_id != entry.entry_id for other in hass.config_entries.async_entries(DOMAIN)):
        return
    try:
        from .frontend import async_remove_frontend

        await async_remove_frontend(hass)
    except Exception:
        _LOGGER.warning("Could not remove the Volcano Hybrid card resource", exc_info=True)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Explain legacy entries without guessing which physical device they used."""
    if entry.version == 1:
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"legacy_entry_{entry.entry_id}",
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="legacy_configuration",
            translation_placeholders={"name": entry.title},
        )
        _LOGGER.error(
            "Volcano entry %s uses legacy configuration; see Repairs for setup instructions",
            entry.entry_id,
        )
        return False
    return entry.version == 2
