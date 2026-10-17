"""Serve and automatically register the bundled Hybrid dashboard card."""

from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.frontend import (
    DATA_EXTRA_MODULE_URL,
    add_extra_js_url,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant

CARD_PATH = Path(__file__).parent / "www" / "volcano-hybrid-card.js"
CARD_URL = "/volcano_integration/volcano-hybrid-card.js"
_DATA_STATIC_PATH = "volcano_integration_static_path"


def _is_card_url(url: str) -> bool:
    """Only manage this integration's local route."""
    parsed = urlsplit(url)
    return not parsed.scheme and not parsed.netloc and parsed.path == CARD_URL


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register once per integration setup, independently of the device entries.

    Storage resources also work with HA Cast. YAML installations load an extra
    frontend module without modifying the user's configuration or resources.
    A content hash invalidates browser caches whenever the bundled card changes.
    """
    content = await hass.async_add_executor_job(CARD_PATH.read_bytes)
    url = f"{CARD_URL}?v={sha256(content).hexdigest()[:12]}"
    if not hass.data.get(_DATA_STATIC_PATH):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_PATH), True)]
        )
        hass.data[_DATA_STATIC_PATH] = True

    lovelace = hass.data["lovelace"]
    # HA 2024.11 used a dict; current HA uses LovelaceData.
    resources = lovelace["resources"] if isinstance(lovelace, dict) else lovelace.resources
    if not isinstance(resources, ResourceStorageCollection):
        add_extra_js_url(hass, url)
        return

    await resources.async_get_info()
    for item in resources.async_items():
        if _is_card_url(item["url"]):
            if item["url"] != url or item["type"] != "module":
                await resources.async_update_item(item["id"], {"url": url, "res_type": "module"})
            return
    await resources.async_create_item({"url": url, "res_type": "module"})


async def async_remove_frontend(hass: HomeAssistant) -> None:
    """Remove automatically loaded modules; never rewrite YAML resources."""
    manager = hass.data.get(DATA_EXTRA_MODULE_URL)
    # HA stores a non-iterable UrlManager; keep compatibility with plain URL sets.
    for url in tuple(getattr(manager, "urls", manager or ())):
        if _is_card_url(url):
            remove_extra_js_url(hass, url)
    if (lovelace := hass.data.get("lovelace")) is None:
        return
    resources = lovelace["resources"] if isinstance(lovelace, dict) else lovelace.resources
    if isinstance(resources, ResourceStorageCollection):
        await resources.async_get_info()
        for item in list(resources.async_items()):
            if _is_card_url(item["url"]):
                await resources.async_delete_item(item["id"])
