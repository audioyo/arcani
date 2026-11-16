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
(the same in both channels, so the left channel is measured against the left
ear's rows), and each binaural ear from reference.binaural.render (the
binaural layer alone, as the join tap also holds the bus). Each tap is shown
to be a real waveform before it is judged.

Fixtures: every component case of the vectors that is an Epic 2 fixture file
with no muted ear (the muted cases reuse binaural-beat-6.json and are
covered by the table tests). Static fixtures render their whole length, at
most `case_length_s` of the vectors (both-layers.json is 600 s; its first
10 s hold the same lines); rate-cycle fixtures render 120 s.

Must-fail: the harness drops one side-frequency row (the strongest one) from
the reference table of each layer tap and the cross-check must fail. No
fault code in engine/ or reference/.

Run time: static fixtures at both sample rates; the rate-cycle fixtures,
each about 10 s per tap in the spectrum tool, at the highest sample rate
only (the table does not depend on the sample rate).
"""

import functools
import importlib
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


@functools.lru_cache(maxsize=4)
def taps(name, fs):
    """{(layer, ear): one channel} of the reference render of a fixture case."""
    c = common.case(name)
    path = common.FIXTURES_VALID / c["fixture"]
    recipe = common.load_fixture(c["fixture"])
    ideal = common.reference_module("ideal")
    if is_cycle(name):
        seconds = CYCLE_SECONDS
        assert float(recipe["length_s"]) == seconds, (name, recipe["length_s"])
    else:
        seconds = min(float(recipe["length_s"]), float(common.constants()["case_length_s"]))
    frames = ideal.seconds_to_samples(seconds, fs)
    out = {}
    if "theta_reference" in recipe or "gamma_pac" in recipe:
        render = common.reference_module("stub_chain").render(path, fs, frames=frames)
        if "theta_reference" in recipe:
            out[("theta_reference", "left")] = np.ascontiguousarray(render["theta"][0::2])
        if "gamma_pac" in recipe:
            out[("gamma_pac", "left")] = np.ascontiguousarray(render["gamma"][0::2])
    if "binaural" in recipe:
        left, right = common.reference_module("binaural").render(recipe["binaural"], fs, frames)
        out[("binaural", "left")] = np.ascontiguousarray(left)
        out[("binaural", "right")] = np.ascontiguousarray(right)
    for key, x in out.items():
        assert x.size == frames, (name, key, x.size)
    return out


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
