"""Shared harness of the Story 3.1 component table tests (not a test file).

The component vectors (tests/data/signal_spec_vectors.json, keys
`component_constants`, `component_cases`, `components`; docs/signal-spec.md,
Components) expanded to table order, the two error rows read through the
assertion call `assertions.row`, and one comparison of a table against the
vector rows. The comparison is the assertion every component table test
uses (the Python reference table, the engine table of the tap dump, the
decoded hash probe component), so its must-fail cases live in
tests/python/test_components_reference.py, made by doctoring a table here in
the harness.

A table row is anything with the attributes `layer`, `ear`, `center_hz`,
`low_hz`, `high_hz`, `level`, `gamma_mult`, `theta_mult`, `beat_mult` (the
reference `Component` fits; `Row` here is the harness's own).

No threshold is written here as a literal.
"""

import importlib
import json
import sys
from collections import namedtuple
from decimal import Decimal
from pathlib import Path

from assertions import row as table_row

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
REFERENCE_TABLE = REPO_ROOT / "reference" / "components.py"

LAYERS = ("theta_reference", "gamma_pac", "binaural")
EARS = ("left", "right")
MUTES = ("none", "left", "right")
FIELDS = ("layer", "ear", "center_hz", "low_hz", "high_hz", "level", "gamma_mult", "theta_mult", "beat_mult")
FREQUENCY_FIELDS = ("center_hz", "low_hz", "high_hz")
LEVEL_ROW = "component-level-error"
FREQUENCY_ROW = "component-frequency-error"
COMPONENT_ROW = "spectral-component-level"

Row = namedtuple("Row", FIELDS)

_vectors = None


def vectors():
    global _vectors
    if _vectors is None:
        _vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        for key in ("component_constants", "component_cases", "components"):
            assert key in _vectors, f"the vectors file has no {key} (Story 3.1)"
    return _vectors


def constants():
    return vectors()["component_constants"]


def cases():
    return vectors()["component_cases"]


def case_names():
    return [c["case"] for c in cases()]


def case(name):
    found = [c for c in cases() if c["case"] == name]
    assert len(found) == 1, name
    return found[0]


def fixture_cases():
    """Cases that are an Epic 2 fixture file (named after it, or the same file with a muted ear)."""
    return [c for c in cases() if c["fixture"] != "none"]


def case_recipe(name):
    """The complete compile-ready recipe of a case, parsed."""
    return json.loads(case(name)["recipe"])


def case_layers(name):
    """The three layer cells of a case: layer name to the parsed object, absent layers left out."""
    c = case(name)
    return {layer: json.loads(c[layer]) for layer in LAYERS if c[layer] != "none"}


def load_fixture(file_name):
    path = FIXTURES_VALID / file_name
    assert path.is_file(), f"missing fixture {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def has_cycle(layers):
    """Whether any layer of a {layer: object} dict has a rate cycle of swing above 0 (Components, Rates and cycles)."""
    for layer, key in (("theta_reference", "rate_cycle"), ("gamma_pac", "rate_cycle"),
                       ("binaural", "beat_rate_cycle")):
        cycle = (layers.get(layer) or {}).get(key)
        if cycle is not None and float(cycle["swing_hz"]) > 0.0:
            return True
    return False


def want_rows(name):
    """The vector table of a case in table order: `both` rows expanded, the left ear's rows first."""
    rows = [r for r in vectors()["components"] if r["case"] == name]
    out = []
    for ear in EARS:
        for r in rows:
            assert r["ear"] in ("both",) + EARS, r
            assert r["layer"] in LAYERS, r
            if r["ear"] in ("both", ear):
                out.append(Row(r["layer"], ear, float(Decimal(r["center"])), float(Decimal(r["low"])),
                               float(Decimal(r["high"])), float(Decimal(r["level"])),
                               int(r["gamma_mult"]), int(r["theta_mult"]), int(r["beat_mult"])))
    assert len(out) == int(case(name)["components"]), (name, len(out))
    return out


def as_rows(table):
    """Any table as harness rows (plain Python values)."""
    return [Row(str(r.layer), str(r.ear), float(r.center_hz), float(r.low_hz), float(r.high_hz),
                float(r.level), int(r.gamma_mult), int(r.theta_mult), int(r.beat_mult)) for r in table]


def layer_rows(table, layer, ear):
    return [r for r in table if r.layer == layer and r.ear == ear]


def level_error():
    r = table_row(LEVEL_ROW)
    assert r.kind == "thresholds" and r.unit == "ratio", r
    return r.value


def frequency_error():
    r = table_row(FREQUENCY_ROW)
    assert r.kind == "thresholds" and r.unit == "Hz", r
    return r.value


def compare(got, want):
    """Problems of table `got` against the rows `want` (empty when it holds).

    The same rows in the same order: layer, ear, and the three multipliers
    equal; every center, low, and high strictly within row
    component-frequency-error; every level strictly within row
    component-level-error.
    """
    level_tol = level_error()
    frequency_tol = frequency_error()
    got = as_rows(got)
    problems = []
    if len(got) != len(want):
        problems.append(f"{len(got)} rows, the vectors have {len(want)}")
    for i, (g, w) in enumerate(zip(got, want)):
        name = (g.layer, g.ear, g.gamma_mult, g.theta_mult, g.beat_mult)
        want_name = (w.layer, w.ear, w.gamma_mult, w.theta_mult, w.beat_mult)
        if name != want_name:
            problems.append(f"row {i}: is {name}, the vectors have {want_name}")
            continue
        for field in FREQUENCY_FIELDS:
            error = abs(getattr(g, field) - getattr(w, field))
            if not error < frequency_tol:
                problems.append(f"row {i} {name}: {field} {getattr(g, field)!r} is {error!r} Hz from "
                                f"{getattr(w, field)!r} (row {FREQUENCY_ROW}: {frequency_tol!r})")
        error = abs(g.level - w.level)
        if not error < level_tol:
            problems.append(f"row {i} {name}: level {g.level!r} is {error!r} from {w.level!r} "
                            f"(row {LEVEL_ROW}: {level_tol!r})")
    return problems


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def reference_components():
    """The Python reference table module (reference/components.py)."""
    assert Path(REFERENCE_TABLE).is_file(), f"missing {REFERENCE_TABLE} (Story 3.1 reference table)"
    _repo_on_path()
    return importlib.import_module("reference.components")


def reference_module(name):
    _repo_on_path()
    return importlib.import_module(f"reference.{name}")
