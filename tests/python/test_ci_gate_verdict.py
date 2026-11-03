"""Nightly skip gate and the full-tier verdict, decided in stdlib Python.

Contract with tools/nightly_gate.py:

- `python tools/nightly_gate.py --event EVENT --main-sha SHA --runs FILE
  [--github-output FILE]`. FILE is GitHub API JSON:
    {"workflow_runs": [{"id", "head_sha", "head_branch", "event", "status",
                        "conclusion", "created_at"}, ...]}
  (`created_at` is ISO 8601 UTC, for example "2026-11-01T03:00:12Z"; the
  list may be in any order).
- For any EVENT other than `schedule`, the decision is run.
- For `schedule`: take the newest run (by `created_at`) whose conclusion is
  `success`, head_branch is `main`, and event is `schedule` or
  `workflow_dispatch`. If its head_sha equals SHA, the decision is skip with
  reason exactly `skipped: main unchanged since run <id> (<sha>)`; otherwise
  (or when there is no such run) run.
- Appends `run=true` or `run=false` and `reason=<text>` lines to the
  github-output file (when given), prints the reason, exits 0. Malformed
  input (not JSON, or no `workflow_runs` list) exits 1.

Contract with tools/ci_verdict.py:

- `python tools/ci_verdict.py --needs FILE`. FILE is `toJSON(needs)` from the
  verdict job: {"<job>": {"result": "success|failure|cancelled|skipped",
  "outputs": {...}}}. Required jobs: gate, windows-x64, windows-arm64,
  macos-arm64, android-build, android-arm64, contract-mustfail, hash-compare.
  The gate's outputs carry `run` ("true" or "false") and `reason`.
- Pass (exit 0) when gate is success, its run output is `true`, and every
  other required job is `success`.
- Nightly skip pass (exit 0): gate success, run `false`, every other
  required job `skipped`; prints a line starting `::notice::` that contains
  the gate's reason.
- Anything else exits 1, with one line per offending job naming the job and
  its result (`missing` when the job is absent from FILE). Malformed input
  exits 1.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "tools" / "nightly_gate.py"
VERDICT = REPO_ROOT / "tools" / "ci_verdict.py"
MAIN = "a" * 40
OLD = "b" * 40
REQUIRED = ["gate", "windows-x64", "windows-arm64", "macos-arm64", "android-build",
            "android-arm64", "contract-mustfail", "hash-compare"]
SKIP_REASON = f"skipped: main unchanged since run 111 ({MAIN})"


def run(script, *args):
    result = subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout + result.stderr


# ------------------------------------------------------------- nightly gate


def wf_run(run_id, sha, created, conclusion="success", event="schedule", branch="main",
           status="completed"):
    return {"id": run_id, "head_sha": sha, "head_branch": branch, "event": event,
            "status": status, "conclusion": conclusion, "created_at": created}


def gate(tmp_path, event, runs, main_sha=MAIN, raw=None):
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(raw if raw is not None else json.dumps({"workflow_runs": runs}),
                         encoding="utf-8")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    code, out = run(GATE, "--event", event, "--main-sha", main_sha, "--runs", runs_file,
                    "--github-output", output)
    lines = output.read_text(encoding="utf-8").splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line)
    return code, out, values


def test_unchanged_nightly_skips(tmp_path):
    runs = [wf_run(111, MAIN, "2026-11-01T03:00:12Z")]
    code, out, values = gate(tmp_path, "schedule", runs)
    assert code == 0, out
    assert values.get("run") == "false", values
    assert values.get("reason") == SKIP_REASON, values
    assert SKIP_REASON in out, out


def test_unchanged_since_manual_run_skips(tmp_path):
    runs = [wf_run(111, MAIN, "2026-11-01T15:00:00Z", event="workflow_dispatch")]
    code, out, values = gate(tmp_path, "schedule", runs)
    assert code == 0, out
    assert values.get("run") == "false", values
    assert values.get("reason") == SKIP_REASON, values


def test_changed_main_runs(tmp_path):
    runs = [wf_run(111, OLD, "2026-11-01T03:00:12Z")]
    code, out, values = gate(tmp_path, "schedule", runs)
    assert code == 0, out
    assert values.get("run") == "true", values
    assert values.get("reason"), values


def test_no_previous_run_runs(tmp_path):
    code, out, values = gate(tmp_path, "schedule", [])
    assert code == 0, out
    assert values.get("run") == "true", values


@pytest.mark.parametrize("event", ["pull_request", "workflow_dispatch"])
def test_manual_and_pull_request_never_skip(tmp_path, event):
    runs = [wf_run(111, MAIN, "2026-11-01T03:00:12Z")]
    code, out, values = gate(tmp_path, event, runs)
    assert code == 0, out
    assert values.get("run") == "true", values


@pytest.mark.parametrize(
    "matching",
    [
        {"conclusion": "failure"},
        {"conclusion": "cancelled"},
        {"conclusion": None, "status": "in_progress"},
        {"event": "pull_request"},
        {"event": "push"},
        {"branch": "story/0-1-build-skeleton-and-ci-matrix"},
    ],
    ids=["failed", "cancelled", "in-progress", "pull-request", "push", "other-branch"],
)
def test_matching_sha_on_unqualified_run_does_not_skip(tmp_path, matching):
    runs = [
        wf_run(100, OLD, "2026-10-31T03:00:00Z"),
        wf_run(111, MAIN, "2026-11-01T03:00:12Z", **matching),
    ]
    code, out, values = gate(tmp_path, "schedule", runs)
    assert code == 0, out
    assert values.get("run") == "true", values


def test_newest_qualifying_run_wins_over_older_match(tmp_path):
    runs = [
        wf_run(120, OLD, "2026-11-02T03:00:00Z"),
        wf_run(111, MAIN, "2026-11-01T03:00:12Z"),
    ]
    code, out, values = gate(tmp_path, "schedule", runs)
    assert code == 0, out
    assert values.get("run") == "true", values


def test_newest_qualifying_run_wins_regardless_of_list_order(tmp_path):
    runs = [
        wf_run(111, MAIN, "2026-11-02T03:00:00Z"),
        wf_run(100, OLD, "2026-10-30T03:00:00Z"),
        wf_run(105, OLD, "2026-11-01T03:00:00Z"),
    ]
    code, out, values = gate(tmp_path, "schedule", runs)
    assert code == 0, out
    assert values.get("run") == "false", values
    assert values.get("reason") == SKIP_REASON, values


@pytest.mark.parametrize("raw", ["not json", json.dumps({"runs": []}), json.dumps([1, 2])],
                         ids=["garbage", "no-workflow-runs", "list"])
def test_malformed_runs_fail(tmp_path, raw):
    code, out, _ = gate(tmp_path, "schedule", None, raw=raw)
    assert code == 1, out


def test_gate_without_github_output_prints_reason(tmp_path):
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps({"workflow_runs": [wf_run(111, MAIN, "2026-11-01T03:00:12Z")]}),
                         encoding="utf-8")
    code, out = run(GATE, "--event", "schedule", "--main-sha", MAIN, "--runs", runs_file)
    assert code == 0, out
    assert SKIP_REASON in out, out


# ------------------------------------------------------------------ verdict


def needs(results=None, run_flag="true", reason="main changed", drop=()):
    results = results or {}
    data = {}
    for job in REQUIRED:
        if job in drop:
            continue
        data[job] = {"result": results.get(job, "success"), "outputs": {}}
    if "gate" in data:
        data["gate"]["outputs"] = {"run": run_flag, "reason": reason}
    return data


def verdict(tmp_path, data, raw=None):
    path = tmp_path / "needs.json"
    path.write_text(raw if raw is not None else json.dumps(data), encoding="utf-8")
    return run(VERDICT, "--needs", path)


def all_skipped():
    return {job: "skipped" for job in REQUIRED if job != "gate"}


def assert_one_line_names(output, *needles):
    lines = [line for line in output.splitlines() if all(n in line for n in needles)]
    assert lines, f"no single line names all of {needles}:\n{output}"


def test_all_success_passes(tmp_path):
    code, out = verdict(tmp_path, needs())
    assert code == 0, out


def test_nightly_skip_passes_with_notice(tmp_path):
    code, out = verdict(tmp_path, needs(all_skipped(), run_flag="false", reason=SKIP_REASON))
    assert code == 0, out
    assert any(line.startswith("::notice::") and SKIP_REASON in line
               for line in out.splitlines()), out


@pytest.mark.parametrize("result", ["skipped", "cancelled", "failure"])
def test_android_run_not_success_fails(tmp_path, result):
    code, out = verdict(tmp_path, needs({"android-arm64": result}))
    assert code == 1, out
    assert_one_line_names(out, "android-arm64", result)


@pytest.mark.parametrize("job", [j for j in REQUIRED if j != "gate"])
def test_any_cancelled_job_fails(tmp_path, job):
    code, out = verdict(tmp_path, needs({job: "cancelled"}))
    assert code == 1, out
    assert_one_line_names(out, job, "cancelled")


def test_missing_android_job_fails(tmp_path):
    code, out = verdict(tmp_path, needs(drop=("android-arm64",)))
    assert code == 1, out
    assert_one_line_names(out, "android-arm64", "missing")


def test_missing_gate_fails(tmp_path):
    code, out = verdict(tmp_path, needs(drop=("gate",)))
    assert code == 1, out
    assert_one_line_names(out, "gate", "missing")


def test_gate_failure_fails(tmp_path):
    code, out = verdict(tmp_path, needs(dict(all_skipped(), gate="failure")))
    assert code == 1, out
    assert_one_line_names(out, "gate", "failure")


def test_run_false_but_a_job_not_skipped_fails(tmp_path):
    results = dict(all_skipped(), **{"hash-compare": "success"})
    code, out = verdict(tmp_path, needs(results, run_flag="false", reason=SKIP_REASON))
    assert code == 1, out
    assert_one_line_names(out, "hash-compare", "success")


def test_run_true_but_everything_skipped_fails(tmp_path):
    code, out = verdict(tmp_path, needs(all_skipped(), run_flag="true"))
    assert code == 1, out
    for job in REQUIRED:
        if job != "gate":
            assert_one_line_names(out, job, "skipped")


def test_gate_without_run_output_fails(tmp_path):
    data = needs()
    data["gate"]["outputs"] = {}
    code, out = verdict(tmp_path, data)
    assert code == 1, out


@pytest.mark.parametrize("raw", ["not json", json.dumps([])], ids=["garbage", "list"])
def test_malformed_needs_fail(tmp_path, raw):
    code, out = verdict(tmp_path, None, raw=raw)
    assert code == 1, out
