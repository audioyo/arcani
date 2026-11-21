"""Loudness meter (Story 4.1): ITU-R BS.1770-5 integrated loudness.

Implements docs/signal-spec.md, Loudness, on its own (the command-line
meter in cli/loudness.cpp is the second, independent meter). Calibrated on
EBU Tech 3341 v4.0 cases 1 to 5, synthesized in the harness
(tests/python/test_loudness_tool.py), before it judges an engine render.

- PROTOTYPE: the analog prototype of each K-weighting stage, the binary64
  constants of the spec's Vectors: K-weighting prototype.
- kweighting(fs): (shelf, highpass), each (b0, b1, b2, a1, a2), by the
  spec's binary64 formulas. ValueError unless fs is a positive multiple of 10.
- block_energies(x, fs): z[j] of every 400 ms block (one every 100 ms), the
  sum of both channels' K-weighted mean squares, from zero filter state.
  x is float64 array-like of shape (frames, 2), or (frames,) for one
  channel; an np.memmap is read in chunks. ValueError on another shape, a
  non-finite sample, or a bad fs.
- integrated_lufs(x, fs, gating=True): L in LUFS-I, -inf when no block
  passes; gating=False takes every block (the must-fail meter).
- check_loudness(x, fs, target): the report assertion shape (Story 1.4)
  against row loudness-tolerance: measured L - target in LU, pass when
  |measured| <= the row; a NaN or infinite sample fails with note
  "not finite", a -inf reading with note "silent", both with measured None.

The filter is run as a convolution with the cascade's impulse response (the
spec allows any computation of the same filter): the response is computed by
the difference equation once per rate and truncated where its tail is below
1e-30 of its peak, then applied chunk by chunk with FFTs (overlap-add), so
the output is the zero-state filter output.

NumPy and the standard library only.
"""

from __future__ import annotations

import functools
import math

import numpy as np

from . import row

TOLERANCE_ROW = "loudness-tolerance"

# BS.1770-5, Annex 1.
OFFSET_DB = -0.691
ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
BLOCK_S_NUM, BLOCK_S_DEN = 4, 10      # 400 ms, as an exact ratio
STEPS_PER_BLOCK = 4                   # 75 percent overlap

# docs/signal-spec.md, Loudness, Vectors: K-weighting prototype (binary64).
PROTOTYPE = {
    "shelf": {
        "f0": float.fromhex("0x1.a47e5d678a647p+10"),
        "Q": float.fromhex("0x1.6a12df668776cp-1"),
        "Vh": float.fromhex("0x1.95b9b16bf11c5p+0"),
        "Vb": float.fromhex("0x1.423b88ee23b99p+0"),
    },
    "highpass": {
        "f0": float.fromhex("0x1.311571c130af0p+5"),
        "Q": float.fromhex("0x1.002add8d38a3cp-1"),
        "G": float.fromhex("0x1.0147587ea05d0p+0"),
    },
}

# Impulse response: computed for at most this many samples, cut where the
# tail stays below _TAIL of the peak.
_RESPONSE_MAX = 1 << 15
_TAIL = 1e-30
# FFT size of the overlap-add.
_NFFT = 1 << 18


def _check_fs(fs):
    if isinstance(fs, bool) or not isinstance(fs, (int, np.integer)) or fs <= 0 or fs % 10 != 0:
        raise ValueError(f"sample rate {fs!r} is not a positive multiple of 10 Hz")
    return int(fs)


def _frames(fs):
    """(block frames B, step frames S)."""
    block = fs * BLOCK_S_NUM // BLOCK_S_DEN
    return block, block // STEPS_PER_BLOCK


def kweighting(fs):
    fs = _check_fs(fs)
    out = []
    for stage in ("shelf", "highpass"):
        p = PROTOTYPE[stage]
        k = math.tan(math.pi * p["f0"] / fs)
        kq = k / p["Q"]
        d = 1.0 + kq + k * k
        a1 = 2.0 * (k * k - 1.0) / d
        a2 = (1.0 - kq + k * k) / d
        if stage == "shelf":
            vh, vb = p["Vh"], p["Vb"]
            b0 = (vh + vb * kq + k * k) / d
            b1 = 2.0 * (k * k - vh) / d
            b2 = (vh - vb * kq + k * k) / d
        else:
            g = p["G"]
            b0 = g / d
            b1 = -2.0 * g / d
            b2 = g / d
        out.append((b0, b1, b2, a1, a2))
    return tuple(out)


@functools.lru_cache(maxsize=None)
def _response_spectrum(fs):
    """The rfft (size _NFFT) of the truncated impulse response, and its length."""
    stages = kweighting(fs)
    h = np.zeros(_RESPONSE_MAX)
    # Difference equation of both stages on a unit impulse, in Python floats.
    x1 = x2 = y1 = y2 = 0.0
    u1 = u2 = v1 = v2 = 0.0
    (sb0, sb1, sb2, sa1, sa2), (hb0, hb1, hb2, ha1, ha2) = stages
    for n in range(_RESPONSE_MAX):
        x = 1.0 if n == 0 else 0.0
        y = sb0 * x + sb1 * x1 + sb2 * x2 - sa1 * y1 - sa2 * y2
        x2, x1, y2, y1 = x1, x, y1, y
        v = hb0 * y + hb1 * u1 + hb2 * u2 - ha1 * v1 - ha2 * v2
        u2, u1, v2, v1 = u1, y, v1, v
        h[n] = v
    peak = float(np.max(np.abs(h)))
    above = np.nonzero(np.abs(h) >= _TAIL * peak)[0]
    length = int(above[-1]) + 1
    if length >= _RESPONSE_MAX:
        raise RuntimeError("K-weighting impulse response does not decay within its budget")
    return np.fft.rfft(h[:length], n=_NFFT), length


def _as_channels(x):
    a = x if isinstance(x, np.ndarray) else np.asarray(x, dtype=np.float64)
    if a.ndim == 1:
        a = a.reshape(-1, 1)
    if a.ndim != 2 or a.shape[1] not in (1, 2):
        raise ValueError(f"need shape (frames, 2) or (frames,), got {a.shape}")
    return a


def _step_energies(channel, fs):
    """Sum of y^2 per whole step of S frames for one channel (float64 array-like)."""
    spectrum, length = _response_spectrum(fs)
    _, step = _frames(fs)
    total = channel.shape[0]
    steps = total // step
    energies = np.zeros(steps)
    chunk = _NFFT - length + 1
    carry = np.zeros(length - 1)
    for start in range(0, steps * step, chunk):
        seg = np.asarray(channel[start:start + chunk], dtype=np.float64)
        if not np.all(np.isfinite(seg)):
            raise ValueError("not finite: the signal has a NaN or infinite sample")
        y = np.fft.irfft(np.fft.rfft(seg, n=_NFFT) * spectrum, n=_NFFT)[:seg.size + length - 1]
        y[:length - 1] += carry
        out = y[:seg.size]
        carry = y[seg.size:seg.size + length - 1].copy()
        if carry.size < length - 1:
            carry = np.concatenate([carry, np.zeros(length - 1 - carry.size)])
        stop = min(seg.size, steps * step - start)
        idx = (np.arange(stop) + start) // step
        energies += np.bincount(idx, weights=out[:stop] * out[:stop], minlength=steps)[:steps]
    if steps * step < total:
        tail = np.asarray(channel[steps * step:], dtype=np.float64)
        if not np.all(np.isfinite(tail)):
            raise ValueError("not finite: the signal has a NaN or infinite sample")
    return energies


def block_energies(x, fs):
    fs = _check_fs(fs)
    a = _as_channels(x)
    block, step = _frames(fs)
    sums = None
    for c in range(a.shape[1]):
        e = _step_energies(a[:, c], fs)
        sums = e if sums is None else sums + e
    steps = sums.size
    if steps < STEPS_PER_BLOCK:
        return np.zeros(0)
    blocks = sums[0:steps - 3] + sums[1:steps - 2] + sums[2:steps - 1] + sums[3:steps]
    return blocks / block


def _lufs(z):
    return -math.inf if z <= 0.0 else OFFSET_DB + 10.0 * math.log10(z)


def integrated_lufs(x, fs, gating=True) -> float:
    z = block_energies(x, fs)
    if z.size == 0:
        return -math.inf
    if not gating:
        return _lufs(float(np.mean(z)))
    with np.errstate(divide="ignore"):
        l = np.where(z > 0.0, OFFSET_DB + 10.0 * np.log10(np.where(z > 0.0, z, 1.0)), -np.inf)
    kept = z[l > ABSOLUTE_GATE_LUFS]
    if kept.size == 0:
        return -math.inf
    gate = _lufs(float(np.mean(kept))) + RELATIVE_GATE_LU
    kept = z[(l > ABSOLUTE_GATE_LUFS) & (l > gate)]
    if kept.size == 0:
        return -math.inf
    return _lufs(float(np.mean(kept)))


def check_loudness(x, fs, target) -> dict:
    tol = row(TOLERANCE_ROW)
    result = {"name": "loudness", "row": TOLERANCE_ROW, "threshold": tol.value, "unit": tol.unit,
              "measured": None, "result": "fail", "note": ""}
    try:
        reading = integrated_lufs(x, fs)
    except ValueError as e:
        if str(e).startswith("not finite"):
            result["note"] = "not finite"
            return result
        raise
    if reading == -math.inf:
        result["note"] = "silent"
        return result
    measured = reading - float(target)
    result["measured"] = measured
    result["result"] = "pass" if abs(measured) <= tol.value else "fail"
    return result
