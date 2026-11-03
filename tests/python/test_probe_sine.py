"""Hash probe sine components against the Python ideal sine (Story 0.2, AD-9).

Contract with the probe binary (tests/hashprobe/, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` writes, besides OUT_DIR/probe-arith.f32
  (unchanged, 4096 samples), OUT_DIR/sine-44100.f32 and
  OUT_DIR/sine-48000.f32: raw little-endian float32, 3*fs samples each. Each
  holds the engine sine, unmodulated, 1 s each of the 1 Hz, 450 Hz, and
  1000 Hz carriers in that order, phase 0 at each segment start.
- Each component is within the sine-error bound (tests/tables/thresholds.json)
  of reference/ideal.py `probe_sine_component(fs)`:
  20*log10(max|probe - ideal|) <= bound.
- tests/hashprobe/main.cpp keeps the probe-arith component and its comment
  block, and names both sine components.
- ci/hash_expected.json is not changed by this story: it has no sine-* entry
  (the cross-platform compare is exact against windows-x64 only).

The real build follows tests/python/test_probe_reference.py: configure the
platform preset with ARCANI_BUILD_TESTS=OFF into a temporary directory, build
only arcani-hashprobe (on Windows through tools/dev.ps1), and run it. It skips
only when cmake is not on PATH, or when Windows application control blocks
the probe binary (OSError winerror 4551 or 1260).
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
IDEAL = REPO_ROOT / "reference" / "ideal.py"
THRESHOLDS = REPO_ROOT / "tests" / "tables" / "thresholds.json"
RANGES = REPO_ROOT / "tests" / "tables" / "ranges.json"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
PROBE_SOURCE = REPO_ROOT / "tests" / "hashprobe" / "main.cpp"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
PROBE_ARITH_SAMPLES = 4096


def rows_by_id(path):
    return {row["id"]: row for row in json.loads(path.read_text(encoding="utf-8"))["rows"]}


def sine_bound_dbfs():
    row = rows_by_id(THRESHOLDS)["sine-error"]
    assert row["unit"] == "dBFS", row
    return row["value"]


SAMPLE_RATES = list(rows_by_id(RANGES)["sample-rates"]["value"])


def load_ideal():
    assert IDEAL.is_file(), f"missing {IDEAL}"
    spec = importlib.util.spec_from_file_location("arcani_reference_ideal", IDEAL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def error_dbfs(probe, ideal):
    probe = np.asarray(probe, dtype=np.float64)
    ideal = np.asarray(ideal, dtype=np.float64)
    assert probe.shape == ideal.shape, (probe.shape, ideal.shape)
    worst = float(np.max(np.abs(probe - ideal)))
    return -np.inf if worst == 0.0 else 20.0 * np.log10(worst)


# ------------------------------------------------- without a build


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_measure_passes_float32_ideal_and_fails_doctored(fs):
    """The measure itself: float32 rounding passes, a 1e-5 error fails."""
    ideal = load_ideal().probe_sine_component(fs)
    as_f32 = ideal.astype("<f4")
    assert error_dbfs(as_f32, ideal) <= sine_bound_dbfs()
    doctored = as_f32.copy()
    doctored[fs + fs // 3] += np.float32(1e-5)
    assert error_dbfs(doctored, ideal) > sine_bound_dbfs()


def test_probe_source_keeps_probe_arith_and_names_sine_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for needle in ("Component probe-arith", "probe-arith.f32", "repeat 4096 times",
                   "t = R * s", "s = t - t * s", "out = s * A + B",
                   "tools/probe_reference.py"):
        assert needle in text, needle
    for name in ("sine-44100", "sine-48000"):
        assert name in text, name
    assert "Story 0.2 adds the engine sine as a second component." not in text, (
        "stale line: update it to describe the sine components")


def test_expected_hashes_have_no_sine_entry():
    data = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert "probe-arith" in data["components"]
    assert not [k for k in data["components"] if k.startswith("sine-")], data["components"]


# ------------------------------------------------------------- real build


def cmake_command(args):
    if sys.platform == "win32":
        return [
            "powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"),
            "cmake", *args,
        ]
    return [CMAKE, *args]


def run_cmake(args):
    result = subprocess.run(
        cmake_command(args),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ.copy(),
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(scope="module")
def probe_output(tmp_path_factory):
    """Builds and runs the host probe once; returns (out_dir, build log)."""
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    build = tmp_path_factory.mktemp("hashprobe-sine") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-sine-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True,
                                timeout=120)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


def read_f32(path):
    assert path.is_file(), f"probe did not write {path.name}"
    return np.frombuffer(path.read_bytes(), dtype="<f4")


def test_probe_still_writes_probe_arith(probe_output):
    data = (probe_output / "probe-arith.f32").read_bytes()
    assert len(data) == PROBE_ARITH_SAMPLES * 4


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_probe_sine_component_shape(probe_output, fs):
    samples = read_f32(probe_output / f"sine-{fs}.f32")
    assert samples.shape == (3 * fs,)
    assert np.all(np.isfinite(samples))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_probe_sine_within_bound_of_ideal(probe_output, fs):
    samples = read_f32(probe_output / f"sine-{fs}.f32")
    ideal = load_ideal().probe_sine_component(fs)
    measured = error_dbfs(samples, ideal)
    assert measured <= sine_bound_dbfs(), (
        f"sine-{fs}: {measured:.1f} dBFS against the ideal, bound {sine_bound_dbfs()} dBFS")


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_doctored_probe_output_exceeds_bound(probe_output, fs):
    samples = read_f32(probe_output / f"sine-{fs}.f32").copy()
    samples[2 * fs + 7] += np.float32(1e-5)
    ideal = load_ideal().probe_sine_component(fs)
    assert error_dbfs(samples, ideal) > sine_bound_dbfs()
