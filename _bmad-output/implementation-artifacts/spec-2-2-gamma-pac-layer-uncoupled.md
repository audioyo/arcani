---
title: 'Story 2.2: Gamma PAC layer, uncoupled'
type: 'feature'
created: '2026-11-07'
baseline_commit: '63536b4f89605c9cf950bc742d8f443a88e25a95'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The gamma PAC layer is still the stub `gamma = 0.0`, and the recipe has no gamma field. There is no gamma layer to listen to and no uncoupled control for later coupling comparisons.

**Approach:** Write signal spec §gamma (AM law, uncoupled setting, worked vectors, margin per tap). Add the recipe fields and validator checks. Replace the engine and reference gamma stubs with an uncoupled gamma layer. Add an AM depth tool, calibrated on Python-synthesized signals first.

Decisions (2026-11-07, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields** (`gamma_pac`, optional object, all five members required, placed after `theta_reference` in schema and field table order): `carrier_hz` (row `gamma-carrier`), `rate_hz` (row `gamma-rate`), `am_depth_percent` (row `coupling-depth`), `carrier_wave`, one of `sine`, `triangle`, `softened_square`, and `coupling`, enum `uncoupled` only (Stories 2.3 and 2.4 add `smooth_swell` and `bursts`). Triangle and softened square are schema-valid so compile rejects them by name: parameter `/gamma_pac/carrier_wave`, value the text, rule `non-sine carrier not modeled`, limit `sine`. The carrier rule checks `carrier_hz` against `rate_hz`.
- **AM law:** the theta sine shape at the gamma rate. Two accumulators, phase 0 at n = 0: carrier at `carrier_hz`, envelope at `rate_hz`. `e = (1 + cos 2 pi phi) / 2` (engine: `sine(p + 2^62)`, as §theta), `a = 1 - d * (1 - e)`, `d = am_depth_percent / 100`, `gamma = a * sine(carrier phase)`, both channels. Uncoupled means `d` is constant for the whole render. Unit amplitude: level fields are Epic 4, as for theta.
- **Error margin per tap** (design log (ee)): gamma tap 2 sine evaluations; bus and output add every other layer's count. §gamma states each bound.
- **AM depth tool** (`tests/assertions/am_depth.py`): analytic envelope of a tap, the first and last 0.5 s trimmed; per full gamma cycle the peak and trough. Constant depth means every cycle's peak is within row `reference-match` (as linear full-scale amplitude) of 1 and every trough within it of `1 - d`. No new row. Calibration: harness AM tones at 25 and 100 percent pass; must-fails: depth stepped 1 percent mid-render, and a slow depth drift.
- **Frequency tool:** reused unchanged, with calibration cases added at a 250 Hz carrier and 40 and 60 Hz rates, read within row `frequency-accuracy-calibration`.
- **Fixtures** (`recipes/fixtures/valid/`): `gamma-uncoupled-40hz-25pct.json`, `-40hz-100pct`, `-60hz-25pct`, `-60hz-100pct` (gamma only, 250 Hz sine carrier, 10 s), and `theta-gamma-uncoupled.json` (theta sine, 450 Hz, 6 Hz, 75 percent; gamma 250 Hz, 40 Hz, 100 percent; 10 s) for the bus sum. Invalid: carrier 200 at 60 Hz, triangle, softened square, coupling text not in the enum.
- **Hash check:** probe components `gamma-uncoupled-44100` and `-48000`, scope `engine`, the 5 fixtures in turn. Expected hashes from a green four-platform full run (design log (kk)). Cost: about 16 and 18 MB of float32 per platform per full run; no paid service.
- **Rows:** `pending` cleared on `coupling-depth`. Design log entry (mm).

## Boundaries & Constraints

**Always:** §gamma merges, with vectors from `tools/signal_spec_vectors.py`, before engine or reference implement it. Tests first, from a fresh-context QA agent, committed failing. Every tool has a passing and a must-fail fixture made in the harness. Thresholds and ranges come from the tables. Every existing check, stub chain vector, and pinned hash keeps passing.

**Never:** Coupling, coupling phase, swell, bursts, or the AD-5 rejection (Stories 2.3, 2.4). Change theta, binaural, or master chain behavior. Add level fields, gain ramps, or rate curves. Fault injection or libm in `engine/`. Push or open the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Each gamma fixture, 44.1 and 48 kHz | fixture | gamma tap, bus, output within -100 dBFS of the reference; carrier and rate within row `frequency-accuracy`; depth constant | N/A |
| Range edges | carrier 200/500, rate 30/60, depth 0/100 | accepted (carrier rule permitting) | 199.99, 500.01, 29.99, 60.01, -0.01, 100.01 rejected with the row |
| Carrier rule | 200 Hz at 60 Hz; 240 Hz at 60 Hz | rejected `carrier_rule`, limit `>= 240 Hz (4 x 60 Hz, row carrier-rule)`; accepted | no plan |
| Non-sine carrier | `triangle`, `softened_square` | rejected, rule `non-sine carrier not modeled`, limit `sine` | no plan |
| Unknown text | `carrier_wave: "square"`, `coupling: "swell"` | schema rule `enum` | no plan |
| No `gamma_pac` | every existing fixture | bytes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new §Gamma PAC layer after §Theta reference; the Stub chain `gamma = 0.0` line and its bus bit-equality sentence point to it. `-0.0`: at 100 percent depth the gamma tap can be `-0.0`; state what the bus is there.
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- gamma vectors (increments, envelope, samples at block boundaries, fixtures table), following the §theta pattern; `test_signal_spec_core.py` pins the table count (16 now).
- `recipes/recipe.schema.json`, `engine/src/recipe/field_table.cpp` (gamma rows between theta and binaural), `recipe.hpp` (`GammaPac`, `GammaCarrierWave`, `GammaCoupling`, enum text constants like `kThetaShapeEnum`), `recipe.cpp` (parse, enum check).
- `engine/src/validate/validate.{hpp,cpp}` -- `kRows` gains `gamma-rate`, `gamma-carrier`, `coupling-depth`; `field_value` the three paths; `check_rules` adds the gamma carrier rule then the carrier-wave rule after the theta rules.
- `engine/src/plan/plan.{hpp,cpp}` (`GammaOscillator`: present, two increments, depth), `render/renderer.cpp` (gamma sample replaces `const double gamma = 0.0`; seek sets both gamma phases). Reuse `core::envelope(EnvelopeShape::Sine, ...)` or a sine-only helper in `core/envelope`.
- `reference/stub_chain.py` (gamma tap), new `reference/gamma.py` (from the spec, not from `theta.py` code); `tests/python/test_reference_independent.py` must pass.
- Tests: new `tests/cpp/test_gamma.cpp` (add to `tests/cpp/CMakeLists.txt`, `__has_include` guard as `test_theta.cpp`), `test_validate.cpp`, `test_recipe.cpp`; new `tests/python/test_gamma_reference.py`, `test_am_depth_tool.py`, `test_probe_gamma.py`; `test_frequency_tool.py`, `test_recipe_schema.py`, `test_hash_compare.py` (entry count).
- `tests/hashprobe/main.cpp` (`render_recipe()`; add `probe_gamma()` like `probe_theta()`), `ci/hash_expected.json` (after the full run).
- Records: `tests/tables/ranges.tsv`, `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md` if a row changes, `docs/design-log.md` (mm), `recipes/README.md`, `recipes/fixtures/invalid-expected.json`, `tests/data/recipe_hash_vectors.json` (`tools/recipe_hash.py --write-vectors`).

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- §gamma with worked vectors -- the spec merges first.
- [x] tests (files above) -- QA agent writes failing tests -- tests first.
- [x] schema, field table, recipe, validator, plan, renderer, `reference/gamma.py`, `stub_chain.py`, `tests/assertions/am_depth.py`, hash probe -- implementation.
- [ ] fixtures, hash vectors, rows, design log (mm), README, `ci/hash_expected.json` (after the full run) -- records.
- [x] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §gamma, then it defines the AM law and the uncoupled setting with vectors the engine and the reference each pass, and states the margin per tap by sine evaluations.
- Given each gamma fixture at both rates, then the engine gamma tap and output differ from the reference by less than row `reference-match`, the frequency tool reads carrier and rate within row `frequency-accuracy`, and the AM depth tool finds depth constant at the recipe value.
- Given the harness signals, then the AM depth tool passes the steady tones and fails the stepped and drifting ones.
- Given the hash probe, then the gamma components equal on all four platforms and match their expected entries.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass (the gamma hash-entry tests only after the full run).
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.

## Implementation Notes

- 2026-11-07: §gamma written in `docs/signal-spec.md` with four vector tables (gamma envelope, gamma fixtures, gamma samples, theta and gamma bus) from `tools/signal_spec_vectors.py`; 20 vector tables in all. `tests/cpp/SpecTables.cmake` generates `kGammaEnvelopes`, `kGammaSamples`, `kGammaBus`. The engine gamma envelope never reaches 0 (trough about 2.8e-8), so the engine gamma tap is never `-0.0`; the reference's can be, at 100 percent depth.
- Compile-rejected fixtures (carrier rule 200 Hz at 60 Hz, triangle, softened square) go in `recipes/fixtures/valid/`: that folder is the schema verdict (`recipes/README.md`), and these are schema-valid. The schema faults (`coupling: "swell"`, `carrier_wave: "square"`) go in `invalid/`.
- Red state of the tests-only commit (fresh-context QA agent), on the dev PC: `uv run pytest`: 79 failed, 39 errors, 1599 passed, 2 skipped (baseline 1575 passed). Failures by file: `test_am_depth_tool.py` 40 (no `am_depth.py`), `test_gamma_reference.py` 17 failed plus 39 setup errors (no `reference/gamma.py`, no fixtures), `test_probe_gamma.py` 5 (no probe components), `test_recipe_hash.py` 7 and `test_recipe_schema.py` 7 (no `gamma_pac` in the schema), `test_signal_spec_core.py` 2 (fixture files missing), `test_hash_compare.py` 1 (no gamma expected entries until the four-platform full run). ctest: `arcani_tests` 24 of 214 Catch2 cases fail (gamma parse, field table, validator rows and rules, plan, renderer, fixtures), the build compiles, the other three ctest entries pass.
- QA findings: the frequency tool can misread the carrier on a 100 percent AM tone whose envelope reaches exact zero, so it is pointed only at engine output (trough above 0) and at harness tones with the engine's trough floor; the AM depth tool's sampling grid alone gives about -106.8 dBFS at 44.1 kHz, 60 Hz, 100 percent, against the -100 dBFS row.
- Implementation green on the dev PC: `windows-clang-cl` workflow 4/4 ctest entries pass; `uv run pytest` 1723 passed, 2 skipped, 4 failed, all waiting on the `gamma-uncoupled-*` entries of `ci/hash_expected.json` from a four-platform full run (`test_hash_compare.py::test_real_expected_file_has_every_component_with_its_scope`, `test_probe_determinism.py::test_every_probe_component_has_an_expected_entry`, `test_probe_determinism.py::test_windows_x64_probe_matches_every_expected_entry`, `test_probe_gamma.py::test_expected_entries_name_the_gamma_components`). `check_engine_source.py`, `check_wording.py`, `check_row_coverage.py`, `check_table_log.py --base main`, and `signal_spec_vectors.py --check` exit 0. Engine against reference: worst gamma tap -141.5 dBFS, bus and output -137.0 dBFS; frequency within 3.7e-8 Hz; AM depth worst -106.8 dBFS. Design log (mm).

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-08): blind hunter (BH), edge case hunter (EC), verification gap (VG), all fresh context, on diff 63536b4..2c387ef (`_bmad-output` and the generated `tests/data/signal_spec_vectors.json` left out).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | BH, EC, VG: four pytest cases fail until `ci/hash_expected.json` has the `gamma-uncoupled-*` entries | medium | true; the spec defers the entries to a green four-platform full run (design log (kk)), as Story 2.1 did; every existing pin still matches | CI gate before merge |
| 2 | VG, BH: no render with a binaural ear muted while a gamma layer is present | medium | true; `test_stages.cpp:385` muted-ear test uses only the beat 0 and beat 6 fixtures, and every gamma test uses no mute | patch (test) |
| 3 | BH: no fixture or test renders gamma with a binaural layer, so the 5-sine output bound is unchecked | low | true; every gamma fixture lacks `binaural` | patch (same harness recipe as row 2, reference match on the output) |
| 4 | VG: signal spec "Muted ear" still says the muted channel equals its `theta` tap | low | `docs/signal-spec.md:341`; with `gamma_pac` it equals the bus | patch |
| 5 | BH: "Vectors: gamma envelope" and "gamma samples" prose omit rows the tables hold (phase 1, 2^61, 3 * 2^62; n = 1) | low | prose at `docs/signal-spec.md:959` lists four points only | patch |
| 6 | BH: the gamma AM law cites no research | low | sinusoidal AM at gamma rates is the stimulus of the ASSR studies in research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27` (`digests/verify-r1-1.md`, C1) and FR-3; design log (mm) does not cite it | patch (design log source line) |
| 7 | BH: the schema guard's `/gamma_pac/coupling` exemption is not logged | low | the guard is narrowed for one path and gains a `target` check; (mm) is silent | patch (design log line) |
| 8 | BH: `plan.hpp` header comment line overruns the wrap; three blank lines in `signal_spec_vectors.py` | low | direct formatting | patch |
| 9 | BH: guidebook and `sprint-status.yaml` not updated for the three section commits | low | true; the orchestrator's records step | patch (orchestrator, records commit) |
| 10 | BH: spacing rule between theta and gamma not enforced | low | the spacing rule is Story 3.2 and the component model Story 3.1 | reject (owned by 3.1, 3.2) |
| 11 | BH: compile ignores `coupling`; a future enum value would render as uncoupled | low | the enum has one member today; Story 2.3 adds members and their plan branch | reject |
| 12 | BH: frequency tool has no guard for an envelope reaching exact zero | low | logged in (mm); the engine never reaches zero; the fix adds a branch | reject |
| 13 | BH: AM depth tool assumes unit peak | low | level fields are Epic 4; unreachable today | reject |
| 14 | BH: AM depth tool checks only extremes; shares row `reference-match` | low | shape is held by the sample-by-sample reference match, rate by the frequency tool; the row reuse is logged in (mm) | reject |
| 15 | BH: red-phase `__has_include` and template scaffolding left in tests | low | the same pattern as `test_theta.cpp` (Story 2.1); harmless | reject |
| 16 | BH: `check_rules` hard-codes carrier wave names | low | two literals beside the enum; no caller diverges | reject |
| 17 | BH: `none` backticks inconsistent in the gamma fixtures table | low | cosmetic | reject |
| 18 | EC: theta plus gamma at unit amplitude clips the 24-bit WAV | low | pre-existing (stub chain peaks near 2.0); levels are Epic 4 | reject |
| 19 | EC: AM depth `measured` can be `-inf` | false | the tool feeds no CLI report JSON (same as Story 2.1 row 14) | reject |
| 20 | EC: AM depth tool given invalid `fs` or a rate above Nyquist | low | inputs never given; loud numpy failure | reject |
| 21 | EC: reference renders recipes compile rejects | false | the reference is called only on compile-valid fixtures; out-of-scope inputs are the caller's contract | reject |
| 22 | EC: empty gamma arrays break `SpecTables.cmake` | low | the generator always writes them; `--check` gate | reject |
| 23 | EC: spec cost figure 16 and 18 MB versus 17.6 and 19.2 MB | low | the fix edits this spec's frozen block; the design log has the right figures | reject |

- Review pass 1 patches in f62387c (triage rows 2 to 8). Row 1 waits on the four-platform full run before merge; row 9 is the records commit. Orchestrator check: `windows-clang-cl` workflow 4/4 ctest entries pass; `uv run pytest` 1,725 passed, 2 NDK-only skips, 4 failed (exactly the row 1 hash-entry tests); engine source, wording, row coverage, and table log checks exit 0.
