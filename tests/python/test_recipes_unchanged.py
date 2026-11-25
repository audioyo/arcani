"""CI check: no recipe file changes during a run (Story 4.2; docs/signal-spec.md,
Loudness gain, Store: only the dev PC stores gains).

Contract with tools/check_recipes_unchanged.py (standard library only):
`python tools/check_recipes_unchanged.py [--repo DIR]` (DIR defaults to the
repo root) runs `git status --porcelain --untracked-files=all -- recipes` in
DIR. Exit 0 when it prints nothing; exit 1 with one line per modified,
added, deleted, or untracked path, each line naming the path (relative to
DIR, forward slashes, as git prints it); exit 2 on a git error (for
example DIR is not a git work tree).

Contract with .github/workflows/fast.yml and full.yml: in every job the
step right before the final wall-time step (which stays last,
test_ci_workflows.py) runs `tools/check_recipes_unchanged.py`, so it comes
after every test step.

Every case runs in a temp git repo made here; the checkout is never
touched. The must-fail CI step stores a gain with the real
`arcani-render --store-gain` into a recipe of the temp repo and is caught.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import preview_common as common

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "check_recipes_unchanged.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
FIXTURES_VALID = REPO_ROOT / "recipes" / "fixtures" / "valid"
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(GIT is None, reason="git is not on PATH")


def git(repo, *args):
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME": "Arcani test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Arcani test", "GIT_COMMITTER_EMAIL": "test@example.invalid"})
    r = subprocess.run([GIT, *args], cwd=repo, capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "recipes" / "fixtures" / "valid").mkdir(parents=True)
    (root / "docs").mkdir()
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    shutil.copyfile(FIXTURES_VALID / "theta-cycle-sine.json", root / "recipes" / "fixtures" / "valid" /
                    "theta-cycle-sine.json")
    (root / "recipes" / "a.json").write_text('{"a": 1}\n', encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    (root / "docs" / "notes.md").write_text("notes\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def check(repo_dir):
    assert TOOL.is_file(), f"missing {TOOL} (Story 4.2)"
    return subprocess.run([sys.executable, str(TOOL), "--repo", str(repo_dir)], capture_output=True, text=True,
                          timeout=120)


def lines(r):
    return [line for line in (r.stdout + r.stderr).splitlines() if line.strip()]


def test_tool_is_standard_library_only():
    assert TOOL.is_file(), f"missing {TOOL} (Story 4.2)"
    text = TOOL.read_text(encoding="utf-8")
    for module in ("yaml", "numpy", "pytest", "requests"):
        assert f"import {module}" not in text and f"from {module}" not in text, module


def test_clean_tree_exits_0(repo):
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert lines(r) == [], r.stdout + r.stderr


def test_modified_recipe_exits_1_naming_it(repo):
    (repo / "recipes" / "a.json").write_text('{"a": 2}\n', encoding="utf-8")
    r = check(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    out = lines(r)
    assert len(out) == 1, out
    assert "recipes/a.json" in out[0], out


def test_added_untracked_recipes_exit_1_naming_each(repo):
    (repo / "recipes" / "new.json").write_text("{}\n", encoding="utf-8")
    (repo / "recipes" / "sub" / "deep").mkdir(parents=True)
    (repo / "recipes" / "sub" / "deep" / "x.json").write_text("{}\n", encoding="utf-8")
    r = check(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    out = "\n".join(lines(r))
    assert len(lines(r)) == 2, out
    assert "recipes/new.json" in out, out
    # --untracked-files=all: the file itself, not just its new directory.
    assert "recipes/sub/deep/x.json" in out, out


def test_staged_added_recipe_exits_1(repo):
    (repo / "recipes" / "staged.json").write_text("{}\n", encoding="utf-8")
    git(repo, "add", "recipes/staged.json")
    r = check(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "recipes/staged.json" in "\n".join(lines(r))


def test_deleted_recipe_exits_1_naming_it(repo):
    (repo / "recipes" / "a.json").unlink()
    r = check(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "recipes/a.json" in "\n".join(lines(r))


def test_changes_outside_recipes_exit_0(repo):
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "docs" / "notes.md").unlink()
    (repo / "docs" / "new.md").write_text("new\n", encoding="utf-8")
    (repo / "recipes-like.json").write_text("{}\n", encoding="utf-8")
    r = check(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert lines(r) == [], r.stdout + r.stderr


def test_git_error_exits_2(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    env = os.environ.copy()
    env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)
    r = subprocess.run([sys.executable, str(TOOL), "--repo", str(plain)], capture_output=True, text=True,
                       timeout=120, env=env)
    assert r.returncode == 2, r.stdout + r.stderr


def test_must_fail_a_ci_step_that_stores_a_gain_is_caught(repo):
    render = common.build("arcani-render", common.RENDER)
    recipe = repo / "recipes" / "fixtures" / "valid" / "theta-cycle-sine.json"
    before = recipe.read_bytes()
    assert check(repo).returncode == 0
    r = common.run(render, [recipe, "--store-gain"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert recipe.read_bytes() != before
    c = check(repo)
    assert c.returncode == 1, c.stdout + c.stderr
    assert "recipes/fixtures/valid/theta-cycle-sine.json" in "\n".join(lines(c))


def test_the_checkout_recipes_are_unchanged_by_default_repo():
    """The tool with no --repo runs on this checkout (exit 0 or 1, never 2)."""
    assert TOOL.is_file(), f"missing {TOOL} (Story 4.2)"
    r = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True, timeout=120, cwd=REPO_ROOT)
    assert r.returncode in (0, 1), r.stdout + r.stderr


# ------------------------------------------------------------ workflows


def job_params():
    out = []
    for name in ("fast.yml", "full.yml"):
        jobs = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"]
        out += [(name, job_id) for job_id in jobs]
    return out


@pytest.mark.parametrize("name, job_id", job_params())
def test_every_job_checks_recipes_unchanged_after_its_tests(name, job_id):
    steps = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"][job_id]["steps"]
    assert len(steps) >= 2, job_id
    assert "tools/check_wall_time.py" in str(steps[-1].get("run", "")), steps[-1]
    check_step = steps[-2]
    assert "tools/check_recipes_unchanged.py" in str(check_step.get("run", "")), (job_id, check_step)
    # No other step runs it, so it is the one after every test step.
    others = [s for s in steps[:-2] if "check_recipes_unchanged" in str(s.get("run", ""))]
    assert not others, (job_id, others)
