"""Shared harness of the Story 4.3 true-peak tests (not a test file).

The true-peak vectors (tests/data/signal_spec_vectors.json, keys
`true_peak_constants`, `true_peak_filter`, `true_peak_signals`,
`true_peak_steps`; docs/signal-spec.md, True peak), the three true-peak rows
read through the assertion call `assertions.row` (`true-peak`,
`true-peak-meter-over`, `true-peak-meter-under`), the calibration synthesis
rule (True peak, Calibration, Signal) written here on its own in binary64,
a harness integer meter and its must-fail variants, and the harness
sample-peak check (never a stand-in for the meter).

The vector constants are cross-checked against the rows, never used in
their place. No threshold is written here as a literal.
"""

import hashlib
import importlib
import json
import math

import numpy as np

import preview_common as common
from assertions import row as table_row

REPO_ROOT = common.REPO_ROOT
FIXTURES_VALID = common.FIXTURES_VALID

CEILING_ROW = "true-peak"
OVER_ROW = "true-peak-meter-over"
UNDER_ROW = "true-peak-meter-under"
KEYS = ("true_peak_constants", "true_peak_filter", "true_peak_signals", "true_peak_steps")
MEMBERS = ["linear", "dbtp"]

_vectors = None


def vectors():
    global _vectors
    if _vectors is None:
        _vectors = json.loads(common.VECTORS.read_text(encoding="utf-8"))
        for key in KEYS:
            assert key in _vectors, f"the vectors file has no {key} (Story 4.3)"
    return _vectors


def constants():
    return vectors()["true_peak_constants"]


def sample_rates():
    r = table_row("sample-rates")
    assert r.unit == "Hz", r
    return [int(v) for v in r.values]


# ------------------------------------------------------------ rows


def ceiling_dbtp():
    r = table_row(CEILING_ROW)
    assert r.kind == "thresholds" and r.unit == "dBTP", r
    return r.value


def over_db():
    r = table_row(OVER_ROW)
    assert r.kind == "thresholds" and r.unit == "dB", r
    return r.value


def under_db():
    r = table_row(UNDER_ROW)
    assert r.kind == "thresholds" and r.unit == "dB", r
    return r.value


# ------------------------------------------------------------ the meter under test


def meter():
    """tests/assertions/true_peak.py, imported as assertions.true_peak."""
    return importlib.import_module("assertions.true_peak")


# ------------------------------------------------------------ filter


def filter_integers():
    """n_p[k] as an int64 array of shape (4, 12), from the vectors."""
    k = constants()
    n = np.zeros((int(k["oversampling"]), int(k["taps"])), dtype=np.int64)
    seen = set()
    for r in vectors()["true_peak_filter"]:
        p, t = int(r["phase"]), int(r["tap"])
        assert (p, t) not in seen, r
        seen.add((p, t))
        n[p, t] = int(r["integer"])
    assert len(seen) == n.size
    return n


# ------------------------------------------------------------ synthesis


def seconds_to_samples(t_s, fs):
    """Core, seconds-to-samples rule, harness copy: t * fs (one rounding), nearest, ties to even."""
    t = float(t_s)
    if not (t >= 0.0) or math.isinf(t):
        return 0
    x = t * float(fs)
    if not (x < 2.0 ** 64):
        return 0
    return int(round(x))


def signals(fs=None, role=None):
    rows = vectors()["true_peak_signals"]
    return [r for r in rows if (fs is None or r["fs"] == fs) and (role is None or r["role"] == role)]


def signal(name, fs):
    found = [r for r in signals(fs) if r["signal"] == name]
    assert len(found) == 1, (name, fs)
    return found[0]


def fade(frames, fade_frames):
    """True peak, Calibration, Signal: the raised-cosine fade-in and fade-out, binary64."""
    n = np.arange(frames, dtype=np.float64)
    w = np.ones(frames, dtype=np.float64)
    head = n < fade_frames
    tail = n >= frames - fade_frames
    w[head] = (1.0 - np.cos(math.pi * n[head] / fade_frames)) / 2.0
    w[tail] = (1.0 - np.cos(math.pi * (frames - 1 - n[tail]) / fade_frames)) / 2.0
    return w


def rounded_24(s):
    """s * 2^23 to the nearest integer, ties to even, clamped to the 24-bit range (int64)."""
    x = np.rint(np.asarray(s, dtype=np.float64) * float(1 << 23))
    return np.clip(x, -(1 << 23), (1 << 23) - 1).astype(np.int64)


def synthesize(v, fade_in=True, fade_out=True):
    """The 24-bit integers of signal vector v, shape (frames, 2): a stereo
    sine at fs / D, amplitude A, phase phi, with the 10 ms raised-cosine
    fades. fade_out=False drops the fade-out (a signal cut short at its
    end), fade_in=False the fade-in (an abrupt start); both are harness
    must-fail signals, never a vector."""
    fs = int(v["fs"])
    frames = seconds_to_samples(constants()["signal_s"], fs)
    fade_frames = seconds_to_samples(constants()["fade_s"], fs)
    assert frames == int(v["frames"]) and fade_frames == int(v["fade_frames"]), v
    a = float(v["amplitude"])
    d = float(v["divisor"])
    phi = float(v["phase_deg"])
    n = np.arange(frames, dtype=np.float64)
    w = fade(frames, fade_frames)
    if not fade_in:
        w[:frames // 2] = 1.0
    if not fade_out:
        w[frames // 2:] = 1.0
    s = a * w * np.sin(2.0 * math.pi * n / d + phi * math.pi / 180.0)
    x = rounded_24(s)
    return np.column_stack((x, x))


def data_bytes(x24):
    """3 bytes per sample, little-endian, left then right per frame (the WAV data)."""
    return common.data_bytes(np.asarray(x24, dtype=np.int64).reshape(-1))


def samples_sha256(x24):
    return hashlib.sha256(data_bytes(x24)).hexdigest()


# ------------------------------------------------------------ harness meters


def harness_peak_integer(x24, phases=None, drop_head=0, drop_tail=0):
    """max |sum n_p[k] v[m - k]| over every output of every channel, an
    exact Python int. phases limits the phases; drop_head / drop_tail drop
    that many outputs per phase from the start / end (must-fails)."""
    n = filter_integers()
    x = np.asarray(x24, dtype=np.int64)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    best = 0
    for c in range(x.shape[1]):
        for p in (range(n.shape[0]) if phases is None else phases):
            y = np.convolve(x[:, c], n[p])
            y = y[drop_head:y.size - drop_tail]
            if y.size:
                best = max(best, int(np.max(np.abs(y))))
    return best


def harness_true_peak(x24, **kwargs):
    return harness_peak_integer(x24, **kwargs) / float(1 << 36)


def dbtp(tp):
    return -math.inf if tp == 0.0 else 20.0 * math.log10(tp)


def sample_peak_dbfs(x24):
    """The harness sample peak, 20 log10(max |v| / 2^23); harness only."""
    peak = int(np.max(np.abs(np.asarray(x24, dtype=np.int64)))) if np.asarray(x24).size else 0
    return -math.inf if peak == 0 else 20.0 * math.log10(peak / float(1 << 23))


def sample_peak_check(x24):
    """'pass' when the sample peak is at or below row true-peak (harness only)."""
    return "pass" if sample_peak_dbfs(x24) <= ceiling_dbtp() else "fail"


def calibration_problems(reading_dbtp, expected_dbtp, over, under):
    if not math.isfinite(reading_dbtp):
        return [f"reading {reading_dbtp} is not finite"]
    diff = reading_dbtp - expected_dbtp
    if not (-under <= diff <= over):
        return [f"reading {reading_dbtp!r} dBTP is {diff:+.6f} dB from {expected_dbtp!r}, outside +{over}/-{under} dB"]
    return []


# ------------------------------------------------------------ reports


def true_peak_assertion(report):
    found = [a for a in report["assertions"] if a["name"] == "true_peak"]
    assert len(found) == 1, report["assertions"]
    return found[0]
