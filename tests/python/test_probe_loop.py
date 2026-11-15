"""Hash probe loop components (Story 2.7).

Android runs no ctest, so the hash probe carries a looping recipe and a seek
across its last seam to every platform (four-platform hash check, scope
`engine`).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/loop-44100.f32 and
  OUT_DIR/loop-48000.f32 (probe_loop(fs)): loop-swell-theta-cycle.json
  (loop_constants probe_fixture; a 450 Hz carrier amplitude-modulated by the
  sine envelope at a theta rate of 4 +- 2 Hz cycling every 60 s, 75 percent
  depth, and a 250 Hz sine carrier amplitude-modulated at 40 Hz with a smooth
  swell peaking at the 0 degree coupling phase, 100 percent depth; opening
  60 s, body 120 s, 20 min cap), compiled in measure mode at that rate and
  rendered through the public C API: 5 s from frame 0, then arc_seek to
  seam 9 - seconds_to_samples(2.5, fs) and 5 s more, interleaved stereo, each
  binary64 sample converted to float32, the two segments one after the
  other. The probe embeds the recipe as kLoopSwellRecipe[] (it reads no
  file), with the values of the fixture file.
- So each component holds 2 * 2 * 5 * fs float32 samples, and each segment
  matches the Python reference output (reference.stub_chain.render of the
  fixture file with start and frames) within row `reference-match` per
  channel.
- The earlier components keep their bytes: no earlier probe recipe gains a
  loop.
- The expected entries `loop-44100` and `loop-48000` (scope `engine`) arrive
  only after a green four-platform full run (design log (kk)); until then
  that test fails.

The real build follows tests/python/test_probe_rate_curves.py and skips only
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
FIXTURE = "loop-swell-theta-cycle.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
# The JSON key with its opening quote: "loop in a raw string literal, or
# \"loop in an escaped one.
LOOP_KEY = '"loop'
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-",
                      "gamma-uncoupled-", "gamma-swell-", "binaural-cycle-", "gamma-bursts-", "rate-curves-")
EARLIER_RECIPES = ("kStubChainRecipe[]", "kBinauralCycleRecipe[]", "kRateCurveSwellRecipe[]",
                   "kRateCurveBurstsRecipe[]")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def ideal():
    _repo_on_path()
    return importlib.import_module("reference.ideal")


def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def constants():
    return vectors()["loop_constants"]


def segment_s():
    return float(constants()["probe_segment_s"])


def segment_frames(fs):
    return ideal().seconds_to_samples(segment_s(), fs)


def probe_seam(fs):
    """The frame of the probe seam (loop_constants probe_seam) at this rate."""
    k = int(constants()["probe_seam"])
    rows = [r for r in vectors()["loop_frames"] if r["fixture"] == FIXTURE and r["fs"] == fs]
    assert len(rows) == 1, (FIXTURE, fs)
    seams = [int(s) for s in rows[0]["seam_frames"]]
    assert len(seams) >= k, seams
    return seams[k - 1]


def seek_frame(fs):
    return probe_seam(fs) - ideal().seconds_to_samples(segment_s() / 2.0, fs)


def component_samples(fs):
    return 2 * 2 * segment_frames(fs)


def load_fixture(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 2.7)"
    return json.loads(path.read_text(encoding="utf-8"))


def recipe_body(text, name):
    start = text.find(name)
    assert start >= 0, f"{name} not in the probe source"
    end = text.find(')";', start)
    assert end > start, name
    return text[start:end]


# ------------------------------------------------- without a build


def test_probe_fixture_is_the_spec_probe_fixture():
    c = constants()
    assert c["probe_fixture"] == FIXTURE
    assert segment_s() == 5.0
    assert int(c["probe_seam"]) == 9
    for fs in SAMPLE_RATES:
        assert segment_frames(fs) == 5 * fs
        # The second segment is centered on the probe seam.
        assert seek_frame(fs) + segment_frames(fs) // 2 == probe_seam(fs)
        assert seek_frame(fs) + segment_frames(fs) <= int(
            [r for r in vectors()["loop_frames"] if r["fixture"] == FIXTURE and r["fs"] == fs][0]["end_frame"])


def test_probe_source_names_the_loop_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"loop-{fs}" in text, fs
    assert "probe_loop" in text
    assert "kLoopSwellRecipe[]" in text
    assert "arc_seek" in text


def test_probe_source_embeds_the_swell_loop_fixture_values():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    body = recipe_body(text, "kLoopSwellRecipe[]")
    recipe = load_fixture(FIXTURE)
    loop = recipe["loop"]
    assert LOOP_KEY in body
    for word in ("mode", "opening_s", "body_s", "max_run_time_min", "rate_cycle", "swing_hz", "period_s",
                 "start_phase_deg", "smooth_swell", "coupling_phase_deg"):
        assert word in body, word
    assert f'"{loop["mode"]}' in body or f'\\"{loop["mode"]}' in body, loop["mode"]
    for value in (recipe["length_s"], loop["opening_s"], loop["body_s"], loop["max_run_time_min"],
                  recipe["theta_reference"]["carrier_hz"], recipe["theta_reference"]["rate_cycle"]["swing_hz"],
                  recipe["gamma_pac"]["carrier_hz"], recipe["gamma_pac"]["rate_hz"]):
        assert str(value) in body, value
    # The fixture is the swell loop: a theta rate cycle and the smooth swell.
    assert recipe["gamma_pac"]["coupling"] == "smooth_swell"
    assert recipe["theta_reference"]["rate_cycle"]["swing_hz"] == 2
    assert "binaural" not in recipe


def test_earlier_probe_recipes_have_no_loop():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for name in EARLIER_RECIPES:
        assert LOOP_KEY not in recipe_body(text, name), name


def test_expected_entries_name_the_loop_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        entry = components.get(f"loop-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry loop-{fs} (after the full run)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == component_samples(fs), entry
    assert components["loop-44100"]["sha256"] != components["loop-48000"]["sha256"]


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
    build = tmp_path_factory.mktemp("hashprobe-loop") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-loop-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_loop_component_is_the_start_then_the_seek_across_seam_9(probe_output, fs):
    _repo_on_path()
    sc = importlib.import_module("reference.stub_chain")
    match = importlib.import_module("assertions.reference_match")
    path = probe_output / f"loop-{fs}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4").astype(np.float64)
    assert data.size == component_samples(fs), data.size
    n = segment_frames(fs)
    k = seek_frame(fs)
    table_row("reference-match")
    start, sought = data[:2 * n], data[2 * n:]
    first = sc.render(FIXTURES_VALID / FIXTURE, fs, start=0, frames=n)["output"]
    across = sc.render(FIXTURES_VALID / FIXTURE, fs, start=k, frames=n)["output"]
    failed = []
    for label, segment, want in (("start", start, first), ("across seam 9", sought, across)):
        assert segment.size == want.size == 2 * n, (label, segment.size, want.size)
        failed += [r for r in match.match_stereo(f"{FIXTURE} {fs} {label}", segment, want) if r["result"] != "pass"]
    assert not failed, failed


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_earlier_components_are_still_written(probe_output, fs):
    names = {p.stem for p in probe_output.iterdir() if p.suffix == ".f32"}
    for prefix in EARLIER_COMPONENTS:
        want = prefix if prefix == "probe-arith" else f"{prefix}{fs}"
        assert want in names, (want, sorted(names))
