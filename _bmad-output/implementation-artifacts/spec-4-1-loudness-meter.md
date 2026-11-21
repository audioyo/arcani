---
title: 'Story 4.1: Loudness meter'
type: 'feature'
created: '2026-11-20'
baseline_commit: 'f0451355fdacf70ef2e2d41a991700ec95da6c34'
status: 'in-review'
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
- [x] `_bmad-output/planning-artifacts/epics.md` -- amend the Story 4.1 compliance-signal criterion per decision 1 -- licence
- [x] `docs/signal-spec.md` -- add §Loudness: the filter derivation, gating, the window (looping: the body repeated a whole number of times to at least the minimum; non-looping: the whole session until Story 4.4), the rule and its error, and vectors from `tools/signal_spec_vectors.py` -- the single source of every formula
- [x] `tests/tables/thresholds.tsv`, `docs/design-log.md`, `docs/research-library.md` -- add `loudness-meter-calibration`, `loudness-meter-agreement` and `loudness-window-min`, and clear pending on `loudness-tolerance` -- rule 3 traceability
- [x] `tests/python/test_loudness_tool.py`, `tests/python/test_loudness_cli.py`, `tests/cpp/test_loudness.cpp` -- the failing tests from the matrix, as a tests-only commit -- rule 6
- [x] `tests/assertions/loudness.py` -- `integrated_lufs(x, fs, gating=True)` and `check_loudness(x, fs, target)` -- Python meter and assertion
- [x] `cli/loudness.{hpp,cpp}`, `cli/main.cpp`, `cli/report.cpp` -- C++ meter; `--loudness` adds a `loudness` report member (window frames, window LUFS-I, whole-render LUFS-I), or rejects with `loudness_window_rule` -- the second, independent meter

**Acceptance Criteria:**
- Given the full suite, when it runs on the dev PC and in CI, then everything passes and `tools/check_row_coverage.py` sees every new row in use.
- Given an existing CLI render without `--loudness`, when it runs, then its WAV and report bytes do not change.

## Implementation Notes

Everything below follows `docs/signal-spec.md`, Loudness, and its vectors (`tests/data/signal_spec_vectors.json`, keys `loudness_constants`, `loudness_prototype`, `loudness_coefficients`, `loudness_blocks`, `loudness_tech3341`, `loudness_window_cases`, `loudness_windows`; C++ `kLoudness_*`, `kLoudnessPrototype`, `kLoudnessCoefficients`, `kLoudnessBlocks`, `kTech3341`, `kLoudnessWindowCases`, `kLoudnessWindows` in the generated `spec_tables.hpp`). Vector constants are cross-checked against the rows, never used in their place.

**Python meter, `tests/assertions/loudness.py`** (NumPy and the standard library only):

- `PROTOTYPE`: `{"shelf": {"f0", "Q", "Vh", "Vb"}, "highpass": {"f0", "Q", "G"}}`, binary64, equal to the hex column of Vectors: K-weighting prototype.
- `kweighting(fs) -> (shelf, highpass)`: each a tuple `(b0, b1, b2, a1, a2)` of floats by the spec's binary64 formulas. ValueError unless `fs` is a positive multiple of 10.
- `block_energies(x, fs) -> np.ndarray`: `z[j]` for every block (Integrated loudness), from zero filter state. `x` is a float64 array-like of shape `(frames, 2)` (an `np.memmap` works and is read in chunks, so a 45 min render at 48 kHz never sits in memory twice) or `(frames,)` for one channel. ValueError on any other shape, on a non-finite sample, or on a bad `fs`.
- `integrated_lufs(x, fs, gating=True) -> float`: L in LUFS-I, `-inf` when no block passes (or no block exists); `gating=False` is the must-fail meter (every block).
- `check_loudness(x, fs, target) -> dict`: name `loudness`, row `loudness-tolerance` (read through `row`), threshold, unit, measured `L - target` (LU), result `pass` when `abs(measured) <= threshold`, note `""`; not finite: measured None, note `not finite`, fail; `-inf`: measured None, note `silent`, fail.
- The filter may be run as a convolution with the cascade's impulse response (spec, Filter); the C++ meter runs the difference equation. They are written apart, from the spec, never one from the other.

**C++ meter, `cli/loudness.{hpp,cpp}`** in `arcani_cli_core`, namespace `arcani::cli`:

```
struct Biquad { double b0, b1, b2, a1, a2; };
struct KWeighting { Biquad shelf; Biquad highpass; };
KWeighting k_weighting(std::uint32_t fs);                 // throws std::invalid_argument unless fs is a positive multiple of 10
class LoudnessMeter {
 public:
  explicit LoudnessMeter(std::uint32_t fs);               // throws as k_weighting
  void add(std::span<const double> interleaved_stereo);   // any number of frames per call; odd size throws std::invalid_argument
  std::uint64_t frames() const noexcept;
  std::uint64_t block_count() const noexcept;             // J
  double integrated(bool gating = true) const;            // LUFS-I, -inf when no block passes
};
struct LoudnessWindow { bool accepted; std::uint64_t start_frame, body_frames, repeats, window_frames; };
LoudnessWindow loudness_window(const arc_loop_frames& loop, std::uint64_t end_frame, std::uint64_t min_frames) noexcept;
std::uint64_t loudness_window_min_frames(const arcani::test::tables::Row& row, std::uint32_t fs);  // throws TableError unless unit "s", finite, > 0
std::string loudness_window_limit(const arcani::test::tables::Row& row);  // ">= 60 s (row loudness-window-min)", from the row's value text
```

Splitting the same samples into different `add` calls gives the same `integrated` bits. `loudness_window` without a loop: accepted when `end_frame >= min_frames`, start 0, body `end_frame`, repeats 1; with a loop: always accepted, start `O`, body `B`, repeats `max(1, ceil(min_frames / B))`; a rejected window has every number 0.

**Report and CLI.** `cli/report.hpp` gains `struct LoudnessReport { std::uint64_t window_start_frame, window_body_frames, window_repeats, window_frames; double window_lufs_i, whole_lufs_i; };` and `std::optional<LoudnessReport> loudness` after `preview` in `Report`; `report_json` writes it after `preview` (or `spacing`, `loop`, `frames`) and before `determinism_key`, member order as in the spec, `-inf` as `null`. `arcani-render --loudness`: reads row `loudness-window-min` before any output is opened (a table error exits 3 and writes nothing); after compile, a rejected window prints `rejected: parameter=/length_s value=<N / fs> rule=loudness_window_rule limit=>= 60 s (row loudness-window-min)` and exits 1 with nothing written; otherwise renders as before, feeding the whole-render meter every frame and the window meter frames `[O, O + B)`, then renders the remaining `k - 1` passes with a second renderer (`arc_seek` to `O`, `B` frames, repeated), feeding the same window meter. A non-looping window meter is the whole-render meter. `--loudness` twice or with `--preview` is a usage error. Exit codes otherwise unchanged (no loudness assertion in the report).

**Test contracts (the QA agent may split differently; keep the added CI time to about 3 minutes of CPU per platform, and delete each large file as soon as it is read):**

- `tests/cpp/test_loudness.cpp` (guarded by `__has_include("loudness.hpp")` as Stories 3.2 and 3.3 did): every coefficient within `5e-15` of `kLoudnessCoefficients` at both rates and of the printed value at 48 kHz; block and step frames from `kLoudnessBlocks`; Tech 3341 cases 1 to 5 synthesized by the spec's rule at both rates within row `loudness-meter-calibration` (also feed one case in odd chunk sizes and check the same bits); gating off fails cases 3 and 4 and reads case 5 within the row; silence and a signal shorter than one block give `-inf`; `loudness_window` against every `kLoudnessWindowCases` row; `loudness_window_min_frames` and `loudness_window_limit` against the row and doctored Rows; `report_json` with the loudness member (finite and `null`) in its placements, and unchanged without it. Must-fails doctored here: a coefficient off by `1e-13`, a case read 0.2 LU off, a window off by one frame.
- `tests/cpp/test_cli.cpp` additions: `--loudness` twice, and with `--preview`, exit 2 and write nothing; a 10 s fixture with `--loudness` exits 1 with the exact rejected line and writes nothing; the same fixture without `--loudness` renders as before.
- `tests/python/test_loudness_tool.py`: `PROTOTYPE` against the prototype vectors (bits), `kweighting` within `5e-15` of the coefficient vectors; Tech 3341 cases at both rates within the calibration row, gating off fails cases 3 and 4, case 5 the same; the ideal columns hold within the calibration row too; silent and short give `-inf`; `block_energies` count `floor(T / S) - 3`; memmap input equals array input; `check_loudness` on a render of `loudness_constants.assertion_fixture` (its window, float output) scaled in the harness to read exactly the target passes, scaled to `must_fail_lu` above fails, a NaN fails `not finite`, silence fails `silent`; the rows `loudness-window-min` and `rate-cycle-period` hold the same value.
- `tests/python/test_loudness_cli.py`: for every agreement fixture and rate, `arcani-render --loudness` report member equals the window vectors (start, body, repeats, frames) and its `window_lufs_i` agrees with the Python meter on the tap dump output (`--output-only` without a loop; `--window O B`, repeated `k` times, with one) within row `loudness-meter-agreement`, `null` with `-inf`; `whole_lufs_i` for every non-looping fixture equals `window_lufs_i` and for `loudness_constants.whole_fixtures` agrees with the Python meter on the whole render; a harness-made looping recipe with body 25 s (window case `loop, body 25 s`, `k = 3`) agrees at both rates; a harness agreement must-fail (the C++ reading moved by 0.2 LU fails); both rejected fixtures are refused with the vector's parameter, value, rule, and limit and leave no file; the WAV with `--loudness` equals the WAV without, and the report without `--loudness` has no `loudness` member and the same members and bytes as before.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-20): blind hunter (B), edge case hunter (E), verification gap (V).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| B1 | Stray markup lines at the end of this spec | low | Present; left by the orchestrator's spec write | rejected (fix edits the spec); removed as cleanup |
| B2 | Spec status in-review disagrees with sprint-status | false | in-review is the workflow state during review; sprint-status moves at step 5 | rejected |
| B3 | Agreement test renders every fixture of a hash group; CI time well over the 3 min target | medium | test_cli_and_python_meters_agree renders each fixture in the group but compares only group[0] | patch |
| B4 | Guidebook ticks ACs before review and CI; "four loudness rows cleared" is wrong | low | Records text; the orchestrator owns the guidebook | patch (orchestrator) |
| B5 | Calibration uses identical channels only, so channel bugs pass | medium | Every Tech 3341 case is in phase in both channels | patch |
| B6, E4, E5, E6 | Meters accept fs where K-weighting is meaningless (10, 3000) or fail at 192 kHz | low | Real, but every caller passes a row sample-rates value (44100, 48000); the fix adds guards | rejected |
| B7 | check_loudness matches error text | low | Real but unlikely to bite; the fix adds an exception type | rejected |
| B8 | Looping path never checked for an unchanged WAV and report | false | test_body_25_s_is_measured_three_times_and_agrees checks looping WAV and report bytes | rejected |
| B9 | Readings not bit-exact across platforms; Story 4.2 writes the gain from them | medium | Implementation Notes say tan and log10 differ in the last bits; identical bytes on re-measure is a 4.2 criterion | defer to 4.2 |
| B10 | Signal spec puts the loudness member after spacing, the code after preview | low | Direct one-line doc correction | patch |
| B11 | main.cpp exit-code comment omits the CLI window rule | low | Direct comment correction | patch |
| B12 | Design log (zz) lacks C++ readings, the agreement margin, and the sleep unit | low | Evidence for two new rows is missing | patch |
| B13 | Looping window never checks O + B <= N | false | The engine rejects that recipe (validate.cpp, kLoopExceedsRule) | rejected |
| B14 | report.cpp opens a second anonymous namespace | low | Direct merge | patch |
| E1, E2, E3, E9 | NaN or overflowing samples read as silent (null) | low | Inputs are engine output; NaN and inf checks are Story 5.2; the fix adds guards | rejected |
| E7 | NaN target gives a NaN measured value | low | Target comes from a range-checked recipe field; the fix adds a guard | rejected |
| E8 | A row value giving 0 minimum frames | low | Row is 60 s; a doctored-row must-fail exists | rejected |
| V1 | The k - 1 extra window passes are not observed by any test | medium | Pre-verified: removing the loop moves the reading 0.001 LU | patch (frame-count check) |
| V2 | Which frames the first pass takes is not observed | medium | Pre-verified: opening and body read the same today | patch (frame-count check); start-frame proof deferred to 4.4 |

## Design Notes

**Phased handoff.** As in Stories 3.1 to 3.3, on branch `story/4-1-loudness-meter`: (1) the implementation agent writes the signal spec section and vectors, the rows and design log (zz), the research library rows, the `epics.md` amendment, and these notes, and commits; (2) a fresh-context QA agent commits the failing tests; (3) the implementation agent implements, never editing a test expectation to make a test pass. Commits end with the session attribution lines. No push.

The Tech 3341 tolerance for every integrated case is plus or minus 0.1 LU, which gives the calibration and agreement rows. The gating must-fail works because case 3 without gating reads about -24.2 LUFS.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build passes and ctest is green
- `uv run --locked pytest -n auto` -- expected: all pass
