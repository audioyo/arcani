---
title: 'CI headroom: run the Python tests in parallel'
type: 'chore'
created: '2026-11-19'
status: 'in-review'
baseline_commit: 'a69727e'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/deferred-work.md'
  - '{project-root}/ci/wall_time_budget.json'
---

## Intent

**Problem:** The full windows-x64 job took 44.6 of its 45 min budget on PR #21 (full run 44240503822), and fast windows-x64 took 26.8 of 45. Nearly all of it is the Python suite (`uv run --locked pytest`, 3,658 tests, 50 min serial on the dev PC), which runs on one core while every hosted runner has three or four. Story 4.1 adds tests, so the next PR would go over budget.

**Approach:** Run the Python suite on every core of the runner with pytest-xdist (`-n auto --dist worksteal`) in the same jobs. No job is added, split, or removed, no test or threshold changes, and the hosted runners stay free for this public repo. The row usage file (Story 0.3) must stay correct: today each pytest process writes the rows it read at session end, so with workers the controller would write an empty set. Workers hand their row ids to the controller, which writes the union.

This takes the headroom work forward from the deferred row "Before Story 5.1, shard the full CI tier". It does not do the Story 5.1 part (the whole-session 8 hour renders on nightly and manual runs only); that row stays open.

## Boundaries & Constraints

- No test, assertion, threshold, or golden changes. The same tests run on the same platforms.
- One new pinned dev dependency, `pytest-xdist==3.8.0` (with `execnet==2.1.2`), locked with hashes in `uv.lock`.
- The serial command (`uv run --locked pytest` with no `-n`) still works and writes the same usage file.
- The Android pin check step (`pytest tests/cmake/test_pin_check.py -k android`) stays serial: two tests.
- Budgets in `ci/wall_time_budget.json` are not raised. Lowering them waits for measured runs.

## Tasks & Acceptance

- [x] tests (tests-only commit first): `tests/python/test_parallel_pytest.py`.
- [x] `pyproject.toml`, `uv.lock`: pinned pytest-xdist.
- [x] `tests/python/conftest.py`: workers pass their row ids to the controller; the controller writes the union.
- [x] `.github/workflows/fast.yml`, `full.yml`: every step named "Python tests" runs `uv run --locked pytest -n auto --dist worksteal`.
- [x] Records: design log entry, deferred-work row note, guidebook UPDATE_LOG.

**Acceptance Criteria:**
- Given the fast and full workflows, then every job step named "Python tests" runs exactly `uv run --locked pytest -n auto --dist worksteal`.
- Given `pyproject.toml`, then the dev group pins `pytest-xdist==3.8.0`.
- Given a pytest run of the same test files with two workers and with none, then both write the same, non-empty row usage file.
- Given the whole suite with workers on the dev PC, then the pass and skip counts equal the serial run's (3,658 passed, 2 skipped at a69727e) and `tools/check_row_coverage.py` exits 0.
- Given the PR's CI, then every job is within its unchanged budget, and full windows-x64 drops well under 45 min.
