"""Hash probe burst gamma components (Story 2.4).

Android runs no ctest, so the hash probe carries the coupled 50 ms bursts to
every platform (four-platform hash check, scope `engine`).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/gamma-bursts-44100.f32 and
  OUT_DIR/gamma-bursts-48000.f32 (`probe_bursts()`, like `probe_swell()`):
  the three burst fixtures (signal spec, Vectors: burst fixtures, in that
  order: bursts-40hz, bursts-45hz, bursts-60hz), each compiled in measure
  mode at that rate and rendered through the public C API in one call,
  interleaved stereo, each binary64 sample converted to float32, one fixture
  after another. The probe embeds the recipes (it reads no file); their
  values equal the fixture files.
- So each component holds 2 * 3 * N float32 samples (N = 5 * fs frames
  each), and each fixture's segment matches the Python reference output
  (reference.stub_chain.render of the fixture file) within row
  `reference-match` per channel.
- The earlier components keep their bytes (tests/python/test_probe_determinism.py
  checks every component against ci/hash_expected.json): no earlier probe
  recipe gains the bursts coupling.
- The expected entries `gamma-bursts-44100` and `gamma-bursts-48000` (scope
  `engine`) arrive only after a green four-platform full run (design log
  (kk)); until then that test fails.

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
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
FIXTURES = ("bursts-40hz.json", "bursts-45hz.json", "bursts-60hz.json")
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-",
                      "gamma-uncoupled-", "gamma-swell-", "binaural-cycle-")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def fixture_order_and_frames(fs):
    """The burst fixtures of the vectors, in vector order, with their frames."""
    order, frames = [], {}
    for r in vectors()["burst_samples"]:
        if r["fs"] != fs or r["fixture"] not in FIXTURES:
            continue
        if r["fixture"] not in frames:
            order.append(r["fixture"])
            frames[r["fixture"]] = int(r["frames"])
    return order, frames


def function_body(text, signature):
    """The text of a C++ function from its signature to its closing brace at column 0."""
    start = text.find(signature)
    assert start >= 0, signature
    end = text.find("\n}\n", start)
    assert end > start, signature
    return text[start:end]


# ------------------------------------------------- without a build


def test_vector_fixture_order_is_the_probe_order():
    for fs in SAMPLE_RATES:
        order, frames = fixture_order_and_frames(fs)
        assert tuple(order) == FIXTURES, (fs, order)
        assert set(frames.values()) == {5 * fs}, (fs, frames)


def test_probe_source_names_the_burst_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    assert "probe_bursts(" in text
    for fs in SAMPLE_RATES:
        assert f'"gamma-bursts-{fs}"' in text, fs
        assert f"probe_bursts({fs})" in text, fs


def test_probe_source_embeds_the_burst_fixture_values():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    assert '"coupling": "bursts"' in text
    assert "coupling_phase_deg" in text
    for name in FIXTURES:
        assert name.removesuffix(".json") in text, name


def test_earlier_probe_recipes_are_unchanged():
    # No earlier probe recipe gains the bursts coupling, so every earlier
    # component keeps its bytes.
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    start = text.find("kStubChainRecipe[]")
    assert start >= 0
    body = text[start:text.find(')";', start)]
    assert "bursts" not in body and "coupling_phase_deg" not in body
    for signature in ("std::string gamma_recipe(const GammaFixture& f)",
                      "std::string swell_recipe(const SwellFixture& f)"):
        body = function_body(text, signature)
        assert "bursts" not in body, signature
    assert '"coupling": "smooth_swell"' in function_body(text, "std::string swell_recipe(const SwellFixture& f)")
    assert '"coupling": "uncoupled"' in function_body(text, "std::string gamma_recipe(const GammaFixture& f)")


def test_fixture_files_hold_the_probe_values():
    for name in FIXTURES:
        recipe = json.loads((FIXTURES_VALID / name).read_text(encoding="utf-8"))
        g = recipe["gamma_pac"]
        rate = int(name.removeprefix("bursts-").removesuffix("hz.json"))
        assert recipe["theta_reference"] == {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75,
                                             "shape": "sine"}, name
        assert g == {"carrier_hz": 250, "rate_hz": rate, "am_depth_percent": 100, "carrier_wave": "sine",
                     "coupling": "bursts", "coupling_phase_deg": 0}, name
        assert float(recipe["length_s"]) == 5.0, name


def test_expected_entries_name_the_burst_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        _, frames = fixture_order_and_frames(fs)
        entry = components.get(f"gamma-bursts-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry gamma-bursts-{fs} (after the full run)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == 2 * sum(frames.values()) == 2 * 3 * 5 * fs, entry
    assert components["gamma-bursts-44100"]["sha256"] != components["gamma-bursts-48000"]["sha256"]


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
    build = tmp_path_factory.mktemp("hashprobe-bursts") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-bursts-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_burst_component_is_the_fixtures_in_turn(probe_output, fs):
    _repo_on_path()
    sc = importlib.import_module("reference.stub_chain")
    match = importlib.import_module("assertions.reference_match")
    path = probe_output / f"gamma-bursts-{fs}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4").astype(np.float64)
    order, frames = fixture_order_and_frames(fs)
    assert data.size == 2 * sum(frames.values()) == 2 * 3 * 5 * fs, (data.size, frames)
    table_row("reference-match")
    at = 0
    failed = []
    for name in order:
        n = frames[name]
        segment = data[at:at + 2 * n]
        at += 2 * n
        ref = sc.render(FIXTURES_VALID / name, fs)["output"]
        assert ref.size == 2 * n, (name, fs)
        failed += [r for r in match.match_stereo(f"{name} {fs}", segment, ref) if r["result"] != "pass"]
    assert not failed, failed


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_earlier_components_are_still_written(probe_output, fs):
    names = {p.stem for p in probe_output.iterdir() if p.suffix == ".f32"}
    for prefix in EARLIER_COMPONENTS:
        want = prefix if prefix == "probe-arith" else f"{prefix}{fs}"
        assert want in names, (want, sorted(names))
