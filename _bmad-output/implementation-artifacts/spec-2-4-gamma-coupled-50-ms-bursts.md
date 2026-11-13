---
title: 'Story 2.4: Gamma coupled, 50 ms bursts'
type: 'feature'
created: '2026-11-13'
status: 'in-progress'
baseline_commit: 'f2224d630b925904724298e4d191da8173bb7b63'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Gamma couples to theta only as a smooth swell. The Focus burst shape (50 ms bursts on the coupling phase, design log 2026-10-28 (o)) does not exist, nothing measures spectral lines, and the research run `burst-edge-taper-2026-10-28` figures are unproven through the engine.

**Approach:** Write signal spec §Bursts (burst gate, worked vectors, margin per tap). Add `bursts` coupling, its compile rules, engine and reference bursts, burst-center timing, and a spectrum tool calibrated on Python-synthesized multi-tone signals first.

Decisions (2026-11-13, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields:** `gamma_pac.coupling` enum gains `bursts`. It takes `coupling_phase_deg` like `smooth_swell`. The three Coupling compile rules extend to `bursts` with value and limit naming `bursts` (for example limit `present with coupling bursts`); every `smooth_swell` message and existing hash stays byte-identical.
- **Burst gate:** the smoothed on-off segments of §theta applied to `u = p_E - C mod 2^64`, with half width `Hb` = 25 ms and edge `Wb` = 10 ms of theta envelope phase at the theta rate (rows `burst-width`, `burst-edge`; `w = (50.0 / 1000.0 / 2) * rate_hz`, then `* 2^64`, nearest, ties to even). Plateau `g = 1.0`, off `g = 0.0`, edges the existing half raised cosine. `Wb < Hb - Wb` over the whole theta-rate range. Depth law as swell: `a = 1.0 - (d * g) * (1.0 - e)`. The carrier always plays; off-burst `a = 1.0` exactly.
- **Gamma envelope runs free** (one clock, as uncoupled and swell). The research script restarted the gamma AM at each burst center; at 60 Hz (a whole multiple of 6 Hz) both give -51.3 dB, at 40 and 45 Hz free running gives -59.0 and -58.7 against the run's -57.2 and -58.1 (build agent recompute, 5 s, 48 kHz). §Bursts and design log (qq) state this.
- **AD-5:** engine burst is one function of (theta envelope phase, plan constants C, Hb, Wb); a compile-time test pins it. Story 2.5's binaural AD-5 behavioral test gains a burst fixture.
- **Margin per tap:** gamma tap 3 sines at most (edge cosine, envelope, carrier), bus adds theta's 2, output adds binaural's 1; §Bursts states each bound.
- **Coupling timing:** `coupling_timing.py` gains `coupling="bursts"`: burst center per theta cycle from the same depth curve. A symmetric pulse's theta-rate cosine fit phase is its center, so the swell fit is reused; calibrated on Python-synthesized bursts with known centers, within row `coupling-timing-calibration`, plus a doctored 3 ms shift that fails.
- **Spectrum tool** (`tests/assertions/spectrum.py`): input one tap, fs, a band; output lines (frequency, level re the strongest line) found by a windowed, zero-padded FFT with peak interpolation. Story 3.1 reuses it unchanged.
- **Fixtures:** theta 450 Hz, 6 Hz, sine, 75 percent; gamma 250 Hz, 100 percent, 0 degrees, at 40, 45, 60 Hz; 5 s. Committed `valid/` `bursts-40hz`, `bursts-45hz`, `bursts-60hz` (hash probe components `gamma-bursts-44100`, `-48000`, scope `engine`), compile-rejected `bursts-no-theta`, `bursts-no-coupling-phase`. Harness builds the timing set (4 shapes x 0, 90, 180, 270 degrees x 25, 100 percent at 40 Hz) in a temp folder. Must-fail carrier-gated rectangular 40 Hz burst is built in the harness. Hash cost about 3 MB float32 per platform per full run, no paid service.
- **Spectrum tolerances (Audio, 2026-11-13):** new threshold rows `spectrum-frequency` 0.05 Hz and `spectrum-level` 0.5 dB. The calibration must find every known line within both; Story 3.1 uses the same rows.
- **Research figure match (Audio, 2026-11-13):** at 60 Hz the worst gamma line at or above 394 Hz equals the run's -51.3 dB within row `spectrum-level`; at 40 and 45 Hz it is no louder than -51.3 dB. The test report prints the run's figure beside each measured one.
- **Spec size (Audio, 2026-11-13):** keep the full spec; no split.
- **Rows:** `pending` cleared on `burst-width`, `burst-edge`; `spectrum-frequency`, `spectrum-level` added. Design log entry (qq).

## Boundaries & Constraints

**Always:** §Bursts merges, with vectors from `tools/signal_spec_vectors.py`, before engine or reference implement it. Tests first, from a fresh-context QA agent, committed failing. Each new tool passes Python-synthesized signals of known answer and fails a doctored one before judging a render. Must-fail signals are made in the harness, never in `engine/`. Thresholds and ranges come from the tables. Every existing check, vector, and pinned hash keeps passing.

**Never:** Rate curves, loops, level fields, gain ramps, the spacing rule or component table (Epic 3), or the carrier rule on side frequencies (deferred, Story 2.3 row 5). Change theta, uncoupled, swell, binaural, or master chain output. Read engine internals in either tool. Fault injection or libm in `engine/`. Push or open the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Burst spectra, 44.1 and 48 kHz | 40, 45, 60 Hz fixtures | worst gamma line at or above 394 Hz per the research figure match decision; gamma tap and output within row `reference-match`; no click over row `click-level` | N/A |
| Must-fail | harness carrier-gated rectangular 40 Hz | about -21 dB at or above 394 Hz; click tool fails | N/A |
| Timing set | shape x phase x depth | every burst center within row `coupling-timing` | N/A |
| AD-5 | no theta; theta depth 0; gamma depth 0 without theta | rejected; rejected; accepted, `a = 1.0` exactly | no plan |
| Earlier fixtures | every Story 2.2, 2.3, 2.5 fixture | bytes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new §Bursts after §Coupling (line 1230; vectors end before §Binaural at 1589). Follow §Coupling: fields, compile order, gate law (ideal and engine), depth law, per sample, seek (nothing new), reference, error bound, timing, vectors. Update §Coupling and §Gamma enum mentions ("Story 2.4 adds `bursts`").
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- vectors: `Hb`, `Wb` per theta rate, gate `g` and `a` at plateau, edge, off, burst fixtures, samples at block boundaries. `test_signal_spec_core.py` pins the table count.
- `recipes/recipe.schema.json` (`gamma_pac` near line 104), `engine/src/recipe/recipe.hpp:53,58` (`GammaCoupling`, `kGammaCouplingEnum`), `field_table.cpp`, `recipe.cpp`.
- `engine/src/validate/validate.cpp` `check_rules` -- coupling rules on `bursts`.
- `engine/src/core/envelope.{hpp,cpp}` -- add `burst(theta_envelope_phase, C, Hb, Wb)` and units helpers beside `swell`; reuse the smoothed on-off segment code and `ratio_to_phase`. Constants `kBurstWidthMs`, `kBurstEdgeMs`.
- `engine/src/plan/plan.{hpp,cpp}:95,127` (`GammaOscillator` gains a coupling kind and `Hb`, `Wb`), `render/renderer.cpp:62-67`.
- `reference/gamma.py` (`COUPLINGS`, burst gate from ideal cosines), `reference/stub_chain.py`; `test_reference_independent.py` must pass.
- `tests/assertions/coupling_timing.py` (`swell_curve`, `timing_errors`, `check`), `clicks.py` (`check`), new `spectrum.py`; `tables.py` loads rows.
- Tests: `tests/cpp/test_coupling.cpp`, `test_validate.cpp`, `test_recipe.cpp`; new `tests/python/test_bursts_reference.py`, `test_spectrum_tool.py`, `test_probe_bursts.py`; extend `test_coupling_timing_tool.py`, `test_binaural_ad5.py`, `test_gamma_reference.py` (`COUPLINGS`), `test_recipe_schema.py`, `test_hash_compare.py`.
- `tests/hashprobe/main.cpp:400,493` (`probe_bursts()` like `probe_swell()`), `ci/hash_expected.json` after the full run.
- Records: `tests/tables/ranges.tsv`, `thresholds.tsv` (new spectrum rows), `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md`, `docs/design-log.md` (qq), `recipes/README.md`, `recipes/fixtures/invalid-expected.json`, `tests/data/recipe_hash_vectors.json`.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, vectors -- §Bursts with worked vectors -- the spec merges first.
- [ ] tests (files above) -- fresh-context QA agent writes failing tests -- tests first.
- [ ] schema, recipe, validator, envelope, plan, renderer, reference, `spectrum.py`, `coupling_timing.py`, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows, design log (qq), README, `ci/hash_expected.json` (after the full run) -- records.
- [ ] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §Bursts, then it defines the 50 ms full-width burst with 10 ms raised-cosine edges inside (30 ms plateau), depth-gated, centered on the coupling phase, with vectors engine and reference each pass, and states the margin per tap by sine evaluations.
- Given Python-synthesized multi-tone signals of known lines and levels, then the spectrum tool finds every line within the spectrum rows, and fails one with a line moved outside them.
- Given the burst fixtures' reference renders, then the worst gamma line at or above 394 Hz meets the research figure match decision, and the must-fail harness burst shows about -21 dB and fails the click test.
- Given burst renders, then each burst center is within row `coupling-timing`, no edge discontinuity exceeds row `click-level`, and gamma tap and output are within row `reference-match`.
- Given the hash probe, then the burst components equal on all four platforms and match their expected entries.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Why reuse the smoothed on-off segments: the burst is exactly that shape with a shorter on share (50 ms instead of half a cycle), so its integer segment tests, edge cosine, and error bound are already specified and proven. The only new numbers are `Hb` and `Wb`.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (burst hash-entry tests only after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main`; `tools/signal_spec_vectors.py --check` -- expected: exit 0.
