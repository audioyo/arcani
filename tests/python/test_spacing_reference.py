"""Python reference spacing rule against the signal spec vectors (Story 3.2).

The reference computes every distance, margin, failure, and detail on its
own from docs/signal-spec.md, Spacing, and its own component table
(reference/components.py); the rules of
tests/python/test_reference_independent.py apply. Thresholds come from
tests/tables/*.tsv through the assertion call `assertions.row`; no
threshold is written here as a literal.

Contract with reference/spacing.py (Story 3.2 spec, Implementation Notes):

- `SPACING_HZ = 50.0  # row spacing-rule`, cross-checked against the row.
- `SpacingPair`, a NamedTuple with the fields ear ("left" or "right"),
  min_distance_hz, margin_hz, component_1 (the smaller table index),
  component_2, where (the where text with the reference's own numbers).
- `SpacingError(ValueError)` with the attributes parameter, value, rule
  ("spacing_rule"), limit, detail.
- `spacing_margins(recipe, mute="none")`: {"left": SpacingPair or None,
  "right": ...}, the worst pair of each ear (None with fewer than two layers
  in that ear). It is read here for rejected recipes too, whose margins are
  below 0 (Vectors: spacing margins).
- `check_spacing(recipe, mute="none")`: None when every pair passes, else
  raises SpacingError for the reported failure.
- `pair_form(c_hz, di, dj, db, gamma=(0.0, 0.0), theta=(0.0, 0.0),
  beat=(0.0, 0.0))`: (x, y, h, min_distance_hz, first), each cycle as
  (swing_hz, start_phase_deg) on the 60 s period, first the cycle fraction
  t / P of the first time, None without a sweep.

The vectors' fixture cases hold the layer objects of their file, and the
four starter fixtures hold the starter values of
_bmad-output/specs/spec-arcani-v0-1/starter-recipes.md.
"""

import copy
import inspect
import json
import math
import re

import pytest

import spacing_common as common
from assertions import row as table_row
from assertions.tables import load_tables

STARTERS_DOC = common.REPO_ROOT / "_bmad-output" / "specs" / "spec-arcani-v0-1" / "starter-recipes.md"


def ref():
    return common.reference_spacing()


def ref_table(recipe, mute="none"):
    return common.reference_module("components").component_table(recipe, mute)


def row_name(r):
    return f"{r.layer} ({r.gamma_mult}, {r.theta_mult}, {r.beat_mult})"


def margin_problems(got, m, table):
    """Problems of one ear's reference SpacingPair (or None) against the margin vector `m`."""
    if m["pairs"] == 0:
        return [] if got is None else [f"a pair in an ear with none: {got}"]
    if got is None:
        return ["no pair, the vectors have one"]
    problems = []
    tol = common.frequency_error()
    if got.ear != m["ear"]:
        problems.append(f"ear {got.ear}, want {m['ear']}")
    if not abs(got.min_distance_hz - common.ideal(m["distance"])) < tol:
        problems.append(f"min distance {got.min_distance_hz!r}, want {m['distance']}")
    if not abs(got.margin_hz - common.ideal(m["margin"])) < tol:
        problems.append(f"margin {got.margin_hz!r}, want {m['margin']}")
    if got.margin_hz != got.min_distance_hz - common.rule_hz():
        problems.append("margin is not one subtraction of row spacing-rule")
    if (got.component_1, got.component_2) != (int(m["index_1"]), int(m["index_2"])):
        problems.append(f"components {got.component_1}, {got.component_2}, want {m['index_1']}, {m['index_2']}")
    else:
        for index, want in ((got.component_1, m["row_1"]), (got.component_2, m["row_2"])):
            if row_name(table[index]) != want:
                problems.append(f"row {index} is {row_name(table[index])}, want {want}")
    problems += common.compare_where_texts(got.where, m["where"])
    return problems


# ------------------------------------------------------------ vectors and rows


def test_constants_agree_with_the_rows():
    c = common.constants()
    assert float(c["rule_hz"]) == common.rule_hz()
    assert float(c["time_error_s"]) == common.time_error_s()
    assert c["rule"] == "spacing_rule"
    assert c["limit"] == common.limit_text()
    assert c["whole_session"] == common.WHOLE_SESSION
    assert c["listed_intervals"] == common.LISTED_INTERVALS
    assert c["carrier_fields"] == {"gamma_pac": "/gamma_pac/carrier_hz", "binaural": "/binaural/carrier_left_hz"}
    assert c["must_fail_fixture"] == "spacing-binaural-250-256-gamma-260.json"
    assert set(c["starter_fixtures"]) < set(c["fixtures"])
    assert c["must_fail_fixture"] in c["fixtures"]
    assert len(c["starter_fixtures"]) == 4


def test_spacing_rows_are_present_and_read_through_the_assertion_call():
    for row_id in (common.RULE_ROW, common.TIME_ROW):
        r = table_row(row_id)
        assert r.value > 0.0, r
        assert r.value == load_tables()[row_id].value
    assert common.period_s() > 0.0


def test_reference_constant_equals_row_spacing_rule():
    assert ref().SPACING_HZ == common.rule_hz()


def test_every_case_recipe_holds_its_layer_cells_and_the_fixtures_their_files():
    fixtures = 0
    for c in common.cases():
        recipe = common.case_recipe(c["case"])
        layers = common.case_layers(c["case"])
        for layer in common.LAYERS:
            assert recipe.get(layer) == layers.get(layer), (c["case"], layer)
        if c["fixture"] != "none":
            fixtures += 1
            fixture = common.load_fixture(c["fixture"])
            for layer in common.LAYERS:
                assert fixture.get(layer) == layers.get(layer), (c["case"], layer)
    assert fixtures > len(common.constants()["fixtures"])
    for name in common.constants()["fixtures"]:
        assert name.removesuffix(".json") in common.case_names(), name


def test_the_margin_vectors_cover_every_case_and_ear():
    rows = common.vectors()["spacing_margins"]
    assert len(rows) == 2 * len(common.cases())
    for c in common.cases():
        for ear in common.EARS:
            m = common.margin(c["case"], ear)
            assert (m["pairs"] > 0) == (m["distance"] != "none"), m


def test_rejected_cases_are_their_worst_failing_pair():
    """The reported failure is the smaller distance of the two ears, ties to the left ear."""
    for c in common.cases():
        left, right = common.margin(c["case"], "left"), common.margin(c["case"], "right")
        dists = [(common.ideal(m["distance"]) if m["distance"] != "none" else math.inf, n)
                 for n, m in enumerate((left, right))]
        worst = min(dists)
        assert (c["result"] == "rejected") == (worst[0] < common.rule_hz()), c["case"]
        if c["result"] == "rejected":
            assert c["detail"].startswith(common.EARS[worst[1]] + " ear: "), c["case"]


# ------------------------------------------------------------ the reference module


def test_reference_module_contract():
    mod = ref()
    assert mod.SpacingPair._fields == ("ear", "min_distance_hz", "margin_hz", "component_1", "component_2", "where")
    assert issubclass(mod.SpacingError, ValueError)
    for fn in (mod.spacing_margins, mod.check_spacing):
        params = inspect.signature(fn).parameters
        assert list(params) == ["recipe", "mute"] and params["mute"].default == "none", fn
    params = inspect.signature(mod.pair_form).parameters
    assert list(params) == ["c_hz", "di", "dj", "db", "gamma", "theta", "beat"]
    for name in ("gamma", "theta", "beat"):
        assert tuple(params[name].default) == (0.0, 0.0), name


@pytest.mark.parametrize("name", common.case_names())
def test_reference_margins_equal_the_vectors(name):
    c = common.case(name)
    recipe = common.case_recipe(name)
    got = ref().spacing_margins(recipe, c["mute"])
    assert set(got) == set(common.EARS)
    table = ref_table(recipe, c["mute"])
    for ear in common.EARS:
        problems = margin_problems(got[ear], common.margin(name, ear), table)
        assert not problems, f"{name} {ear}:\n" + "\n".join(problems)
        if got[ear] is not None:
            assert isinstance(got[ear], ref().SpacingPair)
            assert isinstance(got[ear].component_1, int) and isinstance(got[ear].component_2, int)
            assert got[ear].component_1 < got[ear].component_2


@pytest.mark.parametrize("name", common.case_names())
def test_reference_check_spacing_passes_or_raises_as_the_vectors_say(name):
    c = common.case(name)
    recipe = common.case_recipe(name)
    if c["result"] == "pass":
        assert ref().check_spacing(recipe, c["mute"]) is None
        return
    assert c["result"] == "rejected"
    with pytest.raises(ref().SpacingError) as info:
        ref().check_spacing(recipe, c["mute"])
    e = info.value
    problems = common.error_problems(e.parameter, e.value, e.rule, e.limit, e.detail, c)
    assert not problems, f"{name}:\n" + "\n".join(problems)


@pytest.mark.parametrize("r", common.pair_rows(), ids=lambda r: r["label"])
def test_reference_pair_form_equals_the_pair_vectors(r):
    tol = common.frequency_error()
    x, y, h, distance, first = ref().pair_form(
        float.fromhex(r["c_hex"]), int(r["di"]), int(r["dj"]), int(r["db"]),
        gamma=(float.fromhex(r["swing_gamma_hex"]), float.fromhex(r["start_gamma_hex"])),
        theta=(float.fromhex(r["swing_theta_hex"]), float.fromhex(r["start_theta_hex"])),
        beat=(float.fromhex(r["swing_beat_hex"]), float.fromhex(r["start_beat_hex"])))
    for got, want in ((x, r["x"]), (y, r["y"]), (h, r["h"]), (distance, r["distance"])):
        assert abs(got - common.ideal(want)) < tol, (r["label"], got, want)
    assert distance >= 0.0
    if r["first"] == "none":
        assert first is None, r["label"]
    else:
        assert first is not None, r["label"]
        p = common.period_s()
        assert common.around_cycle(first * p, common.ideal(r["first"]) * p, p) < common.time_error_s(), (
            r["label"], first, r["first"])


# ------------------------------------------------------------ matrix rows


def test_matrix_must_fail_fixture_is_rejected_in_the_right_ear():
    recipe = common.load_fixture(common.constants()["must_fail_fixture"])
    with pytest.raises(ref().SpacingError) as info:
        ref().check_spacing(recipe)
    e = info.value
    assert (e.parameter, e.value, e.rule, e.limit) == (
        "/binaural/carrier_left_hz", "4", "spacing_rule", common.limit_text())
    assert e.detail == "right ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 1) at 256 Hz; whole session"
    # The right ear muted: the left ear's 10 Hz pair is reported instead.
    with pytest.raises(ref().SpacingError) as info:
        ref().check_spacing(recipe, "right")
    assert info.value.value == "10"
    assert info.value.detail.startswith("left ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 0) at 250 Hz")


def binaural_moved(name, delta_hz):
    recipe = copy.deepcopy(common.case_recipe(name))
    recipe["binaural"]["carrier_left_hz"] = recipe["binaural"]["carrier_left_hz"] + delta_hz
    return recipe


def test_matrix_exactly_50_hz_passes_with_margin_0_and_less_fails():
    exact = common.case_recipe("spacing-exactly-50hz")
    assert ref().check_spacing(exact) is None
    for ear in common.EARS:
        p = ref().spacing_margins(exact)[ear]
        assert p.min_distance_hz == common.rule_hz() and p.margin_hz == 0.0
    # Must-fail made here: the binaural carrier 1e-9 Hz closer to the 450 Hz theta carrier.
    with pytest.raises(ref().SpacingError):
        ref().check_spacing(binaural_moved("spacing-exactly-50hz", 1e-9))
    # And 1e-9 Hz away passes with a margin above 0.
    away = binaural_moved("spacing-exactly-50hz", -1e-9)
    assert ref().check_spacing(away) is None
    assert ref().spacing_margins(away)["left"].margin_hz > 0.0
    with pytest.raises(ref().SpacingError) as info:
        ref().check_spacing(common.case_recipe("spacing-49.99hz"))
    assert float(info.value.value) == 450.0 - 400.01


def test_matrix_rate_cycle_collision_at_a_turning_point_whatever_the_session_length():
    c = common.case("spacing-turning-point")
    session = table_row("session-length")
    assert session.unit == "h", session
    for length in (1, 10, 60, session.max * 3600):
        recipe = dict(common.case_recipe(c["case"]), length_s=length)
        with pytest.raises(ref().SpacingError) as info:
            ref().check_spacing(recipe)
        e = info.value
        problems = common.error_problems(e.parameter, e.value, e.rule, e.limit, e.detail, c)
        assert not problems, f"length {length}:\n" + "\n".join(problems)
    # Must-pass twin: the theta carrier 1 Hz higher keeps 50.5 Hz at the turning point.
    higher = common.case_recipe(c["case"])
    higher["theta_reference"]["carrier_hz"] += 1.0
    assert ref().check_spacing(higher) is None
    assert abs(ref().spacing_margins(higher)["right"].min_distance_hz - (common.rule_hz() + 0.5)) < \
        common.frequency_error()


def test_matrix_sweep_together_is_judged_by_the_multipliers_not_the_intervals():
    name = "spacing-sweep-together"
    recipe = common.case_recipe(name)
    m = common.margin(name, "left")
    table = ref_table(recipe)
    a, b = table[int(m["index_1"])], table[int(m["index_2"])]
    gap = max(b.low_hz - a.high_hz, a.low_hz - b.high_hz)
    assert gap < common.rule_hz(), "the listed intervals are closer than the rule"
    assert ref().check_spacing(recipe) is None
    got = ref().spacing_margins(recipe)["left"]
    assert got.min_distance_hz >= common.rule_hz()
    # Must-fail twin: the gamma cycle at 0 degrees no longer moves with the theta cycle.
    apart = copy.deepcopy(recipe)
    apart["gamma_pac"]["rate_cycle"]["start_phase_deg"] = 0
    with pytest.raises(ref().SpacingError) as info:
        ref().check_spacing(apart)
    assert abs(float(info.value.value) - gap) < common.frequency_error()


def test_matrix_one_layer_has_no_pair():
    for name in ("spacing-one-layer", "theta-sine-6hz"):
        got = ref().spacing_margins(common.case_recipe(name))
        assert got == {"left": None, "right": None}, name
        assert ref().check_spacing(common.case_recipe(name)) is None
    # A muted ear beside a theta reference has one layer in that ear.
    sleep = common.load_fixture("starter-sleep-layers.json")
    for mute, other in (("left", "right"), ("right", "left")):
        got = ref().spacing_margins(sleep, mute)
        assert got[mute] is None and got[other] is not None, mute


def test_matrix_ties_go_to_the_left_ear():
    """Both ears equal: the left ear is reported."""
    name = "spacing-cycles-60deg-apart"
    left, right = common.margin(name, "left"), common.margin(name, "right")
    assert left["distance"] == right["distance"]
    with pytest.raises(ref().SpacingError) as info:
        ref().check_spacing(common.case_recipe(name))
    assert info.value.detail.startswith("left ear: ")


# ------------------------------------------------------------ starters


def _starter_table():
    text = STARTERS_DOC.read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0] in ("Focus", "Learn", "Relax", "Sleep"):
            rows[cells[0]] = cells
    assert set(rows) == {"Focus", "Learn", "Relax", "Sleep"}
    depth = re.search(r"Theta reference AM depth: (\d+) percent in every starter", text)
    assert depth, "starter-recipes.md names no theta depth"
    return rows, float(depth.group(1))


def _num(pattern, text):
    m = re.search(pattern, text)
    assert m, (pattern, text)
    return float(m.group(1))


@pytest.mark.parametrize("mode", ("Focus", "Learn", "Relax", "Sleep"))
def test_starter_fixture_holds_the_starter_values(mode):
    rows, theta_depth = _starter_table()
    _, theta_cell, gamma_cell, binaural_cell, length_cell, loop_cell = rows[mode]
    recipe = common.load_fixture(f"starter-{mode.lower()}-layers.json")
    assert f"starter-{mode.lower()}-layers.json" in common.constants()["starter_fixtures"]
    t = recipe["theta_reference"]
    assert t["carrier_hz"] == _num(r"(\d+(?:\.\d+)?) Hz carrier", theta_cell)
    assert t["rate_hz"] == _num(r"sine AM at (?:a steady )?(\d+(?:\.\d+)?) Hz", theta_cell)
    assert t["am_depth_percent"] == theta_depth
    assert t["shape"] == "sine"
    assert "rate_cycle" not in t
    if gamma_cell == "Off":
        assert "gamma_pac" not in recipe
    else:
        g = recipe["gamma_pac"]
        assert g["carrier_hz"] == _num(r"(\d+) Hz carrier", gamma_cell)
        assert g["rate_hz"] == _num(r"AM at (\d+) Hz", gamma_cell)
        assert g["am_depth_percent"] == _num(r"depth (\d+) percent", gamma_cell)
        assert g["coupling_phase_deg"] == _num(r"coupling phase (\d+) degrees", gamma_cell)
        assert g["coupling"] == ("bursts" if "bursts" in gamma_cell else "smooth_swell")
        assert g["carrier_wave"] == "sine"
    if binaural_cell == "Off":
        assert "binaural" not in recipe
    else:
        b = recipe["binaural"]
        assert b["carrier_left_hz"] == _num(r"(\d+) Hz left", binaural_cell)
        top = _num(r"over 0 to (\d+(?:\.\d+)?) Hz", binaural_cell)
        cycle = b["beat_rate_cycle"]
        assert b["beat_rate_hz"] - cycle["swing_hz"] == 0.0 and b["beat_rate_hz"] + cycle["swing_hz"] == top
        assert cycle["period_s"] == _num(r"every (\d+) s", binaural_cell)
        # From 0 Hz rising (Spacing, Fixtures): the start phase is the cycle minimum.
        assert math.isclose(math.sin(math.radians(cycle["start_phase_deg"])), -1.0)
    if loop_cell.startswith("Yes"):
        cap = _num(r"max run time (\d+) min", loop_cell)
        assert recipe["loop"] == {"mode": mode.lower(), "opening_s": 60, "body_s": 120, "max_run_time_min": cap}
        assert recipe["length_s"] == cap * 60
    else:
        assert "loop" not in recipe
        assert recipe["length_s"] == _num(r"(\d+) min", length_cell) * 60
    for key in ("loudness_gain_db", "fade_s", "ramp_s"):
        assert key not in recipe
    for layer in common.LAYERS:
        for key in (recipe.get(layer) or {}):
            assert "level" not in key and "ramp" not in key and "fade" not in key, (layer, key)


@pytest.mark.parametrize("name", [n.removesuffix(".json") for n in common.constants()["starter_fixtures"]])
def test_starter_fixture_passes_with_a_margin_in_each_ear(name):
    recipe = common.load_fixture(name + ".json")
    assert ref().check_spacing(recipe) is None
    got = ref().spacing_margins(recipe)
    for ear in common.EARS:
        assert got[ear] is not None and got[ear].margin_hz >= 0.0, (name, ear)


# ------------------------------------------------------------ must-fail of the comparisons


def test_must_fail_the_detail_and_error_comparisons_catch_doctored_texts():
    c = common.case("spacing-three-cycles")
    _, _, (kind, time, rates) = common.parse_detail(c["detail"], False)
    assert kind == "first"
    s = common.shortest
    good = (f"right ear: gamma_pac (-1, -1, 0) at 201 Hz and binaural (0, 0, 1) at 151.5 Hz; first at "
            f"{s(common.ideal(time))} s, gamma rate {s(common.ideal(rates[0]))} Hz, theta rate "
            f"{s(common.ideal(rates[1]))} Hz, beat rate {s(common.ideal(rates[2]))} Hz")
    value = s(common.ideal(c["value"]))
    assert common.error_problems(c["parameter"], value, "spacing_rule", c["limit"], good, c) == []
    ft, tt, rt = common.frequency_error(), common.time_error_s(), common.rate_error()
    doctored = [
        ("right ear", "left ear"),
        ("gamma_pac (-1, -1, 0)", "gamma_pac (-1, 1, 0)"),
        ("binaural (0, 0, 1)", "theta_reference (0, 0, 1)"),
        ("at 201 Hz", "at 201.5 Hz"),
        ("at 201 Hz", "at 201.0 Hz"),
        (f"first at {s(common.ideal(time))}", f"first at {s(common.ideal(time) + 2 * tt)}"),
        (f"gamma rate {s(common.ideal(rates[0]))}", f"gamma rate {s(common.ideal(rates[0]) + 2 * rt)}"),
        (f"beat rate {s(common.ideal(rates[2]))} Hz", "beat rate none"),
        ("; first at", "; at"),
    ]
    for old, new in doctored:
        assert good.count(old) == 1, old
        bad = good.replace(old, new)
        assert common.error_problems(c["parameter"], value, "spacing_rule", c["limit"], bad, c), (old, new)
    assert common.error_problems("/gamma_pac/carrier_hz", value, "spacing_rule", c["limit"], good, c)
    assert common.error_problems(c["parameter"], s(common.ideal(c["value"]) + 2 * ft), "spacing_rule",
                                 c["limit"], good, c)
    assert common.error_problems(c["parameter"], value + "0", "spacing_rule", c["limit"], good, c)
    assert common.error_problems(c["parameter"], value, "spacing", c["limit"], good, c)
    assert common.error_problems(c["parameter"], value, "spacing_rule", ">= 40 Hz (row spacing-rule)", good, c)
    # A time within the row around the cycle end is near 0 s.
    p = common.period_s()
    assert common.around_cycle(0.0, p - 0.5 * tt, p) < tt
    assert not common.around_cycle(0.0, p - 2 * tt, p) < tt
    # A static pair's value must be exact.
    mf = common.case("spacing-binaural-250-256-gamma-260")
    detail = mf["detail"]
    assert common.error_problems(mf["parameter"], "4", "spacing_rule", mf["limit"], detail, mf) == []
    assert common.error_problems(mf["parameter"], s(4.0 + 0.5 * ft), "spacing_rule", mf["limit"], detail, mf)


def test_must_fail_the_margin_comparison_catches_doctored_pairs():
    name = "spacing-three-cycles"
    recipe = common.case_recipe(name)
    table = ref_table(recipe)
    m = common.margin(name, "right")
    Pair = ref().SpacingPair
    _, time, rates = common.parse_where(m["where"], False)
    s = common.shortest
    where = (f"first at {s(common.ideal(time))} s, gamma rate {s(common.ideal(rates[0]))} Hz, "
             f"theta rate {s(common.ideal(rates[1]))} Hz, beat rate {s(common.ideal(rates[2]))} Hz")
    d = common.ideal(m["distance"])
    good = Pair("right", d, d - common.rule_hz(), int(m["index_1"]), int(m["index_2"]), where)
    assert margin_problems(good, m, table) == []
    ft = common.frequency_error()
    for bad in (good._replace(min_distance_hz=d + 2 * ft, margin_hz=d + 2 * ft - common.rule_hz()),
                good._replace(margin_hz=math.nextafter(good.margin_hz, 0.0)),
                good._replace(component_2=good.component_2 + 1),
                good._replace(ear="left"),
                good._replace(where=common.WHOLE_SESSION),
                None):
        assert margin_problems(bad, m, table), bad


def test_must_fail_the_shortest_text_check():
    for text in ("4", "260", "151.5", "0.1", "1e-07", "0.0001", "1e-04", "3.245203439081782"):
        assert common.is_shortest(text), text
    for text in ("4.0", "260.0", "0151.5", "0.10", "3.2452034390817820", "+4", "4.", "x"):
        assert not common.is_shortest(text), text
    assert common.shortest(50.0) == "50"
    assert common.limit_text() == common.constants()["limit"]


def test_must_fail_the_grammar_rejects_broken_details():
    good = "right ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural (0, 0, 1) at 256 Hz; whole session"
    common.parse_detail(good, True)
    for bad in (good.replace("right ear", "both ears"),
                good.replace("; whole session", ""),
                good.replace("whole session", "all session"),
                good.replace("gamma_pac (-1, 0, 0)", "gamma_pac (-1, 0)"),
                good.replace(" at 256 Hz", " at 256"),
                good.replace("gamma_pac", "gamma"),
                good + "; whole session"):
        with pytest.raises(common.GrammarError):
            common.parse_detail(bad, True)
    first = ("left ear: theta_reference (0, -1, 0) at 326 Hz and gamma_pac (1, 1, 0) at 299 Hz; first at 6.9 s, "
             "gamma rate 59.7 Hz, theta rate 5.3 Hz, beat rate none")
    common.parse_detail(first, True)
    for bad in (first.replace("beat rate none", "beat rate none Hz"),
                first.replace("gamma rate 59.7 Hz", "gamma rate 59.7"),
                first.replace(" s, gamma", ", gamma")):
        with pytest.raises(common.GrammarError):
            common.parse_detail(bad, True)


def test_vectors_file_is_json_with_the_story_keys():
    data = json.loads(common.VECTORS.read_text(encoding="utf-8"))
    assert len(data["spacing_cases"]) == len(common.case_names())
    assert {c["result"] for c in data["spacing_cases"]} == {"pass", "rejected"}
    assert sum(1 for c in data["spacing_cases"] if c["case"].startswith("ad5-")) == 14
