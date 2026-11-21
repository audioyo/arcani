"""Shared harness of the Story 4.1 loudness tests (not a test file).

The loudness vectors (tests/data/signal_spec_vectors.json, keys
`loudness_constants`, `loudness_prototype`, `loudness_coefficients`,
`loudness_blocks`, `loudness_tech3341`, `loudness_window_cases`,
`loudness_windows`; docs/signal-spec.md, Loudness), the four loudness rows
read through the assertion call `assertions.row`
(`loudness-meter-calibration`, `loudness-meter-agreement`,
`loudness-window-min`, `loudness-tolerance`), the Tech 3341 synthesis rule
(Loudness, Calibration, Signal) written here on its own, the comparisons
the tests share, and tap dump helpers that read the float64 output through
np.memmap and delete each file as soon as it is read.

The vector constants are cross-checked against the rows, never used in
their place. No threshold is written here as a literal: the only fixed
number is the coefficient bound, half a unit in the last decimal place
BS.1770 prints (`published_decimals` of the vectors), which the spec states
is the printed precision of the standard, not a tuned tolerance.
"""

import contextlib
import gc
import importlib
import json
import math
import os
from decimal import Decimal
from pathlib import Path

import numpy as np

import preview_common as common
from assertions import row as table_row

REPO_ROOT = common.REPO_ROOT
FIXTURES_VALID = common.FIXTURES_VALID
RENDER = common.RENDER
TAPDUMP = common.TAPDUMP

CALIBRATION_ROW = "loudness-meter-calibration"
AGREEMENT_ROW = "loudness-meter-agreement"
WINDOW_MIN_ROW = "loudness-window-min"
TOLERANCE_ROW = "loudness-tolerance"
CYCLE_PERIOD_ROW = "rate-cycle-period"

KEYS = ("loudness_constants", "loudness_prototype", "loudness_coefficients", "loudness_blocks",
        "loudness_tech3341", "loudness_window_cases", "loudness_windows")
MEMBERS = ["window_start_frame", "window_body_frames", "window_repeats", "window_frames",
           "window_lufs_i", "whole_lufs_i"]

_vectors = None


def vectors():
    global _vectors
    if _vectors is None:
        _vectors = json.loads(common.VECTORS.read_text(encoding="utf-8"))
        for key in KEYS:
            assert key in _vectors, f"the vectors file has no {key} (Story 4.1)"
    return _vectors


def constants():
    return vectors()["loudness_constants"]


def sample_rates():
    r = table_row("sample-rates")
    assert r.unit == "Hz", r
    return [int(v) for v in r.values]


def ideal(text):
    return float(Decimal(text))


# ------------------------------------------------------------ rows


def calibration_lu():
    r = table_row(CALIBRATION_ROW)
    assert r.kind == "thresholds" and r.unit == "LU", r
    return r.value


def agreement_lu():
    r = table_row(AGREEMENT_ROW)
    assert r.kind == "thresholds" and r.unit == "LU", r
    return r.value


def window_min_s():
    r = table_row(WINDOW_MIN_ROW)
    assert r.kind == "thresholds" and r.unit == "s", r
    return r.value


def tolerance_lu():
    r = table_row(TOLERANCE_ROW)
    assert r.kind == "thresholds" and r.unit == "LU", r
    return r.value


def coefficient_bound():
    """Half a unit in the last decimal place BS.1770 prints (5e-15 for 14 places)."""
    return 0.5 * 10.0 ** -int(constants()["published_decimals"])


# ------------------------------------------------------------ the meter under test


def meter():
    """tests/assertions/loudness.py, imported as assertions.loudness."""
    return importlib.import_module("assertions.loudness")


# ------------------------------------------------------------ Tech 3341 synthesis


def seconds_to_samples(t_s, fs):
    """Core, seconds-to-samples rule, harness copy: t * fs (one rounding), nearest, ties to even."""
    t = float(t_s)
    if not (t >= 0.0) or math.isinf(t):
        return 0
    x = t * float(fs)
    if not (x < 2.0 ** 64):
        return 0
    return int(round(x))


def tech3341_cases(fs=None):
    rows = vectors()["loudness_tech3341"]
    return [r for r in rows if fs is None or r["fs"] == fs]


def tech3341_case(number, fs):
    found = [r for r in tech3341_cases(fs) if r["case"] == number]
    assert len(found) == 1, (number, fs)
    return found[0]


def tech3341_signal(case, fs=None):
    """Loudness, Calibration, Signal: a stereo 1 kHz sine, the level the
    per-channel peak, the same in both channels, segments back to back, the
    phase running on from frame 0 across every level change:
    x[n] = 10^(P_s / 20) * sin(2 * pi * ((1000 * n) mod fs) / fs).
    Returns a float64 array of shape (frames, 2)."""
    fs = case["fs"] if fs is None else fs
    tone = int(constants()["test_hz"])
    frames = [seconds_to_samples(d, fs) for d in case["durations_s"]]
    if fs == case["fs"]:
        assert frames == [int(f) for f in case["frames"]], (case["case"], fs, frames)
        assert sum(frames) == int(case["total_frames"]), (case["case"], fs)
    total = sum(frames)
    n = np.arange(total, dtype=np.int64)
    r = ((tone * n) % fs).astype(np.float64)
    s = np.sin(2.0 * math.pi * r / float(fs))
    amp = np.empty(total, dtype=np.float64)
    at = 0
    for level, count in zip(case["levels_dbfs"], frames):
        amp[at:at + count] = 10.0 ** (float(level) / 20.0)
        at += count
    x = amp * s
    return np.column_stack((x, x))


def calibration_problems(reading, want, tol):
    """A reading against a Tech 3341 value: within tol LU, finite."""
    if reading is None or not math.isfinite(reading):
        return [f"reading {reading} is not finite"]
    if not abs(reading - want) <= tol:
        return [f"reading {reading!r} LUFS is {reading - want:+.6f} LU from {want!r}, beyond {tol} LU"]
    return []


def agreement_problems(cpp, python, tol):
    """The command-line reading (a JSON number or None for null) against the
    Python reading (a float, -inf when silent): both null and -inf, or both
    finite and within tol LU."""
    if cpp is None or python == -math.inf:
        if cpp is None and python == -math.inf:
            return []
        return [f"command-line reading {cpp!r} and Python reading {python!r}: one is silent, the other is not"]
    if not isinstance(cpp, (int, float)) or isinstance(cpp, bool) or not math.isfinite(cpp):
        return [f"command-line reading {cpp!r} is not a finite number"]
    if not math.isfinite(python):
        return [f"Python reading {python!r} is not finite"]
    if not abs(cpp - python) <= tol:
        return [f"command-line {cpp!r} and Python {python!r} differ by {cpp - python:+.6f} LU, beyond {tol} LU"]
    return []


# ------------------------------------------------------------ windows


def window_row(fixture, fs):
    found = [r for r in vectors()["loudness_windows"] if r["fixture"] == fixture and r["fs"] == fs]
    assert len(found) == 1, (fixture, fs)
    return found[0]


def window_case(name, fs):
    found = [r for r in vectors()["loudness_window_cases"] if r["case"] == name and r["fs"] == fs]
    assert len(found) == 1, (name, fs)
    return found[0]


def member_from_vector(v):
    """The window numbers of the report member the vector names."""
    return {"window_start_frame": int(v["start_frame"]), "window_body_frames": int(v["body_frames"]),
            "window_repeats": int(v["repeats"]), "window_frames": int(v["window_frames"])}


def member_problems(member, v):
    """The report member against a window vector: members in order, window numbers equal."""
    if not isinstance(member, dict) or list(member) != MEMBERS:
        return [f"loudness members {list(member) if isinstance(member, dict) else member}, want {MEMBERS}"]
    p = []
    for key, want in member_from_vector(v).items():
        got = member[key]
        if not isinstance(got, int) or isinstance(got, bool) or got != want:
            p.append(f"{key} {got!r}, want {want}")
    for key in ("window_lufs_i", "whole_lufs_i"):
        got = member[key]
        if got is not None and (not isinstance(got, (int, float)) or isinstance(got, bool) or not math.isfinite(got)):
            p.append(f"{key} {got!r} is neither a finite number nor null")
    return p


def rejected_line(v):
    return f"rejected: parameter={v['parameter']} value={v['value']} rule={v['rule']} limit={v['limit']}"


# ------------------------------------------------------------ binaries and files


def clean_env():
    """The test process environment without ARCANI_REFERENCE_MACHINE, so the
    render speed assertion is not applicable and every report is the same."""
    env = os.environ.copy()
    env.pop("ARCANI_REFERENCE_MACHINE", None)
    return env


def render_cli(render, recipe, fs, out_dir, loudness=True, timeout=900):
    """arcani-render RECIPE --out out_dir/x.wav --rate fs [--loudness]: (result, wav, report path)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "x.wav"
    args = [recipe, "--out", wav, "--rate", fs]
    if loudness:
        args.append("--loudness")
    r = common.run(render, args, timeout=timeout, env=clean_env())
    return r, wav, out_dir / "x.report.json"


def unlink(path):
    with contextlib.suppress(FileNotFoundError):
        Path(path).unlink()


@contextlib.contextmanager
def f64_frames(path, frames=None):
    """The float64 file at `path` as an np.memmap of shape (frames, 2). On
    exit the map is closed and the file deleted (Windows cannot delete a
    mapped file)."""
    path = Path(path)
    size = path.stat().st_size
    assert size % 16 == 0, (path, size)
    if frames is not None:
        assert size == 16 * frames, (path, size, frames)
    mm = np.memmap(path, dtype="<f8", mode="r", shape=(size // 16, 2)) if size else None
    try:
        yield mm if mm is not None else np.zeros((0, 2), dtype=np.float64)
    finally:
        if mm is not None:
            handle = getattr(mm, "_mmap", None)
            del mm
            gc.collect()
            if handle is not None:
                with contextlib.suppress(BufferError, ValueError):
                    handle.close()
        unlink(path)


def tapdump(tapdump_exe, recipe, fs, out_dir, window=None, timeout=900):
    """Runs arcani-tapdump RECIPE fs out_dir --output-only, or with
    window=(start, frames) --window START FRAMES; returns the out.f64 path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    args = [recipe, fs, out_dir]
    args += ["--output-only"] if window is None else ["--window", window[0], window[1]]
    r = common.run(tapdump_exe, args, timeout=timeout)
    assert r.returncode == 0, r.stdout + r.stderr
    path = out_dir / "out.f64"
    assert path.is_file(), path
    if window is not None:
        # --window also writes the taps; only the output is read here.
        for other in out_dir.iterdir():
            if other.name != "out.f64" and other.suffix == ".f64":
                unlink(other)
    return path


def loudness_block(text):
    """The `  "loudness": {...},\\n` block of a report text, and the text without it."""
    start = text.find('  "loudness": {\n')
    assert start >= 0, text
    end = text.find("\n  },\n", start)
    assert end >= 0, text
    end += len("\n  },\n")
    return text[start:end], text[:start] + text[end:]


def file_digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()
