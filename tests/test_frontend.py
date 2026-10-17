"""Exercise automatic resources and the actual HTTP-served bundle."""

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, UrlManager, add_extra_js_url
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.volcano_integration import async_remove_entry
from custom_components.volcano_integration.const import DOMAIN
from custom_components.volcano_integration.frontend import CARD_PATH, CARD_URL, async_setup_frontend


async def test_integration_loads_real_frontend_dependencies(hass, frontend_setup):
    # No Bluetooth hardware is needed to register the card; keep HTTP/frontend real.
    hass.config.components.add("bluetooth_adapters")
    frontend_setup.side_effect = async_setup_frontend
    assert await async_setup_component(hass, "volcano_integration", {})
    assert "frontend" in hass.config.components
    lovelace = hass.data["lovelace"]
    resources = lovelace["resources"] if isinstance(lovelace, dict) else lovelace.resources
    assert any(item["url"].startswith(CARD_URL) for item in resources.async_items())


@pytest.mark.parametrize("legacy", [False, True])
async def test_storage_registration_and_upgrade(hass, legacy):
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    hass.data["lovelace"] = (
        {"resources": resources} if legacy else SimpleNamespace(resources=resources)
    )
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    await resources.async_create_item({"url": "/local/other-card.js", "res_type": "module"})
    old = await resources.async_create_item({"url": f"{CARD_URL}?v=old", "res_type": "js"})
    await async_setup_frontend(hass)
    items = resources.async_items()
    assert len(items) == 2
    updated = next(item for item in items if item["id"] == old["id"])
    assert updated["url"].startswith(f"{CARD_URL}?v=")
    assert not updated["url"].endswith("old")
    assert updated["type"] == "module"
    # Re-registration must not duplicate or rewrite unchanged resources.
    await async_setup_frontend(hass)
    assert resources.async_items() == items
    hass.http.async_register_static_paths.assert_awaited_once()


async def test_new_storage_resource_and_real_http(hass, hass_client):
    assert await async_setup_component(hass, "http", {})
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    hass.data["lovelace"] = SimpleNamespace(resources=resources)
    await async_setup_frontend(hass)
    [item] = resources.async_items()
    client = await hass_client()
    response = await client.get(item["url"])
    assert response.status == 200
    content = await response.read()
    expected = await hass.async_add_executor_job(CARD_PATH.read_bytes)
    assert content == expected
    assert item["url"] == f"{CARD_URL}?v={sha256(content).hexdigest()[:12]}"
    assert "javascript" in response.headers["Content-Type"]


@pytest.mark.parametrize("legacy", [False, True])
async def test_yaml_registers_extra_module_without_changing_resources(hass, legacy):
    original = [{"url": "/local/user-card.js", "type": "module"}]
    resources = ResourceYAMLCollection(original)
    hass.data["lovelace"] = (
        {"resources": resources} if legacy else SimpleNamespace(resources=resources)
    )
    hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(Mock(), [])
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    await async_setup_frontend(hass)
    await async_setup_frontend(hass)
    [url] = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert url.startswith(f"{CARD_URL}?v=")
    assert resources.async_items() == original


async def test_resource_removed_only_with_last_entry_and_restored(hass, entry):
    hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(Mock(), [])
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    hass.data["lovelace"] = SimpleNamespace(resources=resources)
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    other = await resources.async_create_item({"url": "/local/other.js", "res_type": "module"})
    external = await resources.async_create_item(
        {"url": f"https://example.com{CARD_URL}", "res_type": "module"}
    )
    await async_setup_frontend(hass)
    second = MockConfigEntry(domain=DOMAIN, version=2, data={"bt_address": "11:22:33:44:55:66"})
    second.add_to_hass(hass)
    await async_remove_entry(hass, second)
    assert len(resources.async_items()) == 3
    # HA calls the remove hook while the entry being removed is still registered.
    await hass.config_entries.async_remove(second.entry_id)
    await async_remove_entry(hass, entry)
    assert resources.async_items() == [other, external]
    await async_setup_frontend(hass)
    assert len(resources.async_items()) == 3
    hass.http.async_register_static_paths.assert_awaited_once()


async def test_yaml_cleanup_preserves_user_configuration(hass, entry):
    original = [{"url": "/local/user.js", "type": "module"}]
    resources = ResourceYAMLCollection(original)
    hass.data["lovelace"] = SimpleNamespace(resources=resources)
    on_change = Mock()
    hass.data[DATA_EXTRA_MODULE_URL] = UrlManager(on_change, ["/other/module.js"])
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    await async_setup_frontend(hass)
    card_url = next(
        url for url in hass.data[DATA_EXTRA_MODULE_URL].urls if url.startswith(CARD_URL)
    )
    on_change.reset_mock()
    await async_remove_entry(hass, entry)
    assert hass.data[DATA_EXTRA_MODULE_URL].urls == {"/other/module.js"}
    on_change.assert_called_once_with("removed", card_url)
    assert resources.async_items() == original


@pytest.mark.parametrize("mode", ["storage", "yaml"])
async def test_real_frontend_entry_removal_and_readdition(
    hass, entry, ble, frontend_setup, mode, caplog
):
    """Exercise HA's real frontend state and entry lifecycle, not a mock URL set."""
    hass.config.components.add("bluetooth_adapters")
    frontend_setup.side_effect = async_setup_frontend
    lovelace_config = {"mode": mode}
    user_resource = {"url": "/local/user-card.js", "type": "module"}
    if mode == "yaml":
        lovelace_config["resources"] = [user_resource]
    assert await async_setup_component(hass, DOMAIN, {"lovelace": lovelace_config})
    await hass.async_block_till_done()
    assert entry.runtime_data is not None
    urls = hass.data[DATA_EXTRA_MODULE_URL]
    assert isinstance(urls, UrlManager)
    lovelace = hass.data["lovelace"]
    resources = lovelace["resources"] if isinstance(lovelace, dict) else lovelace.resources
    if mode == "storage":
        await resources.async_create_item({"url": user_resource["url"], "res_type": "module"})
    add_extra_js_url(hass, "/other/module.js")

    def card_registered():
        collection = (
            resources.async_items() if mode == "storage" else [{"url": url} for url in urls.urls]
        )
        return any(item["url"].startswith(CARD_URL) for item in collection)

    assert card_registered()
    # Reload/unload must retain the card; deleting the last configured entry removes it.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert card_registered()
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not card_registered()
    assert "/other/module.js" in urls.urls
    assert any(item["url"] == user_resource["url"] for item in resources.async_items())
    assert "Could not remove the Volcano Hybrid card resource" not in caplog.text

    replacement = MockConfigEntry(domain=DOMAIN, version=2, data=dict(entry.data))
    replacement.add_to_hass(hass)
    try:
        assert await hass.config_entries.async_setup(replacement.entry_id)
        await hass.async_block_till_done()
        assert card_registered()
        assert "Could not register the Volcano Hybrid card" not in caplog.text
    finally:
        await hass.config_entries.async_remove(replacement.entry_id)
    assert not card_registered()
