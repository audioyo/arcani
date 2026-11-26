"""Shared harness of the Story 4.4 gain ramp tests (not a test file).

The gain vectors (tests/data/signal_spec_vectors.json, keys
`gain_constants`, `gain_law`, `gain_fixture_ramps`, `gain_windows`,
`gain_compile_cases`; docs/signal-spec.md, Gain ramps), the three gain rows
read through the assertion call `assertions.row` (`gain-ramp-min`,
`layer-gain`, `gain-ramp-count`), harness synthesis of raised-cosine,
linear, and step gains in binary64, and tap dump helpers that read the ten
files of `arcani-tapdump --window` and delete each one as soon as it is read.

The vector constants are cross-checked against the rows, never used in
their place. No threshold is written here as a literal.
"""

import contextlib
import importlib
import json
import math
import sys
from pathlib import Path

import numpy as np

import preview_common as common
from assertions import row as table_row

REPO_ROOT = common.REPO_ROOT
FIXTURES_VALID = common.FIXTURES_VALID
RENDER = common.RENDER
TAPDUMP = common.TAPDUMP

RAMP_MIN_ROW = "gain-ramp-min"
LAYER_GAIN_ROW = "layer-gain"
RAMP_COUNT_ROW = "gain-ramp-count"
KEYS = ("gain_constants", "gain_law", "gain_fixture_ramps", "gain_windows", "gain_compile_cases")

# reference/stub_chain.py KEYS after Story 4.4, and the tap dump file of each.
TAP_KEYS = ("output", "theta", "gamma", "bus", "join", "master", "theta_gained", "gamma_gained", "binaural",
            "binaural_gained")
TAP_FILES = {"output": "out", "theta": "theta", "gamma": "gamma", "bus": "bus", "join": "join",
             "master": "master", "theta_gained": "theta_gained", "gamma_gained": "gamma_gained",
             "binaural": "binaural", "binaural_gained": "binaural_gained"}
# Before-gain tap, after-gain tap, schedule, per layer (Gain ramps, Taps).
LAYER_PAIRS = (("theta", "theta_gained", "theta_reference"), ("gamma", "gamma_gained", "gamma_pac"),
               ("binaural", "binaural_gained", "binaural"))

_vectors = None


def vectors():
    global _vectors
    if _vectors is None:
        _vectors = json.loads(common.VECTORS.read_text(encoding="utf-8"))
        for key in KEYS:
            assert key in _vectors, f"the vectors file has no {key} (Story 4.4)"
    return _vectors


def constants():
    return vectors()["gain_constants"]


def sample_rates():
    r = table_row("sample-rates")
    assert r.unit == "Hz", r
    return [int(v) for v in r.values]


# ------------------------------------------------------------ rows


def ramp_min_ms():
    r = table_row(RAMP_MIN_ROW)
    assert r.kind == "thresholds" and r.unit == "ms", r
    return r.value


def layer_gain_row():
    r = table_row(LAYER_GAIN_ROW)
    assert r.kind == "ranges" and r.unit == "ratio", r
    return r


def ramp_count_row():
    r = table_row(RAMP_COUNT_ROW)
    assert r.kind == "ranges" and r.unit == "ramps", r
    return r


# ------------------------------------------------------------ modules under test


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def tool():
    """tests/assertions/gain_ramps.py, imported as assertions.gain_ramps."""
    return importlib.import_module("assertions.gain_ramps")


def clicks():
    return importlib.import_module("assertions.clicks")


def reference_gain():
    """reference/gain.py, imported as reference.gain."""
    _repo_on_path()
    return importlib.import_module("reference.gain")


def stub_chain():
    _repo_on_path()
    return importlib.import_module("reference.stub_chain")


def reference_match():
    return importlib.import_module("assertions.reference_match")


# ------------------------------------------------------------ vectors


def seconds_to_samples(t_s, fs):
    """Core, seconds-to-samples rule, harness copy: t * fs (one rounding), nearest, ties to even."""
    t = float(t_s)
    if not (t >= 0.0) or math.isinf(t):
        return 0
    x = t * float(fs)
    if not (x < 2.0 ** 64):
        return 0
    return int(round(x))


def fixture_ramps(fixture, fs):
    return [r for r in vectors()["gain_fixture_ramps"] if r["fixture"] == fixture and r["fs"] == fs]


def window(fixture, fs):
    found = [r for r in vectors()["gain_windows"] if r["fixture"] == fixture and r["fs"] == fs]
    assert len(found) == 1, (fixture, fs)
    return found[0]


def compile_case(name):
    found = [c for c in vectors()["gain_compile_cases"] if c["case"] == name]
    assert len(found) == 1, name
    return found[0]


def load_recipe(name):
    path = FIXTURES_VALID / name
    assert path.is_file(), f"missing fixture {path} (Story 4.4)"
    return json.loads(path.read_text(encoding="utf-8"))


def schedules(recipe):
    """{schedule: gain object} of a recipe dict, in schedule order (theta, gamma, binaural, master)."""
    out = {}
    for s in constants()["schedules"]:
        holder = recipe.get(s)
        if holder is not None and "gain" in holder:
            out[s] = holder["gain"]
    return out


def edges(fixture, fs):
    """Every ramp start and end frame of a render fixture, in vector order."""
    out = []
    for r in fixture_ramps(fixture, fs):
        out += [int(r["start_frame"]), int(r["end_frame"])]
    return out


def window_start(edge, fs, end):
    """The probe window rule: 1 s from max(0, min(edge - 0.5 s, N - 1 s))."""
    length = seconds_to_samples(float(constants()["probe_window_s"]), fs)
    half = seconds_to_samples(float(constants()["probe_half_s"]), fs)
    return max(0, min(edge - half, end - length)), length


# ------------------------------------------------------------ synthesis


def raised_cosine(a, b, length):
    """The ideal ramp a + (b - a) * (1 - cos(pi k / L)) / 2 for k = 0 to L - 1, binary64, NumPy cosine."""
    k = np.arange(length, dtype=np.float64)
    return a + (b - a) * ((1.0 - np.cos(np.pi * (k / float(length)))) * 0.5)


def linear(a, b, length):
    k = np.arange(length, dtype=np.float64)
    return a + (b - a) * (k / float(length))


def gain_curve(total, initial, segments):
    """A gain of `total` frames: `initial` until the first segment, then each
    (n0, values, b): the ramp values from n0, then b held until the next."""
    g = np.full(total, float(initial), dtype=np.float64)
    for n0, values, b in segments:
        g[n0:n0 + values.size] = values
        g[n0 + values.size:] = float(b)
    return g


def tone(hz, fs, total, amplitude=1.0):
    n = np.arange(total, dtype=np.int64)
    return amplitude * np.sin(2.0 * math.pi * ((hz * n) % fs).astype(np.float64) / float(fs))


# ------------------------------------------------------------ tap dumps


def channel(x, c):
    return np.ascontiguousarray(np.asarray(x)[c::2])


def unlink(path):
    with contextlib.suppress(FileNotFoundError):
        Path(path).unlink()


def dump_window(tapdump_exe, recipe, fs, start, frames, out_dir, final=False):
    """Every tap and the output of `arcani-tapdump RECIPE fs OUT --window START FRAMES [--final]`:
    {key: float64 array of 2 * frames}; each file is deleted as soon as it is read."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    args = [recipe, fs, out_dir, "--window", start, frames] + (["--final"] if final else [])
    r = common.run(tapdump_exe, args, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    out = {}
    for key in TAP_KEYS:
        path = out_dir / f"{TAP_FILES[key]}.f64"
        assert path.is_file(), f"arcani-tapdump wrote no {path.name} (Story 4.4: ten files)"
        out[key] = np.fromfile(path, dtype="<f8").astype(np.float64)
        unlink(path)
        assert out[key].size == 2 * int(frames), (key, out[key].size, frames)
    return out
