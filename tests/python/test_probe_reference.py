"""The probe-arith reference and the host-built hash probe agree bit for bit (AD-9).

Contract with tools/probe_reference.py (numpy):

- Importable. `probe_arith()` returns a numpy float32 array of 4096 samples:
  the same fixed sequence of float32 multiplies and adds as the C++ probe,
  each operation rounded to float32 separately, in the same order. The
  module docstring documents the operation order side by side with the C++
  probe and names the contractable expressions (each `a*b + c` a compiler
  could fuse into one multiply-add).
- `probe_arith_fused()` returns the same sequence computed as if every
  contractable expression were fused: the product and the add in float64,
  then a single round to float32. Its bytes differ from `probe_arith()`,
  which proves the probe is sensitive to contraction.
- CLI: `--out DIR` writes DIR/probe-arith.f32 (raw little-endian float32,
  4096 samples). `--write` updates the `probe-arith` entry of the expected
  file; `--check` exits 0 when the expected file's `probe-arith` entry
  equals the reference (sha256 of the little-endian bytes and sample count),
  1 otherwise, naming expected and found. `--expected FILE` (default
  ci/hash_expected.json in the repo) selects the file for --write and
  --check. Schema: {"components": {"probe-arith": {"samples": 4096,
  "sha256": "<hex>"}}}; --write keeps other keys and components.

Contract with the probe binary (tests/hashprobe/, CMake target
`arcani-hashprobe`, built by every preset, output at
`<build>/tests/hashprobe/arcani-hashprobe[.exe]`):

- `arcani-hashprobe OUT_DIR` writes OUT_DIR/probe-arith.f32, raw
  little-endian float32, 4096 samples, and exits 0. The component name is the
  file stem.
- ARCANI_HASHPROBE_EXTRA_FLAGS: test-only cache variable, a list of compile
  options appended to the probe target only. Used only by the
  contract-mustfail CI job with -ffp-contract=fast; never in presets.

The real build configures the platform preset (windows-clang-cl,
macos-appleclang, or linux-clang) with ARCANI_BUILD_TESTS=OFF into a
temporary directory and builds only arcani-hashprobe, on Windows through
tools/dev.ps1. It skips only when cmake is not on PATH, or when Windows
application control blocks the probe binary (OSError winerror 4551 or 1260).
"""

import hashlib
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
REFERENCE = REPO_ROOT / "tools" / "probe_reference.py"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
SAMPLES = 4096


def load_reference():
    assert REFERENCE.is_file(), f"missing {REFERENCE}"
    spec = importlib.util.spec_from_file_location("probe_reference", REFERENCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def le_bytes(array):
    return np.asarray(array, dtype="<f4").tobytes()


def run_reference(*args):
    result = subprocess.run(
        [sys.executable, str(REFERENCE), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(scope="module")
def ref():
    return load_reference()


def test_reference_shape_and_dtype(ref):
    out = ref.probe_arith()
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.float32
    assert out.shape == (SAMPLES,)
    assert np.all(np.isfinite(out))
    assert len(np.unique(out)) > 1


def test_reference_is_deterministic(ref):
    assert le_bytes(ref.probe_arith()) == le_bytes(ref.probe_arith())


def test_reference_matches_expected_file(ref):
    data = json.loads(EXPECTED.read_text(encoding="utf-8"))
    entry = data["components"]["probe-arith"]
    assert entry["samples"] == SAMPLES
    assert entry["sha256"] == hashlib.sha256(le_bytes(ref.probe_arith())).hexdigest()


def test_check_passes_on_repo_file():
    code, out = run_reference("--check")
    assert code == 0, out


def test_check_fails_on_wrong_hash(tmp_path):
    data = json.loads(EXPECTED.read_text(encoding="utf-8"))
    data["components"]["probe-arith"]["sha256"] = "0" * 64
    wrong = tmp_path / "hash_expected.json"
    wrong.write_text(json.dumps(data), encoding="utf-8")
    code, out = run_reference("--check", "--expected", wrong)
    assert code == 1, out
    assert "0" * 64 in out, out


def test_write_then_check(tmp_path, ref):
    target = tmp_path / "hash_expected.json"
    target.write_text(json.dumps({"note": "kept", "components": {
        "probe-arith": {"samples": 1, "sha256": "0" * 64},
        "other": {"samples": 2, "sha256": "1" * 64},
    }}), encoding="utf-8")
    code, out = run_reference("--write", "--expected", target)
    assert code == 0, out
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["note"] == "kept"
    assert data["components"]["other"] == {"samples": 2, "sha256": "1" * 64}
    # Story 1.6: the entry carries scope "probe" (tools/hash_compare.py
    # --must-differ requires it), so --write must keep it.
    assert data["components"]["probe-arith"] == {
        "samples": SAMPLES,
        "sha256": hashlib.sha256(le_bytes(ref.probe_arith())).hexdigest(),
        "scope": "probe",
    }
    code, out = run_reference("--check", "--expected", target)
    assert code == 0, out


def test_out_writes_reference_bytes(tmp_path, ref):
    code, out = run_reference("--out", tmp_path)
    assert code == 0, out
    data = (tmp_path / "probe-arith.f32").read_bytes()
    assert len(data) == SAMPLES * 4
    assert data == le_bytes(ref.probe_arith())


def test_fused_computation_changes_the_output(ref):
    """Contraction must change the bits, or the contract-mustfail job proves nothing."""
    assert "contract" in (ref.__doc__ or "").lower(), "module must document contractable expressions"
    fused = ref.probe_arith_fused()
    assert fused.dtype == np.float32 and fused.shape == (SAMPLES,)
    assert le_bytes(fused) != le_bytes(ref.probe_arith())


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
def probe_build(tmp_path_factory):
    build = tmp_path_factory.mktemp("hashprobe") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    return build, code, out


@pytest.mark.skipif(CMAKE is None, reason="cmake is not on PATH")
def test_host_probe_matches_reference(probe_build, tmp_path, ref):
    build, code, out = probe_build
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path / "probe-out"
    out_dir.mkdir()
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True,
                                timeout=120)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    data = (out_dir / "probe-arith.f32").read_bytes()
    assert len(data) == SAMPLES * 4
    assert data == le_bytes(ref.probe_arith())
