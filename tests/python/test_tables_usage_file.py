"""Row usage file across processes (Story 1.4; tests/assertions/tables.cpp).

The C++ assertion library writes the ids it reads to $ARCANI_ROW_USAGE_FILE.
The first process of a run truncates the file at start and sets
ARCANI_ROW_USAGE_INHERITED=1 for its children; a process that starts with
ARCANI_ROW_USAGE_INHERITED set keeps the file and adds its ids to it.

Runs the arcani-render already built by the platform preset
(build/<preset>/cli/), which reads row `render-speed`. Skips when that binary
is missing, or when Windows application control blocks it (OSError winerror
4551 or 1260).
"""

import os
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
EXE = REPO_ROOT / "build" / PRESET / "cli" / (
    "arcani-render.exe" if sys.platform == "win32" else "arcani-render"
)
FIXTURE = REPO_ROOT / "recipes" / "fixtures" / "valid" / "stub-chain-1s-beat-6.json"


def render_with_usage(tmp_path, inherited):
    if not EXE.is_file():
        pytest.skip(f"arcani-render is not built at {EXE}")
    usage = tmp_path / "usage.txt"
    usage.write_text("stale-id\n", encoding="utf-8")
    env = dict(os.environ, ARCANI_ROW_USAGE_FILE=str(usage))
    env.pop("ARCANI_ROW_USAGE_INHERITED", None)
    env.pop("ARCANI_REFERENCE_MACHINE", None)
    if inherited:
        env["ARCANI_ROW_USAGE_INHERITED"] = "1"
    try:
        result = subprocess.run(
            [str(EXE), str(FIXTURE), "--out", str(tmp_path / "x.wav")],
            capture_output=True, text=True, timeout=120, env=env,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked {EXE}")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return usage.read_text(encoding="utf-8").splitlines()


def test_first_process_truncates_the_usage_file(tmp_path):
    assert render_with_usage(tmp_path, inherited=False) == ["render-speed"]


def test_child_process_adds_to_the_usage_file(tmp_path):
    assert sorted(render_with_usage(tmp_path, inherited=True)) == ["render-speed", "stale-id"]
