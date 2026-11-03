---
title: 'Story 0.3: threshold and range tables as data'
type: 'feature'
created: '2026-11-03'
status: 'in-progress'
baseline_commit: '0dbe46f0dc32be257f74c8d6ca7b988d629334d7'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
  - '{project-root}/_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Thresholds and locked ranges live in prose (`thresholds-and-ranges.md`) plus two interim JSON files from Story 0.2 that hold only the 12 rows that story needed. Nothing proves every row is cited, that C++ and Python read the same numbers, that a changed value is logged, or that every row is actually asserted.

**Approach:** Replace the interim files with complete threshold and range tables under `tests/tables/`, read by one C++ and one Python loader inside a small assertion library under `tests/assertions/`. Add three CI checks: a C++/Python cross-check, a design-log gate on table changes, and a two-way coverage check between assertions and rows.

Decisions (2026-11-03, build agent, under Audio's standing "settle tech forks yourselves" preference; spec approved by Audio 2026-11-03, kept as one story at about 2,600 tokens):
- Tables are tab-separated text with one header row, not JSON: a C++ test loader parses it without a JSON library, and diffs read row by row.
- An edit that changes only a row's `pending` field needs no design log entry. The gate exists for changed values (CLAUDE.md, Workflow); marking a row as now used is not a value change.
- The cross-platform fallback bound in `ci/hash_tolerance.json` must equal its threshold row, checked through the assertion library, so the -100 dBFS value has one source.

## Boundaries & Constraints

**Always:**
- Rows: every row of both tables in `thresholds-and-ranges.md` maps to at least one data row (column `spec_row` = that table's first-column text, verbatim). Rows the md does not list (`sine-error`, `binaural-carrier-right`, `sample-rates`, from Story 0.2) keep their ids and cite a design log entry or say "Derived". Ids are kebab-case and unique across both tables; Story 0.2's ids stay unchanged.
- Columns: thresholds `id, value, unit, spec_row, source, pending`; ranges `id, min, max, max_bound (inclusive|exclusive), unit, spec_row, source, pending`. A set (sample rates, block sizes) is one row whose value lists its members separated by single spaces. Qualitative pass conditions (byte-identical, zero NaN) become numeric rows with a unit naming what is counted (for example `0` `differing bytes`). Every number in a row appears in its md row's pass condition or range text; "below N" is `max_bound` exclusive.
- `pending` is empty or a story key from `sprint-status.yaml`: the story whose acceptance criteria first assert that row, read from `epics.md`.
- Loaders (Python `tests/assertions/tables.py`, C++ `tests/assertions/tables.hpp|.cpp`): fail, naming file, line and id, on an empty `source`, a missing column, a duplicate id, a non-numeric value, or `min > max`. Values are kept as their exact text plus a parsed binary64.
- Assertion library: one call per assertion takes a row id and returns that row; an unknown or empty id fails the test. Each call records the id in a usage file (pytest session and ctest each write one; the ctest entry sets its path through the test's environment). Every existing test that reads `tests/tables/` moves to this call.
- Cross-check: a test-only `arcani-tables-dump` binary prints every row the C++ loader read; a Python test builds and runs it (pattern of `tests/python/test_probe_reference.py:166-197`) and requires identical ids, value texts, parsed values, and units.
- `tools/check_table_log.py --base REF`: rows added, removed, or changed in any field except `pending` between `REF` and the working tree need lines added to `docs/design-log.md` in the same range that name each id in backticks. Fails naming each unlogged id. CI uses the merge base with `origin/main`.
- `tools/check_row_coverage.py`: reads both tables, the usage files, and `sprint-status.yaml`. Fails naming the row on: a row with no use and empty `pending`; a used row that is still `pending`; a `pending` key not in sprint status, or whose story is `done`.
- Both fast jobs run the table-log check before the build and the coverage check after ctest and pytest; checkout fetches enough history for the merge base.
- Passing and must-fail fixtures for every check (the table-log fixture builds a throwaway git repo in a temp directory). Tests first by a fresh-context QA agent, committed tests-only before implementation. Python stdlib plus the locked dev dependencies only. No em dashes; CLAUDE.md "Never" terms stay out. This story's own table changes get a design log entry (cc) naming every new and changed id.

**Never:**
- Changing any threshold or range value, or a Story 0.2 bound. A value that cannot be read off the md is a question for Audio, not a guess.
- Engine changes. Report output for renders (AD-17's per-render report is Story 1.4). The wording check (Story 0.4).
- Changing `tools/hash_compare.py`; the bound check lives in a test.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Uncited row | a row with an empty `source` | both loaders fail | name file, line, id |
| Bad row | duplicate id, missing column, `min > max`, non-numeric value | both loaders fail | name file, line, id |
| Cross-check | repo tables | C++ dump equals Python rows | names first differing id |
| Unlogged change | value edited, no design log line naming it | table-log check exits 1 | names id |
| Logged change | value edited, added log line names `` `id` `` | exits 0 | N/A |
| Pending only | only `pending` changed | exits 0 | N/A |
| Removed row | row deleted, no log line | exits 1 | names id |
| Unknown row | assertion call with an id not in the tables, or empty | test fails | names id |
| Unused row | row with no use and no `pending` | coverage exits 1 | names id |
| Stale pending | `pending` story is `done`, or the key is unknown | coverage exits 1 | names id and story |
| Used but pending | row used and still `pending` | coverage exits 1 | names id |
| Md row lost | an md table row with no data row | test fails | names md row |
| Bound drift | `ci/hash_tolerance.json` bound differs from its row | test fails | names both values |

</frozen-after-approval>

## Code Map

- `tests/tables/thresholds.json`, `ranges.json` -- replace with `thresholds.tsv`, `ranges.tsv`; delete the JSON files. Add `tests/tables/README.md` (columns, set and bound rules, pending rule).
- `tests/cpp/SpecTables.cmake:53` -- `arcani_generate_spec_tables` reads the two tables files plus the vectors; drop the tables part, keep the vectors part. `tests/cpp/CMakeLists.txt` -- link the new C++ loader, set the usage-file environment on `add_test` (line 31).
- `tests/cpp/test_phase.cpp`, `test_sine.cpp`, `spec_helpers.hpp` -- read bounds and ranges through the C++ assertion call instead of generated constants (`spec::kHzRanges` and friends).
- `tests/python/test_signal_spec_core.py:49-50, 446-527`, `tests/python/test_probe_sine.py` -- move to the Python assertion call; the interim well-formed and literal-pinning tests (`EXPECTED_THRESHOLDS`, `EXPECTED_RANGES`) are replaced by the new loader and md-mapping tests.
- `tests/python/test_hash_compare.py` -- add the bound-equals-row test against `ci/hash_tolerance.json`.
- `tests/python/conftest.py` -- new or extended: write the pytest usage file at session end.
- `.github/workflows/fast.yml` -- checkout depth and the two check steps in `linux-x64` and `windows-x64`; `tests/python/test_ci_workflows.py` covers the steps.
- `ci/wall_time_budget.json` -- adjust only if the new steps need it, with the reason in the design log.
- `docs/design-log.md` -- entry (cc): table format, every id added, pending rule, gate exemption for `pending`; Current state row.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- close the "Story 0.3 absorbs `tests/tables/`" entry with the closure prefix the ledger already uses.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- `0-2-engine-sine-oscillator-spike-that-ships: done` (PR #2 merged as 0dbe46f).
- Do not change: engine sources, `tools/hash_compare.py`, `ci/hash_expected.json`, `tests/data/signal_spec_vectors.json`.

## Tasks & Acceptance

**Execution:**
- [ ] QA agent, failing tests-only commit: loader, cross-check, md-mapping, table-log, coverage, and bound tests with fixtures under `tests/fixtures/tables/`.
- [ ] `tests/tables/*.tsv`, `README.md` -- full tables.
- [ ] `tests/assertions/*` -- loaders and assertion call, C++ and Python, plus `arcani-tables-dump`.
- [ ] Port Story 0.2's C++ and Python tests, `SpecTables.cmake`, `tests/cpp/CMakeLists.txt`.
- [ ] `tools/check_table_log.py`, `tools/check_row_coverage.py`, `.github/workflows/fast.yml`.
- [ ] `docs/design-log.md`, `deferred-work.md`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given a clean checkout, when the `windows-clang-cl` workflow preset, `uv run pytest`, and then both checks run, then everything passes, every md table row has a data row, and every data row is either used by an assertion or pending on a story that is not done.
- Given Audio's go-ahead to push, when the fast tier runs on the branch, then both jobs run the table-log and coverage checks and pass.

## Spec Change Log

## Implementation Notes

## Review Triage Log

## Design Notes

Coverage proves both directions with one artifact: the usage files say which rows ran, the tables say which rows exist, and sprint status says which pending promises have expired. Rows with no consumer yet (binaural isolation, loudness, render speed) are expected to be `pending` on their Epic 1 to 5 stories; the check then fails the day such a story is marked done without asserting its rows.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build and ctest pass, C++ usage file written.
- `uv run pytest` -- expected: all pass, Python usage file written.
- `uv run python tools/check_row_coverage.py` and `uv run python tools/check_table_log.py --base origin/main` -- expected: exit 0.
