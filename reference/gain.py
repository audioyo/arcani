"""Reference gain schedules (docs/signal-spec.md, Gain ramps; Story 4.4).

Implemented from the signal spec only, never from engine code, engine
binaries, or engine output (AD-16, AD-19). Every value is binary64 with
NumPy's cosine, never the engine's approximation.

- frames(gain, fs): [(n0, L, n1, a, b)] per ramp of one gain member, in
  array order (Gain ramps, Ramp frames): n0 = seconds_to_samples(start_s),
  L = seconds_to_samples(duration_s), n1 = n0 + L, a the gain before the
  ramp (initial for the first), b its `to`. [] for None.
- values(gain, fs, n): the binary64 gains of a uint64 frame index array by
  the reference law. Segments by exact integer comparisons: initial before
  the first ramp, the ramp on [n0, n1), b held from n1 on. On a ramp,
  k = n - n0, r = k / L (one binary64 division), h = (1.0 -
  numpy.cos(numpy.pi * r)) * 0.5, g = a + (b - a) * h, in that order.
  1.0 for every frame when gain is None.

NumPy, the standard library, and reference/ only.
"""

import numpy as np

from . import ideal


def frames(gain, fs):
    """Ramp frames of one gain member."""
    if gain is None:
        return []
    out = []
    before = float(gain["initial"])
    for ramp in gain.get("ramps", []):
        n0 = ideal.seconds_to_samples(float(ramp["start_s"]), fs)
        length = ideal.seconds_to_samples(float(ramp["duration_s"]), fs)
        to = float(ramp["to"])
        out.append((n0, length, n0 + length, before, to))
        before = to
    return out


def values(gain, fs, n):
    """The gain at each frame of the uint64 index array n."""
    idx = np.asarray(n, dtype=np.uint64)
    if gain is None:
        return np.ones(idx.size, dtype=np.float64)
    g = np.full(idx.size, float(gain["initial"]), dtype=np.float64)
    for n0, length, n1, a, b in frames(gain, fs):
        on = (idx >= np.uint64(n0)) & (idx < np.uint64(n1))
        k = (idx[on] - np.uint64(n0)).astype(np.float64)   # exact: k < 2^53
        r = k / float(length)
        h = (1.0 - np.cos(np.pi * r)) * 0.5
        g[on] = a + (b - a) * h
        g[idx >= np.uint64(n1)] = b
    return g
