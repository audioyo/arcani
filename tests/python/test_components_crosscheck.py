"""Cross-check: reference renders of every Epic 2 shape fixture held to the component table (Story 3.1).

docs/signal-spec.md, Components, Cross-check. The spectrum tool
(tests/assertions/spectrum.py, unchanged) measures reference renders of the
Epic 2 fixtures, one layer tap at a time, through the cross-check tool
(tests/assertions/component_check.py, calibrated in
tests/python/test_component_check_tool.py), and the measurement is held to
the reference component table (reference/components.py):

- A fixture without a rate cycle: `check_static` on each layer tap; every
  measured line within row spectral-component-level of the tap's strongest
  is a table row within rows spectrum-frequency and spectrum-level, and
  every table row is measured.
- A fixture with a rate cycle (120 s, two whole cycles): `check_bands`; the
  table's intervals, widened by the tool's resolution plus each sweep's
  spectral edge, merge into bands. The edge is closed form, never tuned to
  a fixture: a row swept sinusoidally with half width A over period P has
  the Bessel line spectrum of modulation index A * P, lines 1 / P apart, and
  the edge is the distance past A at which those lines fall below row
  spectral-component-level re the row's strongest line (spec amendment
  2026-11-16, on sweep turning points that put lines up to 0.15 Hz past an
  interval);
  each band's power equals the sum of its rows' level^2 within row
  spectrum-level, and no line at or above the threshold lies outside them.

Taps: the theta reference and gamma PAC taps of reference.stub_chain.render
(the same in both channels: the right channel is asserted equal to the left
bit for bit, and each channel is measured against its own ear's rows), and each binaural ear from reference.binaural.render (the
binaural layer alone, as the join tap also holds the bus). Each tap is shown
to be a real waveform before it is judged.

Fixtures: every component case of the vectors that is an Epic 2 fixture file
with no muted ear (the muted cases reuse binaural-beat-6.json and are
covered by the table tests). Static fixtures render their whole length, at
most `case_length_s` of the vectors (both-layers.json is 600 s; its first
10 s hold the same lines); rate-cycle fixtures render 120 s.

Cases without a fixture file (rendered from their vector recipe in tmp_path):
the static ones line by line, and `swell-cycles-60deg-apart` and
`bursts-cycles-60deg-apart` by band power at 120 s, so a nonzero coupling
phase and two rate cycles with different start phases are measured too.

Must-fail: the harness drops one side-frequency row (the strongest one) from
the reference table of each layer tap and the cross-check must fail. No
fault code in engine/ or reference/.

Run time: static fixtures at both sample rates; the rate-cycle fixtures,
each about 10 s per tap in the spectrum tool, at the highest sample rate
only (the table does not depend on the sample rate).
"""

import functools
import importlib
import json
import math

import numpy as np
import pytest

import components_common as common
from assertions import row as table_row
from assertions.tables import load_tables

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
CYCLE_RATE = max(SAMPLE_RATES)
CYCLE_SECONDS = 120.0


def cc():
    return importlib.import_module("assertions.component_check")


def crosscheck_cases():
    out = []
    for c in common.fixture_cases():
        if c["mute"] != "none":
            continue
        out.append(c["case"])
    return out


def is_cycle(name):
    return common.has_cycle(common.case_layers(name))


STATIC = [n for n in crosscheck_cases() if not is_cycle(n)]
CYCLES = [n for n in crosscheck_cases() if is_cycle(n)]


def has_side_rows(name):
    return any((r.gamma_mult, r.theta_mult) != (0, 0) for r in common.want_rows(name))


# The must-fail cases: fixtures whose table has a side frequency to drop.
STATIC_SIDES = [n for n in STATIC if has_side_rows(n)]
CYCLE_SIDES = [n for n in CYCLES if has_side_rows(n)]


def render_taps(path, recipe, fs, seconds):
    """{(layer, ear): one channel} of the reference render of a recipe file.

    The theta and gamma taps are the same in both channels: the right channel
    is asserted equal to the left bit for bit, then each is measured against
    its own ear's rows.
    """
    frames = common.reference_module("ideal").seconds_to_samples(seconds, fs)
    out = {}
    if "theta_reference" in recipe or "gamma_pac" in recipe:
        render = common.reference_module("stub_chain").render(path, fs, frames=frames)
        for layer, key in (("theta_reference", "theta"), ("gamma_pac", "gamma")):
            if layer not in recipe:
                continue
            left = np.ascontiguousarray(render[key][0::2])
            right = np.ascontiguousarray(render[key][1::2])
            assert left.tobytes() == right.tobytes(), (path, layer, "the right channel differs from the left")
            out[(layer, "left")] = left
            out[(layer, "right")] = right
    if "binaural" in recipe:
        left, right = common.reference_module("binaural").render(recipe["binaural"], fs, frames)
        out[("binaural", "left")] = np.ascontiguousarray(left)
        out[("binaural", "right")] = np.ascontiguousarray(right)
    for key, x in out.items():
        assert x.size == frames, (path, key, x.size)
    return out


@functools.lru_cache(maxsize=4)
def taps(name, fs):
    """{(layer, ear): one channel} of the reference render of a fixture case."""
    c = common.case(name)
    path = common.FIXTURES_VALID / c["fixture"]
    recipe = common.load_fixture(c["fixture"])
    if is_cycle(name):
        seconds = CYCLE_SECONDS
        assert float(recipe["length_s"]) == seconds, (name, recipe["length_s"])
    else:
        seconds = min(float(recipe["length_s"]), float(common.constants()["case_length_s"]))
    return render_taps(path, recipe, fs, seconds)


def tables_of(name):
    return common.as_rows(common.reference_components().component_table_from_file(
        common.FIXTURES_VALID / common.case(name)["fixture"]))


def real_waveform(where, x):
    """Silence is not evidence: the tap swings well above zero and is finite."""
    assert np.all(np.isfinite(x)), where
    peak = float(np.max(np.abs(x)))
    assert peak > 0.01, (where, peak)


def judged(name, fs, check):
    """(where, reports, rows, x) per layer tap of a fixture."""
    table = tables_of(name)
    out = []
    for (layer, ear), x in taps(name, fs).items():
        rows = common.layer_rows(table, layer, ear)
        where = f"{name} {fs} {layer} {ear}"
        assert rows, f"{where}: the table has no rows for a tap the render has"
        real_waveform(where, x)
        out.append((where, check(where, x, fs, rows), rows, x))
    return out


def failing(reports):
    return [r for r in reports if r["result"] != "pass"]


def drop_strongest_side(rows):
    """The table with its strongest side-frequency row dropped (the harness's doctoring); None without one."""
    side = [r for r in rows if (r.gamma_mult, r.theta_mult) != (0, 0)]
    if not side:
        return None
    s = max(side, key=lambda r: r.level)
    out = list(rows)
    out.remove(s)
    return out


def test_every_epic_2_shape_is_cross_checked():
    """Each theta shape, uncoupled gamma, smooth swell, bursts, and binaural have a fixture here."""
    seen = set()
    for name in crosscheck_cases():
        layers = common.case_layers(name)
        if "theta_reference" in layers:
            seen.add(("theta", layers["theta_reference"]["shape"]))
        if "gamma_pac" in layers:
            seen.add(("gamma", layers["gamma_pac"]["coupling"]))
        if "binaural" in layers:
            seen.add(("binaural", "cycle" if "beat_rate_cycle" in layers["binaural"] else "fixed"))
    for want in (("theta", "sine"), ("theta", "smoothed_on_off"), ("theta", "sawtooth"), ("theta", "reverse_saw"),
                 ("gamma", "uncoupled"), ("gamma", "smooth_swell"), ("gamma", "bursts"), ("binaural", "fixed"),
                 ("binaural", "cycle")):
        assert want in seen, want
    assert STATIC and CYCLES and STATIC_SIDES and CYCLE_SIDES
    for name in CYCLES:
        recipe = common.load_fixture(common.case(name)["fixture"])
        assert float(recipe["length_s"]) == CYCLE_SECONDS, name
        # Two whole cycles: every cycle period divides the render length.
        for layer, key in (("theta_reference", "rate_cycle"), ("gamma_pac", "rate_cycle"),
                           ("binaural", "beat_rate_cycle")):
            cycle = (recipe.get(layer) or {}).get(key)
            if cycle is not None:
                ratio = CYCLE_SECONDS / float(cycle["period_s"])
                assert ratio == math.floor(ratio) and ratio >= 2, (name, layer)


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("name", STATIC)
def test_static_fixture_lines_are_the_table(name, fs):
    results = judged(name, fs, cc().check_static)
    problems = []
    for where, reports, _, _ in results:
        assert [r["row"] for r in reports] == ["spectrum-frequency", "spectrum-level",
                                               common.COMPONENT_ROW], reports
        problems += [(where, r) for r in failing(reports)]
    assert not problems, problems


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("name", STATIC_SIDES)
def test_must_fail_static_cross_check_with_one_side_frequency_dropped(name, fs):
    doctored = 0
    for (layer, ear), x in taps(name, fs).items():
        rows = common.layer_rows(tables_of(name), layer, ear)
        dropped = drop_strongest_side(rows)
        if dropped is None:
            continue
        doctored += 1
        reports = cc().check_static(f"{name} {fs} {layer} {ear} dropped", x, fs, dropped)
        assert failing(reports), (name, fs, layer, ear, reports)
    assert doctored > 0, name


@pytest.mark.parametrize("name", CYCLES)
def test_rate_cycle_fixture_band_powers_are_the_table(name):
    fs = CYCLE_RATE
    results = judged(name, fs, cc().check_bands)
    problems = []
    for where, reports, _, _ in results:
        rows = {r["row"] for r in reports}
        assert rows == {"spectrum-level", common.COMPONENT_ROW}, reports
        problems += [(where, r) for r in failing(reports)]
    assert not problems, problems


@pytest.mark.parametrize("name", CYCLE_SIDES)
def test_must_fail_band_cross_check_with_one_side_frequency_dropped(name):
    fs = CYCLE_RATE
    doctored = 0
    for (layer, ear), x in taps(name, fs).items():
        rows = common.layer_rows(tables_of(name), layer, ear)
        dropped = drop_strongest_side(rows)
        if dropped is None:
            continue
        doctored += 1
        reports = cc().check_bands(f"{name} {fs} {layer} {ear} dropped", x, fs, dropped)
        assert failing(reports), (name, layer, ear, reports)
    assert doctored > 0, name


def test_the_threshold_is_the_row():
    assert cc().threshold_db() == table_row(common.COMPONENT_ROW).value


# ------------------------------------------------------------ the phase-dependent model, rendered

# Cases no fixture file has: every measured fixture sits at the 0 degree
# coupling phase with in-phase rate cycles, so these renders check the parts of
# the model that turn with a phase: summed burst lines at a nonzero coupling
# phase, and a row swept by two rate cycles with different start phases.
NO_FILE = [n for n in common.case_names() if common.case(n)["fixture"] == "none"]
NO_FILE_STATIC = [n for n in NO_FILE if not is_cycle(n)]
NO_FILE_CYCLES = ["swell-cycles-60deg-apart", "bursts-cycles-60deg-apart"]


def written_case(name, folder, seconds):
    """The case recipe with length_s set to `seconds`, written to folder; (path, recipe)."""
    recipe = common.case_recipe(name)
    recipe["length_s"] = seconds
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(recipe), encoding="utf-8")
    return path, recipe


def case_judged(name, x_taps, fs, check):
    table = common.as_rows(common.reference_components().component_table(common.case_recipe(name)))
    out = []
    for (layer, ear), x in x_taps.items():
        rows = common.layer_rows(table, layer, ear)
        where = f"{name} {fs} {layer} {ear}"
        assert rows, where
        real_waveform(where, x)
        out.append((where, check(where, x, fs, rows), rows, x))
    return out


def test_the_phase_cases_are_present():
    for name in ("bursts-60hz-135deg", "bursts-45hz-45deg"):
        assert name in NO_FILE_STATIC, name
    for name in NO_FILE_CYCLES:
        assert name in NO_FILE and is_cycle(name), name


@pytest.mark.parametrize("fs", SAMPLE_RATES)
@pytest.mark.parametrize("name", NO_FILE_STATIC)
def test_static_case_without_a_fixture_lines_are_the_table(name, fs, tmp_path):
    seconds = float(common.constants()["case_length_s"])
    path, recipe = written_case(name, tmp_path, seconds)
    x_taps = render_taps(path, recipe, fs, seconds)
    problems = []
    doctored = 0
    for where, reports, rows, x in case_judged(name, x_taps, fs, cc().check_static):
        problems += [(where, r) for r in failing(reports)]
        dropped = drop_strongest_side(rows)
        if dropped is not None:
            doctored += 1
            assert failing(cc().check_static(where + " dropped", x, fs, dropped)), where
    assert not problems, problems
    if any((r.gamma_mult, r.theta_mult) != (0, 0) for r in common.want_rows(name)):
        assert doctored > 0, name


@pytest.mark.parametrize("name", NO_FILE_CYCLES)
def test_rate_cycle_case_without_a_fixture_band_powers_are_the_table(name, tmp_path):
    fs = CYCLE_RATE
    path, recipe = written_case(name, tmp_path, CYCLE_SECONDS)
    x_taps = render_taps(path, recipe, fs, CYCLE_SECONDS)
    problems = []
    doctored = 0
    for where, reports, rows, x in case_judged(name, x_taps, fs, cc().check_bands):
        problems += [(where, r) for r in failing(reports)]
        dropped = drop_strongest_side(rows)
        if dropped is not None:
            doctored += 1
            assert failing(cc().check_bands(where + " dropped", x, fs, dropped)), where
    assert not problems, problems
    assert doctored > 0, name
