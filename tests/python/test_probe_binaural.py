"""Hash probe binaural cycle components (Story 2.5).

Android runs no ctest, so the hash probe carries the binaural beat rate cycle
and its seek to every platform (four-platform hash check, scope `engine`).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/binaural-cycle-44100.f32 and
  OUT_DIR/binaural-cycle-48000.f32: binaural-cycle-sleep.json (a 100 Hz pure
  sine in the left ear and a pure sine in the right ear whose beat rate
  cycles over 0 to 3 Hz every 60 s from 0 Hz rising; signal spec, Vectors:
  binaural fixtures) compiled in measure mode at that rate and rendered
  through the public C API: 5 s from frame 0, then arc_seek to
  seconds_to_samples(55, fs) and 5 s more, interleaved stereo, each binary64
  sample converted to float32, the two segments one after the other. The
  probe embeds the recipe (it reads no file); its values equal the fixture
  file.
- So each component holds 2 * 2 * 5 * fs float32 samples, and each segment
  matches the Python reference output (reference.stub_chain.render of the
  fixture file, frames [0, 5 fs) and [k, k + 5 fs) with
  k = seconds_to_samples(55, fs)) within row `reference-match` per channel.
- The earlier components keep their bytes: no earlier probe recipe gains a
  beat_rate_cycle or waveform field.
- The expected entries `binaural-cycle-44100` and `binaural-cycle-48000`
  (scope `engine`) arrive only after a green four-platform full run (design
  log (kk)); until then that test fails.

The real build follows tests/python/test_probe_swell.py and skips only when
cmake is not on PATH, or when Windows application control blocks the probe
binary (winerror 4551 or 1260).
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
FIXTURE = "binaural-cycle-sleep.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
SEGMENT_S = 5
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-",
                      "gamma-uncoupled-", "gamma-swell-")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def seek_seconds():
    return float(json.loads(VECTORS.read_text(encoding="utf-8"))["binaural_constants"]["seek_s"])


def component_samples(fs):
    return 2 * 2 * SEGMENT_S * fs


# ------------------------------------------------- without a build


def test_seek_point_is_55_s():
    assert seek_seconds() == 55.0


def test_probe_source_names_the_binaural_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"binaural-cycle-{fs}" in text, fs
    assert "arc_seek" in text


def test_probe_source_embeds_the_cycle_fixture_values():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for word in ("beat_rate_cycle", "swing_hz", "period_s", "start_phase_deg", "270", "1.5", "120"):
        assert word in text, word
    assert FIXTURE.removesuffix(".json") in text


def test_earlier_probe_recipes_have_no_cycle_or_waveform():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    start = text.find("kStubChainRecipe[]")
    assert start >= 0
    body = text[start:text.find(')";', start)]
    assert "beat_rate_cycle" not in body and "waveform" not in body


def test_fixture_file_holds_the_probe_values():
    recipe = json.loads((FIXTURES_VALID / FIXTURE).read_text(encoding="utf-8"))
    assert recipe["binaural"] == {"carrier_left_hz": 100, "beat_rate_hz": 1.5,
                                  "beat_rate_cycle": {"swing_hz": 1.5, "period_s": 60, "start_phase_deg": 270}}
    assert float(recipe["length_s"]) == 120.0
    assert "theta_reference" not in recipe and "gamma_pac" not in recipe


def test_expected_entries_name_the_binaural_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        entry = components.get(f"binaural-cycle-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry binaural-cycle-{fs} (after the full run)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == component_samples(fs), entry
    assert components["binaural-cycle-44100"]["sha256"] != components["binaural-cycle-48000"]["sha256"]


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
    build = tmp_path_factory.mktemp("hashprobe-binaural") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-binaural-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_binaural_component_is_the_start_then_the_seek(probe_output, fs):
    _repo_on_path()
    sc = importlib.import_module("reference.stub_chain")
    match = importlib.import_module("assertions.reference_match")
    path = probe_output / f"binaural-cycle-{fs}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4").astype(np.float64)
    assert data.size == component_samples(fs), data.size
    n = SEGMENT_S * fs
    k = ideal().seconds_to_samples(seek_seconds(), fs)
    assert k == 55 * fs
    ref = sc.render(FIXTURES_VALID / FIXTURE, fs)["output"]
    table_row("reference-match")
    failed = []
    for label, segment, want in (("start", data[:2 * n], ref[:2 * n]),
                                 ("after seek", data[2 * n:], ref[2 * k:2 * (k + n)])):
        assert segment.size == want.size == 2 * n, (label, segment.size, want.size)
        failed += [r for r in match.match_stereo(f"{FIXTURE} {fs} {label}", segment, want) if r["result"] != "pass"]
    assert not failed, failed
    # The second segment is not the first one again: the seek moved the cycle.
    assert not np.array_equal(data[:2 * n], data[2 * n:])


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_earlier_components_are_still_written(probe_output, fs):
    names = {p.stem for p in probe_output.iterdir() if p.suffix == ".f32"}
    for prefix in EARLIER_COMPONENTS:
        want = prefix if prefix == "probe-arith" else f"{prefix}{fs}"
        assert want in names, (want, sorted(names))
