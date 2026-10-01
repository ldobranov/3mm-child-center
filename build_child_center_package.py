#!/usr/bin/env python3
"""Build the reviewed Child Center application package deterministically."""

from __future__ import annotations

import argparse
import hashlib
import io
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit
import zipfile


ROOT = Path(__file__).resolve().parent
PACKAGE_VERSION = "0.7.6"
FIXED_ARCHIVE_TIME = (2026, 1, 1, 0, 0, 0)


def wheel_filename(version: str = PACKAGE_VERSION) -> str:
    return f"child_center_application-{version}-py3-none-any.whl"


def _archive_write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_ARCHIVE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_wheel(version: str = PACKAGE_VERSION) -> bytes:
    if version != PACKAGE_VERSION:
        raise ValueError(f"Only reviewed version {PACKAGE_VERSION} can be built")
    output = io.BytesIO()
    package_root = ROOT / "service" / "child_center_application"
    dist_info = f"child_center_application-{version}.dist-info"
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(package_root.glob("*.py"), key=lambda item: item.name):
            _archive_write(
                archive,
                f"child_center_application/{path.name}",
                path.read_bytes(),
            )
        _archive_write(
            archive,
            f"{dist_info}/METADATA",
            (
                "Metadata-Version: 2.1\n"
                "Name: child-center-application\n"
                f"Version: {version}\n"
            ).encode("utf-8"),
        )
        _archive_write(
            archive,
            f"{dist_info}/WHEEL",
            (
                "Wheel-Version: 1.0\n"
                "Generator: 3mm-child-center-builder\n"
                "Root-Is-Purelib: true\n"
                "Tag: py3-none-any\n"
            ).encode("utf-8"),
        )
        _archive_write(archive, f"{dist_info}/RECORD", b"")
    return output.getvalue()


def package_files(
    destination: str = "http://127.0.0.1",
    *,
    version: str = PACKAGE_VERSION,
) -> dict[str, bytes]:
    if version != PACKAGE_VERSION:
        raise ValueError(f"Only reviewed version {PACKAGE_VERSION} can be built")
    parsed_destination = urlsplit(destination)
    if (
        parsed_destination.scheme not in {"http", "https"}
        or not parsed_destination.netloc
        or parsed_destination.username is not None
        or parsed_destination.password is not None
        or parsed_destination.path not in {"", "/"}
        or parsed_destination.query
        or parsed_destination.fragment
    ):
        raise ValueError("Barsy API destination must be an HTTP(S) origin")

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["configuration_defaults"]["BARSY_API_URL"] = destination.rstrip("/")

    application = json.loads(
        (ROOT / "application-extension.json").read_text(encoding="utf-8")
    )
    application["version"] = version
    wheel = build_wheel(version)
    artifact = f"service/{wheel_filename(version)}"
    application["service"]["artifact"] = artifact
    application["service"]["artifact_sha256"] = hashlib.sha256(wheel).hexdigest()

    compiled_ui = json.loads(
        (ROOT / "compiled-ui.json").read_text(encoding="utf-8")
    )
    compiled_ui["version"] = version
    spec = importlib.util.spec_from_file_location('child_center_release_068', ROOT / 'release_068.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.apply(manifest, application, compiled_ui)

    spec = importlib.util.spec_from_file_location('child_center_release_069', ROOT / 'release_069.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.apply(manifest, application, compiled_ui)

    spec = importlib.util.spec_from_file_location('child_center_release_0610', ROOT / 'release_0610.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.apply(manifest, application, compiled_ui)

    spec = importlib.util.spec_from_file_location('child_center_release_071', ROOT / 'release_071.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.apply(manifest, application, compiled_ui)

    spec = importlib.util.spec_from_file_location('child_center_release_072', ROOT / 'release_072.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.apply(manifest, application, compiled_ui)

    files = {
        "manifest.json": _canonical_json(manifest),
        "application-extension.json": _canonical_json(application),
        "compiled-ui.json": _canonical_json(compiled_ui),
        artifact: wheel,
    }
    frontend_root = ROOT / "source" / "frontend"
    frontend_sources = (
        path
        for path in frontend_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".vue", ".ts", ".js"}
    )
    for path in sorted(
        frontend_sources,
        key=lambda item: item.relative_to(frontend_root).as_posix(),
    ):
        relative = path.relative_to(frontend_root).as_posix()
        files[f"source/frontend/{relative}"] = path.read_bytes()
    return files


def build_package(
    destination: str = "http://127.0.0.1",
    *,
    version: str = PACKAGE_VERSION,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, payload in package_files(destination, version=version).items():
            _archive_write(archive, name, payload)
    return output.getvalue()


def build_directory(output: Path, destination: str = "http://127.0.0.1") -> Path:
    """Stage package contents without creating an outer ZIP or replacing files.

    Zip the contents of the returned directory, not its parent directory.
    The wheel is still required by ApplicationExtensionV1.
    """
    files = package_files(destination)
    output = Path(output)
    if output.is_symlink() or output.exists():
        raise ValueError("Package directory must be new; existing paths are never overwritten")
    output.mkdir(parents=True, exist_ok=False)
    for name, payload in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
    return output.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--output", type=Path, help="Create an installable ZIP")
    target.add_argument("--output-dir", type=Path, help="Prepare a new folder for manual ZIP creation")
    parser.add_argument("--destination", default="http://127.0.0.1")
    arguments = parser.parse_args()

    if arguments.output_dir is not None:
        print(build_directory(arguments.output_dir, arguments.destination))
        return

    package = build_package(
        arguments.destination,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(package)
    print(hashlib.sha256(package).hexdigest())


if __name__ == "__main__":
    main()
