"""Discovery must use HA's shared scanner and reject duplicate addresses."""

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.volcano_integration.const import DOMAIN


async def test_discovery_and_existing_entry_deduplication(hass, entry):
    info = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="S&B VOLCANO")
    with (
        patch("homeassistant.setup.async_process_deps_reqs", return_value=True),
        patch("homeassistant.config_entries.async_process_deps_reqs", return_value=True),
        patch(
            "custom_components.volcano_integration.config_flow.bluetooth.async_discovered_service_info",
            return_value=[info],
        ) as discovery,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        discovery.assert_called_with(hass, connectable=True)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"selected_device": info.address}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


async def test_manual_address_when_offline_and_invalid_input(hass):
    with (
        patch("homeassistant.setup.async_process_deps_reqs", return_value=True),
        patch("homeassistant.config_entries.async_process_deps_reqs", return_value=True),
        patch(
            "custom_components.volcano_integration.config_flow.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch("custom_components.volcano_integration.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"bt_address": "invalid"}
        )
        assert result["errors"] == {"base": "invalid_address"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"bt_address": "aa:bb:cc:dd:ee:ff"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["bt_address"] == "AA:BB:CC:DD:EE:FF"
        assert result["result"].unique_id == "AA:BB:CC:DD:EE:FF"
