"""Folder delivery must use exactly the reviewed package payload, without a ZIP."""

import hashlib
import json

import pytest

from test_package import _builder_module


def test_directory_contains_reviewed_wheel_and_contract_without_outer_zip(tmp_path):
    builder = _builder_module()
    output = builder.build_directory(tmp_path / "manual-package")
    actual = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*") if path.is_file()
    }
    assert actual == builder.package_files()
    assert not list(output.rglob("*.zip"))
    assert not list(output.rglob("__pycache__"))
    contract = json.loads(actual["application-extension.json"])
    assert hashlib.sha256(actual[contract["service"]["artifact"]]).hexdigest() == (
        contract["service"]["artifact_sha256"]
    )
    assert builder.package_files() == builder.package_files()


def test_directory_never_overwrites_existing_path(tmp_path):
    builder = _builder_module()
    with pytest.raises(ValueError, match="never overwritten"):
        builder.build_directory(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_destination_creates_no_directory(tmp_path):
    builder = _builder_module()
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="HTTP\\(S\\) origin"):
        builder.build_directory(output, "https://user:secret@example.invalid")
    assert not output.exists()
