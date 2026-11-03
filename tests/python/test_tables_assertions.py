"""The Python assertion call over the tables (Story 0.3).

Contract with tests/assertions/__init__.py (package `assertions`, on sys.path
through tests/python/conftest.py):

- `row(row_id)` returns the `assertions.tables.Row` for that id from
  `TABLES_DIR` (loaded once, cached) and records the id. An empty or unknown
  id raises `TableError` (or a subclass) whose message names the id, and is
  not recorded.
- `used_ids()` returns the set of ids recorded so far in this process.
- `write_usage(path)` writes the sorted recorded ids, one per line, each
  ended by "\n" (no "\r"), creating parent directories.

Contract with tests/python/conftest.py: at session end it writes the usage
file to $ARCANI_PYTEST_ROW_USAGE, or, when that is unset,
`<repo>/build/row-usage/pytest.txt`.

Only ids that some test truly asserts are passed to `row` here (`sine-error`
and `frequency-accuracy`, both asserted since Story 0.2), so this module does
not mark a pending row as used.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
USED_A = "sine-error"
USED_B = "frequency-accuracy"


@pytest.fixture(scope="module")
def assertions():
    return importlib.import_module("assertions")


@pytest.fixture(scope="module")
def tables():
    return importlib.import_module("assertions.tables")


def test_row_returns_row_and_records_id(assertions, tables):
    r = assertions.row(USED_A)
    assert isinstance(r, tables.Row)
    assert r.id == USED_A
    assert r == tables.load_tables()[USED_A]
    assert USED_A in assertions.used_ids()


def test_row_is_cached(assertions):
    assert assertions.row(USED_A) is assertions.row(USED_A)


@pytest.mark.parametrize("bad_id", ["no-such-row", "Sine-Error", " sine-error"])
def test_unknown_id_raises_names_it_and_is_not_recorded(assertions, tables, bad_id):
    with pytest.raises(tables.TableError) as info:
        assertions.row(bad_id)
    assert bad_id.strip() in str(info.value), str(info.value)
    assert bad_id not in assertions.used_ids()


def test_empty_id_raises_and_is_not_recorded(assertions, tables):
    with pytest.raises(tables.TableError):
        assertions.row("")
    assert "" not in assertions.used_ids()


def test_write_usage_format(assertions, tmp_path):
    assertions.row(USED_B)
    assertions.row(USED_A)
    out = tmp_path / "nested" / "dir" / "usage.txt"
    assertions.write_usage(out)
    data = out.read_bytes()
    assert b"\r" not in data
    ids = sorted(assertions.used_ids())
    assert {USED_A, USED_B} <= set(ids)
    assert data.decode("utf-8") == "".join(f"{i}\n" for i in ids)


def test_pytest_session_writes_usage_file(tmp_path):
    """conftest writes $ARCANI_PYTEST_ROW_USAGE at session end."""
    out = tmp_path / "usage" / "pytest.txt"
    env = dict(os.environ, ARCANI_PYTEST_ROW_USAGE=str(out))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(Path(__file__)), "-k", "test_row_returns_row_and_records_id"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.is_file(), "conftest did not write the usage file"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert USED_A in lines, lines
    assert lines == sorted(lines), lines
