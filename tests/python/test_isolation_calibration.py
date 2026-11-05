"""Isolation calibration signals: known answers for the muted-ear measurement (Story 1.2).

Contract with tools/isolation_calibration.py (standard library only):

- `--check` exits 0 when tests/data/isolation_calibration.json equals a fresh
  run, 1 otherwise (`--out FILE` selects another file); with no flag it writes
  the file.
- `build()` returns the data; `encode(samples)` / `decode(text)` convert
  between a list of floats and base64 of little-endian float32.
- JSON: {"description", "generator", "encoding", "phase_offset_rad",
  "setups": [{"id", "fs", "carrier_hz", "active_channel": "left"|"right",
  "frames", "active": <base64>, "cases": [{"level_db", "muted": <base64>}]}]}.
- Levels are -100, -91, -89, and -60 dB in each setup, in that order.

This file proves the signals hold the leakage they claim, by a least-squares
sine fit that shares nothing with the C++ DFT, and that the method the C++
harness uses (tests/cpp/isolation.hpp: Hann window w[n] = 0.5 - 0.5 *
cos(2 * pi * n / N), single-bin DFT at the active carrier, level =
20 * log10(|X_muted| / |X_active|)) reads each within 0.5 dB. The C++
calibration test (tests/cpp/test_isolation.cpp) then reads the same file
with the C++ measurement. Verdicts use row binaural-isolation-engine through
the assertion call; the levels are data, not thresholds.
"""

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from assertions import row as table_row

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "isolation_calibration.py"
DATA = REPO_ROOT / "tests" / "data" / "isolation_calibration.json"
WORDING = REPO_ROOT / "tools" / "check_wording.py"

KNOWN_LEVELS_DB = [-100, -91, -89, -60]
# The least-squares fit reads float32 sines; float32 rounding moves the fitted
# amplitude by about 1e-7 relative, far inside 0.01 dB (1.2e-3 relative).
FIT_TOL_DB = 0.01
# Acceptance criterion: the measurement reads each known level within 0.5 dB.
MEASURE_TOL_DB = 0.5
ROW_UNIT = "dB below the ear's own binaural carrier"


def load_generator():
    spec = importlib.util.spec_from_file_location("isolation_calibration", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def data():
    assert DATA.is_file(), f"missing {DATA}: run python tools/isolation_calibration.py"
    return json.loads(DATA.read_text(encoding="utf-8"))


def decode(text):
    return np.asarray(load_generator().decode(text), dtype=np.float64)


def fit_amplitude(x, f_hz, fs):
    """Amplitude of the best least-squares sine at f_hz (with free phase and offset)."""
    n = np.arange(len(x), dtype=np.float64)
    w = 2.0 * math.pi * f_hz / fs
    basis = np.stack([np.cos(w * n), np.sin(w * n), np.ones_like(n)], axis=1)
    coef, *_ = np.linalg.lstsq(basis, x, rcond=None)
    return float(math.hypot(coef[0], coef[1]))


def hann_bin(x, f_hz, fs):
    n = np.arange(len(x), dtype=np.float64)
    w = 0.5 - 0.5 * np.cos(2.0 * math.pi * n / len(x))
    return abs(np.sum(w * x * np.exp(-2j * math.pi * f_hz * n / fs)))


def level_db(muted, active):
    return 20.0 * math.log10(muted / active)


def engine_row_db():
    row = table_row("binaural-isolation-engine")
    assert row.unit == ROW_UNIT, row
    return row.value


# ---------------------------------------------------------------- generator


def test_generator_check_passes_on_repo_file():
    result = subprocess.run([sys.executable, str(GENERATOR), "--check"], capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_generator_check_fails_on_tampered_copy(tmp_path, data):
    tampered = dict(data)
    tampered["phase_offset_rad"] = data["phase_offset_rad"] + 1.0
    path = tmp_path / "isolation_calibration.json"
    path.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8", newline="\n")
    result = subprocess.run([sys.executable, str(GENERATOR), "--check", "--out", str(path)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "differs" in result.stdout


def test_encode_decode_round_trip_is_float32():
    gen = load_generator()
    values = [0.0, 1.0, -1.0, 1e-5, 0.1]
    back = gen.decode(gen.encode(values))
    assert back == [float(np.float32(v)) for v in values]
    with pytest.raises(ValueError):
        gen.decode("AAAA")  # 3 bytes: not a whole float32


# ---------------------------------------------------------------- structure


def test_file_layout(data):
    assert data["generator"] == "tools/isolation_calibration.py"
    assert data["encoding"] == "base64 of little-endian float32"
    assert len(data["setups"]) >= 2
    channels = set()
    for setup in data["setups"]:
        assert setup["fs"] in (44100, 48000), setup["id"]
        assert setup["active_channel"] in ("left", "right"), setup["id"]
        channels.add(setup["active_channel"])
        assert [c["level_db"] for c in setup["cases"]] == KNOWN_LEVELS_DB, setup["id"]
        assert decode(setup["active"]).shape == (setup["frames"],), setup["id"]
        for case in setup["cases"]:
            assert decode(case["muted"]).shape == (setup["frames"],), (setup["id"], case["level_db"])
    assert channels == {"left", "right"}, "each ear must be the active ear in some setup"
    cycles = [s["carrier_hz"] * s["frames"] / s["fs"] for s in data["setups"]]
    assert any(abs(c - round(c)) > 0.1 for c in cycles), (
        "at least one setup needs a fractional number of carrier cycles in the window")


def test_file_passes_the_wording_check():
    result = subprocess.run([sys.executable, str(WORDING), str(DATA)], capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------- known answers


def setup_cases(data):
    for setup in data["setups"]:
        active = decode(setup["active"])
        for case in setup["cases"]:
            yield setup, active, case, decode(case["muted"])


def test_signals_hold_their_known_leakage(data):
    for setup, active, case, muted in setup_cases(data):
        f, fs = setup["carrier_hz"], setup["fs"]
        a_active = fit_amplitude(active, f, fs)
        a_muted = fit_amplitude(muted, f, fs)
        assert abs(a_active - 1.0) < 1e-6, setup["id"]
        got = level_db(a_muted, a_active)
        assert abs(got - case["level_db"]) <= FIT_TOL_DB, (setup["id"], case["level_db"], got)


def test_fit_catches_a_doctored_level(data):
    setup, active, case, muted = next(setup_cases(data))
    f, fs = setup["carrier_hz"], setup["fs"]
    doctored = muted * 10.0 ** (1.0 / 20.0)
    got = level_db(fit_amplitude(doctored, f, fs), fit_amplitude(active, f, fs))
    assert abs(got - case["level_db"]) > FIT_TOL_DB


def test_hann_single_bin_method_reads_each_level_within_tolerance(data):
    for setup, active, case, muted in setup_cases(data):
        f, fs = setup["carrier_hz"], setup["fs"]
        got = level_db(hann_bin(muted, f, fs), hann_bin(active, f, fs))
        assert abs(got - case["level_db"]) <= MEASURE_TOL_DB, (setup["id"], case["level_db"], got)


def test_known_levels_give_pass_pass_fail_fail_against_the_engine_row(data):
    threshold = engine_row_db()
    for setup in data["setups"]:
        verdicts = ["pass" if c["level_db"] <= -threshold else "fail" for c in setup["cases"]]
        assert verdicts == ["pass", "pass", "fail", "fail"], (setup["id"], threshold, verdicts)
