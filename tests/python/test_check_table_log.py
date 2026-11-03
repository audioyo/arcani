"""Design-log gate on table changes (Story 0.3).

Contract with tools/check_table_log.py (stdlib only):

- `python tools/check_table_log.py --base REF [--repo DIR]`; DIR defaults to
  the git top level of the working directory.
- Compares tests/tables/thresholds.tsv and tests/tables/ranges.tsv at REF
  (git show; a file missing at REF has no rows) with the working tree (a
  missing file has no rows). Rows are keyed by id, fields by header name.
- A changed id is one added, removed, or with any field other than
  `pending` different. A change of `pending` alone needs no log line.
- Logged ids: every backtick span on lines added to docs/design-log.md
  between REF and the working tree (`git diff REF -- docs/design-log.md`,
  lines starting with "+" but not "+++"). A line that was already there at
  REF does not log anything.
- Exit 0 when every changed id is logged, and when nothing changed. Exit 1
  with one line per unlogged id naming the id and whether it was added,
  removed, or changed. Exit 2 on a git error (bad REF, not a repo).

Each case builds a throwaway git repo in tmp_path; fixture rows are made up.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "check_table_log.py"
GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git is not on PATH")

T_HEADER = "id\tvalue\tunit\tspec_row\tsource\tpending"
R_HEADER = "id\tmin\tmax\tmax_bound\tunit\tspec_row\tsource\tpending"
T_ROWS = {
    "fixture-alpha": "fixture-alpha\t-120\tdBFS\t\tFixture only\t",
    "fixture-beta": "fixture-beta\t0.01\tHz\t\tFixture only\t9-1-fixture-story",
}
R_ROWS = {
    "fixture-gamma": "fixture-gamma\t1\t6\tinclusive\tHz\t\tFixture only\t",
}
LOG = "# Design log\n\n### 2026-01-01 (a): fixture entry\n\nOld entry naming `fixture-old`.\n"


def git(repo, *args):
    result = subprocess.run([GIT, "-C", str(repo), *args], capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def write_tables(repo, t_rows=T_ROWS, r_rows=R_ROWS):
    d = repo / "tests" / "tables"
    d.mkdir(parents=True, exist_ok=True)
    (d / "thresholds.tsv").write_bytes(
        ("\n".join([T_HEADER, *t_rows.values()]) + "\n").encode("utf-8"))
    (d / "ranges.tsv").write_bytes(
        ("\n".join([R_HEADER, *r_rows.values()]) + "\n").encode("utf-8"))


def write_log(repo, text):
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "design-log.md").write_bytes(text.encode("utf-8"))


def append_log(repo, line):
    write_log(repo, (repo / "docs" / "design-log.md").read_text(encoding="utf-8") + line + "\n")


def init_repo(path, with_tables=True):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "Fixture")
    git(path, "config", "user.email", "fixture@example.invalid")
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "core.autocrlf", "false")
    if with_tables:
        write_tables(path)
    write_log(path, LOG)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")
    return git(path, "rev-parse", "HEAD")


def commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def check(repo, base, cwd=None):
    assert TOOL.is_file(), f"missing {TOOL}"
    # The ceiling keeps git from finding a repository above the temp directory.
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(repo).parent))
    result = subprocess.run(
        [sys.executable, str(TOOL), "--base", base, "--repo", str(repo)],
        cwd=cwd or repo, env=env, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout + result.stderr


def line_naming(out, row_id):
    lines = [line for line in out.splitlines() if row_id in line]
    assert lines, f"no line names {row_id}: {out}"
    return lines[0].lower()


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    return path, init_repo(path)


def test_tool_exists():
    assert TOOL.is_file(), f"missing {TOOL}"


def test_nothing_changed_exits_0(repo):
    path, base = repo
    code, out = check(path, base)
    assert code == 0, out


def test_unlogged_value_change_exits_1_naming_id(repo):
    path, base = repo
    write_tables(path, {**T_ROWS, "fixture-alpha": "fixture-alpha\t-110\tdBFS\t\tFixture only\t"})
    code, out = check(path, base)
    assert code == 1, out
    assert "changed" in line_naming(out, "fixture-alpha"), out
    assert "fixture-beta" not in out and "fixture-gamma" not in out, out


def test_unlogged_source_change_exits_1(repo):
    path, base = repo
    write_tables(path, r_rows={"fixture-gamma": "fixture-gamma\t1\t6\tinclusive\tHz\t\tFixture, new source\t"})
    code, out = check(path, base)
    assert code == 1, out
    assert "changed" in line_naming(out, "fixture-gamma"), out


def test_logged_change_exits_0(repo):
    path, base = repo
    write_tables(path, {**T_ROWS, "fixture-alpha": "fixture-alpha\t-110\tdBFS\t\tFixture only\t"})
    append_log(path, "- `fixture-alpha`: fixture value moved.")
    commit_all(path, "change and log")
    code, out = check(path, base)
    assert code == 0, out


def test_logged_change_uncommitted_exits_0(repo):
    path, base = repo
    write_tables(path, r_rows={"fixture-gamma": "fixture-gamma\t1\t7\tinclusive\tHz\t\tFixture only\t"})
    append_log(path, "Range `fixture-gamma` widened in this fixture.")
    code, out = check(path, base)
    assert code == 0, out


def test_log_line_naming_another_id_does_not_count(repo):
    path, base = repo
    write_tables(path, {**T_ROWS, "fixture-alpha": "fixture-alpha\t-110\tdBFS\t\tFixture only\t"})
    append_log(path, "- `fixture-beta` and fixture-alpha without backticks.")
    code, out = check(path, base)
    assert code == 1, out
    assert "fixture-alpha" in out, out


def test_log_line_already_at_base_does_not_count(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    base = init_repo(path)
    append_log(path, "- `fixture-alpha` named before the base.")
    commit_all(path, "old log line")
    base = git(path, "rev-parse", "HEAD")
    write_tables(path, {**T_ROWS, "fixture-alpha": "fixture-alpha\t-110\tdBFS\t\tFixture only\t"})
    code, out = check(path, base)
    assert code == 1, out
    assert "fixture-alpha" in out, out


def test_pending_only_change_exits_0(repo):
    path, base = repo
    write_tables(path, {**T_ROWS, "fixture-beta": "fixture-beta\t0.01\tHz\t\tFixture only\t"},
                 {"fixture-gamma": "fixture-gamma\t1\t6\tinclusive\tHz\t\tFixture only\t9-2-other-story"})
    code, out = check(path, base)
    assert code == 0, out


def test_removed_row_unlogged_exits_1_naming_id(repo):
    path, base = repo
    write_tables(path, {"fixture-alpha": T_ROWS["fixture-alpha"]})
    commit_all(path, "remove beta")
    code, out = check(path, base)
    assert code == 1, out
    assert "removed" in line_naming(out, "fixture-beta"), out


def test_removed_row_logged_exits_0(repo):
    path, base = repo
    write_tables(path, {"fixture-alpha": T_ROWS["fixture-alpha"]})
    append_log(path, "- Removed `fixture-beta`.")
    code, out = check(path, base)
    assert code == 0, out


def test_added_row_unlogged_exits_1_naming_id(repo):
    path, base = repo
    write_tables(path, r_rows={**R_ROWS,
                               "fixture-delta": "fixture-delta\t0\t30\texclusive\tHz\t\tFixture only\t"})
    code, out = check(path, base)
    assert code == 1, out
    assert "added" in line_naming(out, "fixture-delta"), out
    assert "fixture-gamma" not in out, out


def test_tables_absent_at_base_count_as_added(tmp_path):
    path = tmp_path / "repo"
    base = init_repo(path, with_tables=False)
    write_tables(path)
    code, out = check(path, base)
    assert code == 1, out
    for row_id in (*T_ROWS, *R_ROWS):
        assert "added" in line_naming(out, row_id), out
    append_log(path, "- New rows `fixture-alpha`, `fixture-beta`, `fixture-gamma`.")
    code, out = check(path, base)
    assert code == 0, out


def test_bad_base_exits_2(repo):
    path, _ = repo
    code, out = check(path, "no-such-ref-xyz")
    assert code == 2, out


def test_not_a_repo_exits_2(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out = check(plain, "HEAD", cwd=plain)
    assert code == 2, out


def test_repo_defaults_to_working_directory(repo):
    path, base = repo
    write_tables(path, {**T_ROWS, "fixture-alpha": "fixture-alpha\t-110\tdBFS\t\tFixture only\t"})
    result = subprocess.run([sys.executable, str(TOOL), "--base", base], cwd=path,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "fixture-alpha" in result.stdout + result.stderr
