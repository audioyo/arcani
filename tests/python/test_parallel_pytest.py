"""Parallel Python tests in CI (spec-ci-parallel-pytest.md).

Contract:

- In .github/workflows/fast.yml and full.yml, every job step named
  "Python tests" runs exactly `uv run --locked pytest -n auto --dist worksteal`.
  The jobs that have one: fast linux-x64 and windows-x64; full windows-x64,
  windows-arm64, and macos-arm64.
- pyproject.toml pins `pytest-xdist==3.8.0` in the dev dependency group.
- The row usage file (tests/python/conftest.py, Story 0.3) holds the same ids
  whether pytest runs with two workers or with none: the workers hand their
  row ids to the controller, which writes the union. Without that, the
  controller, which runs no test, writes an empty file.
- Each xdist worker runs numpy's BLAS and OpenMP with one thread
  (OPENBLAS_NUM_THREADS, OMP_NUM_THREADS, MKL_NUM_THREADS = 1, set by the
  conftest before numpy loads), so N workers on N cores do not oversubscribe:
  on fast linux-x64 with 4 workers the rate-curve timing tests took up to
  24 min each with threaded BLAS (design log (yy)). A serial run keeps the
  environment as it is.
"""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
COMMAND = "uv run --locked pytest -n auto --dist worksteal"
PYTEST_JOBS = [
    ("fast.yml", "linux-x64"),
    ("fast.yml", "windows-x64"),
    ("full.yml", "windows-x64"),
    ("full.yml", "windows-arm64"),
    ("full.yml", "macos-arm64"),
]
# Two quick files that read different rows (frequency-accuracy and sine-error;
# click-highpass and click-level).
USAGE_FILES = ["tests/python/test_tables_assertions.py", "tests/python/test_click_tool.py"]


def load(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name, job_id", PYTEST_JOBS)
def test_python_tests_step_runs_in_parallel(name, job_id):
    steps = load(name)["jobs"][job_id]["steps"]
    found = [s for s in steps if s.get("name") == "Python tests"]
    assert len(found) == 1, f"{name} {job_id}: {len(found)} steps named Python tests"
    assert str(found[0].get("run", "")).strip() == COMMAND, found[0]


@pytest.mark.parametrize("name", ["fast.yml", "full.yml"])
def test_no_other_python_tests_step(name):
    jobs = load(name)["jobs"]
    have = sorted(j for j, job in jobs.items()
                  if any(s.get("name") == "Python tests" for s in job.get("steps", [])))
    want = sorted(j for n, j in PYTEST_JOBS if n == name)
    assert have == want, (name, have, want)


def test_xdist_pinned():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = project["dependency-groups"]["dev"]
    assert "pytest-xdist==3.8.0" in dev, dev


def run_usage(tmp_path, label, extra):
    usage = tmp_path / f"{label}.txt"
    env = dict(os.environ, ARCANI_PYTEST_ROW_USAGE=str(usage))
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra, *USAGE_FILES]
    done = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    assert usage.is_file(), f"{label}: no usage file written"
    return usage.read_text(encoding="utf-8").split()


def test_row_usage_same_with_workers(tmp_path):
    serial = run_usage(tmp_path, "serial", ["-p", "no:xdist"])
    parallel = run_usage(tmp_path, "parallel", ["-n", "2"])
    assert serial, "the serial run read no rows"
    assert {"frequency-accuracy", "sine-error", "click-highpass", "click-level"} <= set(serial), serial
    assert parallel == serial, (parallel, serial)


THREAD_VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
PROBE = (
    "import json, os, numpy\n"
    "def test_probe():\n"
    "    with open(os.environ['ARCANI_THREAD_PROBE_OUT'], 'w', encoding='utf-8') as f:\n"
    "        json.dump([os.environ.get(v) for v in %r], f)\n" % (THREAD_VARS,)
)


def test_workers_run_blas_single_threaded(tmp_path):
    probe = REPO_ROOT / "tests" / "python" / f"test_zz_thread_probe_{os.getpid()}.py"
    probe.write_text(PROBE, encoding="utf-8")
    seen = {}
    try:
        env = {k: v for k, v in os.environ.items() if k not in THREAD_VARS}
        env["ARCANI_PYTEST_ROW_USAGE"] = str(tmp_path / "usage.txt")
        base = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(probe)]
        for label, extra in (("parallel", ["-n", "1"]), ("serial", ["-p", "no:xdist"])):
            env["ARCANI_THREAD_PROBE_OUT"] = str(tmp_path / f"{label}.json")
            done = subprocess.run(base + extra, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300)
            assert done.returncode == 0, (label, done.stdout[-1500:], done.stderr[-1500:])
            seen[label] = json.loads((tmp_path / f"{label}.json").read_text(encoding="utf-8"))
    finally:
        probe.unlink()
    assert seen["parallel"] == ["1", "1", "1"], seen
    assert seen["serial"] == [None, None, None], seen
