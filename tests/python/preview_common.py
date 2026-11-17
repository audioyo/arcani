"""Shared harness of the Story 3.3 listening preview tests (not a test file).

The preview vectors (tests/data/signal_spec_vectors.json, keys
`preview_constants`, `preview_gains`, `preview_layers`, `preview_frames`;
docs/signal-spec.md, Preview), the three preview rows read through the
assertion call `assertions.row` (`preview-length`, `preview-seam-tail`,
`preview-peak-level`), the spec 24-bit rounding rule written here
independently of cli/, a WAV reader for the CLI's 2-channel 24-bit files,
and the paths of the built binaries.

The vector constants are cross-checked against the rows, never used in
their place. No threshold is written here as a literal.
"""

import importlib
import json
import os
import shutil
import struct
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
REFERENCE_PREVIEW = REPO_ROOT / "reference" / "preview.py"
GENERATOR = REPO_ROOT / "tools" / "signal_spec_vectors.py"
RENDER_PREVIEWS = REPO_ROOT / "tools" / "render_previews.py"
CHECKLIST = REPO_ROOT / "_bmad-output" / "implementation-artifacts" / "listening-3-3-preview.md"

LENGTH_ROW = "preview-length"
SEAM_TAIL_ROW = "preview-seam-tail"
PEAK_ROW = "preview-peak-level"
EARS = ("left", "right")
LAYERS = ("theta_reference", "gamma_pac", "binaural")

CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE = ".exe" if sys.platform == "win32" else ""
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / f"arcani-tapdump{EXE}"
RENDER = REPO_ROOT / "build" / PRESET / "cli" / f"arcani-render{EXE}"

_vectors = None


def vectors():
    global _vectors
    if _vectors is None:
        _vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        for key in ("preview_constants", "preview_gains", "preview_layers", "preview_frames"):
            assert key in _vectors, f"the vectors file has no {key} (Story 3.3)"
    return _vectors


def constants():
    return vectors()["preview_constants"]


def gain_rows():
    return vectors()["preview_gains"]


def layer_rows():
    return vectors()["preview_layers"]


def frame_rows():
    return vectors()["preview_frames"]


def frame_row(fixture, fs):
    found = [r for r in frame_rows() if r["fixture"] == fixture and r["fs"] == fs]
    assert len(found) == 1, (fixture, fs)
    return found[0]


def gain_row(peak, layers_max):
    found = [r for r in gain_rows() if float(r["peak_dbfs"]) == peak and r["layers_max"] == max(layers_max, 1)]
    assert len(found) == 1, (peak, layers_max)
    return found[0]


def from_bits(text):
    """A binary64 from its bits as 0x hex text."""
    return struct.unpack("<d", struct.pack("<Q", int(text, 16)))[0]


def bits(x):
    return f"0x{struct.unpack('<Q', struct.pack('<d', float(x)))[0]:016x}"


def ideal(text):
    return float(Decimal(text))


# ------------------------------------------------------------ rows


def length_s():
    r = table_row(LENGTH_ROW)
    assert r.kind == "thresholds" and r.unit == "s", r
    return r.value


def seam_tail_s():
    r = table_row(SEAM_TAIL_ROW)
    assert r.kind == "thresholds" and r.unit == "s", r
    return r.value


def peak_dbfs():
    r = table_row(PEAK_ROW)
    assert r.kind == "thresholds" and r.unit == "dBFS", r
    return r.value


def gain():
    """g at row preview-peak-level for two layers per ear (every fixture of the preview set), from the vectors."""
    return from_bits(gain_row(peak_dbfs(), 2)["gain_bits"])


def amplitude():
    """10^(P/20) at row preview-peak-level, from the vectors."""
    return float.fromhex(gain_row(peak_dbfs(), 1)["amplitude_hex"])


# ------------------------------------------------------------ recipes


def load_fixture(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def layers_per_ear(recipe, mute="none"):
    """Preview, Layers, from the recipe fields (harness copy, independent of reference/)."""
    shared = sum(1 for layer in ("theta_reference", "gamma_pac") if layer in recipe)
    return {ear: shared + (1 if "binaural" in recipe and mute != ear else 0) for ear in EARS}


# ------------------------------------------------------------ modules


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def reference_preview():
    """The Python reference preview module (reference/preview.py)."""
    assert REFERENCE_PREVIEW.is_file(), f"missing {REFERENCE_PREVIEW} (Story 3.3 reference preview)"
    _repo_on_path()
    return importlib.import_module("reference.preview")


def reference_module(name):
    _repo_on_path()
    return importlib.import_module(f"reference.{name}")


def generator():
    """tools/signal_spec_vectors.py, loaded from its file."""
    assert GENERATOR.is_file(), f"missing {GENERATOR}"
    spec = importlib.util.spec_from_file_location("signal_spec_vectors_for_preview", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ 24-bit rounding


def quantize_24(samples):
    """docs/signal-spec.md, 24-bit rounding, on a float64 array: NaN gives 0;
    x = s * 2^23 (exact); x >= 8388607 gives 8388607, x <= -8388608 gives
    -8388608; else the nearest integer, ties to even (np.rint)."""
    s = np.asarray(samples, dtype=np.float64)
    x = s * float(2 ** 23)
    out = np.rint(np.where(np.isnan(x), 0.0, x))
    out = np.where(x >= 8388607.0, 8388607.0, out)
    out = np.where(x <= -8388608.0, -8388608.0, out)
    return out.astype(np.int32)


def preview_samples(out, g):
    """quantize_24(out * g), one binary64 multiplication per sample."""
    return quantize_24(np.asarray(out, dtype=np.float64) * g)


# ------------------------------------------------------------ WAV


def wav_layout(path):
    """(header_bytes, frames, rate) of a CLI WAV (RIFF 44 bytes, or RF64 80 bytes)."""
    with open(path, "rb") as f:
        head = f.read(80)
    assert head[8:12] == b"WAVE", path
    if head[0:4] == b"RIFF":
        assert head[12:16] == b"fmt " and head[36:40] == b"data", path
        header, fmt = 44, 12
        data = struct.unpack("<I", head[40:44])[0]
    else:
        assert head[0:4] == b"RF64" and head[12:16] == b"ds64", path
        header, fmt = 80, 48
        data = struct.unpack("<Q", head[28:36])[0]
    assert head[fmt:fmt + 4] == b"fmt ", path
    channels, rate = struct.unpack("<HI", head[fmt + 10:fmt + 16])
    assert channels == 2 and struct.unpack("<H", head[fmt + 22:fmt + 24])[0] == 24, path
    assert data % 6 == 0, path
    assert os.path.getsize(path) == header + data, f"{path}: size is not header + data"
    return header, data // 6, rate


def read_frames(path, start, count):
    """Interleaved int32 samples of frames [start, start + count) of a CLI WAV."""
    header, frames, _ = wav_layout(path)
    assert 0 <= start and start + count <= frames, (start, count, frames)
    with open(path, "rb") as f:
        f.seek(header + 6 * start)
        raw = f.read(6 * count)
    b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
    return np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.int32)


def data_bytes(samples):
    """3 bytes per sample, little-endian two's complement."""
    v = np.asarray(samples, dtype=np.int64) & 0xFFFFFF
    out = np.empty((v.size, 3), dtype=np.uint8)
    out[:, 0] = v & 0xFF
    out[:, 1] = (v >> 8) & 0xFF
    out[:, 2] = (v >> 16) & 0xFF
    return out.tobytes()


# ------------------------------------------------------------ binaries


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [CMAKE, *args]


def build(target, path):
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    result = subprocess.run(cmake_command(["--build", "--preset", PRESET, "--target", target]),
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900, env=os.environ.copy())
    assert result.returncode == 0, (
        f"building {target} failed (configure the {PRESET} preset first):\n{result.stdout}{result.stderr}")
    assert path.is_file(), f"{target} not at {path}"
    return path


def run(exe, args, timeout=300, **kwargs):
    try:
        return subprocess.run([str(exe), *[str(a) for a in args]], capture_output=True, text=True, timeout=timeout,
                              **kwargs)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked {Path(exe).name} (winerror {e.winerror})")
        raise


def tapdump_window(tapdump, recipe_path, fs, start, frames, out_dir):
    """out.f64 of `arcani-tapdump RECIPE RATE OUT_DIR --window START FRAMES`, interleaved float64."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    r = run(tapdump, [recipe_path, fs, out_dir, "--window", start, frames])
    assert r.returncode == 0, r.stdout + r.stderr
    data = np.fromfile(out_dir / "out.f64", dtype="<f8")
    assert data.size == 2 * frames, (data.size, frames)
    return data


def tapdump_whole(tapdump, recipe_path, fs, out_dir):
    """out.f64 of the whole session (`--output-only`), interleaved float64."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    r = run(tapdump, [recipe_path, fs, out_dir, "--output-only"])
    assert r.returncode == 0, r.stdout + r.stderr
    return np.fromfile(out_dir / "out.f64", dtype="<f8")
