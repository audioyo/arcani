"""Stored loudness gain: the Python loudness hash, the reference renderer in
final mode, and the Python meter on a stored final render (Story 4.2;
docs/signal-spec.md, Loudness gain).

Contract with tools/recipe_hash.py (spec Implementation Notes, Python):
`loudness_hash_value(value, schema=None)` and `loudness_hash_bytes(data,
schema=None)` give the loudness hash: SHA-256 hex of the RFC 8785 canonical
form of the object holding only the top-level members tagged
`loudness-relevant` that the recipe has. `--loudness` prints the loudness
hash instead of the recipe hash, in the same line format
("<hash>  <path>").

Contract with reference/stub_chain.py: `render(recipe_path, fs, frames=None,
start=0, mode="measure")`. With mode="final" it reads `loudness_gain_db`
from the recipe, computes k = round(100.0 * v) (ties away from zero) and g by
the spec steps in binary64 (Linear gain: binary exponentiation of
c = 0x1.004b7e9b5ce5dp+0, 1 / p for k < 0), and multiplies the master by g;
every other key is the measure-mode value. mode="measure" (the default) is
unchanged.

Contract with arcani-tapdump: an optional trailing `--final` compiles the
recipe in final mode; every other mode is unchanged. Here:
`arcani-tapdump RECIPE RATE OUT_DIR --final` (the whole session with every
tap).

Contract with the hash probe: components `stub-chain-final-44100` and
`stub-chain-final-48000`, the final-mode render of
stub-chain-1s-beat-6.json; their ci/hash_expected.json entries (scope
`engine`) arrive only after a green four-platform full run.

Vectors: tests/data/signal_spec_vectors.json, keys `loudness_gain_constants`,
`loudness_hashes`, `loudness_gain_values`; rows `loudness-gain`,
`loudness-tolerance`, `reference-match` through the assertion call. Every
store works on a temp copy, never on the checkout; each large file is
deleted as soon as it is read.
"""

import hashlib
import importlib
import importlib.util
import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import loudness_common as lc
import preview_common as common
from assertions import row as table_row

REPO_ROOT = common.REPO_ROOT
FIXTURES_VALID = common.FIXTURES_VALID
TOOL = REPO_ROOT / "tools" / "recipe_hash.py"
PROBE_SOURCE = REPO_ROOT / "tests" / "hashprobe" / "main.cpp"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
GAIN_ROW = "loudness-gain"
MATCH_ROW = "reference-match"
SAMPLE_RATES = lc.sample_rates()
MATCHED = ("output", "theta", "bus", "join", "master")
DUMP_FILES = {"output": "out", "theta": "theta", "gamma": "gamma", "bus": "bus", "join": "join", "master": "master"}

BOTH_LAYERS = "both-layers.json"
SAME_LOUDNESS_HASH = ["both-layers-metadata-edited.json", "both-layers-seed-changed.json",
                      "both-layers-engine-version-changed.json", "both-layers-schema-minor-changed.json",
                      "both-layers-reformatted.json"]
DIFFERENT_LOUDNESS_HASH = ["both-layers-beat-rate-changed.json", "both-layers-binaural-carrier-left-changed.json",
                           "both-layers-theta-carrier-changed.json", "both-layers-length-changed.json",
                           "both-layers-loudness-target-changed.json"]


def vectors():
    return json.loads(common.VECTORS.read_text(encoding="utf-8"))


def constants():
    return vectors()["loudness_gain_constants"]


def recipe_hash_tool():
    spec = importlib.util.spec_from_file_location("arcani_recipe_hash_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub_chain():
    common._repo_on_path()
    return importlib.import_module("reference.stub_chain")


def reference_match():
    return importlib.import_module("assertions.reference_match")


def from_hex(text):
    return float.fromhex(text)


def bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def gain_value(text):
    found = [r for r in vectors()["loudness_gain_values"] if r["text"] == text]
    assert len(found) == 1, text
    return found[0]


def hash_row(fixture):
    found = [r for r in vectors()["loudness_hashes"] if r["fixture"] == fixture]
    assert len(found) == 1, fixture
    return found[0]


def harness_linear_gain(k, c):
    """Loudness gain, Linear gain, harness copy (binary64 throughout)."""
    m = abs(int(k))
    p, b = 1.0, c
    while m > 0:
        if m % 2 == 1:
            p = p * b
        m //= 2
        if m > 0:
            b = b * b
    return 1.0 / p if k < 0 else p


def with_gain_text(src, dst, text):
    """A copy of recipe src with the value text of loudness_gain_db replaced, other bytes kept."""
    raw = Path(src).read_bytes().decode("utf-8")
    key = '"loudness_gain_db": '
    at = raw.find(key)
    assert at >= 0, src
    start = at + len(key)
    end = start
    while raw[end] not in ",\r\n}":
        end += 1
    Path(dst).write_bytes((raw[:start] + text + raw[end:]).encode("utf-8"))
    return Path(dst)


# ------------------------------------------------------------ rows and constants


def test_row_loudness_gain_and_the_vector_bounds_agree():
    r = table_row(GAIN_ROW)
    c = constants()
    assert r.kind == "ranges" and r.unit == "dB", r
    assert r.min == float(c["min_db"]) and r.max == float(c["max_db"]), (r, c)
    assert c["row"] == GAIN_ROW
    assert c["min_limit"] == f">= {r.min_text} dB (row {GAIN_ROW})"
    assert c["max_limit"] == f"<= {r.max_text} dB (row {GAIN_ROW})"
    assert int(c["k_min"]) == round(r.min * int(c["steps_per_db"]))
    assert int(c["k_max"]) == round(r.max * int(c["steps_per_db"]))
    assert bits(from_hex(c["c_hex"])) == int(c["c_bits"], 16)
    assert c["store_fixtures"] == [lc.constants()["assertion_fixture"], "theta-cycle-sine.json"]


def test_stored_gain_vectors_follow_the_linear_gain_steps():
    c = from_hex(constants()["c_hex"])
    for v in vectors()["loudness_gain_values"]:
        x = 100.0 * float(v["text"])
        assert bits(x) == bits(from_hex(v["x_hex"])), v
        k = int(math.copysign(math.floor(abs(x) + 0.5), x))
        assert k == int(v["k"]), v
        assert bits(harness_linear_gain(k, c)) == int(v["g_bits"], 16), v


# ------------------------------------------------------------ loudness hash


def test_loudness_hash_value_gives_every_vector():
    tool = recipe_hash_tool()
    assert hasattr(tool, "loudness_hash_value"), "tools/recipe_hash.py has no loudness_hash_value (Story 4.2)"
    assert hasattr(tool, "loudness_hash_bytes"), "tools/recipe_hash.py has no loudness_hash_bytes (Story 4.2)"
    schema = tool.load_schema()
    members = set(constants()["hash_members"])
    for v in vectors()["loudness_hashes"]:
        path = FIXTURES_VALID / v["fixture"]
        data = path.read_bytes()
        value = tool.strict_loads(data)
        # The vector itself: the canonical form of the loudness-relevant members.
        subset = {k: value[k] for k in value if k in members}
        assert tool.canonicalize(subset).decode("utf-8") == v["canonical"], v["fixture"]
        assert hashlib.sha256(v["canonical"].encode("utf-8")).hexdigest() == v["loudness_hash"], v["fixture"]
        assert tool.loudness_hash_value(value) == v["loudness_hash"], v["fixture"]
        assert tool.loudness_hash_value(value, schema) == v["loudness_hash"], v["fixture"]
        assert tool.loudness_hash_bytes(data) == v["loudness_hash"], v["fixture"]
        assert tool.hash_bytes(data, schema) == v["recipe_hash"], v["fixture"]


def test_loudness_hash_ignores_stored_members_metadata_and_seed():
    tool = recipe_hash_tool()
    value = tool.strict_loads((FIXTURES_VALID / "stub-chain-1s-beat-6.json").read_bytes())
    want = hash_row("stub-chain-1s-beat-6.json")["loudness_hash"]
    for key, new in (("loudness_gain_db", -20.0), ("loudness_hash", "0" * 64), ("author", "x"),
                     ("date", "2027-01-02"), ("rationale", "y"), ("seed", 7), ("engine_version", "0.0.2"),
                     ("schema_version", "1.1")):
        edited = dict(value)
        edited[key] = new
        assert tool.loudness_hash_value(edited) == want, key
    for key, new in (("length_s", 2), ("loudness_target_lufs", -35)):
        edited = dict(value)
        edited[key] = new
        assert tool.loudness_hash_value(edited) != want, key
    edited = dict(value)
    del edited["theta_reference"]
    assert tool.loudness_hash_value(edited) != want


def test_both_layers_variants_share_or_change_the_loudness_hash():
    base = hash_row(BOTH_LAYERS)
    for name in SAME_LOUDNESS_HASH:
        assert hash_row(name)["loudness_hash"] == base["loudness_hash"], name
    for name in ("both-layers-seed-changed.json", "both-layers-engine-version-changed.json",
                 "both-layers-schema-minor-changed.json"):
        assert hash_row(name)["recipe_hash"] != base["recipe_hash"], name
    for name in DIFFERENT_LOUDNESS_HASH:
        assert hash_row(name)["loudness_hash"] != base["loudness_hash"], name
    tool = recipe_hash_tool()
    for name in SAME_LOUDNESS_HASH + DIFFERENT_LOUDNESS_HASH + [BOTH_LAYERS]:
        assert tool.loudness_hash_bytes((FIXTURES_VALID / name).read_bytes()) == hash_row(name)["loudness_hash"], name


def test_recipe_hash_tool_prints_the_loudness_hash_with_loudness_flag():
    path = FIXTURES_VALID / "stub-chain-1s-beat-6.json"
    r = subprocess.run([sys.executable, str(TOOL), "--loudness", str(path)], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.split()[0] == hash_row(path.name)["loudness_hash"], r.stdout
    plain = subprocess.run([sys.executable, str(TOOL), str(path)], capture_output=True, text=True, timeout=120)
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert plain.stdout.split()[0] == hash_row(path.name)["recipe_hash"], plain.stdout


# ------------------------------------------------------------ reference, final mode


def test_reference_final_mode_applies_every_stored_gain_bit_for_bit(tmp_path):
    sc = stub_chain()
    fixture = FIXTURES_VALID / constants()["final_fixture"]
    fs = SAMPLE_RATES[-1]
    measure = sc.render(fixture, fs)
    assert set(measure) == set(sc.KEYS)
    default = sc.render(fixture, fs, mode="measure")
    for key in sc.KEYS:
        assert np.array_equal(measure[key].view(np.uint64), default[key].view(np.uint64)), key
    assert np.array_equal(measure["master"].view(np.uint64), measure["join"].view(np.uint64))
    for v in vectors()["loudness_gain_values"]:
        path = with_gain_text(fixture, tmp_path / "gain.json", v["text"])
        final = sc.render(path, fs, mode="final")
        g = from_hex(v["g_hex"])
        assert bits(g) == int(v["g_bits"], 16)
        for key in ("theta", "gamma", "bus", "join"):
            assert np.array_equal(final[key].view(np.uint64), measure[key].view(np.uint64)), (v["text"], key)
        want = final["join"] * g
        assert np.array_equal(final["master"].view(np.uint64), want.view(np.uint64)), v["text"]
        assert np.array_equal(final["output"].view(np.uint64), final["master"].view(np.uint64)), v["text"]
        if int(v["k"]) == 0:
            assert np.array_equal(final["output"].view(np.uint64), measure["output"].view(np.uint64)), v["text"]
        # Must fail: g one ulp off changes the master.
        off = final["join"] * math.nextafter(g, 2.0)
        assert not np.array_equal(final["master"].view(np.uint64), off.view(np.uint64)), v["text"]


@pytest.fixture(scope="module")
def tapdump():
    return common.build("arcani-tapdump", common.TAPDUMP)


@pytest.fixture(scope="module")
def render():
    return common.build("arcani-render", common.RENDER)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_engine_final_render_matches_the_reference(tapdump, tmp_path, fs):
    sc = stub_chain()
    match = reference_match()
    table_row(MATCH_ROW)
    fixture = FIXTURES_VALID / constants()["final_fixture"]
    r = common.run(tapdump, [fixture, fs, tmp_path, "--final"])
    assert r.returncode == 0, r.stdout + r.stderr
    engine = {key: np.fromfile(tmp_path / f"{name}.f64", dtype="<f8") for key, name in DUMP_FILES.items()}
    reference = sc.render(fixture, fs, mode="final")
    measure = sc.render(fixture, fs)
    failed = []
    for key in MATCHED:
        assert engine[key].size == reference[key].size == 2 * fs, (key, engine[key].size)
        failed += [x for x in match.match_stereo(f"final {key} {fs}", engine[key], reference[key])
                   if x["result"] != "pass"]
    assert not failed, failed
    # The engine applies g bit for bit to its own join, and leaves the
    # measure-mode taps alone (the gain is the vector of the fixture's stored
    # gain, -10.00 dB: true_peak_constants.final_fixture_gain, Story 4.3
    # decision 3).
    tp = vectors()["true_peak_constants"]
    assert tp["final_fixture"] == constants()["final_fixture"]
    text = tp["final_fixture_gain"]
    assert json.loads(fixture.read_text(encoding="utf-8"))["loudness_gain_db"] == float(text)
    assert fixture.read_text(encoding="utf-8").count(f'"loudness_gain_db": {text},') == 1
    assert int(gain_value(text)["k"]) == -1000
    g = from_hex(gain_value(text)["g_hex"])
    assert np.array_equal(engine["master"].view(np.uint64), (engine["join"] * g).view(np.uint64))
    assert np.array_equal(engine["output"].view(np.uint64), engine["master"].view(np.uint64))
    # Must fail: the measure-mode reference master is 10 dB off the final engine output.
    assert any(x["result"] != "pass" for x in match.match_stereo("measure vs final", engine["output"], measure["output"]))


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_tapdump_without_final_is_unchanged(tapdump, tmp_path, fs):
    fixture = FIXTURES_VALID / constants()["final_fixture"]
    r = common.run(tapdump, [fixture, fs, tmp_path])
    assert r.returncode == 0, r.stdout + r.stderr
    join = np.fromfile(tmp_path / "join.f64", dtype="<f8")
    master = np.fromfile(tmp_path / "master.f64", dtype="<f8")
    assert np.array_equal(master.view(np.uint64), join.view(np.uint64))


# ------------------------------------------------------------ the Python meter on a stored render


def test_python_meter_reads_a_stored_final_render_within_the_tolerance(render, tmp_path):
    fixture = "theta-cycle-sine.json"
    recipe = tmp_path / fixture
    shutil.copyfile(FIXTURES_VALID / fixture, recipe)
    r = common.run(render, [recipe, "--store-gain"], env=lc.clean_env())
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("stored: loudness_gain_db="), r.stdout
    stored = json.loads(recipe.read_text(encoding="utf-8"))
    assert stored["loudness_hash"] == hash_row(fixture)["loudness_hash"]
    target = float(stored["loudness_target_lufs"])
    tol = lc.tolerance_lu()
    meter = lc.meter()
    for fs in SAMPLE_RATES:
        out = tmp_path / f"final-{fs}"
        out.mkdir()
        wav = out / "x.wav"
        rr = common.run(render, [recipe, "--out", wav, "--rate", fs, "--mode", "final"], env=lc.clean_env(),
                        timeout=900)
        assert rr.returncode == 0, rr.stdout + rr.stderr
        _, frames, rate = common.wav_layout(wav)
        assert rate == fs
        samples = common.read_frames(wav, 0, frames).astype(np.float64) / float(1 << 23)
        lc.unlink(wav)
        reading = meter.integrated_lufs(samples.reshape(-1, 2), fs)
        assert math.isfinite(reading), reading
        assert abs(reading - target) <= tol, (fs, reading, target)
        # Must fail: the measure-mode render reads far above the target.
        mm = out / "m.wav"
        rm = common.run(render, [recipe, "--out", mm, "--rate", fs], env=lc.clean_env(), timeout=900)
        assert rm.returncode == 0, rm.stdout + rm.stderr
        _, mframes, _ = common.wav_layout(mm)
        unit = common.read_frames(mm, 0, mframes).astype(np.float64) / float(1 << 23)
        lc.unlink(mm)
        assert meter.integrated_lufs(unit.reshape(-1, 2), fs) - target > tol


# ------------------------------------------------------------ hash probe


def test_probe_source_names_the_final_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"stub-chain-final-{fs}" in text, fs
    assert "ARC_MODE_FINAL" in text


def test_expected_entries_name_the_final_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        entry = components.get(f"stub-chain-final-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry stub-chain-final-{fs} (after the full run)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == 2 * fs, entry
