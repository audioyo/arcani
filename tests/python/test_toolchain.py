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
      "pytest": {"version": "9.2.0"},
      "apple_clang": {"version": "17.0.0.17000013",
                      "xcode_path": "/Applications/Xcode_16.4.app"},
      "android_ndk": {"version": "r30", "url": "...", "sha256": "...",
                      "clang_version": "21.0.0", "api_level": 21}
    }

Per-platform download entries ({"url", "sha256"}): llvm, cmake, and ninja
have windows_x64, windows_arm64, linux_x64, and linux_arm64; cmake and ninja
also have macos_arm64. apple_clang.version is the version CMake reports as
CMAKE_CXX_COMPILER_VERSION for AppleClang with Xcode 16.4.
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
    "apple_clang": "17.0.0.17000013",
    "android_ndk": "r30",
}

WINDOWS_ARM64_ASSETS = {
    "llvm": "LLVM-23.1.4-woa64.msi",
    "cmake": "cmake-4.4.5-windows-arm64.zip",
    "ninja": "ninja-winarm64.zip",
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


def test_download_urls_carry_the_pinned_version():
    # A version bump must come with the matching download URL (and hash).
    checked = []
    for name, entry in load_pins().items():
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        candidates = [entry] + [v for v in entry.values() if isinstance(v, dict)]
        for item in candidates:
            url = item.get("url")
            if url is None:
                continue
            checked.append(url)
            assert isinstance(version, str) and version in url, f"{name}: {version} not in {url}"
    assert checked, "toolchain.json records no download URLs"


def download_entry(tool, platform):
    data = load_pins()
    assert tool in data, f"toolchain.json has no entry for {tool}"
    entry = data[tool].get(platform)
    assert isinstance(entry, dict), f"{tool} has no {platform} entry"
    assert isinstance(entry.get("url"), str) and entry["url"].startswith("https://"), entry
    assert isinstance(entry.get("sha256"), str), entry
    return entry


@pytest.mark.parametrize("tool, asset", sorted(WINDOWS_ARM64_ASSETS.items()))
def test_windows_arm64_assets(tool, asset):
    entry = download_entry(tool, "windows_arm64")
    assert entry["url"].rsplit("/", 1)[-1] == asset, entry["url"]


@pytest.mark.parametrize("tool", ["llvm", "cmake", "ninja"])
def test_linux_arm64_assets(tool):
    download_entry(tool, "linux_arm64")


@pytest.mark.parametrize("tool", ["cmake", "ninja"])
def test_macos_arm64_assets(tool):
    download_entry(tool, "macos_arm64")


def test_apple_clang_pin():
    pin("apple_clang")
    assert load_pins()["apple_clang"].get("xcode_path") == "/Applications/Xcode_16.4.app"


def test_android_ndk_pin():
    pin("android_ndk")
    ndk = load_pins()["android_ndk"]
    assert ndk.get("url") == "https://dl.google.com/android/repository/android-ndk-r30-linux.zip"
    assert ndk.get("sha256") == "753611f410d002cfcd3f3dc2ef49aad532089d3180b436c060a90bf0fcb64df2"
    assert ndk.get("clang_version") == "21.0.0"
    assert type(ndk.get("api_level")) is int and ndk["api_level"] == 21
