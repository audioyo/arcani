"""Hash probe component `components` (Story 3.1).

The component table carries no sample, so the hash probe hashes its bits to
prove the table is the same on all four platforms (scope `engine`).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe;
Story 3.1 spec, Implementation Notes):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/components.f32, the
  component after `loop-48000`. For each case of the vectors'
  `component_constants.probe_cases`, in order (the recipe text embedded like
  the other probe fixtures, compiled at 48000 Hz, no muted ear): one float32
  holding the row count, then per row 21 float32 values: layer, ear,
  gamma_mult, theta_mult, beat_mult as their integer values (layer 0
  theta_reference, 1 gamma_pac, 2 binaural; ear 0 left, 1 right), then
  center_hz, low_hz, high_hz, level, each as the four 16-bit words of its
  binary64 pattern, most significant first, every word a float32 in 0 to
  65535.
- So the component holds 6 + 21 * 314 = 6600 samples, and its decoded table
  of each case equals the Python reference table within rows
  component-level-error and component-frequency-error, the same rows in the
  same order.
- The earlier components keep their names.
- The expected entry `components` (scope `engine`, 6600 samples) arrives only
  after a green four-platform full run; until then that test fails.

The real build follows tests/python/test_probe_loop.py and skips only when
cmake is not on PATH, or when Windows application control blocks the probe
binary (winerror 4551 or 1260).
"""

import json
import os
import shutil
import struct
import subprocess
import sys

import numpy as np
import pytest

import components_common as common
from assertions.tables import load_tables

REPO_ROOT = common.REPO_ROOT
PROBE_SOURCE = REPO_ROOT / "tests" / "hashprobe" / "main.cpp"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"

COMPONENT = "components"
PROBE_RATE = 48000
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
VALUES_PER_ROW = 21
WANT_ROWS = (106, 46, 72, 64, 24, 2)
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-",
                      "gamma-uncoupled-", "gamma-swell-", "binaural-cycle-", "gamma-bursts-", "rate-curves-",
                      "loop-")


def probe_cases():
    return list(common.constants()["probe_cases"])


def component_samples():
    return len(probe_cases()) + VALUES_PER_ROW * sum(len(common.want_rows(n)) for n in probe_cases())


def encode(tables):
    """The probe encoding of a list of tables, as float32 (the harness's own, for the decoder's must-fail)."""
    out = []
    for table in tables:
        out.append(float(len(table)))
        for r in table:
            out += [float(common.LAYERS.index(r.layer)), float(common.EARS.index(r.ear)), float(r.gamma_mult),
                    float(r.theta_mult), float(r.beat_mult)]
            for v in (r.center_hz, r.low_hz, r.high_hz, r.level):
                bits = struct.unpack("<Q", struct.pack("<d", float(v)))[0]
                out += [float((bits >> s) & 0xFFFF) for s in (48, 32, 16, 0)]
    return np.asarray(out, dtype=np.float32)


def decode(data, count):
    """`count` tables decoded from the float32 samples; asserts the encoding rules."""
    data = np.asarray(data, dtype=np.float32)
    values = data.astype(np.float64)
    assert np.all(values == np.floor(values)), "a probe value is not a whole number"
    tables = []
    at = 0
    for _ in range(count):
        n = int(values[at])
        at += 1
        table = []
        for _ in range(n):
            v = values[at:at + VALUES_PER_ROW]
            assert v.size == VALUES_PER_ROW, "truncated row"
            at += VALUES_PER_ROW
            layer, ear = int(v[0]), int(v[1])
            assert 0 <= layer < len(common.LAYERS) and 0 <= ear < len(common.EARS), (layer, ear)
            words = [int(w) for w in v[5:]]
            assert all(0 <= w <= 0xFFFF for w in words), words
            doubles = []
            for k in range(4):
                bits = 0
                for w in words[4 * k:4 * k + 4]:
                    bits = (bits << 16) | w
                doubles.append(struct.unpack("<d", struct.pack("<Q", bits))[0])
            table.append(common.Row(common.LAYERS[layer], common.EARS[ear], *doubles,
                                    int(v[2]), int(v[3]), int(v[4])))
        tables.append(table)
    assert at == values.size, (at, values.size)
    return tables


# ------------------------------------------------- without a build


def test_probe_cases_are_the_spec_probe_cases():
    names = probe_cases()
    assert names == ["theta-smoothed-on-off-1hz", "theta-sawtooth-6hz", "bursts-45hz", "bursts-60hz",
                     "gamma-cycle-swell-theta-cycle", "binaural-cycle-sleep"]
    assert tuple(len(common.want_rows(n)) for n in names) == WANT_ROWS
    assert component_samples() == 6600
    for n in names:
        assert common.case(n)["mute"] == "none", n


def test_decoder_round_trips_and_must_fail_catches_a_flipped_bit():
    tables = [common.want_rows(n) for n in probe_cases()]
    data = encode(tables)
    assert data.size == component_samples()
    got = decode(data, len(tables))
    for g, w in zip(got, tables):
        assert g == w
    # One low bit of one level flipped: the decoded value differs, though within the error rows.
    flipped = data.copy()
    flipped[1 + VALUES_PER_ROW - 1] = float(int(flipped[1 + VALUES_PER_ROW - 1]) ^ 1)
    bad = decode(flipped, len(tables))
    assert bad[0][0] != tables[0][0]
    # A word out of range or a fraction is refused.
    for value in (65536.0, 0.5):
        broken = data.copy()
        broken[1 + 5] = value
        with pytest.raises(AssertionError):
            decode(broken, len(tables))
    with pytest.raises(AssertionError):
        decode(data[:-1], len(tables))


def test_probe_source_names_the_components_component_after_loop_48000():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    loop = text.find('{"loop-48000"')
    assert loop >= 0
    comp = text.find(f'{{"{COMPONENT}"', loop)
    assert comp > loop, "no components entry after loop-48000 in the probe's component list"
    assert "arc_plan_component" in text
    # The probe embeds each probe case's layers; every layer value text of the case appears.
    for name in probe_cases():
        for layer, obj in common.case_layers(name).items():
            assert f'"{layer}"' in text or f'\\"{layer}\\"' in text, (name, layer)


def test_expected_entry_names_the_components_component():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    entry = components.get(COMPONENT)
    assert entry is not None, f"no ci/hash_expected.json entry {COMPONENT} (after the full run)"
    assert entry.get("scope") == "engine", entry
    assert entry.get("samples") == component_samples(), entry


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
    build = tmp_path_factory.mktemp("hashprobe-components") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-components-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


def test_components_component_decodes_to_the_reference_table(probe_output):
    path = probe_output / f"{COMPONENT}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4")
    assert data.size == component_samples(), data.size
    tables = decode(data, len(probe_cases()))
    reference = common.reference_components()
    for name, got in zip(probe_cases(), tables):
        assert got, name
        want = common.as_rows(reference.component_table(common.case_recipe(name)))
        problems = common.compare(got, want)
        assert not problems, f"{name} against the reference:\n" + "\n".join(problems)
        problems = common.compare(got, common.want_rows(name))
        assert not problems, f"{name} against the vectors:\n" + "\n".join(problems)


def test_earlier_components_are_still_written(probe_output):
    names = {p.stem for p in probe_output.iterdir() if p.suffix == ".f32"}
    for prefix in EARLIER_COMPONENTS:
        if prefix == "probe-arith":
            assert prefix in names, sorted(names)
            continue
        for fs in SAMPLE_RATES:
            assert f"{prefix}{fs}" in names, (prefix, fs, sorted(names))
