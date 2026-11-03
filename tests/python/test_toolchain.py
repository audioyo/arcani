"""Toolchain pins in toolchain.json (repo root).

Expected shape: one JSON object, one key per tool, each value an object with
at least a "version" string. Extra keys (for example "sha256", "url") are
allowed. Example:

    {
      "cmake":  {"version": "4.4.5"},
      "llvm":   {"version": "23.1.4", "windows_x64": {"url": "...", "sha256": "..."}},
      "ninja":  {"version": "1.13.2"},
      "catch2": {"version": "3.16.1", "url": "...", "sha256": "..."},
      "python": {"version": "3.14"},
      "uv":     {"version": "0.13.6"},
      "numpy":  {"version": "2.5.4"},
      "pytest": {"version": "9.2.0"}
    }
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLCHAIN = REPO_ROOT / "toolchain.json"

EXPECTED_PINS = {
    "cmake": "4.4.5",
    "llvm": "23.1.4",
    "ninja": "1.13.2",
    "catch2": "3.16.1",
    "python": "3.14",
    "uv": "0.13.6",
    "numpy": "2.5.4",
    "pytest": "9.2.0",
}


def load_pins():
    assert TOOLCHAIN.is_file(), f"missing {TOOLCHAIN}"
    data = json.loads(TOOLCHAIN.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "toolchain.json must be a JSON object"
    return data


def pin(name):
    data = load_pins()
    assert name in data, f"toolchain.json has no entry for {name}"
    entry = data[name]
    assert isinstance(entry, dict), f"{name} entry must be an object"
    assert isinstance(entry.get("version"), str), f"{name} entry needs a version string"
    return entry["version"]


@pytest.mark.parametrize("name,version", sorted(EXPECTED_PINS.items()))
def test_pin_file_has_expected_version(name, version):
    assert pin(name) == version


def test_sha256_values_are_well_formed():
    # Every sha256 anywhere in the file must be 64 hex characters.
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "sha256":
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(load_pins())
    assert found, "toolchain.json records no sha256 for third-party downloads"
    for value in found:
        assert isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value), value


def test_running_python_matches_pin():
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert running == pin("python")


def test_numpy_matches_pin():
    import numpy

    assert numpy.__version__ == pin("numpy")


def test_pytest_matches_pin():
    assert pytest.__version__ == pin("pytest")
