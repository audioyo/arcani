"""Hash probe gamma PAC components (Story 2.2).

Android runs no ctest, so the hash probe carries the gamma PAC layer to every
platform (four-platform hash check, scope `engine`).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/gamma-uncoupled-44100.f32
  and OUT_DIR/gamma-uncoupled-48000.f32: the five gamma fixtures (signal
  spec, Vectors: gamma fixtures, in that order: gamma-uncoupled-40hz-25pct,
  gamma-uncoupled-40hz-100pct, gamma-uncoupled-60hz-25pct,
  gamma-uncoupled-60hz-100pct, theta-gamma-uncoupled), each compiled in
  measure mode at that rate and rendered through the public C API in one
  call, interleaved stereo, each binary64 sample converted to float32, one
  fixture after another. The probe embeds the recipes (it reads no file);
  their values equal the fixture files.
- So each component holds 2 * sum(N) float32 samples (2 * 5 * N, N = 10 * fs
  frames each), and each fixture's segment matches the Python reference
  output (reference.stub_chain.render of the fixture file) within row
  `reference-match` per channel (the float32 conversion stays far below it).
- The earlier components keep their bytes: no earlier probe recipe has a
  gamma_pac field, so their expected entries in ci/hash_expected.json do
  not change.
- The expected entries `gamma-uncoupled-44100` and `gamma-uncoupled-48000`
  (scope `engine`) arrive only after a green four-platform full run
  (design log (kk)); until then that test fails.

The real build follows tests/python/test_probe_theta.py and skips only when
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
FIXTURES = tuple(f"gamma-uncoupled-{rate}hz-{depth}pct.json"
                 for rate in (40, 60) for depth in (25, 100)) + ("theta-gamma-uncoupled.json",)
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-")


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def vectors():
    return json.loads(VECTORS.read_text(encoding="utf-8"))


def fixture_order_and_frames(fs):
    order, frames = [], {}
    for r in vectors()["gamma_samples"]:
        if r["fs"] != fs:
            continue
        if r["fixture"] not in frames:
            order.append(r["fixture"])
            frames[r["fixture"]] = int(r["frames"])
    return order, frames


# ------------------------------------------------- without a build


def test_vector_fixture_order_is_the_probe_order():
    for fs in SAMPLE_RATES:
        order, frames = fixture_order_and_frames(fs)
        assert tuple(order) == FIXTURES, (fs, order)
        assert set(frames.values()) == {10 * fs}, (fs, frames)


def test_probe_source_names_the_gamma_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"gamma-uncoupled-{fs}" in text, fs


def test_probe_source_embeds_the_gamma_fixture_values():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for word in ("gamma_pac", "carrier_wave", "coupling", "uncoupled", "250"):
        assert word in text, word


def test_earlier_probe_recipes_have_no_gamma_layer():
    # The stub chain recipe keeps its bytes: it gains no gamma_pac field.
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    start = text.find("kStubChainRecipe[]")
    assert start >= 0
    body = text[start:text.find(')";', start)]
    assert "gamma_pac" not in body


def test_expected_entries_name_the_gamma_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        _, frames = fixture_order_and_frames(fs)
        entry = components.get(f"gamma-uncoupled-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry gamma-uncoupled-{fs} (after the full run)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == 2 * sum(frames.values()), entry
    assert components["gamma-uncoupled-44100"]["sha256"] != components["gamma-uncoupled-48000"]["sha256"]


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
    build = tmp_path_factory.mktemp("hashprobe-gamma") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-gamma-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_gamma_component_is_the_fixtures_in_turn(probe_output, fs):
    _repo_on_path()
    sc = importlib.import_module("reference.stub_chain")
    match = importlib.import_module("assertions.reference_match")
    path = probe_output / f"gamma-uncoupled-{fs}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4").astype(np.float64)
    order, frames = fixture_order_and_frames(fs)
    assert data.size == 2 * sum(frames.values()), (data.size, frames)
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
