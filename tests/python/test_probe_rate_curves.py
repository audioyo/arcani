"""Hash probe rate-curve components (Story 2.6).

Android runs no ctest, so the hash probe carries the theta and gamma rate
cycles and their seek to every platform (four-platform hash check, scope
`engine`).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/rate-curves-44100.f32 and
  OUT_DIR/rate-curves-48000.f32 (probe_rate_curves(fs)):
  gamma-cycle-swell-theta-cycle.json and then bursts-theta-cycle.json (signal
  spec, Vectors: theta and gamma rate cycles; rate_curve_constants
  probe_fixtures), each compiled in measure mode at that rate and rendered
  through the public C API: 5 s from frame 0, then arc_seek to
  seconds_to_samples(55, fs) and 5 s more, interleaved stereo, each binary64
  sample converted to float32, the four segments one after the other. The
  probe embeds the two recipes (it reads no file), with the values of the
  fixture files.
- So each component holds 2 * 2 * 10 * fs float32 samples, and each segment
  matches the Python reference output (reference.stub_chain.render of the
  fixture file, frames [0, 5 fs) and [k, k + 5 fs) with
  k = seconds_to_samples(55, fs)) within row `reference-match` per channel.
- The earlier components keep their bytes: no earlier probe recipe gains a
  rate_cycle field.
- The expected entries `rate-curves-44100` and `rate-curves-48000` (scope
  `engine`) arrive only after a green four-platform full run (design log
  (kk)); until then that test fails.

The real build follows tests/python/test_probe_binaural.py and skips only
when cmake is not on PATH, or when Windows application control blocks the
probe binary (winerror 4551 or 1260).
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row
from assertions.tables import load_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_SOURCE = REPO_ROOT / "tests" / "hashprobe" / "main.cpp"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
FIXTURES = ("gamma-cycle-swell-theta-cycle.json", "bursts-theta-cycle.json")
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
SEGMENT_S = 5
# The JSON key with its opening quote: "rate_cycle" in a raw string literal, or
# \"rate_cycle\" in an escaped one. A beat_rate_cycle key does not contain it.
RATE_CYCLE_KEY = '"rate_cycle'
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-",
                      "gamma-uncoupled-", "gamma-swell-", "binaural-cycle-", "gamma-bursts-")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def seek_seconds():
    return float(vectors()["binaural_constants"]["seek_s"])


def component_samples(fs):
    return 2 * len(FIXTURES) * 2 * SEGMENT_S * fs


def load_fixture(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.6)"
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------- without a build


def test_probe_fixtures_are_the_spec_probe_fixtures():
    assert tuple(vectors()["rate_curve_constants"]["probe_fixtures"]) == FIXTURES
    assert seek_seconds() == 55.0


def test_probe_source_names_the_rate_curve_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"rate-curves-{fs}" in text, fs
    assert "probe_rate_curves" in text
    assert "arc_seek" in text


def test_probe_source_embeds_the_two_fixture_values():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for name in FIXTURES:
        assert name.removesuffix(".json") in text, name
    # RATE_CYCLE_KEY, not beat_rate_cycle (which contains the bare words).
    for word in (RATE_CYCLE_KEY, "swing_hz", "period_s", "start_phase_deg", "smooth_swell", "bursts", "120"):
        assert word in text, word
    # The cycles of the two fixtures: theta 4 +- 2 Hz, gamma 45 +- 15 Hz.
    swell = load_fixture(FIXTURES[0])
    bursts = load_fixture(FIXTURES[1])
    assert swell["theta_reference"]["rate_cycle"]["swing_hz"] == 2
    assert swell["gamma_pac"]["rate_cycle"]["swing_hz"] == 15
    assert bursts["theta_reference"]["rate_cycle"]["swing_hz"] == 2
    assert "rate_cycle" not in bursts["gamma_pac"]
    for recipe in (swell, bursts):
        assert float(recipe["length_s"]) == 120.0
        assert "binaural" not in recipe


def test_earlier_probe_recipes_have_no_rate_cycle():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for name in ("kStubChainRecipe[]", "kBinauralCycleRecipe[]"):
        start = text.find(name)
        assert start >= 0, name
        body = text[start:text.find(')";', start)]
        assert RATE_CYCLE_KEY not in body, name


def test_expected_entries_name_the_rate_curve_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        entry = components.get(f"rate-curves-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry rate-curves-{fs} (after the full run)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == component_samples(fs), entry
    assert components["rate-curves-44100"]["sha256"] != components["rate-curves-48000"]["sha256"]


# ------------------------------------------------------------- real build


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [CMAKE, *args]


def run_cmake(args):
    result = subprocess.run(cmake_command(args), cwd=REPO_ROOT, capture_output=True, text=True,
                            timeout=600, env=os.environ.copy())
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(scope="module")
def probe_output(tmp_path_factory):
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    build = tmp_path_factory.mktemp("hashprobe-rate-curves") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-rate-curves-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_rate_curve_component_is_each_fixture_start_then_seek(probe_output, fs):
    _repo_on_path()
    sc = importlib.import_module("reference.stub_chain")
    match = importlib.import_module("assertions.reference_match")
    path = probe_output / f"rate-curves-{fs}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4").astype(np.float64)
    assert data.size == component_samples(fs), data.size
    n = SEGMENT_S * fs
    k = ideal().seconds_to_samples(seek_seconds(), fs)
    assert k == 55 * fs
    table_row("reference-match")
    failed = []
    for i, name in enumerate(FIXTURES):
        ref = sc.render(FIXTURES_VALID / name, fs, frames=k + n)["output"]
        part = data[4 * n * i:4 * n * (i + 1)]
        start, sought = part[:2 * n], part[2 * n:]
        for label, segment, want in (("start", start, ref[:2 * n]), ("after seek", sought, ref[2 * k:2 * (k + n)])):
            assert segment.size == want.size == 2 * n, (name, label, segment.size, want.size)
            failed += [r for r in match.match_stereo(f"{name} {fs} {label}", segment, want) if r["result"] != "pass"]
        # The second segment is not the first one again: the seek moved the cycles.
        assert not np.array_equal(start, sought), name
    assert not failed, failed
    # The two fixtures differ (swell, then bursts).
    assert not np.array_equal(data[:2 * n], data[4 * n:6 * n])


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_earlier_components_are_still_written(probe_output, fs):
    names = {p.stem for p in probe_output.iterdir() if p.suffix == ".f32"}
    for prefix in EARLIER_COMPONENTS:
        want = prefix if prefix == "probe-arith" else f"{prefix}{fs}"
        assert want in names, (want, sorted(names))
