"""The Python reference preview (reference/preview.py) against the Preview
vectors, the rows, and the two checklist fixtures (Story 3.3;
docs/signal-spec.md, Preview).

Contract with reference/preview.py (spec Implementation Notes): constants
PREVIEW_LENGTH_S, PREVIEW_SEAM_TAIL_S, PREVIEW_PEAK_DBFS (equal to the rows
preview-length, preview-seam-tail, preview-peak-level); PreviewRowError, a
ValueError for an invalid peak level; seconds_to_samples(t_s, fs),
peak_valid(peak_dbfs), amplitude(peak_dbfs), gain(peak_dbfs, layers_max)
(n_max 0 counts as 1), layers_per_ear(recipe, mute="none") ->
{"left": n, "right": n}, preview_frames(recipe, fs, length_s=..., seam_tail_s=...),
seams_heard(recipe, fs) -> (O, O + B) or None, report_member(recipe, fs,
peak_dbfs=...) -> {"signed": False, "peak_dbfs", "layers_per_ear", "gain",
"seconds": F / fs}.

Gains and frame counts are compared exactly (bits, integers); the ideal
within 2 units in the last place of g. The checklist fixtures are the
generator's text, pass the carrier rule (row carrier-rule) and the spacing
rule with the margins written in design log entry (xx), and hold the words
of the story's decision 6. g is built without a transcendental call, both in
cli/preview.cpp and in reference/preview.py (a source scan).

Must-fail cases are made here by doctoring a value, a vector row, a
fixture text, or a source text.
"""

import inspect
import json
import math
import re

import pytest

import preview_common as common
from assertions import row as table_row

SPEC_STORY = common.REPO_ROOT / "_bmad-output" / "implementation-artifacts" / "spec-3-3-early-listening-preview.md"
DESIGN_LOG = common.REPO_ROOT / "docs" / "design-log.md"
CLI_PREVIEW = common.REPO_ROOT / "cli" / "preview.cpp"


def ref():
    return common.reference_preview()


def ulp(x):
    return math.nextafter(x, math.inf) - x


def gain_problems(got, r):
    """Problems of a gain against its gain vector row: bits exact, ideal within 2 ulp."""
    p = []
    if common.bits(got) != r["gain_bits"]:
        p.append(f"gain bits {common.bits(got)}, want {r['gain_bits']}")
    want = float.fromhex(r["gain_hex"])
    if not abs(common.ideal(r["ideal"]) - got) <= 2.0 * ulp(want):
        p.append("gain is not within 2 ulp of the ideal")
    return p


def frame_problems(mod, recipe, r):
    p = []
    fs = r["fs"]
    f = mod.preview_frames(recipe, fs)
    if not isinstance(f, int) or f != int(r["preview_frames"]):
        p.append(f"F {f}, want {r['preview_frames']}")
    seams = mod.seams_heard(recipe, fs)
    if r["looping"] == "yes":
        want = (int(r["opening_end_frame"]), int(r["first_seam_frame"]))
        if seams != want:
            p.append(f"seams {seams}, want {want}")
    elif seams is not None:
        p.append(f"seams {seams} without a loop")
    member = mod.report_member(recipe, fs)
    want_member = {"signed": False, "peak_dbfs": common.peak_dbfs(), "layers_per_ear": r["layers_max"],
                   "gain": common.from_bits(r["gain_bits"]), "seconds": float(r["seconds"])}
    if list(member) != list(want_member):
        p.append(f"report member keys {list(member)}")
    else:
        for k, v in want_member.items():
            got = member[k]
            if type(got) is not type(v) or (isinstance(v, float) and common.bits(got) != common.bits(v)) or got != v:
                p.append(f"report member {k} {got!r}, want {v!r}")
    return p


# ------------------------------------------------------------ rows and constants


def test_rows_are_read_through_the_assertion_call_and_equal_the_vector_constants():
    c = common.constants()
    assert common.length_s() == float(c["length_s"])
    assert common.seam_tail_s() == float(c["seam_tail_s"])
    assert common.peak_dbfs() == float(c["peak_dbfs"])
    assert float.fromhex(c["sqrt10_hex"]) == math.sqrt(10.0)
    assert c["listening_rate"] in [int(v) for v in table_row("sample-rates").values]
    assert c["fixtures"] == c["starter_fixtures"] + c["checklist_fixtures"]


def test_reference_constants_equal_the_rows():
    mod = ref()
    assert mod.PREVIEW_LENGTH_S == common.length_s()
    assert mod.PREVIEW_SEAM_TAIL_S == common.seam_tail_s()
    assert mod.PREVIEW_PEAK_DBFS == common.peak_dbfs()


def test_reference_module_contract():
    mod = ref()
    assert issubclass(mod.PreviewRowError, ValueError)
    sig = {name: list(inspect.signature(getattr(mod, name)).parameters) for name in (
        "seconds_to_samples", "peak_valid", "amplitude", "gain", "layers_per_ear", "preview_frames",
        "seams_heard", "report_member")}
    assert sig["seconds_to_samples"] == ["t_s", "fs"]
    assert sig["peak_valid"] == ["peak_dbfs"]
    assert sig["amplitude"] == ["peak_dbfs"]
    assert sig["gain"] == ["peak_dbfs", "layers_max"]
    assert sig["layers_per_ear"] == ["recipe", "mute"]
    assert inspect.signature(mod.layers_per_ear).parameters["mute"].default == "none"
    assert sig["preview_frames"] == ["recipe", "fs", "length_s", "seam_tail_s"]
    params = inspect.signature(mod.preview_frames).parameters
    assert params["length_s"].default == common.length_s()
    assert params["seam_tail_s"].default == common.seam_tail_s()
    assert sig["seams_heard"] == ["recipe", "fs"]
    assert sig["report_member"] == ["recipe", "fs", "peak_dbfs"]
    assert inspect.signature(mod.report_member).parameters["peak_dbfs"].default == common.peak_dbfs()


# ------------------------------------------------------------ gain


@pytest.mark.parametrize("r", common.gain_rows(), ids=lambda r: f"{r['peak_dbfs']}dB-{r['layers_max']}")
def test_reference_gain_equals_the_gain_vectors(r):
    mod = ref()
    p = float(r["peak_dbfs"])
    assert mod.peak_valid(p)
    assert common.bits(mod.amplitude(p)) == common.bits(float.fromhex(r["amplitude_hex"]))
    g = mod.gain(p, r["layers_max"])
    assert not gain_problems(g, r)
    if r["layers_max"] == 1:
        assert common.bits(mod.gain(p, 0)) == r["gain_bits"], "n_max 0 counts as 1"


def test_reference_invalid_peaks_raise():
    mod = ref()
    bad = [float(t) for t in common.constants()["invalid_peaks"]]
    c = common.constants()
    bad += [math.nextafter(float(c["peak_max_dbfs"]), math.inf), math.nextafter(float(c["peak_min_dbfs"]), -math.inf),
            math.nextafter(common.peak_dbfs(), 0.0), math.nan, math.inf, -math.inf]
    for p in bad:
        assert not mod.peak_valid(p), p
        with pytest.raises(mod.PreviewRowError):
            mod.amplitude(p)
        with pytest.raises(mod.PreviewRowError):
            mod.gain(p, 2)
    assert mod.peak_valid(float(c["peak_min_dbfs"])) and mod.peak_valid(float(c["peak_max_dbfs"]))


def test_must_fail_the_gain_comparison_catches_a_flipped_bit_and_3_ulp():
    for r in common.gain_rows():
        g = common.from_bits(r["gain_bits"])
        assert not gain_problems(g, r)
        flipped = common.from_bits(f"0x{int(r['gain_bits'], 16) ^ 1:016x}")
        assert gain_problems(flipped, r)
        far = g
        for _ in range(3):
            far = math.nextafter(far, math.inf)
        assert gain_problems(far, r)


# ------------------------------------------------------------ layers and frames


@pytest.mark.parametrize("r", common.layer_rows(), ids=lambda r: r["case"])
def test_reference_layers_equal_the_layer_vectors(r):
    mod = ref()
    recipe = common.load_fixture(r["fixture"])
    got = mod.layers_per_ear(recipe, r["mute"])
    assert got == {"left": r["left"], "right": r["right"]}
    assert got == common.layers_per_ear(recipe, r["mute"])
    assert max(got.values()) == r["layers_max"]
    assert common.bits(mod.gain(common.peak_dbfs(), max(got.values()))) == r["gain_bits"]


def test_must_fail_a_layer_vector_off_by_one_is_caught():
    for r in common.layer_rows():
        recipe = common.load_fixture(r["fixture"])
        got = common.layers_per_ear(recipe, r["mute"])
        assert got == {"left": r["left"], "right": r["right"]}
        assert got != {"left": r["left"] + 1, "right": r["right"]}
        assert got != {"left": r["left"], "right": r["right"] + 1}


@pytest.mark.parametrize("r", common.frame_rows(), ids=lambda r: f"{r['fixture']}-{r['fs']}")
def test_reference_frames_equal_the_frame_vectors(r):
    mod = ref()
    recipe = common.load_fixture(r["fixture"])
    assert mod.seconds_to_samples(float(r["length_s"]), r["fs"]) == int(r["end_frame"])
    assert mod.seconds_to_samples(common.length_s(), r["fs"]) == int(r["length_frames"])
    assert mod.seconds_to_samples(common.seam_tail_s(), r["fs"]) == int(r["tail_frames"])
    assert int(r["preview_frames"]) / r["fs"] == float(r["seconds"])
    if r["looping"] == "yes":
        assert int(r["opening_end_frame"]) / r["fs"] == float(r["opening_end_s"])
        assert int(r["first_seam_frame"]) / r["fs"] == float(r["first_seam_s"])
    assert not frame_problems(mod, recipe, r)


def test_must_fail_the_frame_comparison_catches_f_plus_1_and_a_signed_member():
    mod = ref()
    r = common.frame_row(common.constants()["fixtures"][0], common.constants()["listening_rate"])
    recipe = common.load_fixture(r["fixture"])
    assert not frame_problems(mod, recipe, r)
    bad = dict(r, preview_frames=str(int(r["preview_frames"]) + 1))
    assert frame_problems(mod, recipe, bad)
    bad = dict(r, first_seam_frame=str(int(r["first_seam_frame"]) + 1))
    assert frame_problems(mod, recipe, bad)
    bad = dict(r, gain_bits=f"0x{int(r['gain_bits'], 16) ^ 1:016x}")
    assert frame_problems(mod, recipe, bad)


def test_reference_seconds_to_samples_equals_the_whole_sample_vectors():
    mod = ref()
    for v in common.vectors()["loop_whole_samples"]:
        t = float.fromhex(v["t_hex"])
        assert mod.seconds_to_samples(t, 44100) == int(v["n_44100"]), v["t"]
        assert mod.seconds_to_samples(t, 48000) == int(v["n_48000"]), v["t"]
    for t in (-1.0, math.nan, math.inf, -math.inf, 2.0 ** 64):
        assert mod.seconds_to_samples(t, 48000) == 0, t


@pytest.mark.parametrize("fs", [44100, 48000])
def test_reference_short_sessions_are_previewed_whole(fs):
    mod = ref()
    for name in ("stub-chain-1s-beat-6.json", "theta-gamma-uncoupled.json"):
        recipe = common.load_fixture(name)
        n = mod.seconds_to_samples(float(recipe["length_s"]), fs)
        assert n < mod.seconds_to_samples(common.length_s(), fs)
        assert mod.preview_frames(recipe, fs) == n, name
        assert mod.seams_heard(recipe, fs) is None
    # A looping recipe whose cap falls inside the tail, and one with one body pass only.
    focus = common.load_fixture(common.constants()["starter_fixtures"][0])
    assert "loop" in focus
    o = mod.seconds_to_samples(float(focus["loop"]["opening_s"]), fs)
    b = mod.seconds_to_samples(float(focus["loop"]["body_s"]), fs)
    for length in (float(focus["loop"]["opening_s"]) + float(focus["loop"]["body_s"]),
                   float(focus["loop"]["opening_s"]) + float(focus["loop"]["body_s"]) + common.seam_tail_s() / 2):
        short = dict(focus, length_s=length)
        assert mod.preview_frames(short, fs) == mod.seconds_to_samples(length, fs) <= o + b + \
            mod.seconds_to_samples(common.seam_tail_s(), fs)


# ------------------------------------------------------------ checklist fixtures


@pytest.mark.parametrize("name", common.constants()["checklist_fixtures"])
def test_checklist_fixture_file_is_the_generator_text(name):
    gen = common.generator()
    path = common.FIXTURES_VALID / name
    assert path.read_bytes() == gen.preview_fixture_text(name).encode("utf-8")


def test_must_fail_a_doctored_fixture_text_differs_from_the_generator():
    gen = common.generator()
    name = common.constants()["checklist_fixtures"][0]
    text = (common.FIXTURES_VALID / name).read_text(encoding="utf-8")
    assert text.replace('"rate_hz": 60', '"rate_hz": 61', 1) != gen.preview_fixture_text(name)


def _logged_margins():
    """{fixture: (min_distance_hz, margin_hz)} from design log entry (xx)."""
    log = DESIGN_LOG.read_text(encoding="utf-8")
    at = log.index("### 2026-11-17 (xx)")
    entry = log[at:log.index("\n### ", at + 1)]
    out = {}
    for name in common.constants()["checklist_fixtures"]:
        coupling = name[:-len(".json")].rsplit("-", 1)[1]
        m = re.search(rf"the {coupling}, ([0-9.]+) Hz \(margin ([0-9.]+) Hz\)", entry)
        assert m, f"design log (xx) names no margin for the {coupling} fixture"
        out[name] = (float(m.group(1)), float(m.group(2)))
    return out


@pytest.mark.parametrize("name", common.constants()["checklist_fixtures"])
def test_checklist_fixture_passes_the_spacing_rule_with_the_logged_margin(name):
    spacing = common.reference_module("spacing")
    recipe = common.load_fixture(name)
    assert spacing.check_spacing(recipe) is None
    rule = table_row("spacing-rule")
    tol = table_row("component-frequency-error")
    assert rule.unit == "Hz" and tol.unit == "Hz"
    distance, margin = _logged_margins()[name]
    assert margin == distance - rule.value
    margins = spacing.spacing_margins(recipe)
    for ear in common.EARS:
        pair = margins[ear]
        assert pair is not None, ear
        assert abs(pair.min_distance_hz - distance) < tol.value, (ear, pair)
        assert abs(pair.margin_hz - margin) < tol.value, (ear, pair)
        assert pair.margin_hz > 0.0


@pytest.mark.parametrize("name", common.constants()["checklist_fixtures"])
def test_checklist_fixture_passes_the_carrier_rule(name):
    r = table_row("carrier-rule")
    assert r.unit == "times the modulation rate"
    recipe = common.load_fixture(name)
    for layer in ("theta_reference", "gamma_pac"):
        assert recipe[layer]["carrier_hz"] >= r.value * recipe[layer]["rate_hz"], layer


def _decision_6():
    text = SPEC_STORY.read_text(encoding="utf-8")
    m = re.search(
        r"6\. \*\*Preview set\.\*\* .*?, ([0-9]+) s, no binaural layer: .*?: a ([0-9]+) Hz theta reference carrier "
        r"amplitude-modulated by the ([a-z]+) envelope at ([0-9]+) Hz, ([0-9]+) percent depth, and a gamma PAC layer, "
        r"a ([0-9]+) Hz ([a-z]+) carrier amplitude-modulated at ([0-9]+) Hz, ([0-9]+) percent depth, coupled as "
        r"smooth swell / ([0-9]+) ms bursts at the ([0-9]+) degree coupling phase", text)
    assert m, "decision 6 of the story spec does not read as expected"
    keys = ("length_s", "theta_carrier", "theta_shape", "theta_rate", "theta_depth", "gamma_carrier", "gamma_wave",
            "gamma_rate", "gamma_depth", "burst_ms", "phase")
    return dict(zip(keys, m.groups()))


def fixture_word_problems(recipe, coupling):
    d = _decision_6()
    p = []
    want = {
        ("length_s",): float(d["length_s"]),
        ("theta_reference", "carrier_hz"): float(d["theta_carrier"]),
        ("theta_reference", "shape"): d["theta_shape"],
        ("theta_reference", "rate_hz"): float(d["theta_rate"]),
        ("theta_reference", "am_depth_percent"): float(d["theta_depth"]),
        ("gamma_pac", "carrier_hz"): float(d["gamma_carrier"]),
        ("gamma_pac", "carrier_wave"): d["gamma_wave"],
        ("gamma_pac", "rate_hz"): float(d["gamma_rate"]),
        ("gamma_pac", "am_depth_percent"): float(d["gamma_depth"]),
        ("gamma_pac", "coupling"): coupling,
        ("gamma_pac", "coupling_phase_deg"): float(d["phase"]),
    }
    for path, v in want.items():
        got = recipe
        for k in path:
            got = got.get(k) if isinstance(got, dict) else None
        if got != v:
            p.append(f"{'/'.join(path)} {got!r}, want {v!r}")
    for absent in ("binaural", "loop"):
        if absent in recipe:
            p.append(f"has {absent}")
    return p


@pytest.mark.parametrize("name, coupling", [
    (common.constants()["checklist_fixtures"][0], "smooth_swell"),
    (common.constants()["checklist_fixtures"][1], "bursts"),
])
def test_checklist_fixture_holds_the_words_of_decision_6(name, coupling):
    assert not fixture_word_problems(common.load_fixture(name), coupling)


def test_must_fail_a_doctored_checklist_fixture_breaks_the_words():
    name = common.constants()["checklist_fixtures"][0]
    recipe = common.load_fixture(name)
    for doctor in (lambda r: r["gamma_pac"].update(rate_hz=40),
                   lambda r: r["gamma_pac"].update(coupling="bursts"),
                   lambda r: r.update(length_s=210),
                   lambda r: r.update(binaural={"carrier_left_hz": 100})):
        bad = json.loads(json.dumps(recipe))
        doctor(bad)
        assert fixture_word_problems(bad, "smooth_swell")


# ------------------------------------------------------------ no transcendental call

C_TRANSCENDENTAL = re.compile(
    r"\b(?:std::)?(?:pow|powf|powl|exp|expf|exp2|exp10|expm1|log|logf|log10|log2|log1p|cbrt|hypot|"
    r"sin|cos|tan|sinh|cosh|tanh|atan|atan2|asin|acos)\s*\(")
PY_TRANSCENDENTAL = re.compile(
    r"\b(?:math|np|numpy)\.(?:pow|exp|exp2|expm1|log|log10|log2|log1p|power|float_power|cbrt|"
    r"sin|cos|tan|atan|atan2)\b|\*\*|\bpow\s*\(")


def _strip_c_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _strip_py_comments(text):
    out = []
    for line in text.splitlines():
        out.append(line.split("#", 1)[0])
    text = "\n".join(out)
    return re.sub(r'"""[\s\S]*?"""', "", text)


def c_transcendental_calls(text):
    return C_TRANSCENDENTAL.findall(_strip_c_comments(text))


def py_transcendental_calls(text):
    return PY_TRANSCENDENTAL.findall(_strip_py_comments(text))


def test_cli_preview_builds_g_without_a_transcendental_call():
    assert CLI_PREVIEW.is_file(), f"missing {CLI_PREVIEW} (Story 3.3)"
    calls = c_transcendental_calls(CLI_PREVIEW.read_text(encoding="utf-8"))
    assert not calls, calls


def test_reference_preview_builds_g_without_a_transcendental_call():
    assert common.REFERENCE_PREVIEW.is_file(), f"missing {common.REFERENCE_PREVIEW} (Story 3.3)"
    calls = py_transcendental_calls(common.REFERENCE_PREVIEW.read_text(encoding="utf-8"))
    assert not calls, calls


def test_must_fail_the_transcendental_scans_catch_doctored_sources():
    assert c_transcendental_calls("double a = std::pow(10.0, p / 20.0);")
    assert c_transcendental_calls("double a = exp10(p / 20.0);")
    assert c_transcendental_calls("return std::exp(p * 0.1151);")
    assert not c_transcendental_calls("// std::pow is not used\ndouble x = std::sqrt(10.0) * 10.0;")
    assert py_transcendental_calls("a = 10.0 ** (p / 20.0)")
    assert py_transcendental_calls("a = math.pow(10.0, p / 20.0)")
    assert py_transcendental_calls("a = np.power(10.0, p / 20.0)")
    assert not py_transcendental_calls("x = math.sqrt(10.0)  # not 10 ** 0.5\n")
