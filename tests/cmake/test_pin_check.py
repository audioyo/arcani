"""Configure fails, naming expected and found, when a tool version differs from its pin.

Contract with the build (testing hooks only, never set in presets or CI):

- ARCANI_PIN_OVERRIDE_LLVM: cache variable. When set, CMake uses it in place
  of the active compiler pin from toolchain.json as the expected C++ compiler
  version: apple_clang on macOS, android_ndk clang_version for Android, llvm
  otherwise.
- ARCANI_PIN_OVERRIDE_CMAKE: cache variable. When set, CMake uses it in place
  of the cmake version from toolchain.json as the expected CMake version.

With either set to 0.0.0, configure must exit non-zero with a FATAL_ERROR
message containing the word "expected" followed by 0.0.0 and the word "found"
followed by the real version (digits and dots). The check must run even when
nothing else in the environment is set up, so it has to fire before the
compiler sanity try_compile (for example from CMAKE_USER_MAKE_RULES_OVERRIDE
or right after project() detects the compiler).

The test configures the platform preset (windows-clang-cl on Windows,
macos-appleclang on macOS, linux-clang otherwise) from
the repo root into a temporary build directory. It skips only when cmake is not
on PATH.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
CMAKE = shutil.which("cmake")

pytestmark = pytest.mark.skipif(CMAKE is None, reason="cmake is not on PATH")


def configure_with(tmp_path, define):
    build_dir = tmp_path / "build"
    result = subprocess.run(
        [CMAKE, "--preset", PRESET, "-B", str(build_dir), define],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ.copy(),
    )
    return result.returncode, result.stdout + result.stderr


def assert_names_expected_and_found(output):
    assert re.search(r"expected\D{0,40}0\.0\.0", output, re.IGNORECASE), output
    assert re.search(r"found\D{0,40}\d+\.\d+(\.\d+)?", output, re.IGNORECASE), output


def test_compiler_version_mismatch_fails_configure(tmp_path):
    code, output = configure_with(tmp_path, "-DARCANI_PIN_OVERRIDE_LLVM=0.0.0")
    assert code != 0, output
    assert_names_expected_and_found(output)


def test_cmake_version_mismatch_fails_configure(tmp_path):
    code, output = configure_with(tmp_path, "-DARCANI_PIN_OVERRIDE_CMAKE=0.0.0")
    assert code != 0, output
    assert_names_expected_and_found(output)
