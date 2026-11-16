"""Python reference component table against the signal spec vectors (Story 3.1).

The reference builds the component table from docs/signal-spec.md,
Components, only (the rules of tests/python/test_reference_independent.py
apply). Thresholds come from tests/tables/*.tsv through the assertion call
`assertions.row`; no threshold is written here as a literal.

Contract with reference/components.py (Story 3.1 spec, Implementation Notes):

- `Component`, a NamedTuple with the fields layer ("theta_reference",
  "gamma_pac", or "binaural"), ear ("left" or "right"), center_hz, low_hz,
  high_hz, level, gamma_mult, theta_mult, beat_mult, in that order.
- `NoComponentModel(ValueError)` with the attributes parameter, value, rule
  ("no component model"), and limit.
- `component_table(recipe, mute="none")`: the full table of a parsed recipe
  JSON, the left ear's rows first; mute is "none", "left", or "right".
- `component_table_from_file(recipe_path, mute="none")`: the same from a file.

Every vector case (tests/data/signal_spec_vectors.json, `component_cases`
and `components`): the reference table has the same rows in the same order
(layer, ear, multipliers), every frequency within row
component-frequency-error and every level within row component-level-error.
The fixture cases hold the three layer objects of their file in
recipes/fixtures/valid/.
"""

import inspect
import json
import math

import pytest

import components_common as common
from assertions import row as table_row
from assertions.tables import load_tables


def ref():
    return common.reference_components()


def table(recipe, mute="none"):
    return ref().component_table(recipe, mute)


def base_recipe(**layers):
    recipe = {
        "schema_version": "1.0", "engine_version": "0.0.1", "seed": 42, "author": "Arcani test",
        "date": "2026-11-16", "rationale": "Component test, made in the test.", "length_s": 10,
        "loudness_target_lufs": -36,
    }
    recipe.update(layers)
    return recipe


THETA_SINE = {"carrier_hz": 450, "rate_hz": 6, "am_depth_percent": 75, "shape": "sine"}
GAMMA_SINE = {"carrier_hz": 250, "rate_hz": 40, "am_depth_percent": 100, "carrier_wave": "sine",
              "coupling": "uncoupled"}
BINAURAL_SINE = {"carrier_left_hz": 400, "beat_rate_hz": 6}


# ------------------------------------------------------------ vectors and rows


def test_constants_agree_with_the_rows():
    c = common.constants()
    L = table_row(common.COMPONENT_ROW)
    assert float(c["level_db"]) == L.value
    assert float(c["threshold"]) == 10.0 ** (-L.value / 20.0) or math.isclose(
        float(c["threshold"]), 10.0 ** (-L.value / 20.0), rel_tol=1e-15)
    assert float.fromhex(c["threshold_hex"]) == float(c["threshold"])
    assert float(c["level_error"]) == common.level_error()
    assert float(c["frequency_error"]) == common.frequency_error()
    assert tuple(c["layers"]) == common.LAYERS
    assert tuple(c["ears"]) == common.EARS
    assert c["no_model_rule"] == "no component model"
    assert set(c["probe_cases"]) <= set(common.case_names())


def test_component_rows_are_present():
    for row_id in (common.LEVEL_ROW, common.FREQUENCY_ROW, common.COMPONENT_ROW):
        r = table_row(row_id)
        assert r.value > 0.0, r
        assert r.value == load_tables()[row_id].value


def test_every_fixture_case_holds_the_layer_objects_of_its_file():
    names = common.fixture_cases()
    assert names, "no fixture cases"
    for c in names:
        recipe = common.load_fixture(c["fixture"])
        layers = common.case_layers(c["case"])
        for layer in common.LAYERS:
            if layer in layers:
                assert recipe.get(layer) == layers[layer], (c["case"], layer)
            else:
                assert layer not in recipe, (c["case"], layer)
        assert c["mute"] in common.MUTES, c
        if c["mute"] == "none":
            assert c["fixture"] == c["case"] + ".json", c


def test_every_case_recipe_holds_its_layer_cells():
    for name in common.case_names():
        recipe = common.case_recipe(name)
        layers = common.case_layers(name)
        for layer in common.LAYERS:
            assert recipe.get(layer) == layers.get(layer), (name, layer)


# ------------------------------------------------------------ the reference module


def test_reference_module_contract():
    mod = ref()
    assert mod.Component._fields == common.FIELDS
    assert issubclass(mod.NoComponentModel, ValueError)
    params = inspect.signature(mod.component_table).parameters
    assert list(params) == ["recipe", "mute"] and params["mute"].default == "none"
    params = inspect.signature(mod.component_table_from_file).parameters
    assert list(params) == ["recipe_path", "mute"] and params["mute"].default == "none"


@pytest.mark.parametrize("name", common.case_names())
def test_reference_table_equals_the_vectors(name):
    c = common.case(name)
    got = table(common.case_recipe(name), c["mute"])
    for r in got:
        assert isinstance(r, ref().Component), r
        assert isinstance(r.gamma_mult, int) and isinstance(r.theta_mult, int) and isinstance(r.beat_mult, int)
    problems = common.compare(got, common.want_rows(name))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("c", common.fixture_cases(), ids=lambda c: c["case"])
def test_reference_table_from_the_fixture_file_equals_the_vectors(c):
    got = ref().component_table_from_file(common.FIXTURES_VALID / c["fixture"], c["mute"])
    problems = common.compare(got, common.want_rows(c["case"]))
    assert not problems, "\n".join(problems)
    assert common.as_rows(got) == common.as_rows(table(common.load_fixture(c["fixture"]), c["mute"]))


def test_the_table_depends_only_on_the_layers_and_the_muted_ear():
    name = "three-layers"
    recipe = common.case_recipe(name)
    want = common.as_rows(table(recipe))
    changed = dict(recipe, seed=7, length_s=120, loudness_target_lufs=-30, rationale="Other text.")
    assert common.as_rows(table(changed)) == want
    looped = dict(recipe, length_s=1200, loop={"mode": "learn", "opening_s": 60, "body_s": 120,
                                               "max_run_time_min": 20})
    assert common.as_rows(table(looped)) == want


def test_every_level_is_in_0_1_at_least_the_threshold_and_the_carrier_is_1():
    T = 10.0 ** (-table_row(common.COMPONENT_ROW).value / 20.0)
    tol = common.level_error()
    for name in common.case_names():
        got = common.as_rows(table(common.case_recipe(name), common.case(name)["mute"]))
        assert got, name
        for r in got:
            assert 0.0 < r.level <= 1.0, (name, r)
            assert r.level >= T - tol, (name, r)
            assert 0.0 <= r.low_hz <= r.center_hz <= r.high_hz, (name, r)
            if r.gamma_mult == 0 and r.theta_mult == 0:
                assert r.level == 1.0, (name, r)
        # The theta reference and gamma PAC rows are the same in both ears.
        for layer in ("theta_reference", "gamma_pac"):
            left = [r._replace(ear="") for r in common.layer_rows(got, layer, "left")]
            right = [r._replace(ear="") for r in common.layer_rows(got, layer, "right")]
            assert left == right, (name, layer)


# ------------------------------------------------------------ matrix rows


def near(a, b, tol):
    return abs(a - b) < tol


def test_matrix_sine_theta_450_hz_carrier_am_at_6_hz_75_percent():
    got = common.as_rows(table(base_recipe(theta_reference=THETA_SINE)))
    assert len(got) == 6
    for ear in common.EARS:
        rows = common.layer_rows(got, "theta_reference", ear)
        assert [r.theta_mult for r in rows] == [-1, 0, 1]
        for r, f, level in zip(rows, (444.0, 450.0, 456.0), (0.3, 1.0, 0.3)):
            assert near(r.center_hz, f, common.frequency_error()), r
            assert near(r.level, level, common.level_error()), r


def test_matrix_smooth_swell_9_lines_204_to_296_hz():
    gamma = dict(GAMMA_SINE, coupling="smooth_swell", coupling_phase_deg=0)
    got = common.as_rows(table(base_recipe(theta_reference=THETA_SINE, gamma_pac=gamma)))
    for ear in common.EARS:
        rows = common.layer_rows(got, "gamma_pac", ear)
        assert len(rows) == 9
        assert near(rows[0].center_hz, 204.0, common.frequency_error())
        assert near(rows[-1].center_hz, 296.0, common.frequency_error())
        for r in rows:
            order = abs(r.gamma_mult) + abs(r.theta_mult)
            want = {0: 1.0, 1: 1.0 / 6.0, 2: 1.0 / 12.0}[order]
            assert near(r.level, want, common.level_error()), r
    # The coupling phase moves no line.
    for deg in (90, 180, 270):
        other = common.as_rows(table(base_recipe(theta_reference=THETA_SINE,
                                                 gamma_pac=dict(gamma, coupling_phase_deg=deg))))
        assert not common.compare(other, got), deg


def test_matrix_bursts_whole_ratio_sums_coincident_lines():
    """bursts-60hz.json: 60 Hz over 6 Hz is whole; lines share frequencies and the table holds the sums."""
    rows = common.want_rows("bursts-60hz")
    gamma = common.layer_rows(rows, "gamma_pac", "left")
    centers = [r.center_hz for r in gamma]
    assert len(set(centers)) == len(centers), "one row per frequency"
    assert all(r.gamma_mult == 0 for r in gamma), "summed rows are named (0, m)"
    got = common.as_rows(ref().component_table_from_file(common.FIXTURES_VALID / "bursts-60hz.json"))
    assert not common.compare(got, rows)
    # 45 Hz over 6 Hz: twice the gamma rate is whole; the sums apply too.
    gamma45 = common.layer_rows(common.want_rows("bursts-45hz"), "gamma_pac", "left")
    centers = [r.center_hz for r in gamma45]
    assert len(set(centers)) == len(centers)


@pytest.mark.parametrize("shape", ("sine", "smoothed_on_off", "sawtooth", "reverse_saw"))
def test_matrix_depth_0_is_the_carrier_alone(shape):
    theta = dict(THETA_SINE, shape=shape, am_depth_percent=0)
    for gamma in (dict(GAMMA_SINE, am_depth_percent=0),
                  dict(GAMMA_SINE, am_depth_percent=0, coupling="smooth_swell", coupling_phase_deg=0),
                  dict(GAMMA_SINE, am_depth_percent=0, coupling="bursts", coupling_phase_deg=0)):
        got = common.as_rows(table(base_recipe(theta_reference=theta, gamma_pac=gamma)))
        assert len(got) == 4, (shape, gamma, got)
        for r in got:
            assert (r.gamma_mult, r.theta_mult, r.beat_mult) == (0, 0, 0), r
            assert r.level == 1.0
            assert r.center_hz == (450.0 if r.layer == "theta_reference" else 250.0)


def test_matrix_beat_rate_cycle_binaural_cycle_sleep():
    got = common.as_rows(ref().component_table_from_file(common.FIXTURES_VALID / "binaural-cycle-sleep.json"))
    tol = common.frequency_error()
    left = common.layer_rows(got, "binaural", "left")
    right = common.layer_rows(got, "binaural", "right")
    assert len(left) == len(right) == 1
    assert near(left[0].center_hz, 100.0, tol) and left[0].low_hz == left[0].high_hz == left[0].center_hz
    assert left[0].beat_mult == 0 and right[0].beat_mult == 1
    assert near(right[0].center_hz, 101.5, tol)
    assert near(right[0].low_hz, 100.0, tol) and near(right[0].high_hz, 103.0, tol)
    assert left[0].level == right[0].level == 1.0


def test_matrix_theta_cycle_lines_sweep_k_times_1_to_6_hz_from_the_carrier():
    got = common.as_rows(ref().component_table_from_file(common.FIXTURES_VALID / "theta-cycle-sine.json"))
    tol = common.frequency_error()
    rows = common.layer_rows(got, "theta_reference", "left")
    assert [r.theta_mult for r in rows] == [-1, 0, 1]
    for r in rows:
        k = r.theta_mult
        if k == 0:
            assert r.low_hz == r.high_hz == r.center_hz == 450.0
            continue
        lo, hi = sorted((450.0 + k * 1.0, 450.0 + k * 6.0))
        assert near(r.low_hz, lo, tol) and near(r.high_hz, hi, tol), r
        assert near(r.center_hz, 450.0 + k * 3.5, tol), r


@pytest.mark.parametrize("mute", ("left", "right"))
def test_matrix_muted_ear_has_no_binaural_component(mute):
    recipe = base_recipe(theta_reference=THETA_SINE, binaural=BINAURAL_SINE)
    full = common.as_rows(table(recipe))
    got = common.as_rows(table(recipe, mute))
    other = "right" if mute == "left" else "left"
    assert common.layer_rows(got, "binaural", mute) == []
    assert common.layer_rows(got, "binaural", other) == common.layer_rows(full, "binaural", other)
    assert len(got) == len(full) - 1
    # Must-pass twin: no muted ear keeps both binaural rows.
    assert len(common.layer_rows(full, "binaural", mute)) == 1


def test_matrix_no_binaural_field_no_binaural_row():
    got = common.as_rows(table(base_recipe(theta_reference=THETA_SINE)))
    assert not [r for r in got if r.layer == "binaural"]


# ------------------------------------------------------------ unmodeled shapes


THETA_LIMIT = "sine, smoothed_on_off, sawtooth, reverse_saw"


@pytest.mark.parametrize("recipe, want", [
    (base_recipe(theta_reference=dict(THETA_SINE, shape="custom")),
     ("/theta_reference/shape", "custom", THETA_LIMIT)),
    (base_recipe(gamma_pac=dict(GAMMA_SINE, carrier_wave="triangle")),
     ("/gamma_pac/carrier_wave", "triangle", "sine")),
    (base_recipe(gamma_pac=dict(GAMMA_SINE, carrier_wave="softened_square")),
     ("/gamma_pac/carrier_wave", "softened_square", "sine")),
    (base_recipe(binaural=dict(BINAURAL_SINE, waveform="triangle")),
     ("/binaural/waveform", "triangle", "sine")),
    (base_recipe(theta_reference=dict(THETA_SINE, shape="custom"), gamma_pac=dict(GAMMA_SINE, carrier_wave="triangle"),
                 binaural=dict(BINAURAL_SINE, waveform="triangle")),
     ("/theta_reference/shape", "custom", THETA_LIMIT)),
    (base_recipe(theta_reference=THETA_SINE, gamma_pac=dict(GAMMA_SINE, carrier_wave="triangle"),
                 binaural=dict(BINAURAL_SINE, waveform="triangle")),
     ("/gamma_pac/carrier_wave", "triangle", "sine")),
], ids=["custom", "triangle", "softened-square", "binaural-triangle", "order-theta-first", "order-gamma-next"])
def test_unmodeled_shape_raises_no_component_model(recipe, want):
    with pytest.raises(ref().NoComponentModel) as info:
        table(recipe)
    e = info.value
    assert (e.parameter, e.value, e.limit) == want
    assert e.rule == common.constants()["no_model_rule"] == "no component model"


def test_modeled_shapes_raise_nothing():
    got = table(base_recipe(theta_reference=THETA_SINE, gamma_pac=GAMMA_SINE,
                            binaural=dict(BINAURAL_SINE, waveform="sine")))
    assert len(got) == 14


# ------------------------------------------------------------ must-fail of the comparison


def test_must_fail_the_comparison_catches_a_doctored_table():
    want = common.want_rows("bursts-60hz")
    assert common.compare(want, want) == []
    lt, ft = common.level_error(), common.frequency_error()
    side = next(i for i, r in enumerate(want) if r.layer == "gamma_pac" and r.theta_mult != 0)
    dropped = want[:side] + want[side + 1:]
    assert common.compare(dropped, want)
    doctored = list(want)
    doctored[side] = want[side]._replace(level=want[side].level + 2.0 * lt)
    assert common.compare(doctored, want)
    doctored[side] = want[side]._replace(level=want[side].level + 0.5 * lt)
    assert not common.compare(doctored, want)
    for field in common.FREQUENCY_FIELDS:
        doctored = list(want)
        doctored[side] = want[side]._replace(**{field: getattr(want[side], field) + 2.0 * ft})
        assert common.compare(doctored, want), field
    swapped = list(want)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    assert common.compare(swapped, want)
    renamed = list(want)
    renamed[0] = want[0]._replace(theta_mult=want[0].theta_mult + 1)
    assert common.compare(renamed, want)
    renamed[0] = want[0]._replace(ear="right")
    assert common.compare(renamed, want)


def test_vectors_file_is_json_with_the_story_keys():
    data = json.loads(common.VECTORS.read_text(encoding="utf-8"))
    assert len(data["component_cases"]) == len(common.case_names())
    assert sum(int(c["components"]) for c in data["component_cases"]) == sum(
        len(common.want_rows(n)) for n in common.case_names())
