"""Threshold and range tables as data, and the Python table loader (Story 0.3).

Contract with tests/assertions/tables.py (stdlib only), importable as
`assertions.tables` once tests/python/conftest.py has put `<repo>/tests` on
sys.path:

- `TABLES_DIR` is `<repo>/tests/tables`. `THRESHOLD_COLUMNS` and
  `RANGE_COLUMNS` are the exact header names in order:
  thresholds `id value unit spec_row source pending`; ranges
  `id min max max_bound unit spec_row source pending`.
- `load_table(path, kind)` (kind "thresholds" or "ranges") returns a list of
  frozen `Row`s in file order. A Row keeps the exact text of each number
  (`value_text`, `min_text`, `max_text`) plus its parsed binary64 (`values`,
  a tuple with one member per space-separated set member; `min`, `max`),
  and `path`, `line` (1-based), `kind`, `id`, `unit`, `spec_row`, `source`,
  `pending`, `max_bound`. `Row.value` is the single member of a one-member
  threshold and raises TableError on a set or on a range row.
- `load_tables(dir)` loads thresholds.tsv then ranges.tsv into a dict keyed
  by id, in that order, and fails on an id present in both files.
- Every loader failure raises `TableError` whose message contains the file
  name, `:<line>:`, and the row id (for a header error, the column name).
  The faults are listed in tests/fixtures/tables/bad/expected.tsv (header
  `file kind line id`; an empty id means the fault has no id, such as a
  blank line, and only file and line are checked).
- `dump_lines(rows)` returns the cross-check lines: thresholds
  `thresholds<TAB>id<TAB>unit<TAB>value_text<TAB>bits`, ranges
  `ranges<TAB>id<TAB>unit<TAB>min_text<TAB>min_bits<TAB>max_text<TAB>max_bits<TAB>max_bound`,
  where bits are each binary64 bit pattern as 16 lowercase hex digits,
  set members joined by single spaces.

Contract with the real tables tests/tables/thresholds.tsv and ranges.tsv:

- UTF-8, LF only, exact header, no blank lines, ids kebab-case and unique
  across both files, every row loads.
- Every row of the md "Test thresholds" table in
  _bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md has at least
  one thresholds row whose `spec_row` is that row's first-column text, and
  every row of the md "Locked ranges" table at least one ranges row. A
  non-empty `spec_row` must be a first-column text of the md table that
  matches the row's kind.
- Md number rule: every number of a row with a non-empty `spec_row` equals
  (Decimal) a number in that md row's second column, or is 0. A row with an
  empty `spec_row` has a source starting with "Derived" or containing
  "design log" (case-insensitive).
- Story 0.2 ids keep their units and values (see STORY_02_* below), and the
  cross-platform fallback row is `cross-platform-fallback`, -100 dBFS.
- Every non-empty `pending` is a key of `development_status` in
  _bmad-output/implementation-artifacts/sprint-status.yaml.

Each mapping rule also has a must-fail case built here from a doctored copy
of the md text or of a row.
"""

import dataclasses
import importlib
import re
import struct
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES = REPO_ROOT / "tests" / "tables"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "tables"
MD = REPO_ROOT / "_bmad-output" / "specs" / "spec-arcani-v0-1" / "thresholds-and-ranges.md"
SPRINT_STATUS = REPO_ROOT / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
THRESHOLD_HEADER = ["id", "value", "unit", "spec_row", "source", "pending"]
RANGE_HEADER = ["id", "min", "max", "max_bound", "unit", "spec_row", "source", "pending"]
KEBAB = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MD_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
SECTION = {"thresholds": "Test thresholds", "ranges": "Locked ranges"}

# Story 0.2 rows: id -> (unit, values) and id -> (unit, min, max, max_bound).
STORY_02_THRESHOLDS = {
    "sine-error": ("dBFS", (-120.0,)),
    "frequency-accuracy": ("Hz", (0.01,)),
    "drift-8h": ("ms", (1.0,)),
    "sample-rates": ("Hz", (44100.0, 48000.0)),
}
STORY_02_RANGES = {
    "theta-rate": ("Hz", 1.0, 6.0, "inclusive"),
    "theta-carrier": ("Hz", 100.0, 500.0, "inclusive"),
    "gamma-rate": ("Hz", 30.0, 60.0, "inclusive"),
    "gamma-carrier": ("Hz", 200.0, 500.0, "inclusive"),
    "binaural-carrier": ("Hz", 0.0, 1000.0, "exclusive"),
    "binaural-carrier-right": ("Hz", 0.0, 1030.0, "exclusive"),
    "beat-rate": ("Hz", 0.0, 30.0, "exclusive"),
    "session-length": ("h", 0.0, 8.0, "inclusive"),
}
NOT_IN_MD = ("sine-error", "binaural-carrier-right", "sample-rates")


@pytest.fixture(scope="module")
def tables():
    """The loader module; fails clearly while tests/assertions/ is missing."""
    return importlib.import_module("assertions.tables")


def read_tsv(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[-1] == "", f"{path.name}: must end with a newline"
    return [line.split("\t") for line in lines[:-1]]


def bits(v):
    return "%016x" % struct.unpack("<Q", struct.pack("<d", v))[0]


def bad_cases():
    rows = read_tsv(FIXTURES / "bad" / "expected.tsv")
    assert rows[0] == ["file", "kind", "line", "id"], rows[0]
    return rows[1:]


# ------------------------------------------------------------ good fixtures


def test_good_thresholds_fixture(tables):
    path = FIXTURES / "good" / "thresholds.tsv"
    rows = tables.load_table(path, "thresholds")
    assert [r.id for r in rows] == ["fixture-bound", "fixture-set", "fixture-small"]
    assert [r.line for r in rows] == [2, 3, 4]
    assert all(r.kind == "thresholds" and Path(r.path).name == "thresholds.tsv" for r in rows)
    bound, a_set, small = rows
    assert (bound.value_text, bound.values, bound.value, bound.unit) == ("-120", (-120.0,), -120.0, "dBFS")
    assert a_set.value_text == "1 64 512 4096"
    assert a_set.values == (1.0, 64.0, 512.0, 4096.0)
    assert a_set.unit == "frames"
    assert small.value_text == "0.01" and small.value == 0.01
    assert small.spec_row == "Fixture md row"
    assert small.pending == "9-1-fixture-story"
    assert bound.pending == "" and bound.spec_row == ""
    assert bound.source.startswith("Fixture only")


def test_set_and_range_have_no_single_value(tables):
    a_set = tables.load_table(FIXTURES / "good" / "thresholds.tsv", "thresholds")[1]
    with pytest.raises(tables.TableError):
        a_set.value
    a_range = tables.load_table(FIXTURES / "good" / "ranges.tsv", "ranges")[0]
    with pytest.raises(tables.TableError):
        a_range.value


def test_good_ranges_fixture(tables):
    rows = tables.load_table(FIXTURES / "good" / "ranges.tsv", "ranges")
    assert [r.id for r in rows] == ["fixture-rate", "fixture-below", "fixture-signed"]
    assert [r.line for r in rows] == [2, 3, 4]
    rate, below, signed = rows
    assert (rate.min_text, rate.max_text, rate.min, rate.max, rate.max_bound) == (
        "1", "6", 1.0, 6.0, "inclusive")
    assert (below.min, below.max, below.max_bound, below.unit) == (0.0, 1000.0, "exclusive", "Hz")
    assert (signed.min_text, signed.max_text, signed.min, signed.max) == ("-1.5", "2.25", -1.5, 2.25)
    assert signed.pending == "9-1-fixture-story"
    assert rate.spec_row == "Fixture md range"
    assert all(r.kind == "ranges" for r in rows)


def test_load_tables_orders_thresholds_then_ranges(tables):
    rows = tables.load_tables(FIXTURES / "good")
    assert list(rows) == ["fixture-bound", "fixture-set", "fixture-small",
                          "fixture-rate", "fixture-below", "fixture-signed"]
    assert all(rows[k].id == k for k in rows)


def test_dump_lines_format(tables):
    rows = list(tables.load_tables(FIXTURES / "good").values())
    assert tables.dump_lines(rows) == [
        f"thresholds\tfixture-bound\tdBFS\t-120\t{bits(-120.0)}",
        f"thresholds\tfixture-set\tframes\t1 64 512 4096\t"
        f"{bits(1.0)} {bits(64.0)} {bits(512.0)} {bits(4096.0)}",
        f"thresholds\tfixture-small\tHz\t0.01\t{bits(0.01)}",
        f"ranges\tfixture-rate\tHz\t1\t{bits(1.0)}\t6\t{bits(6.0)}\tinclusive",
        f"ranges\tfixture-below\tHz\t0\t{bits(0.0)}\t1000\t{bits(1000.0)}\texclusive",
        f"ranges\tfixture-signed\tdB\t-1.5\t{bits(-1.5)}\t2.25\t{bits(2.25)}\tinclusive",
    ]


def test_column_names(tables):
    assert tuple(tables.THRESHOLD_COLUMNS) == tuple(THRESHOLD_HEADER)
    assert tuple(tables.RANGE_COLUMNS) == tuple(RANGE_HEADER)
    assert Path(tables.TABLES_DIR).resolve() == TABLES.resolve()


# ------------------------------------------------------------- bad fixtures


def test_bad_fixture_list_covers_every_fault_kind():
    names = {row[0] for row in bad_cases()}
    for needle in ("empty-source", "missing-header-column", "short-row", "duplicate-id",
                   "non-numeric-value", "non-numeric-min", "min-above-max", "bad-max-bound"):
        assert f"{needle}.tsv" in names, needle
    for name in names:
        assert (FIXTURES / "bad" / name).is_file(), name


@pytest.mark.parametrize("name, kind, line, row_id", bad_cases(), ids=lambda v: str(v))
def test_bad_fixture_fails_naming_file_line_id(tables, name, kind, line, row_id):
    with pytest.raises(tables.TableError) as info:
        tables.load_table(FIXTURES / "bad" / name, kind)
    message = str(info.value)
    assert name in message, message
    assert f":{line}:" in message, message
    if row_id:
        assert row_id in message, message


def test_duplicate_across_files_fails(tables):
    with pytest.raises(tables.TableError) as info:
        tables.load_tables(FIXTURES / "dup-across")
    message = str(info.value)
    assert "fixture-twice" in message, message
    assert "ranges.tsv" in message and ":3:" in message, message


def test_each_dup_across_file_loads_alone(tables):
    assert [r.id for r in tables.load_table(FIXTURES / "dup-across" / "thresholds.tsv",
                                            "thresholds")] == ["fixture-twice"]
    assert [r.id for r in tables.load_table(FIXTURES / "dup-across" / "ranges.tsv",
                                            "ranges")] == ["fixture-ok-range", "fixture-twice"]


# --------------------------------------------------------------- real tables


@pytest.mark.parametrize("name, header", [("thresholds.tsv", THRESHOLD_HEADER),
                                          ("ranges.tsv", RANGE_HEADER)])
def test_real_table_text_format(name, header):
    path = TABLES / name
    assert path.is_file(), f"missing {path}"
    data = path.read_bytes()
    assert b"\r" not in data, f"{name}: LF line ends only"
    rows = read_tsv(path)
    assert rows[0] == header, rows[0]
    assert len(rows) > 1, f"{name}: no data rows"
    for n, fields in enumerate(rows[1:], start=2):
        assert fields != [""], f"{name}:{n}: blank line"
        assert len(fields) == len(header), f"{name}:{n}: {fields[0]}: {len(fields)} fields"


def test_real_ids_unique_and_kebab_case():
    seen = {}
    for name in ("thresholds.tsv", "ranges.tsv"):
        for n, fields in enumerate(read_tsv(TABLES / name)[1:], start=2):
            row_id = fields[0]
            assert KEBAB.fullmatch(row_id), f"{name}:{n}: id {row_id!r} is not kebab-case"
            assert row_id not in seen, f"{name}:{n}: {row_id} duplicates {seen.get(row_id)}"
            seen[row_id] = f"{name}:{n}"


def test_real_tables_load(tables):
    rows = tables.load_tables()
    assert rows, "no rows"
    kinds = [r.kind for r in rows.values()]
    assert kinds == sorted(kinds, key=lambda k: k != "thresholds"), "thresholds first, then ranges"
    for row_id, r in rows.items():
        assert r.id == row_id
        assert r.source.strip(), row_id


def test_story_02_ids_keep_units_and_values(tables):
    rows = tables.load_tables()
    for row_id, (unit, values) in STORY_02_THRESHOLDS.items():
        assert row_id in rows, f"missing Story 0.2 threshold {row_id}"
        r = rows[row_id]
        assert r.kind == "thresholds", (row_id, r.kind)
        assert (r.unit, r.values) == (unit, values), (row_id, r.unit, r.values)
    for row_id, (unit, lo, hi, bound) in STORY_02_RANGES.items():
        assert row_id in rows, f"missing Story 0.2 range {row_id}"
        r = rows[row_id]
        assert r.kind == "ranges", (row_id, r.kind)
        assert (r.unit, r.min, r.max, r.max_bound) == (unit, lo, hi, bound), (
            row_id, r.unit, r.min, r.max, r.max_bound)
    for row_id in NOT_IN_MD:
        assert rows[row_id].spec_row == "", f"{row_id} is not an md row"


def test_cross_platform_fallback_row(tables):
    r = tables.load_tables()["cross-platform-fallback"]
    assert r.kind == "thresholds"
    assert (r.value, r.unit) == (-100.0, "dBFS")


def test_real_pending_values_are_sprint_status_keys(tables):
    status = yaml.safe_load(SPRINT_STATUS.read_text(encoding="utf-8"))["development_status"]
    for r in tables.load_tables().values():
        if r.pending:
            assert r.pending in status, f"{r.id}: pending {r.pending!r} is not a sprint-status key"


# ---------------------------------------------------------------- md mapping


def md_tables(text):
    """Returns {section title: [(first column, second column), ...]} for each md table."""
    out, section = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.setdefault(section, []).append((cells[0], cells[1]))
    return {k: v[2:] for k, v in out.items()}  # drop header and separator


def numbers_of(r):
    if r.kind == "thresholds":
        return r.value_text.split(" ")
    return [r.min_text, r.max_text]


def mapping_problems(md_text, rows):
    """Every md row has a data row, and every data row traces to the md or a log."""
    md = md_tables(md_text)
    problems = []
    for kind, section in SECTION.items():
        assert md.get(section), f"md has no {section!r} table"
        mapped = {r.spec_row for r in rows if r.kind == kind}
        for first, _ in md[section]:
            if first not in mapped:
                problems.append(f"md row lost: {section}: {first}")
    for r in rows:
        if not r.spec_row:
            src = r.source.lower()
            if not (r.source.startswith("Derived") or "design log" in src):
                problems.append(f"{r.id}: empty spec_row and source cites neither Derived nor a design log")
            continue
        second = dict(md[SECTION[r.kind]]).get(r.spec_row)
        if second is None:
            problems.append(f"{r.id}: spec_row {r.spec_row!r} is not a row of md {SECTION[r.kind]!r}")
            continue
        allowed = {Decimal(m) for m in MD_NUMBER.findall(second)}
        for text in numbers_of(r):
            if Decimal(text) != 0 and Decimal(text) not in allowed:
                problems.append(f"{r.id}: {text} is not in md row {r.spec_row!r}: {second}")
    return problems


@pytest.fixture(scope="module")
def real_rows(tables):
    return list(tables.load_tables().values())


@pytest.fixture(scope="module")
def md_text():
    return MD.read_text(encoding="utf-8")


def test_md_parse_sees_both_tables(md_text):
    md = md_tables(md_text)
    assert len(md["Test thresholds"]) == 21, [f for f, _ in md["Test thresholds"]]
    assert len(md["Locked ranges"]) == 13, [f for f, _ in md["Locked ranges"]]


def test_md_mapping_holds_for_real_tables(md_text, real_rows):
    problems = mapping_problems(md_text, real_rows)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("after, extra", [
    ("| Render speed |", "| Fixture extra assertion | At least 3 widgets | Fixture |"),
    ("| Loudness levels |", "| Fixture extra parameter | 2 to 9 Hz | Fixture |"),
])
def test_md_row_lost_is_named(md_text, real_rows, after, extra):
    lines = md_text.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith(after))
    doctored = "\n".join(lines[:at + 1] + [extra] + lines[at + 1:])
    name = extra.split("|")[1].strip()
    problems = mapping_problems(doctored, real_rows)
    assert [p for p in problems if name in p], problems


def test_spec_row_from_the_other_table_is_named(md_text, real_rows):
    victim = next(r for r in real_rows if r.kind == "thresholds" and r.spec_row)
    other = md_tables(md_text)["Locked ranges"][0][0]
    rows = [dataclasses.replace(r, spec_row=other) if r is victim else r for r in real_rows]
    problems = mapping_problems(md_text, rows)
    assert [p for p in problems if victim.id in p and "not a row" in p], problems


def test_number_not_in_md_row_is_named(md_text, real_rows):
    victim = next(r for r in real_rows if r.kind == "ranges" and r.spec_row)
    rows = [dataclasses.replace(r, max_text="123457") if r is victim else r for r in real_rows]
    problems = mapping_problems(md_text, rows)
    assert [p for p in problems if victim.id in p and "123457" in p], problems


def test_zero_passes_the_number_rule(md_text, real_rows):
    victim = next(r for r in real_rows if r.kind == "ranges" and r.spec_row)
    rows = [dataclasses.replace(r, min_text="0") if r is victim else r for r in real_rows]
    assert not [p for p in mapping_problems(md_text, rows) if victim.id in p]


def test_uncited_row_outside_md_is_named(md_text, real_rows):
    victim = next(r for r in real_rows if not r.spec_row)
    rows = [dataclasses.replace(r, source="Fixture: made up") if r is victim else r
            for r in real_rows]
    problems = mapping_problems(md_text, rows)
    assert [p for p in problems if victim.id in p], problems
