"""Writes the calibration signals for the binaural isolation measurement (Story 1.2; band mode Story 2.5).

Usage:
  python tools/isolation_calibration.py            write tests/data/isolation_calibration.json
  python tools/isolation_calibration.py --check    exit 0 if the file equals a fresh run, else 1
  --out FILE selects another file for writing and --check.

The isolation measurement (tests/cpp/isolation.hpp) uses the muted-ear
method: with one ear's binaural oscillator muted, it reads the muted channel's
level at the active ear's carrier, relative to the active channel's own
carrier, with a Hann-windowed single-bin DFT. Before it judges any engine
render it must read signals with a known answer. These are those signals:

- Each setup has a sample rate, an active channel (left or right), and an
  active carrier. The active channel is a unit-amplitude unmodulated sine at
  that carrier, phase 0 at sample 0.
- Each case adds a muted channel: an unmodulated sine at the same carrier,
  with amplitude 10^(level_db / 20) and a phase offset of PHASE_OFFSET_RAD, so
  the muted channel sits exactly level_db below the active carrier.
- Levels: -100, -91, -89, and -60 dB. Against the 90 dB engine row
  (binaural-isolation-engine) they give pass, pass, fail, fail.
- Setup 400hz-48000-left-active: 400 Hz carrier, 48 kHz, whole cycles in the
  window. Setup 406hz-44100-right-active: 406 Hz carrier, 44.1 kHz, a
  fractional number of cycles in the window, so the window has to do its work.
  Both are mode "bin" (one Hann-windowed DFT bin at the carrier).
- Band mode (Story 2.5): along a beat rate cycle the active carrier sweeps a
  band, so the measurement sums the energy over it. Each band setup's active
  channel is a unit-amplitude sine whose frequency follows the rate-curve law
  of docs/signal-spec.md, Rate curve, f(t) = center + swing *
  sin(2 pi t / period + start), from phase 0, its phase the closed-form
  integral center * t + swing * period / (2 pi) * (cos(start) -
  cos(2 pi t / period + start)). The muted channel is the same swept sine at
  level_db with the PHASE_OFFSET_RAD offset, so its energy over the band is
  exactly level_db below the active channel's. Setup
  sweep-100-103hz-48000-left-active: 101.5 Hz center, 1.5 Hz swing (100 to
  103 Hz), 0.5 s period, start 270 degrees, 48 kHz. Setup
  sweep-403-406hz-44100-right-active: 403 Hz center, 3 Hz swing (400 to
  406 Hz), the same period and start, 44.1 kHz. Each lasts DURATION_BAND_S
  and names its band (band_lo_hz, band_hi_hz, the swept carrier's minimum
  and maximum).

Samples are computed in binary64 with math.sin (test tooling, not engine
code), rounded to float32 (round to nearest, ties to even), and stored as
base64 of little-endian float32, so the file stays text (the wording check
skips binary files and must still scan this one). The levels are data, not
thresholds: the verdicts come from the threshold rows at test time.

Standard library only.
"""

import argparse
import base64
import json
import math
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "tests" / "data" / "isolation_calibration.json"

DURATION_S = 0.1
DURATION_BAND_S = 0.5
PHASE_OFFSET_RAD = 1.0
LEVELS_DB = (-100, -91, -89, -60)

# (id, fs, carrier_hz, active channel)
SETUPS = (
    ("400hz-48000-left-active", 48000, 400.0, "left"),
    ("406hz-44100-right-active", 44100, 406.0, "right"),
)

# (id, fs, center_hz, swing_hz, period_s, start_deg, active channel)
BAND_SETUPS = (
    ("sweep-100-103hz-48000-left-active", 48000, 101.5, 1.5, 0.5, 270.0, "left"),
    ("sweep-403-406hz-44100-right-active", 44100, 403.0, 3.0, 0.5, 270.0, "right"),
)


def frames(fs):
    return round(DURATION_S * fs)


def sine(fs, carrier_hz, n_frames, amplitude, phase_rad):
    w = 2.0 * math.pi * carrier_hz / fs
    return [amplitude * math.sin(w * n + phase_rad) for n in range(n_frames)]


def swept_sine(fs, center_hz, swing_hz, period_s, start_deg, n_frames, amplitude, phase_rad):
    """A sine on the rate-curve law, its phase the closed-form integral (radians)."""
    start = math.radians(start_deg)
    k = swing_hz * period_s / (2.0 * math.pi)
    out = []
    for n in range(n_frames):
        t = n / fs
        cycles = center_hz * t + k * (math.cos(start) - math.cos(2.0 * math.pi * t / period_s + start))
        cycles -= math.floor(cycles)
        out.append(amplitude * math.sin(2.0 * math.pi * cycles + phase_rad))
    return out


def encode(samples):
    raw = struct.pack(f"<{len(samples)}f", *samples)
    return base64.b64encode(raw).decode("ascii")


def decode(text):
    raw = base64.b64decode(text.encode("ascii"), validate=True)
    if len(raw) % 4:
        raise ValueError("base64 payload is not a whole number of float32 samples")
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


def build():
    setups = []
    for setup_id, fs, carrier_hz, active in SETUPS:
        n = frames(fs)
        cases = []
        for level_db in LEVELS_DB:
            amplitude = 10.0 ** (level_db / 20.0)
            cases.append({
                "level_db": level_db,
                "muted": encode(sine(fs, carrier_hz, n, amplitude, PHASE_OFFSET_RAD)),
            })
        setups.append({
            "id": setup_id,
            "mode": "bin",
            "fs": fs,
            "carrier_hz": carrier_hz,
            "active_channel": active,
            "frames": n,
            "active": encode(sine(fs, carrier_hz, n, 1.0, 0.0)),
            "cases": cases,
        })
    for setup_id, fs, center, swing, period, start, active in BAND_SETUPS:
        n = round(DURATION_BAND_S * fs)
        law = (fs, center, swing, period, start, n)
        cases = []
        for level_db in LEVELS_DB:
            amplitude = 10.0 ** (level_db / 20.0)
            cases.append({
                "level_db": level_db,
                "muted": encode(swept_sine(*law, amplitude, PHASE_OFFSET_RAD)),
            })
        setups.append({
            "id": setup_id,
            "mode": "band",
            "fs": fs,
            "carrier_hz": center,
            "swing_hz": swing,
            "period_s": period,
            "start_phase_deg": start,
            "band_lo_hz": center - swing,
            "band_hi_hz": center + swing,
            "active_channel": active,
            "frames": n,
            "active": encode(swept_sine(*law, 1.0, 0.0)),
            "cases": cases,
        })
    return {
        "description": ("Calibration signals for the muted-ear isolation measurement "
                        "(tests/cpp/isolation.hpp). Mode bin: active channel a unit-amplitude "
                        "unmodulated sine at carrier_hz. Mode band: active channel a "
                        "unit-amplitude sine whose frequency follows carrier_hz + swing_hz * "
                        "sin(2 pi t / period_s + start_phase_deg), spanning band_lo_hz to "
                        "band_hi_hz. Muted channel: the same signal at level_db relative to "
                        "it, phase offset phase_offset_rad."),
        "generator": "tools/isolation_calibration.py",
        "encoding": "base64 of little-endian float32",
        "phase_offset_rad": PHASE_OFFSET_RAD,
        "setups": setups,
    }


def render(data):
    return json.dumps(data, indent=2) + "\n"


def main(argv):
    parser = argparse.ArgumentParser(description="Write the isolation calibration signals.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv[1:])
    text = render(build())
    if args.check:
        try:
            found = args.out.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"isolation calibration: cannot read {args.out}: {exc}")
            return 1
        if found != text:
            print(f"isolation calibration: {args.out} differs from a fresh run of {Path(__file__).name}")
            return 1
        print(f"isolation calibration: {args.out} is current")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"isolation calibration: wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
