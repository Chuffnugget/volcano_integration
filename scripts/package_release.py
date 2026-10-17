"""Build the flat integration ZIP consumed by HACS (no repository wrapper)."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build_release(root: Path, destination: Path, tag: str | None = None) -> Path:
    source = root / "custom_components" / "volcano_integration"
    version = json.loads((source / "manifest.json").read_text(encoding="utf-8"))["version"]
    if tag is not None and tag.removeprefix("v") != version:
        raise ValueError(f"Tag {tag} does not match manifest version {version}")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "volcano_integration.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        output.write(root / "LICENSE", "LICENSE")
        for path in sorted(source.rglob("*")):
            if (
                path.is_file()
                and path.suffix in {".py", ".json", ".yaml", ".png", ".svg", ".js"}
                and "__pycache__" not in path.parts
            ):
                output.write(path, path.relative_to(source).as_posix())
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    print(build_release(Path(__file__).resolve().parents[1], args.output, args.tag))
