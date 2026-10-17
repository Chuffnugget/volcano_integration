"""Validate exactly the layout HACS extracts into the integration directory."""

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from scripts.package_release import build_release


def test_release_archive_and_version(tmp_path):
    root = Path(__file__).resolve().parents[1]
    manifest = root / "custom_components/volcano_integration/manifest.json"
    version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    archive = build_release(root, tmp_path, f"v{version}")
    with ZipFile(archive) as release:
        assert release.testzip() is None
        assert "LICENSE" in release.namelist()
        assert {
            "__init__.py",
            "manifest.json",
            "translations/en.json",
            "protocol.py",
            "frontend.py",
            "diagnostics.py",
            "switch.py",
            "www/volcano-hybrid-card.js",
            "brand/icon.png",
            "brand/icon@2x.png",
        } <= set(release.namelist())
        assert not any(
            name.startswith("custom_components/") or "__pycache__" in name
            for name in release.namelist()
        )
        assert json.loads(release.read("manifest.json"))["version"] == version
    with pytest.raises(ValueError, match="does not match"):
        build_release(root, tmp_path, f"v{version}-mismatch")


def test_service_ui_limits_match_runtime():
    from custom_components.volcano_integration import SERVICE_SCHEMAS
    from custom_components.volcano_integration.const import MAX_SHUTOFF_MINUTES, MIN_SHUTOFF_MINUTES

    root = Path(__file__).resolve().parents[1]
    services = yaml.safe_load(
        (root / "custom_components/volcano_integration/services.yaml").read_text()
    )
    slider = services["set_auto_shutoff_setting"]["fields"]["minutes"]["selector"]["number"]
    assert (slider["min"], slider["max"]) == (MIN_SHUTOFF_MINUTES, MAX_SHUTOFF_MINUTES)
    assert SERVICE_SCHEMAS["connect"]({})["wait_until_connected"] is True
    assert services["connect"]["fields"]["wait_until_connected"]["default"] is True
    assert services["set_temperature"]["fields"]["temperature"]["selector"]["number"]["step"] == 1
    assert SERVICE_SCHEMAS["set_temperature"]({"temperature": 170.6})["temperature"] == 171
