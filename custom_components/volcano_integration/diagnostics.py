"""Download useful state without Bluetooth addresses, names or serial numbers."""

from dataclasses import asdict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import VolcanoConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VolcanoConfigEntry
) -> dict:
    """Use an explicit allowlist rather than exporting configuration or BLE objects."""
    manager = entry.runtime_data
    return {
        "config_version": entry.version,
        "connected": manager.connected,
        "connection_requested": manager.connection_requested,
        "state": async_redact_data(asdict(manager.state), {"serial_number"}),
    }
