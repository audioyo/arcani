"""Loader for the threshold and locked-range tables (tests/tables/*.tsv).

Stdlib only. The C++ loader (tables.hpp, tables.cpp) applies the same rules,
and tests/python/test_tables_crosscheck.py proves both return the same rows.
Format rules are in tests/tables/README.md. Every error names the file, the
1-based line, and the row id (or, for a header error, the column).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

TABLES_DIR = Path(__file__).resolve().parents[1] / "tables"
THRESHOLD_COLUMNS = ("id", "value", "unit", "spec_row", "source", "pending")
RANGE_COLUMNS = ("id", "min", "max", "max_bound", "unit", "spec_row", "source", "pending")
COLUMNS = {"thresholds": THRESHOLD_COLUMNS, "ranges": RANGE_COLUMNS}
MAX_BOUNDS = ("inclusive", "exclusive")

NUMBER_RE = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")
ID_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class TableError(Exception):
    """A table file breaks a format rule."""


class UnknownRowError(TableError, LookupError):
    """An assertion asked for an empty id or an id in neither table."""


@dataclass(frozen=True)
class Row:
    kind: str
    id: str
    unit: str
    spec_row: str
    source: str
    pending: str
    path: Path
    line: int
    value_text: str = ""
    values: tuple[float, ...] = ()
    min_text: str = ""
    max_text: str = ""
    min: float = 0.0
    max: float = 0.0
    max_bound: str = ""

    @property
    def value(self) -> float:
        if self.kind != "thresholds":
            raise TableError(f"{self.path.name}:{self.line}: {self.id}: a range row has no single value")
        if len(self.values) != 1:
            raise TableError(f"{self.path.name}:{self.line}: {self.id}: a set has no single value")
        return self.values[0]


def _fail(path: Path, line: int, what: str, reason: str):
    raise TableError(f"{path.name}:{line}: {what}: {reason}")


def _number(path: Path, line: int, row_id: str, column: str, text: str) -> float:
    if not NUMBER_RE.fullmatch(text):
        _fail(path, line, row_id, f"{column} is not a number: '{text}'")
    return float(text)


def load_table(path, kind: str) -> list[Row]:
    path = Path(path)
    if kind not in COLUMNS:
        raise ValueError(f"unknown table kind: {kind}")
    columns = COLUMNS[kind]
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise TableError(f"{path.name}:0: cannot read: {e}") from e
    if text.endswith("\n"):
        text = text[:-1]
    lines = text.split("\n")
    header = lines[0].split("\t") if lines and lines[0] else []
    for column in columns:
        if column not in header:
            _fail(path, 1, column, "missing column")
    if tuple(header) != columns:
        _fail(path, 1, "header", f"columns must be exactly {', '.join(columns)}")
    rows: list[Row] = []
    seen: set[str] = set()
    for number, raw in enumerate(lines[1:], start=2):
        if raw.endswith("\r"):
            _fail(path, number, raw.split("\t", 1)[0] or "row", "CR line end")
        fields = raw.split("\t")
        row_id = fields[0]
        if raw.strip() == "":
            _fail(path, number, "row", "blank line")
        if len(fields) != len(columns):
            _fail(path, number, row_id, f"{len(fields)} fields, expected {len(columns)} (missing column)")
        f = dict(zip(columns, fields))
        if not ID_RE.fullmatch(row_id):
            _fail(path, number, row_id or "row", "id is not kebab-case")
        if row_id in seen:
            _fail(path, number, row_id, "duplicate id")
        seen.add(row_id)
        if not f["source"].strip():
            _fail(path, number, row_id, "empty source")
        common = dict(kind=kind, id=row_id, unit=f["unit"], spec_row=f["spec_row"],
                      source=f["source"], pending=f["pending"], path=path, line=number)
        if kind == "thresholds":
            members = f["value"].split(" ")
            values = tuple(_number(path, number, row_id, "value", m) for m in members)
            rows.append(Row(**common, value_text=f["value"], values=values))
        else:
            lo = _number(path, number, row_id, "min", f["min"])
            hi = _number(path, number, row_id, "max", f["max"])
            if lo > hi:
                _fail(path, number, row_id, f"min {f['min']} is above max {f['max']}")
            if f["max_bound"] not in MAX_BOUNDS:
                _fail(path, number, row_id, f"max_bound must be inclusive or exclusive: '{f['max_bound']}'")
            rows.append(Row(**common, min_text=f["min"], max_text=f["max"], min=lo, max=hi,
                            max_bound=f["max_bound"]))
    return rows


def load_tables(tables_dir=TABLES_DIR) -> dict[str, Row]:
    tables_dir = Path(tables_dir)
    out: dict[str, Row] = {}
    for kind in ("thresholds", "ranges"):
        for r in load_table(tables_dir / f"{kind}.tsv", kind):
            if r.id in out:
                first = out[r.id]
                _fail(r.path, r.line, r.id, f"duplicate id, also {first.path.name}:{first.line}")
            out[r.id] = r
    return out


def _bits(value: float) -> str:
    return "%016x" % struct.unpack("<Q", struct.pack("<d", value))[0]


def dump_line(r: Row) -> str:
    if r.kind == "thresholds":
        bits = " ".join(_bits(v) for v in r.values)
        return "\t".join(("thresholds", r.id, r.unit, r.value_text, bits))
    return "\t".join(("ranges", r.id, r.unit, r.min_text, _bits(r.min), r.max_text, _bits(r.max),
                      r.max_bound))


def dump_lines(rows) -> list[str]:
    if isinstance(rows, dict):
        rows = rows.values()
    return [dump_line(r) for r in rows]
