---
title: 'Story 2.5: Binaural layer'
type: 'feature'
created: '2026-11-11'
baseline_commit: '25e283a6145fae5fed1b8e22968324235f78e357'
status: 'in-progress'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The binaural layer is still the Story 1.2 stub: a fixed beat rate, no rate curve, no waveform rule, no reference module of its own, and no test that gamma ignores it (AD-5). Sleep needs a beat rate that cycles over 0 to 3 Hz every 60 s (design log (n)), and Story 2.6 needs one rate-curve law to reuse.

**Approach:** Write signal spec §binaural and §rate-curve (law, closed-form phase integral, Sleep-style cycle and start phase, vectors). Add an optional sinusoidal beat-rate cycle and an optional `waveform` field, worst-case range checks, engine and reference rate curve, a phase-tracking mode in the frequency tool and a band mode in the isolation measurement (each calibrated on Python-synthesized signals first), and the AD-5 sweep test.

Decisions (2026-11-11, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields:** `binaural.waveform` optional, enum `sine`, `triangle` (absent means sine). Compile rejects non-sine: parameter `/binaural/waveform`, value the text, rule `non-sine binaural not modeled`, limit `sine` (design log (o)). New optional `binaural.beat_rate_cycle` {`swing_hz`, `period_s`, `start_phase_deg`}, all required inside it. `beat_rate_hz` stays required and becomes the cycle's center. Existing fixtures and hashes stay unchanged.
- **Rate-curve law (one law, reused by Story 2.6 unchanged):** `rate(t) = r + s * sin(2 * pi * t / P + phi0)`, `r` the center, `s` the swing, `P` the period, `phi0` the start phase (0 degrees = at the center, rising). v0.1 has only this sinusoidal cycle; no piecewise-linear curves (no v0.1 recipe needs one since design log (n)).
- **Closed-form phase integral, engine:** the right ear phase is `phase_C[n] + U[n] mod 2^64`. `phase_C[n] = n * inc(f_L + r)` (constant increment), cycle phase `p_P[n] = P0 + n * inc(1 / P)` (`P0` by the coupling phase rule on `start_phase_deg`). `U[n]` is `K * (cos(phi0) - cos(cycle phase))` cycles in phase units, `K = s * P / (2 * pi)` once per plan, the cosines by the engine sine at `+2^62`. The cycles-to-units conversion (exact reduction mod 1, times 2^64, nearest, ties to even, mod 2^64, clamp-safe) is fixed in §rate-curve. Every value is a pure function of `n`, so seek and block-size invariance need nothing new. Without a cycle the right ear is the stub's bits exactly.
- **Range checks, worst case:** `r - s` and `r + s` against row `beat-rate`; `f_L + r + s` against `binaural-carrier-right`; `swing_hz >= 0` (rule `range.min`, limit `>= 0 Hz`); new rows `rate-cycle-period` and `rate-cycle-start-phase` (0 to 360 inclusive, 360 the same as 0). Order: after the existing binaural range checks, before the waveform rule.
- **Isolation band mode** (`tests/cpp/isolation.hpp`): for a rate-curve fixture, the muted channel's energy over the band the active carrier spans (plus a guard of 2 bins) against the active channel's. Calibrated on Python-synthesized swept tones with known leakage (`tools/isolation_calibration.py`), with a doctored must-fail.
- **Frequency tool phase mode** (`tests/assertions/frequency.py`): unwrapped analytic phase of a tap minus the closed-form integral; instantaneous rate error from its derivative, ends trimmed; fails if phase steps. Calibrated on Python-synthesized swept tones with a known schedule and a must-fail one off by 0.02 Hz.
- **AD-5 fixtures:** theta 450 Hz, 6 Hz, 75 percent; gamma 250 Hz, 40 Hz, smooth swell 0 degrees, 100 percent; binaural 100 Hz left. Hand-checked spacing: binaural at most 110 Hz, gamma side frequencies from 204 Hz. Sweep: beat 0, 4, 10 Hz fixed, cycle start phases 0, 90, 270 degrees, and no binaural. The gamma tap is byte-identical across all, and the coupling timing tool's peak times are equal.
- **Fixtures:** committed `binaural-beat-0`, `-6`, `-29` (left 400 Hz, 5 s), `binaural-cycle-sleep` (100 Hz left, center 1.5, swing 1.5, 60 s period, start phase 270 degrees, 120 s), compile-rejected `binaural-waveform-triangle`, `binaural-cycle-below-0`, `binaural-cycle-above-30`; invalid: cycle missing `period_s`. Hash probe components `binaural-cycle-44100` and `-48000` (5 s from frame 0 plus 5 s after a seek to 55 s, scope `engine`).
- **Margin per tap:** fixed beat 1 sine; cycle right ear 2 sines (cycle cosine, carrier); output adds the bus. §binaural states each bound.
- **Sleep start phase (Audio, 2026-11-11):** the cycle starts at 0 Hz, rising, so a session opens with no beat and it eases in: `start_phase_deg` 270 in the sine convention above. Engineering default; no study sets it (Lee et al. 2024 does not say). §rate-curve names it.
- **Cycle period (Audio, 2026-11-11):** row `rate-cycle-period` is locked to exactly 60 s (min 60, max 60, inclusive), the only value with a source (Lee et al. 2024, design log (n)), until a study supports others. A 59.99 s or 60.01 s period is rejected with the row.
- **Rows and log:** design log entry (oo); `binaural-isolation-*` and `frequency-accuracy` unchanged.

## Boundaries & Constraints

**Always:** §binaural and §rate-curve merge, with vectors from `tools/signal_spec_vectors.py`, before engine or reference implement them. Tests first, from a fresh-context QA agent, committed failing. Each new tool mode passes calibration before it judges a render. Must-fail renders are made in the harness, never in `engine/`. Thresholds and ranges come from the tables. Every existing vector, fixture byte, and pinned hash keeps passing. The binaural pair joins after every other stage and nothing reads it.

**Never:** Couple gamma or anything else to the binaural layer. Rate curves on theta or gamma (Story 2.6), loops (2.7), bursts (2.4), spacing checks (Epic 3), level fields or ramps (Epic 4), the Sleep starter recipe. Non-sine binaural synthesis. Piecewise-linear curves. Fault injection or libm in `engine/`. Push or open the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fixed beats | 0, 6, 29 Hz, 44.1 and 48 kHz | isolation >= 90 dB at join, >= 60 dB at master; each ear and output within `reference-match`; carriers within `frequency-accuracy` | N/A |
| Sleep cycle | 0 to 3 Hz every 60 s, 120 s | same isolation and match; instantaneous rate within `frequency-accuracy` of the schedule, no phase step | N/A |
| Worst case | `r - s` = -0.01; `r + s` = 30; `f_L + r + s` reaches 1030 | rejected, row named, parameter the cycle field | no plan |
| Waveform | absent; `sine`; `triangle` | accepted; accepted (same bits); rejected `non-sine binaural not modeled` | no plan |
| Start phase | 0, 360, -0.01, 360.01 | 0 and 360 render identically; last two rejected with the row | no plan |
| Seek | cycle fixture, seek to 55 s | byte-identical to the continuous render | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- replace "Binaural oscillators" in §Stub chain (line 345) with a pointer; new §Binaural layer and §Rate curve after §Coupling (line 1230 onward), following the §coupling pattern: fields, compile order, law (ideal and engine), per sample, seek, reference, error bound, vectors. Update the header story list (line 5).
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- vectors: `P0`, `K`, `inc(1/P)`, `U[n]` at chosen `n`, right-ear samples at block boundaries; `test_signal_spec_core.py` pins the table count (24 now).
- `recipes/recipe.schema.json` (`binaural` at line 145), `engine/src/recipe/field_table.cpp` (line 50), `recipe.hpp` (`Binaural`, line 69), `recipe.cpp`.
- `engine/src/validate/validate.{hpp,cpp}` -- `kRows` (line 31) gains the two rows; worst-case checks beside the derived right-carrier check (line 188); waveform rule in `check_rules`.
- `engine/src/plan/plan.{hpp,cpp}` -- `BinauralEars` (line 100) gains the cycle constants; muting still zeroes `inc` and amplitude. `engine/src/render/renderer.cpp` lines 36 and 76: right ear adds `U[n]`; seek sets the cycle phase.
- `engine/src/core/` -- the cycles-to-units conversion beside the coupling phase rule; reuse `core::sine`.
- New `reference/binaural.py`; `reference/stub_chain.py` (lines 85-99) calls it; `tests/python/test_reference_independent.py` must pass.
- `tests/cpp/isolation.hpp`, `test_isolation.cpp`, `tools/isolation_calibration.py`, `tests/data/isolation_calibration.json` -- band mode.
- `tests/assertions/frequency.py` -- phase mode; `coupling_timing.py` reused unchanged for AD-5.
- Tests: new `tests/cpp/test_binaural.cpp` (add to `tests/cpp/CMakeLists.txt`), `test_validate.cpp`, `test_recipe.cpp`, `test_seek.cpp`; new `tests/python/test_binaural_reference.py`, `test_binaural_ad5.py`, `test_probe_binaural.py`; update `test_frequency_tool.py`, `test_isolation_calibration.py`, `test_recipe_schema.py`, `test_hash_compare.py`.
- `tests/hashprobe/main.cpp` (`probe_binaural_cycle()` like `probe_swell()`), `ci/hash_expected.json` after the full run; `tests/tapdump/` renders harness temp recipes.
- Records: `tests/tables/ranges.tsv`, `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md`, `docs/design-log.md` (oo), `recipes/README.md`, `recipes/fixtures/invalid-expected.json`, `tests/data/recipe_hash_vectors.json` (`tools/recipe_hash.py --write-vectors`).

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- §binaural and §rate-curve with worked vectors -- the spec merges first.
- [x] tests (files above) -- fresh-context QA agent writes failing tests -- tests first.
- [x] schema, field table, recipe, validator, plan, renderer, core conversion, `reference/binaural.py`, `stub_chain.py`, isolation band mode, frequency phase mode, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows, design log (oo), README, `ci/hash_expected.json` (after the full run) -- records.
- [ ] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §binaural and §rate-curve, then they define right carrier = left carrier + beat(t), the rate-curve law and its closed-form phase integral, and the Sleep cycle with its start phase, with vectors the engine and reference each pass.
- Given the isolation band mode and the frequency phase mode, then each reads its Python-synthesized calibration signals within tolerance and fails its doctored one.
- Given the AD-5 sweep, then the gamma tap is byte-identical and every swell peak time is equal across all binaural settings.
- Given the hash probe, then the binaural cycle components equal on all four platforms and match their expected entries.

## Design Notes

Why center plus swing, not min and max: `beat_rate_hz` stays required, so every existing recipe, fixture, and hash is untouched, and a cycle is an optional addition. The same shape fits Story 2.6 (`rate_hz` plus an optional cycle on theta and gamma).

Why a closed form, not a per-sample sum of increments: each sample's phase is a pure function of `n` from integer accumulators and one engine cosine, so seek is O(1), block size cannot matter, and the reference computes the same integral independently.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (binaural hash-entry tests only after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.

## Implementation Notes

- 2026-11-12: Signal spec Binaural layer and Rate curve sections with five vector tables (cycles to units, rate cycle, rate curve, binaural fixtures, binaural samples; 29 in all) from `tools/signal_spec_vectors.py`, commit efce4f1 (wording follow-up 706a1b2). `tests/cpp/SpecTables.cmake` generates `kInvTwoPi`, `kSeekSeconds`, `kCyclesToUnits`, `kRateCycles`, `kBinauralSamples`. Build agent choices: `K = (s * P) * 0x1.45f306dc9c883p-3` (the binary64 nearest 1 / (2 pi)); the right carrier worst case is `(f_L + r) + s`, two roundings; field order `carrier_left_hz`, `beat_rate_hz`, `beat_rate_cycle`, `waveform`; a muted right ear drops the cycle so it outputs `+0.0`.
- Deviation from the frozen text: the design log entry is (pp), not (oo). Entry (oo) was already taken on 2026-11-11 by the Story 2.3 wall-time budget change (commit b072d0c), after this spec was written; reusing the letter would make two entries with one id.
- Open question, not in the frozen text (design log (pp), `deferred-work.md`): the cycle right ear's engine error is the cycle cosine's error times `2 pi K`. It is within row `reference-match` for every committed fixture (Sleep: bound -105.7 dBFS, measured -105.9), but compile accepts swings whose `K` exceeds about 13.9 (start phases other than 90 and 270 degrees) or 27.9 (90 and 270), where the right ear would no longer match the ideal reference within -100 dBFS. Left to Audio.
- Red state of the tests-only commit 19e5dad (fresh-context QA agent): Catch2 42 of 286 cases fail, the build compiles; `uv run pytest` 78 failed, 8 errors, about 2,166 passed, 2 skipped (by file: `test_binaural_reference.py` 28, `test_frequency_tool.py` 25, `test_recipe_hash.py` 6, `test_probe_binaural.py` 6, `test_recipe_schema.py` 5, `test_isolation_calibration.py` 5, `test_binaural_ad5.py` 2 plus 8 errors, `test_hash_compare.py` 1).
- Frequency phase mode (QA finding 1): the raw per-sample derivative of the untapered FFT analytic phase reads about 0.19 Hz on a perfect 10 s swept tone, so the tool tapers each end by a raised cosine over the first half of its 0.5 s trim before the transform. Calibration tones then read within 8.8e-5 Hz (row 0.001 Hz) and a 0.02 Hz schedule offset reads 0.0201 Hz. The contract's per-sample definition (`rate_error_hz = np.diff(residual) * fs`) is kept.
- Test edits during implementation (QA defects, none weakens a threshold): `test_binaural.cpp` "v and v + 1 are the same point" used 0.3, -0.3, 0.7, for which `v + 1.0` is not exact in binary64; now 0.375, -0.375, 0.75. `test_binaural.cpp` expected at least 12 sample vectors per fixed-beat fixture; the generator writes 11 (start, block boundaries, 1000, the end, two past it); now `>= 11`. `test_frequency_tool.py::own_residual` now applies the documented end taper. `test_recipe_schema.py`: a numeric `waveform` gives jsonschema `type` and `enum` errors (as `gamma_pac.carrier_wave` does); the test now requires `type` among them. `test_tables_loader.py`: the md Locked ranges table has 14 rows with the new "Binaural beat rate cycle" row. The band calibration setup id follows the contract: `sweep-403-406hz-44100-right-active` (400 to 406 Hz).
- Implementation green on the dev PC: `windows-clang-cl` workflow 4/4 ctest entries pass (Catch2 286 of 286 cases); `uv run pytest` 2,256 passed, 2 skipped, 4 failed, all waiting on the `binaural-cycle-*` entries of `ci/hash_expected.json` from a four-platform full run (`test_hash_compare.py::test_real_expected_file_has_every_component_with_its_scope`, `test_probe_binaural.py::test_expected_entries_name_the_binaural_components`, `test_probe_determinism.py::test_every_probe_component_has_an_expected_entry` and `::test_windows_x64_probe_matches_every_expected_entry`). `check_engine_source.py`, `check_wording.py`, `check_row_coverage.py`, `check_table_log.py --base main`, `signal_spec_vectors.py --check`, and `isolation_calibration.py --check` exit 0. Engine against reference on the four binaural fixtures at both rates: fixed beats -145.0 dBFS worst, Sleep cycle -105.9 dBFS; Sleep right ear instantaneous rate within 8.4e-5 Hz of the schedule; fixed carriers within 1.8e-12 Hz. Design log (pp).

## Spec Change Log

## Review Triage Log
