"""Assertion library: every assertion reads its threshold or range through `row`.

`row(row_id)` returns the table row and records the id, so the coverage check
(tools/check_row_coverage.py) can prove every row is asserted and every
assertion has a row. An empty or unknown id raises UnknownRowError, which
fails the calling test. tests/python/conftest.py writes the recorded ids at
the end of the pytest session.
"""

from __future__ import annotations

from pathlib import Path

from .tables import TABLES_DIR, Row, TableError, UnknownRowError, load_tables

__all__ = ["Row", "TableError", "UnknownRowError", "row", "used_ids", "write_usage"]

_rows: dict[str, Row] | None = None
_used: set[str] = set()


def _table() -> dict[str, Row]:
    global _rows
    if _rows is None:
        _rows = load_tables(TABLES_DIR)
    return _rows


def row(row_id: str) -> Row:
    if not isinstance(row_id, str) or not row_id:
        raise UnknownRowError("assertion asked for an empty row id")
    found = _table().get(row_id)
    if found is None:
        raise UnknownRowError(f"no threshold or range row with id '{row_id}'")
    _used.add(row_id)
    return found


def used_ids() -> set[str]:
    return set(_used)


def write_usage(path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("".join(f"{i}\n" for i in sorted(_used)).encode("utf-8"))
