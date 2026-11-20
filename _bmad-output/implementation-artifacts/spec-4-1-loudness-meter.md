---
title: 'Story 4.1: Loudness meter'
type: 'feature'
created: '2026-11-20'
baseline_commit: 'f0451355fdacf70ef2e2d41a991700ec95da6c34'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** No code can measure loudness yet. Story 4.2 will store a loudness gain in each recipe and Story 4.3 will check true peak; both need a loudness meter that has been proven correct before it judges any render.

**Approach:** Write a §Loudness section in `docs/signal-spec.md`. It defines ITU-R BS.1770 integrated loudness (K-weighting, 400 ms blocks with 75 percent overlap, an absolute gate at -70 LUFS, a relative gate at -10 LU) and the steady-part window, with worked vectors. Build two independent meters: one in Python (`tests/assertions/loudness.py`) and one in C++ in `arcani_cli_core`. Calibrate both on the Tech 3341 integrated-loudness signals, prove that the two agree on engine renders, and add the 1 LU loudness assertion.

Decisions (Audio, 2026-11-20):

1. **Test signals.** The EBU terms of use (July 2019) forbid for-profit use and redistribution of its test sequences, so the EBU files are never downloaded or committed. Both meters are calibrated on Tech 3341 v4.0 (November 2023) Table 1 cases 1 to 5, synthesized in the harness from the levels and durations printed in the public document (stereo 1 kHz sine, in phase in both channels). Case 6 (5.1) and cases 7 and 8 (programme recordings) are out of scope. The Story 4.1 acceptance criterion in `epics.md` is amended to say so, with the reason.
2. **Window minimum.** Row `loudness-window-min` is 60 s, one period of row `rate-cycle-period`. A looping body is repeated a whole number of times to at least 60 s. A non-looping steady part shorter than 60 s is rejected with `loudness_window_rule`, but only when loudness is measured (CLI `--loudness` now, Story 4.2's measure command later); plain measure-mode renders of short recipes are unchanged.

## Boundaries & Constraints

**Always:** Meters stay outside `engine/`. Every threshold is read through the table loaders, and each new row gets a design-log line. Every assertion has a passing fixture and a must-fail fixture; must-fail fixtures are doctored in the harness. The meters read the float output; a 24-bit WAV of today's unit-gain fixtures clips. K-weighting coefficients are derived from the BS.1770 analog prototype, and at 48 kHz they must reproduce the published BS.1770 coefficients. Both 44.1 kHz and 48 kHz are supported. Tests go first, as a tests-only commit by a fresh-context QA agent.

**Never:** No loudness gain, recipe write, true peak, ramps, or limiter (Stories 4.2 to 4.5). No pass/fail loudness entry in the CLI report yet: renders have no gain until Story 4.2, so every render would fail. No 5.1 or surround support (Tech 3341 case 6).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Calibration | synthesized Tech 3341 cases 1 to 5, 44.1 and 48 kHz | each meter reads within 0.1 LU (row `loudness-meter-calibration`) | N/A |
| Gating must-fail | each meter with gating turned off in the harness | fails cases 3 and 4 (relative and absolute gate); case 5 reads the same either way | N/A |
| Agreement | every valid looping and long fixture, both rates | the Python and C++ meters agree within row `loudness-meter-agreement` (0.1 LU) | N/A |
| Assertion pass | a render scaled in the harness to exactly the target | passes row `loudness-tolerance` (1 LU) | N/A |
| Assertion must-fail | the same render scaled to +1.5 LU | fails | N/A |
| Short steady part | a non-looping recipe shorter than 60 s, measured with `--loudness` | rejected, nothing written | named rule `loudness_window_rule`, with parameter, value and limit |
| All silent | gated blocks empty | integrated loudness reported as -inf | no crash |

</frozen-after-approval>

## Code Map

- `tests/assertions/clicks.py` + `tests/python/test_click_tool.py` -- pattern for the tool, its contract docstring, calibration on NumPy signals, and `check(...)` report shape
- `tests/assertions/__init__.py` -- `row(id)` records row use for `tools/check_row_coverage.py`
- `tests/python/preview_common.py` -- `tapdump_whole` reads the float64 output of `arcani-tapdump --output-only`
- `cli/CMakeLists.txt` -- `arcani_cli_core` static library: the C++ meter lives here
- `cli/main.cpp`, `cli/report.{hpp,cpp}` -- args parsing; `report_json` with optional members (copy `PreviewReport`)
- `engine/include/arcani/arcani.h` -- `arc_plan_loop` / `arc_loop_frames` give the body and seams for the looping window
- `engine/src/plan/plan.cpp`, `engine/src/validate/` -- error shape `{parameter, value, rule, limit}`; do not change the existing compile order
- `tests/tables/thresholds.tsv`, `tests/tables/README.md`, `tools/check_table_log.py` -- new rows plus design-log lines; clear `pending` on `loudness-tolerance`
- `docs/signal-spec.md` `## Preview` (line 4427) -- section shape; `tools/signal_spec_vectors.py` generates the vector tables
- `docs/research-library.md` line 106 -- extend with ITU-R BS.1770-5 and EBU Tech 3341 v4.0 rows
- `docs/design-log.md` -- next entry after (yy)

## Tasks & Acceptance

**Execution:**
- [ ] `_bmad-output/planning-artifacts/epics.md` -- amend the Story 4.1 compliance-signal criterion per decision 1 -- licence
- [ ] `docs/signal-spec.md` -- add §Loudness: the filter derivation, gating, the window (looping: the body repeated a whole number of times to at least the minimum; non-looping: the whole session until Story 4.4), the rule and its error, and vectors from `tools/signal_spec_vectors.py` -- the single source of every formula
- [ ] `tests/tables/thresholds.tsv`, `docs/design-log.md`, `docs/research-library.md` -- add `loudness-meter-calibration`, `loudness-meter-agreement` and `loudness-window-min`, and clear pending on `loudness-tolerance` -- rule 3 traceability
- [ ] `tests/python/test_loudness_tool.py`, `tests/python/test_loudness_cli.py`, `tests/cpp/test_loudness.cpp` -- the failing tests from the matrix, as a tests-only commit -- rule 6
- [ ] `tests/assertions/loudness.py` -- `integrated_lufs(x, fs, gating=True)` and `check_loudness(x, fs, target)` -- Python meter and assertion
- [ ] `cli/loudness.{hpp,cpp}`, `cli/main.cpp`, `cli/report.cpp` -- C++ meter; `--loudness` adds a `loudness` report member (window frames, window LUFS-I, whole-render LUFS-I), or rejects with `loudness_window_rule` -- the second, independent meter

**Acceptance Criteria:**
- Given the full suite, when it runs on the dev PC and in CI, then everything passes and `tools/check_row_coverage.py` sees every new row in use.
- Given an existing CLI render without `--loudness`, when it runs, then its WAV and report bytes do not change.

## Design Notes

The Tech 3341 tolerance for every integrated case is plus or minus 0.1 LU, which gives the calibration and agreement rows. The gating must-fail works because case 3 without gating reads about -24.2 LUFS.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build passes and ctest is green
- `uv run --locked pytest -n auto` -- expected: all pass
</content>
</invoke>
