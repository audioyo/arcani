---
title: 'Story 4.3: True peak'
type: 'feature'
created: '2026-11-25'
status: 'in-progress'
baseline_commit: '390dc6152f2db747cddb8fc172ac3d4ec214b89c'
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
5. **Tech 3341 cases in scope** (Audio, 2026-11-25). Table 1 true-peak cases 15 to 19 only, every one with the printed tolerance +0.2/-0.4 dB. Cases 20 to 23 are out of scope: their printed description names no anti-aliasing filter and no fade, and the filter sets the peak being measured (as 4.1 left out cases 6 to 8). Every calibration signal (cases 15 to 19 and the closed-form sines) gets case 15's printed 10 ms fade-in and fade-out as a raised-cosine ramp, written in the spec. Without it, the abrupt start of a tone measured from zero state overshoots (case 18 reads -5.32 dBTP against -6.0 +0.2), which is the meter's response to the edge, not the tone's peak; with it, every case reads its steady part within 1e-4 dB (planning correction 2026-11-25, see Spec Change Log). The `epics.md` criterion and the research library entry record the narrowed case list.

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
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/tables/thresholds.tsv`, `docs/design-log.md`, `docs/research-library.md`: the True peak section, coefficients and Tech 3341 cases read from the documents, vectors (filter taps, calibration cases, closed-form signals, the must-fail), rows, log entries. Merged before code.
- [x] `tests/python/test_true_peak_tool.py`, `tests/python/test_true_peak_cli.py`, `tests/cpp/test_true_peak.cpp`, updates to `test_cli.cpp`, `test_api.cpp`, `test_store_gain.py`: failing tests from the matrix and ACs, tests-only commit.
- [x] `cli/true_peak.{hpp,cpp}`, `cli/report.{hpp,cpp}`, `cli/main.cpp`, `cli/recipe_write.{hpp,cpp}`, `cli/CMakeLists.txt`, `tests/assertions/true_peak.py`: meters, assertion, report member, store step.
- [x] `recipes/fixtures/valid/stub-chain-1s-beat-6.json`, `ci/hash_expected.json`: the decision 3 gain and re-pins.

**Acceptance Criteria:**
- Given any final render in the suite at 44.1 and 48 kHz, when both meters read it, then their linear true peaks are equal bit for bit and the Python assertion agrees with the report.
- Given the full suite on the dev PC and in CI, when it runs, then everything passes, `tools/check_row_coverage.py` sees `true-peak` in use, and added CI time stays near 3 minutes of CPU per platform.

## Implementation Notes

Everything below follows `docs/signal-spec.md`, True peak (and the Loudness gain, Store step 8 it adds), and its vectors (`tests/data/signal_spec_vectors.json`, keys `true_peak_constants`, `true_peak_filter`, `true_peak_signals`, `true_peak_steps`; C++ `kTruePeak_*`, `kTruePeakFilter`, `kTruePeakSignals`, `kTruePeakSteps` in the generated `spec_tables.hpp`). Vector constants are cross-checked against the rows, never used in their place. Rows `true-peak` (-1 dBTP), `true-peak-meter-over` (0.2 dB), and `true-peak-meter-under` (0.4 dB) are in `tests/tables/thresholds.tsv`, pending on this story; clear `pending` once a test reads each through `row()`.

**Fade on cases 16 to 19 (phase 1 finding, settled as a planning correction; see decision 5 and Spec Change Log).** Decision 5 calls cases 16 to 19 steady tones. Read from zero filter state with an abrupt start, case 18 reads about -5.32 dBTP, 0.68 dB above -6.0 and outside +0.2 dB, while its steady part reads -6.03. So the spec section applies case 15's printed 10 ms raised-cosine fade to every calibration signal (cases 15 to 19 and the closed-form sines); with it every case reads its steady part within 1e-4 dB and passes. The signals' steady parts are the steady tones of decision 5.

**Python, `tests/assertions/true_peak.py`** (numpy, no engine import): `true_peak(x24, fs)` takes integer samples of shape (frames, 2) (or (frames,)), returns `TP` as a float: per channel `np.convolve` of the int64 samples with each phase's int64 integers `n_p` (full mode, so the 11 trailing outputs are included), `max |.|` over phases and channels, then one division by 2^36. `check_true_peak(x24, fs)` returns the assertion dict (name `true_peak`, row, threshold, unit, measured, result, note) with the row read through `assertions.row("true-peak")`. Integers outside [-2^23, 2^23 - 1] or a non-integer dtype raise `ValueError`.

**Command-line tooling, `cli/true_peak.{hpp,cpp}`** in `arcani_cli_core`, namespace `arcani::cli` (no `engine/src` include):

```
class TruePeakMeter {                       // streaming, both channels, zero state
 public:
  void add(std::int32_t left, std::int32_t right);   // one frame of 24-bit integers
  double linear() const;                    // TP after the 11 trailing zeros (calls finish once internally or idempotently)
};
double true_peak_dbtp(double linear);       // 20 * log10(linear); -inf at 0
```

Each channel keeps its last 12 inputs; each `add` computes the 4 phase outputs for that frame; `linear()` also feeds 11 zero frames (without changing the stored state, or once) so the result does not depend on when it is called. Sums in `std::int64_t` then one division by 2^36, or in `double` (exact either way, Meter, Exact).

**Report, `cli/report.{hpp,cpp}`:** `struct TruePeakReport { double linear; double dbtp; };`, `std::optional<TruePeakReport> true_peak` in `Report`, written after `loudness` and before `determinism_key` (`dbtp` null when not finite); `Assertion true_peak_assertion(const arcani::test::tables::Row& row, double linear)`: measured `dbtp`, pass when `dbtp <= row.value()`, silent: measured null, pass, note `silent`.

**`cli/main.cpp`:** in the render loop, where each sample is quantized (`quantize_24`), feed the meter in final mode only; after render speed and the loudness assertions, append `true_peak` in final mode only. `run_store`: read row `true-peak` in step 1; after step 7, render `[0, N)` of the final plan in one pass, quantize, meter, and call `true_peak_step`; on rejection print its line and exit 1 before step 9. Update the header comment (steps 1 to 10), the usage text if needed, and `CLAUDE.md` only if a command changes (it does not).

**`cli/recipe_write.{hpp,cpp}`:**

```
struct TruePeakStep { bool stored; double dbtp; std::string line; };   // line empty when stored
TruePeakStep true_peak_step(const arcani::test::tables::Row& row, double tp_linear, double target_lufs,
                            std::string_view gain_text);
                            // throws TableError unless a thresholds row in dBTP with a finite value
```

The line is exactly `rejected: parameter=/loudness_gain_db value=<gain_text> rule=true_peak limit=<= <row value text> dBTP (row <row id>) target_lufs=<T> true_peak_dbtp=<dbtp>`, with `<T>` and `<dbtp>` as shortest round-trip texts (`std::to_chars`).

**Fixture and pins.** `recipes/fixtures/valid/stub-chain-1s-beat-6.json`: `loudness_gain_db` `-10.00` (hash-excluded; recipe hash and loudness hash unchanged). `ci/hash_expected.json` `stub-chain-final-44100` and `stub-chain-final-48000`: re-pinned from the dev PC probe, confirmed on all four platforms by the next full run, as in 4.2. Tests that name `-1.5` for this fixture (`tests/cpp/test_api.cpp`, `tests/cpp/test_cli.cpp`, `tests/python/test_store_gain.py`) use `kTruePeak_final_fixture_gain` / `true_peak_constants.final_fixture_gain` (the `-10.00` row of the stored gain vectors gives `g`).

**Test contracts (the QA agent may split differently; keep the added CI time to about 3 minutes of CPU per platform; every store works on a temp copy; delete each large file as soon as it is read):**

- `tests/python/test_true_peak_tool.py`: the filter vectors equal the printed coefficients and `n_p * 2^-13`, phase 2 and 3 are the reversals, the phase sums match; every `true_peak_signals` row at both rates: the harness synthesizes the signal (True peak, Calibration, Signal) in binary64, its 24-bit stereo bytes hash to `samples_sha256`, `true_peak` equals `true_peak_hex` bit for bit, the reading is within rows `true-peak-meter-over` and `true-peak-meter-under` of the expected value (Tech 3341 cases 15 to 19 and the closed-form sines), and `check_true_peak` gives the row's assertion result; the hidden overshoot fails `check_true_peak` while the harness sample-peak check passes; the silent signal gives measured null, pass, note `silent`; must-fails doctored in the harness: a meter without oversampling (phase 0 only, or the sample peak) reads the hidden overshoot below the ceiling, a meter that drops the 11 trailing outputs or the first 11 differs from the vector on a signal cut short (no fade-out); a non-integer or out-of-range input raises. The vector constants agree with the three rows.
- `tests/cpp/test_true_peak.cpp` (guarded by `__has_include("true_peak.hpp")`): `TruePeakMeter` on every `kTruePeakSignals` row synthesized in C++ (hash the bytes with the engine-independent SHA-256 the tests already use, or compare integers with the Python harness through a vector), `linear()` equal to `true_peak` bit for bit; frame-by-frame and all-at-once feeding give the same bits; `true_peak_dbtp(0)` is `-inf`; `true_peak_step` against every `kTruePeakSteps` row (stored or not; the line equal except the `true_peak_dbtp=` text, compared after `strtod` within 1e-12 dB, exactly for full scale), with the real `true-peak` row; with a doctored row at -7 dBTP the half-scale case (-6.02 dBTP) is rejected, and a row with unit `dB` throws.
- `tests/cpp/test_cli.cpp`: every final render gains the `true_peak` member and the last assertion `true_peak` (`final_loudness_render` and the store tests' final renders): pass, measured equal to `dbtp`; a measure-mode render's report and WAV bytes are unchanged and have no `true_peak` (compare with a pre-4.3 expectation: no member, no assertion); the 1 s final fixture at both rates passes `true_peak` at about -4 dBTP; the store over the ceiling: since the tables are compiled in, the over-ceiling path is covered by `true_peak_step`; the CLI store tests check that both 4.2 store fixtures still store (exit 0, the same `stored:` line); a silent final render (a no-layer final recipe, made in the harness from `stub-chain-1s-no-layers.json` with its gain stored) gives `linear` 0, `dbtp` null, `true_peak` pass with note `silent`.
- `tests/python/test_true_peak_cli.py`: for every final render in the suite at 44.1 and 48 kHz (the 1 s final fixture, `theta-cycle-sine-stored.json`, and the stored temp copies), the Python meter on the WAV's 24-bit samples equals the report's `true_peak.linear` bit for bit (parse the JSON number with `float`, the shortest round-trip text), and `check_true_peak` agrees with the report's `true_peak` assertion; a WAV doctored in the harness (a stored temp copy whose gain is raised until the true peak is above -1 dBTP, or the samples scaled in the harness) fails `check_true_peak`.
- `tests/python/test_store_gain.py`, `tests/cpp/test_api.cpp`: the 1 s final fixture's gain is `-10.00`, its applied gain is the `-10.00` row's `g`; the reference match in final mode still passes.
- `tools/check_row_coverage.py` sees `true-peak`, `true-peak-meter-over`, and `true-peak-meter-under` in use.

## Spec Change Log

- 2026-11-25, phase 1 (03297b2): decision 5 said cases 16 to 19 are steady tones with no fade. Measured from zero state, an abrupt tone start overshoots past the printed +0.2 dB (case 18 reads -5.32 dBTP). Amended: every calibration signal gets case 15's printed 10 ms raised-cosine fade. Audio's call (cases 20 to 23 out of scope) is unchanged; the fade wording was a planning detail. KEEP: the exact-integer meter and the vector SHA-256 pins of the 24-bit signal bytes.

## Design Notes

**Phased handoff,** as in 4.1 and 4.2, on branch `story/4-3-true-peak`: the implementation agent writes the spec section, vectors, rows, and design log and commits; a fresh-context QA agent commits the failing tests; the implementation agent implements without editing a test expectation. No push until review.

**Known-peak signals.** A sine at fs/4 starting at 45 degrees has samples at +-A/sqrt(2), and the 4x grid lands on its crests, so its true peak is A while its sample peak is 3.01 dB lower. That is the must-fail, and with other levels a calibration signal.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl`: expected build passes and ctest is green.
- `uv run --locked pytest -n auto`: expected all pass.
- `git status --porcelain -- recipes` after the suite: expected only the decision 3 fixture edit, committed.
