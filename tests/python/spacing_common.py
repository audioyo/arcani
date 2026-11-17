"""Shared harness of the Story 3.2 spacing tests (not a test file).

The spacing vectors (tests/data/signal_spec_vectors.json, keys
`spacing_constants`, `spacing_cases`, `spacing_margins`, `spacing_pairs`;
docs/signal-spec.md, Spacing), the error rows read through the assertion
call `assertions.row`, and the grammar of a spacing error detail:

    <ear> ear: <layer 1> (<i>, <j>, <b>) at <center 1> Hz and <layer 2> (<i>, <j>, <b>) at <center 2> Hz; <where>
    <where>:  whole session
           |  listed intervals, a row mirrored below 0 Hz
           |  first at <t> s, gamma rate <rate> Hz, theta rate <rate> Hz, beat rate <rate> Hz

with `none` in place of `<rate> Hz` for a layer the recipe does not have.
Words are compared exactly, numbers within the rows: centers and distances
within component-frequency-error, a time within spacing-time-error around
the cycle (`min(d mod P, P - d mod P)`, P from row rate-cycle-period), each
rate within frequency-accuracy. The vector texts hold ideal numbers at 25
digits; a text the engine or the reference writes must hold shortest
round-trip numbers. The comparisons' must-fail cases live in
tests/python/test_spacing_reference.py, made by doctoring texts here.

No threshold is written here as a literal.
"""

import importlib
import json
import math
import re
import sys
from decimal import Decimal
from pathlib import Path

from assertions import row as table_row

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
REFERENCE_SPACING = REPO_ROOT / "reference" / "spacing.py"

LAYERS = ("theta_reference", "gamma_pac", "binaural")
EARS = ("left", "right")
RULE_ROW = "spacing-rule"
TIME_ROW = "spacing-time-error"
FREQUENCY_ROW = "component-frequency-error"
RATE_ROW = "frequency-accuracy"
PERIOD_ROW = "rate-cycle-period"
WHOLE_SESSION = "whole session"
LISTED_INTERVALS = "listed intervals, a row mirrored below 0 Hz"

_vectors = None


def vectors():
    global _vectors
    if _vectors is None:
        _vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        for key in ("spacing_constants", "spacing_cases", "spacing_margins", "spacing_pairs"):
            assert key in _vectors, f"the vectors file has no {key} (Story 3.2)"
    return _vectors


def constants():
    return vectors()["spacing_constants"]


def cases():
    return vectors()["spacing_cases"]


def case_names():
    return [c["case"] for c in cases()]


def case(name):
    found = [c for c in cases() if c["case"] == name]
    assert len(found) == 1, name
    return found[0]


def case_recipe(name):
    return json.loads(case(name)["recipe"])


def case_layers(name):
    c = case(name)
    return {layer: json.loads(c[layer]) for layer in LAYERS if c[layer] != "none"}


def margin(name, ear):
    found = [m for m in vectors()["spacing_margins"] if m["case"] == name and m["ear"] == ear]
    assert len(found) == 1, (name, ear)
    return found[0]


def pair_rows():
    rows = vectors()["spacing_pairs"]
    assert rows, "no spacing_pairs vectors"
    return rows


def load_fixture(file_name):
    path = FIXTURES_VALID / file_name
    assert path.is_file(), f"missing fixture {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------ rows


def rule_hz():
    r = table_row(RULE_ROW)
    assert r.kind == "thresholds" and r.unit == "Hz", r
    return r.value


def frequency_error():
    r = table_row(FREQUENCY_ROW)
    assert r.kind == "thresholds" and r.unit == "Hz", r
    return r.value


def time_error_s():
    r = table_row(TIME_ROW)
    assert r.kind == "thresholds", r
    return {"s": 1.0, "ms": 1e-3}[r.unit] * r.value


def rate_error():
    r = table_row(RATE_ROW)
    assert r.kind == "thresholds" and r.unit == "Hz", r
    return r.value


def period_s():
    r = table_row(PERIOD_ROW)
    assert r.kind == "ranges" and r.unit == "s" and r.min == r.max, r
    return r.min


def limit_text():
    """The limit text, the row value as its shortest round-trip text."""
    return f">= {shortest(rule_hz())} Hz (row {RULE_ROW})"


# ------------------------------------------------------------ texts


def shortest(x):
    """The shortest round-trip text of a binary64, as the C++ std::to_chars writes it."""
    x = float(x)
    if x == 0.0:
        return "-0" if math.copysign(1.0, x) < 0 else "0"
    r = repr(x)
    if "e" in r or "E" in r:
        mant, exp = r.split("e")
        if mant.endswith(".0"):
            mant = mant[:-2]
        e = int(exp)
        return f"{mant}e{'-' if e < 0 else '+'}{abs(e):02d}"
    if r.endswith(".0"):
        r = r[:-2]
    return r


def _significant_digits(text):
    mantissa = text.lstrip("-").split("e")[0].split("E")[0]
    return mantissa.replace(".", "").strip("0") or "0"


def is_shortest(text):
    """A shortest round-trip text: it names its binary64 with the fewest significant
    digits (fixed or scientific, as std::to_chars picks the shorter form)."""
    if not re.fullmatch(NUM, text):
        return False
    x = float(text)
    if not math.isfinite(x):
        return False
    if text.startswith("-") != (math.copysign(1.0, x) < 0):
        return False
    mantissa = text.lstrip("-").split("e")[0]
    if mantissa.endswith(".") or (("." in mantissa) and mantissa.endswith("0")):
        return False  # a trailing zero after the point is never shortest
    if len(mantissa.split(".")[0]) > 1 and mantissa.startswith("0"):
        return False
    return _significant_digits(text) == _significant_digits(repr(x))


def ideal(text):
    """An ideal vector number text as a binary64 (nearest)."""
    return float(Decimal(text))


NUM = r"(-?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?)"
LAYER = r"(theta_reference|gamma_pac|binaural)"
MULTS = r"\((-?[0-9]+), (-?[0-9]+), (-?[0-9]+)\)"
ROW_NAME_RE = re.compile(rf"^{LAYER} {MULTS}$")
PAIR_RE = re.compile(rf"^{LAYER} {MULTS} at {NUM} Hz and {LAYER} {MULTS} at {NUM} Hz$")
RATE = r"(none|-?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)? Hz)"
FIRST_RE = re.compile(rf"^first at {NUM} s, gamma rate {RATE}, theta rate {RATE}, beat rate {RATE}$")
DETAIL_RE = re.compile(r"^(left|right) ear: ([^;]*); ([^;]*)$")


class GrammarError(AssertionError):
    pass


def parse_row_name(text):
    m = ROW_NAME_RE.match(text)
    if not m:
        raise GrammarError(f"row name does not follow the grammar: {text!r}")
    return (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def parse_pair(text, engine):
    """((layer, i, j, b, center text), (layer, i, j, b, center text))."""
    m = PAIR_RE.match(text)
    if not m:
        raise GrammarError(f"pair does not follow the grammar: {text!r}")
    rows = []
    for k in (0, 5):
        layer, i, j, b, center = m.group(1 + k, 2 + k, 3 + k, 4 + k, 5 + k)
        if engine and not is_shortest(center):
            raise GrammarError(f"center {center!r} is not a shortest round-trip text")
        rows.append((layer, int(i), int(j), int(b), center))
    return tuple(rows)


def parse_where(text, engine):
    """(kind, time text or None, (gamma, theta, beat) rate texts or Nones)."""
    if text in (WHOLE_SESSION, LISTED_INTERVALS):
        return (text, None, (None, None, None))
    m = FIRST_RE.match(text)
    if not m:
        raise GrammarError(f"where does not follow the grammar: {text!r}")
    time = m.group(1)
    rates = []
    for raw in m.group(2, 3, 4):
        r = "none" if raw == "none" else raw[:-len(" Hz")]
        if engine and r != "none" and not is_shortest(r):
            raise GrammarError(f"rate {r!r} is not a shortest round-trip text")
        rates.append(r)
    if engine and not is_shortest(time):
        raise GrammarError(f"time {time!r} is not a shortest round-trip text")
    return ("first", time, tuple(rates))


def parse_detail(text, engine):
    m = DETAIL_RE.match(text)
    if not m:
        raise GrammarError(f"detail does not follow the grammar: {text!r}")
    return m.group(1), parse_pair(m.group(2), engine), parse_where(m.group(3), engine)


def around_cycle(a, b, p):
    d = math.fmod(abs(a - b), p)
    return min(d, p - d)


def compare_pair_texts(got, want):
    """Problems of the pair text `got` (engine or reference) against `want` (a vector)."""
    problems = []
    try:
        g = parse_pair(got, True)
    except GrammarError as e:
        return [str(e)]
    w = parse_pair(want, False)
    tol = frequency_error()
    for n, (gr, wr) in enumerate(zip(g, w), start=1):
        if gr[:4] != wr[:4]:
            problems.append(f"row {n} is {gr[:4]}, want {wr[:4]}")
        if not abs(float(gr[4]) - ideal(wr[4])) < tol:
            problems.append(f"row {n} center {gr[4]} Hz, want {wr[4]} Hz (row {FREQUENCY_ROW})")
    return problems


def compare_where_texts(got, want):
    try:
        g = parse_where(got, True)
    except GrammarError as e:
        return [str(e)]
    w = parse_where(want, False)
    if g[0] != w[0]:
        return [f"where is {g[0]!r}, want {w[0]!r}"]
    if g[0] != "first":
        return []
    problems = []
    if not around_cycle(float(g[1]), ideal(w[1]), period_s()) < time_error_s():
        problems.append(f"first time {g[1]} s, want {w[1]} s (row {TIME_ROW}, around the cycle)")
    for name, gr, wr in zip(("gamma", "theta", "beat"), g[2], w[2]):
        if (gr == "none") != (wr == "none"):
            problems.append(f"{name} rate {gr}, want {wr}")
        elif gr != "none" and not abs(float(gr) - ideal(wr)) < rate_error():
            problems.append(f"{name} rate {gr} Hz, want {wr} Hz (row {RATE_ROW})")
    return problems


def compare_detail(got, want):
    """Problems of the detail `got` against the vector detail `want` (empty when it holds)."""
    try:
        g = parse_detail(got, True)
    except GrammarError as e:
        return [str(e)]
    w = parse_detail(want, False)
    problems = []
    if g[0] != w[0]:
        problems.append(f"ear {g[0]}, want {w[0]}")
    pair_got = got.split(": ", 1)[1].split("; ", 1)[0]
    pair_want = want.split(": ", 1)[1].split("; ", 1)[0]
    problems += compare_pair_texts(pair_got, pair_want)
    problems += compare_where_texts(got.split("; ", 1)[1], want.split("; ", 1)[1])
    return problems


def carrier_field(layer):
    return constants()["carrier_fields"].get(layer)


def error_problems(parameter, value, rule, limit, detail, c):
    """Problems of one spacing error (five texts) against a rejected case `c`."""
    problems = []
    if parameter != c["parameter"]:
        problems.append(f"parameter {parameter}, want {c['parameter']}")
    if rule != constants()["rule"]:
        problems.append(f"rule {rule}, want {constants()['rule']}")
    if limit != c["limit"]:
        problems.append(f"limit {limit}, want {c['limit']}")
    want_value = ideal(c["value"])
    if not is_shortest(value):
        problems.append(f"value {value!r} is not a shortest round-trip text")
    elif not abs(float(value) - want_value) < frequency_error():
        problems.append(f"value {value}, want {c['value']} (row {FREQUENCY_ROW})")
    else:
        kind = parse_where(c["detail"].split("; ", 1)[1], False)[0]
        if (kind != "first" or want_value == 0.0) and float(value) != want_value:
            problems.append(f"value {value}, want exactly {shortest(want_value)} (a static pair)")
    problems += [f"detail: {p}" for p in compare_detail(detail, c["detail"])]
    try:
        _, pair, _ = parse_detail(detail, True)
        if parameter != carrier_field(pair[1][0]):
            problems.append(f"parameter {parameter} is not the carrier field of row 2's layer {pair[1][0]}")
    except GrammarError:
        pass
    return problems


# ------------------------------------------------------------ modules


def _repo_on_path():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def reference_spacing():
    """The Python reference spacing module (reference/spacing.py)."""
    assert REFERENCE_SPACING.is_file(), f"missing {REFERENCE_SPACING} (Story 3.2 reference spacing rule)"
    _repo_on_path()
    return importlib.import_module("reference.spacing")


def reference_module(name):
    _repo_on_path()
    return importlib.import_module(f"reference.{name}")
