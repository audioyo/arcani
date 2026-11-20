"""pytest setup: the assertion library and the pytest row usage file.

Puts tests/ on sys.path so tests import the assertion library as
`assertions`, and writes the ids every assertion read through
`assertions.row` at session end, for tools/check_row_coverage.py. The file is
$ARCANI_PYTEST_ROW_USAGE, or build/row-usage/pytest.txt when that is unset.

With pytest-xdist workers (`-n`), each worker hands its ids to the controller
through `workeroutput` and only the controller writes the file, the union of
every worker's ids, so it is the same file a serial run writes
(spec-ci-parallel-pytest.md).
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS = str(REPO_ROOT / "tests")
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import assertions  # noqa: E402

_WORKER_KEY = "arcani_row_usage"


class _MergeWorkerUsage:
    """Controller side: adds each finished worker's ids to this process's set."""

    def pytest_testnodedown(self, node, error):
        for row_id in getattr(node, "workeroutput", {}).get(_WORKER_KEY, []):
            assertions.mark_used(row_id)


def pytest_configure(config):
    if config.pluginmanager.hasplugin("xdist") and not hasattr(config, "workerinput"):
        config.pluginmanager.register(_MergeWorkerUsage(), "arcani-merge-worker-usage")


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        session.config.workeroutput[_WORKER_KEY] = sorted(assertions.used_ids())
        return
    target = os.environ.get("ARCANI_PYTEST_ROW_USAGE")
    path = Path(target) if target else REPO_ROOT / "build" / "row-usage" / "pytest.txt"
    assertions.write_usage(path)
