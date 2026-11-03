"""Two-way coverage between assertions and table rows (Story 0.3).

Contract with tools/check_row_coverage.py (stdlib plus pyyaml; loads the
tables with the Python loader tests/assertions/tables.py):

- `python tools/check_row_coverage.py [--tables DIR] [--usage FILE ...]
  [--sprint-status FILE]`; `--usage` is given once, followed by one or more
  files. Defaults: <repo>/tests/tables, the usage files
  <repo>/build/row-usage/*.txt, and
  <repo>/_bmad-output/implementation-artifacts/sprint-status.yaml (its
  `development_status` mapping).
- Usage files hold one id per line; blank lines are ignored; the used set is
  the union of all usage files.
- Exit 1, one line per problem naming the row id, when: a row is in no
  usage file and its `pending` is empty (unused); a used row still has a
  `pending` story (names id and story); a `pending` key is not in
  development_status (names id and story); a `pending` story is `done`
  (names id and story); a usage file names an id that is in no table
  (names id); the tables fail to load.
- Exit 0 otherwise. Exit 2 when no usage file is found.

Fixtures are built in tmp_path; rows and story keys are made up.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "check_row_coverage.py"

T_HEADER = "id\tvalue\tunit\tspec_row\tsource\tpending"
R_HEADER = "id\tmin\tmax\tmax_bound\tunit\tspec_row\tsource\tpending"
STATUS = """development_status:
  epic-9: in-progress
  9-1-fixture-open-story: backlog
  9-2-fixture-review-story: review
  9-3-fixture-done-story: done
"""


def t_row(row_id, pending=""):
    return f"{row_id}\t1\tHz\t\tFixture only: made-up row\t{pending}"


def r_row(row_id, pending=""):
    return f"{row_id}\t0\t1\tinclusive\tHz\t\tFixture only: made-up row\t{pending}"


def make(tmp_path, t_rows, r_rows, usage, status=STATUS):
    """Writes tables, usage files ({name: [ids]}), and sprint status; returns args."""
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "thresholds.tsv").write_bytes(("\n".join([T_HEADER, *t_rows]) + "\n").encode())
    (tables / "ranges.tsv").write_bytes(("\n".join([R_HEADER, *r_rows]) + "\n").encode())
    args = ["--tables", str(tables)]
    usage_dir = tmp_path / "row-usage"
    usage_dir.mkdir()
    paths = []
    for name, ids in usage.items():
        path = usage_dir / name
        path.write_bytes("".join(f"{i}\n" for i in ids).encode())
        paths.append(str(path))
    if paths:
        args += ["--usage", *paths]  # one option followed by every file
    status_path = tmp_path / "sprint-status.yaml"
    status_path.write_text(status, encoding="utf-8")
    return args + ["--sprint-status", str(status_path)]


def run(args):
    assert TOOL.is_file(), f"missing {TOOL}"
    result = subprocess.run([sys.executable, str(TOOL), *args], cwd=REPO_ROOT,
                            capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout + result.stderr


def lines_naming(out, *needles):
    return [line for line in out.splitlines() if all(n in line for n in needles)]


GOOD_T = [t_row("fixture-used-a"), t_row("fixture-later", "9-1-fixture-open-story")]
GOOD_R = [r_row("fixture-used-b"), r_row("fixture-in-review", "9-2-fixture-review-story")]
GOOD_USAGE = {"ctest.txt": ["fixture-used-a"], "pytest.txt": ["", "fixture-used-b", ""]}


def test_tool_exists():
    assert TOOL.is_file(), f"missing {TOOL}"


def test_all_good_exits_0(tmp_path):
    code, out = run(make(tmp_path, GOOD_T, GOOD_R, GOOD_USAGE))
    assert code == 0, out


def test_union_of_usage_files_is_required(tmp_path):
    """Dropping the pytest file leaves fixture-used-b unused."""
    code, out = run(make(tmp_path, GOOD_T, GOOD_R, {"ctest.txt": ["fixture-used-a"]}))
    assert code == 1, out
    assert lines_naming(out, "fixture-used-b"), out
    assert not lines_naming(out, "fixture-used-a"), out


def test_unused_row_without_pending_exits_1(tmp_path):
    code, out = run(make(tmp_path, GOOD_T + [t_row("fixture-orphan")], GOOD_R, GOOD_USAGE))
    assert code == 1, out
    assert lines_naming(out, "fixture-orphan"), out
    assert not lines_naming(out, "fixture-later"), out


def test_used_row_still_pending_exits_1(tmp_path):
    usage = {**GOOD_USAGE, "ctest.txt": ["fixture-used-a", "fixture-later"]}
    code, out = run(make(tmp_path, GOOD_T, GOOD_R, usage))
    assert code == 1, out
    assert lines_naming(out, "fixture-later", "9-1-fixture-open-story"), out


def test_pending_on_unknown_story_exits_1(tmp_path):
    t_rows = GOOD_T + [t_row("fixture-lost", "9-9-fixture-no-such-story")]
    code, out = run(make(tmp_path, t_rows, GOOD_R, GOOD_USAGE))
    assert code == 1, out
    assert lines_naming(out, "fixture-lost", "9-9-fixture-no-such-story"), out


def test_pending_on_done_story_exits_1(tmp_path):
    r_rows = GOOD_R + [r_row("fixture-expired", "9-3-fixture-done-story")]
    code, out = run(make(tmp_path, GOOD_T, r_rows, GOOD_USAGE))
    assert code == 1, out
    assert lines_naming(out, "fixture-expired", "9-3-fixture-done-story"), out


def test_usage_id_not_in_tables_exits_1(tmp_path):
    usage = {**GOOD_USAGE, "pytest.txt": ["fixture-used-b", "fixture-ghost"]}
    code, out = run(make(tmp_path, GOOD_T, GOOD_R, usage))
    assert code == 1, out
    assert lines_naming(out, "fixture-ghost"), out


def test_table_error_exits_1(tmp_path):
    bad = [t_row("fixture-used-a"), "fixture-no-source\t1\tHz\t\t\t"]
    code, out = run(make(tmp_path, bad, GOOD_R, GOOD_USAGE))
    assert code == 1, out
    assert "fixture-no-source" in out, out


def test_no_usage_file_exits_2(tmp_path):
    args = make(tmp_path, GOOD_T, GOOD_R, {})
    args += ["--usage", str(tmp_path / "row-usage" / "missing.txt")]
    code, out = run(args)
    assert code == 2, out
    assert "ctest" in out and "pytest" in out, f"message should say to run ctest and pytest: {out}"

