"""CI wall-time budget table and its checker.

Contract with tools/check_wall_time.py (stdlib only):

- `python tools/check_wall_time.py --tier fast|full --job NAME
  --start EPOCH_SECONDS [--now EPOCH_SECONDS] [--budget FILE]`. `--now`
  defaults to the current time; `--budget` defaults to the repo's
  ci/wall_time_budget.json (not relative to the working directory). Prints
  one line containing the wall minutes ((now - start) / 60) and the job's
  budget minutes. Exit 0 when wall <= budget, exit 1 when wall > budget,
  exit 1 when the job is not in the table for that tier.
- `python tools/check_wall_time.py --estimate [--budget FILE]` prints one
  line per runner label (summed over both tiers) with its monthly minutes
  (sum of budget_minutes * runs_per_month over jobs on that runner), its
  billing multiplier, and its billed-equivalent minutes (monthly minutes *
  multiplier); then one line with the total billed-equivalent minutes and
  the account allowance; and, when `public_repo` is true, a line stating
  that billed minutes are 0 for a public repo. Exit 0.
- Numbers may print as integers or with a decimal part (50 or 50.0).

Budget file schema:

    {"allowance_minutes_per_month": int, "public_repo": bool, "source": str,
     "tiers": {"fast": {"<job id>": {"budget_minutes": n, "runner": "<label>",
                                      "multiplier": n, "runs_per_month": n}},
               "full": {...}}}

The real table lists exactly the job ids of .github/workflows/fast.yml (tier
fast) and .github/workflows/full.yml (tier full); each entry's `runner`
equals that job's `runs-on`, and each job's `timeout-minutes` is twice its
budget.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_wall_time.py"
BUDGET = REPO_ROOT / "ci" / "wall_time_budget.json"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
START = 1_800_000_000


def run(*args, cwd=None):
    result = subprocess.run(
        [sys.executable, str(CHECKER), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )
    return result.returncode, result.stdout + result.stderr


def num(n):
    """Regex for the number n printed as an integer or with a zero decimal part."""
    return rf"(?<![\d.]){n}(\.0+)?(?![\d.])"


def line_with(output, *numbers, text=None):
    for line in output.splitlines():
        if text is not None and text not in line:
            continue
        if all(re.search(num(n), line) for n in numbers):
            return line
    raise AssertionError(f"no line with {numbers} {text or ''}:\n{output}")


def synthetic_budget(tmp_path, public=True):
    table = {
        "allowance_minutes_per_month": 2000,
        "public_repo": public,
        "source": "synthetic",
        "tiers": {
            "fast": {
                "job-a": {"budget_minutes": 10, "runner": "runner-a", "multiplier": 1,
                          "runs_per_month": 30},
                "job-b": {"budget_minutes": 40, "runner": "runner-b", "multiplier": 2,
                          "runs_per_month": 5},
            },
            "full": {
                "job-a": {"budget_minutes": 5, "runner": "runner-a", "multiplier": 1,
                          "runs_per_month": 20},
                "job-c": {"budget_minutes": 15, "runner": "runner-c", "multiplier": 10,
                          "runs_per_month": 2},
            },
        },
    }
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


# ---------------------------------------------------------------- checker


def test_over_budget_fails(tmp_path):
    code, out = run("--tier", "fast", "--job", "job-b", "--start", START,
                    "--now", START + 50 * 60, "--budget", synthetic_budget(tmp_path))
    assert code == 1, out
    line_with(out, 50, 40)


def test_under_budget_passes(tmp_path):
    code, out = run("--tier", "fast", "--job", "job-b", "--start", START,
                    "--now", START + 10 * 60, "--budget", synthetic_budget(tmp_path))
    assert code == 0, out
    line_with(out, 10, 40)


def test_exactly_at_budget_passes(tmp_path):
    code, out = run("--tier", "fast", "--job", "job-b", "--start", START,
                    "--now", START + 40 * 60, "--budget", synthetic_budget(tmp_path))
    assert code == 0, out


def test_tier_selects_the_budget(tmp_path):
    # job-a: 10 minutes in fast, 5 in full.
    args = ["--job", "job-a", "--start", START, "--now", START + 7 * 60,
            "--budget", synthetic_budget(tmp_path)]
    code, out = run("--tier", "fast", *args)
    assert code == 0, out
    code, out = run("--tier", "full", *args)
    assert code == 1, out
    line_with(out, 7, 5)


@pytest.mark.parametrize("tier, job", [("fast", "job-x"), ("fast", "job-c"), ("full", "job-b")])
def test_unknown_job_fails(tmp_path, tier, job):
    code, out = run("--tier", tier, "--job", job, "--start", START, "--now", START + 60,
                    "--budget", synthetic_budget(tmp_path))
    assert code == 1, out
    assert job in out, out


def test_now_defaults_to_current_time(tmp_path):
    code, out = run("--tier", "fast", "--job", "job-a", "--start", int(time.time()) - 60,
                    "--budget", synthetic_budget(tmp_path))
    assert code == 0, out
    code, out = run("--tier", "fast", "--job", "job-a", "--start", int(time.time()) - 3600,
                    "--budget", synthetic_budget(tmp_path))
    assert code == 1, out


def test_budget_defaults_to_repo_table(tmp_path):
    code, out = run("--tier", "fast", "--job", "linux-x64", "--start", START,
                    "--now", START + 30, cwd=tmp_path)
    assert code == 0, out


def test_estimate_prints_multiplied_minutes(tmp_path):
    code, out = run("--estimate", "--budget", synthetic_budget(tmp_path))
    assert code == 0, out
    # runner-a: 10*30 + 5*20 = 400 minutes, x1 = 400 billed-equivalent.
    line_with(out, 400, 1, text="runner-a")
    # runner-b: 40*5 = 200 minutes, x2 = 400.
    line_with(out, 200, 2, 400, text="runner-b")
    # runner-c: 15*2 = 30 minutes, x10 = 300.
    line_with(out, 30, 10, 300, text="runner-c")
    # total billed-equivalent 1100 against the 2000 allowance.
    line_with(out, 1100, 2000)
    assert any("public" in line.lower() and re.search(num(0), line)
               for line in out.splitlines()), out


def test_estimate_on_real_table():
    code, out = run("--estimate")
    assert code == 0, out
    table = json.loads(BUDGET.read_text(encoding="utf-8"))
    runners = {e["runner"] for tier in table["tiers"].values() for e in tier.values()}
    for runner in runners:
        assert runner in out, (runner, out)


# ------------------------------------------------------------ real table


def load_workflow(name):
    path = WORKFLOWS / name
    assert path.is_file(), f"missing {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_budget():
    assert BUDGET.is_file(), f"missing {BUDGET}"
    return json.loads(BUDGET.read_text(encoding="utf-8"))


def test_real_table_shape():
    table = load_budget()
    assert isinstance(table["allowance_minutes_per_month"], int)
    assert table["allowance_minutes_per_month"] > 0
    assert table["public_repo"] is True
    assert isinstance(table["source"], str) and table["source"].strip()
    assert set(table["tiers"]) == {"fast", "full"}
    for tier, jobs in table["tiers"].items():
        for job, e in jobs.items():
            for key in ("budget_minutes", "multiplier", "runs_per_month"):
                assert isinstance(e[key], (int, float)) and e[key] > 0, (tier, job, key, e)
            assert isinstance(e["runner"], str) and e["runner"], (tier, job, e)


@pytest.mark.parametrize("tier, workflow", [("fast", "fast.yml"), ("full", "full.yml")])
def test_real_table_covers_every_workflow_job(tier, workflow):
    jobs = load_workflow(workflow)["jobs"]
    table = load_budget()["tiers"][tier]
    assert set(table) == set(jobs), (sorted(table), sorted(jobs))
    for job_id, job in jobs.items():
        assert table[job_id]["runner"] == job["runs-on"], (job_id, table[job_id], job["runs-on"])


@pytest.mark.parametrize("tier, workflow", [("fast", "fast.yml"), ("full", "full.yml")])
def test_timeout_is_twice_the_budget(tier, workflow):
    jobs = load_workflow(workflow)["jobs"]
    table = load_budget()["tiers"][tier]
    for job_id, job in jobs.items():
        assert job.get("timeout-minutes") == 2 * table[job_id]["budget_minutes"], (
            job_id, job.get("timeout-minutes"), table[job_id]["budget_minutes"])
