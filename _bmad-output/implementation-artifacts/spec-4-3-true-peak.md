---
title: 'Story 4.3: True peak'
type: 'feature'
created: '2026-11-25'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Nothing measures true peak. A stored loudness gain (Story 4.2) can bring a render to -36 LUFS-I, but nothing proves the 24-bit file stays under the -1 dBTP ceiling between samples (row `true-peak`, FR-5, NFR15), and `--store-gain` would write a gain whose render clips.

**Approach:** Add a true-peak meter per ITU-R BS.1770-5 Annex 2 (4x oversampling with the printed 48-tap filter) twice, as for loudness: in the Python assertion library and in the command-line tooling, both outside `engine/`. Calibrate both on the EBU Tech 3341 true-peak cases, synthesized from the printed document, and on Python signals with closed-form inter-sample peaks. Every final-mode render report gets a `true_peak` assertion on the 24-bit samples it wrote. `--store-gain` renders the session with the new gain and refuses to store when the true peak would exceed the ceiling.

Decisions (planning, 2026-11-25; Audio can overrule any of them at approval):

1. **Which renders.** The check runs on every final-mode render, the only renders at playback level. Measure-mode renders run at unit gain and clip by design, so their WAVs and reports stay byte-identical (as for loudness in 4.2).
2. **Input.** The meter reads the 24-bit integers as written (`quantize_24`), each divided by 2^23. The Annex 2 coefficients are multiples of 2^-13, so every product and sum is exact in binary64: both meters give the same linear true peak bit for bit, and they are compared that way. Only the dB conversion calls `log10`.
3. **The 1 s final fixture.** `stub-chain-1s-beat-6.json` peaks near 2.0, so its placeholder gain -1.5 dB would fail the new check. It changes to `-10.00` (peak about 0.63, -4 dBTP; a stored gain vectors row already exists). Its `stub-chain-final-*` pins are re-measured and confirmed on all four platforms, as in 4.2.
4. **Store refusal.** After the final compile (Store, step 7), the store renders frames `[0, N)` in final mode, rounds them to 24 bits, and measures true peak. Above the ceiling, it writes nothing, prints `rejected: parameter=/loudness_gain_db value=<gain text> rule=true_peak limit=<= -1 dBTP (row true-peak) target_lufs=<T> true_peak_dbtp=<tp>`, and exits 1. The `stored:` line is unchanged.

## Boundaries & Constraints

**Always:** Meters stay outside `engine/`, and the CLI never includes `engine/src`. Every Annex 2 coefficient, Tech 3341 case, and tolerance comes from the published documents, cited in `docs/research-library.md`. If a Tech 3341 true-peak case's printed description does not fully define its signal, stop and ask Audio; do not guess it. Never download or commit EBU test files. Every new row gets a design-log line. Every check has a passing and a must-fail fixture, doctored in the harness. Store tests work on temp copies. Tests go first, as a tests-only commit by a fresh-context QA agent.

**Never:** No ramps (4.4), no limiter (4.5), no engine stage, and no change to measure-mode bytes, recipe hashes, or loudness hashes. No sample-peak shortcut in place of oversampling.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Calibration | Tech 3341 true-peak cases and closed-form signals, both rates | each meter reads within the stated tolerance | N/A |
| Hidden overshoot | fs/4 sine at 45 degrees, peak -0.5 dBFS (sample peak about -3.5 dBFS) | `true_peak` fails; a sample-peak check passes | N/A |
| Final render | any final render | report member `true_peak` and assertion `true_peak` (row `true-peak`, pass when at or below -1 dBTP) | exit 4 on fail |
| Silent final render | all-zero output | measured null, note `silent`, pass | N/A |
| Measure render | any | report and WAV unchanged byte for byte | N/A |
| Store over ceiling | gain whose final render exceeds -1 dBTP (doctored row in the harness) | nothing written; the decision 4 line | exit 1 |
| Store under ceiling | both 4.2 store fixtures | stored as in 4.2 | exit 0 |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md`: new section `## True peak` after `## Loudness gain` (line 4879 onward): Annex 2 filter as printed (4 phases of 12 taps), full convolution from zero state with 11 trailing zero inputs, true peak = max of |oversampled| per Annex 2, dBTP = 20 log10, the pass rule, the report member, the store step (insert between Store steps 7 and 8, line 4973), calibration signals, vectors. Update Loudness intro (4550) and "Final fixture" (5002) text.
- `tests/tables/thresholds.tsv:37`: row `true-peak` (pending `4-3-true-peak`; clear once read through `row()`). Add the Tech 3341 true-peak tolerance row(s) as printed.
- `docs/research-library.md:107-108`: extend the BS.1770-5 entry (Annex 2) and the Tech 3341 entry (true-peak cases).
- `tests/assertions/loudness.py` (pattern), new `tests/assertions/true_peak.py`: `true_peak(x24, fs)` returning the linear peak and `check_true_peak(...)` in the assertion report shape.
- `tests/python/loudness_common.py:131-165`: Tech 3341 synthesis pattern; add a `true_peak_common.py` beside it.
- `cli/loudness.{hpp,cpp}` (style), new `cli/true_peak.{hpp,cpp}` in `arcani_cli_core`: streaming meter fed `quantize_24` values (`cli/wav.hpp:17`).
- `cli/main.cpp`: render loop `:576-620` (feed the meter where samples are quantized), assertions `:681-691` (append `true_peak` last, final mode only), `run_store` `:340-455` (new step after 7). `cli/report.{hpp,cpp}:144-148`: `true_peak_assertion`, the report member.
- `cli/recipe_write.{hpp,cpp}`: a pure `true_peak_step(row, tp_linear, target, gain_text)` returning stored or the rejection text, so the over-ceiling case is unit-tested with a doctored row (tables are compiled in via `ARCANI_TABLES_DIR`, so no runtime table override exists).
- `recipes/fixtures/valid/stub-chain-1s-beat-6.json`: gain `-10.00`; `ci/hash_expected.json:114-123` re-pinned; tests that name its `-1.5` (`tests/cpp/test_api.cpp`, `tests/cpp/test_cli.cpp:495`, `tests/python/test_store_gain.py`).
- `tests/cpp/test_cli.cpp:1553` (`final_loudness_render`), `:1765`, `:1831`: final renders gain the `true_peak` assertion checks.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/tables/thresholds.tsv`, `docs/design-log.md`, `docs/research-library.md`: the True peak section, coefficients and Tech 3341 cases read from the documents, vectors (filter taps, calibration cases, closed-form signals, the must-fail), rows, log entries. Merged before code.
- [ ] `tests/python/test_true_peak_tool.py`, `tests/python/test_true_peak_cli.py`, `tests/cpp/test_true_peak.cpp`, updates to `test_cli.cpp`, `test_api.cpp`, `test_store_gain.py`: failing tests from the matrix and ACs, tests-only commit.
- [ ] `cli/true_peak.{hpp,cpp}`, `cli/report.{hpp,cpp}`, `cli/main.cpp`, `cli/recipe_write.{hpp,cpp}`, `cli/CMakeLists.txt`, `tests/assertions/true_peak.py`: meters, assertion, report member, store step.
- [ ] `recipes/fixtures/valid/stub-chain-1s-beat-6.json`, `ci/hash_expected.json`: the decision 3 gain and re-pins.

**Acceptance Criteria:**
- Given any final render in the suite at 44.1 and 48 kHz, when both meters read it, then their linear true peaks are equal bit for bit and the Python assertion agrees with the report.
- Given the full suite on the dev PC and in CI, when it runs, then everything passes, `tools/check_row_coverage.py` sees `true-peak` in use, and added CI time stays near 3 minutes of CPU per platform.

## Design Notes

**Phased handoff,** as in 4.1 and 4.2, on branch `story/4-3-true-peak`: the implementation agent writes the spec section, vectors, rows, and design log and commits; a fresh-context QA agent commits the failing tests; the implementation agent implements without editing a test expectation. No push until review.

**Known-peak signals.** A sine at fs/4 starting at 45 degrees has samples at +-A/sqrt(2), and the 4x grid lands on its crests, so its true peak is A while its sample peak is 3.01 dB lower. That is the must-fail, and with other levels a calibration signal.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl`: expected build passes and ctest is green.
- `uv run --locked pytest -n auto`: expected all pass.
- `git status --porcelain -- recipes` after the suite: expected only the decision 3 fixture edit, committed.
