"""pytest setup: the assertion library and the pytest row usage file.

Puts tests/ on sys.path so tests import the assertion library as
`assertions`, and writes the ids every assertion read through
`assertions.row` at session end, for tools/check_row_coverage.py. The file is
$ARCANI_PYTEST_ROW_USAGE, or build/row-usage/pytest.txt when that is unset.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS = str(REPO_ROOT / "tests")
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import assertions  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("ARCANI_PYTEST_ROW_USAGE")
    path = Path(target) if target else REPO_ROOT / "build" / "row-usage" / "pytest.txt"
    assertions.write_usage(path)
