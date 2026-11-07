---
title: 'Story 2.1: Theta reference envelopes'
type: 'feature'
created: '2026-11-06'
baseline_commit: 'f5c5f2f778ea5fbbd9248e2bc44088d2aed67ffb'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The theta reference is still a stub: an unmodulated sine at the theta carrier. Gamma cannot couple to a phase that is not in the file, and nothing measures carrier, rate, envelope shape, or clicks.

**Approach:** Write signal spec §theta (four envelope shapes, 0 degree points, edge smoothing, AM depth law, worked vectors). Add the recipe fields and validator checks. Replace the engine stub and the reference stub with the real layer. Add a frequency accuracy tool and a click tool, each calibrated on Python-synthesized signals first.

Decisions (2026-11-06, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Recipe fields** (`theta_reference`, all required): `carrier_hz`, `rate_hz` (row `theta-rate`), `am_depth_percent` (row `theta-depth`), `shape`, one of `sine`, `smoothed_on_off`, `sawtooth`, `reverse_saw`, `custom`. The schema accepts `custom` so the validator can reject it as `/theta_reference/shape`, value `custom`, rule `shape not modeled in the signal spec`, limit `sine, smoothed_on_off, sawtooth, reverse_saw`. The carrier rule checks `carrier_hz` against `rate_hz`.
- **Envelope phase:** a second 64-bit accumulator at `rate_hz`, start phase 0, so `phi = phase / 2^64` and `phi = 0` is the shape's 0 degree point at n = 0. Envelope `e(phi)` lies in [0, 1].
- **Depth law:** amplitude `a = 1 - d * (1 - e)`, `d = am_depth_percent / 100`, so 75 percent dips to a quarter of peak (design log 2026-10-29 (s)). `theta = a * sine(carrier phase)`, both channels.
- **Shapes:** sine `e = (1 + cos 2 pi phi) / 2`. Smoothed on-off: on for a share `D` of the cycle centered on `phi = 0`, with raised-cosine edges of length `E` seconds inside the on share. Sawtooth: a linear rise to 1 at `phi = 1`, then a raised-cosine drop of length `E` starting at `phi = 0`. Reverse saw: the mirror image, a raised-cosine rise of length `E` ending at `phi = 0`, then a linear fall. `D` and `E` are fixed constants, not recipe fields. Each gets a fixed range row (the precedent of `burst-width` and `burst-edge`): `theta-on-share` 50 percent and `theta-edge` 10 ms, decided by Audio (2026-11-06) as engineering defaults. No study sets them. 10 ms matches the gamma burst edges, the top of the 5 to 10 ms rise-time convention (design log 2026-10-28 (o)). At the top theta rate (6 Hz), the edge fits inside every segment.
- **Engine math:** cosine as the engine sine at phase plus 2^62. Edge position as a binary64 ratio of integer phase offsets, converted by the spec's clamped conversion rule. No libm. The reference uses the ideal functions in binary64 on the same phases.
- **Stub fixtures keep their bytes:** existing fixtures with a theta reference gain `rate_hz: 6`, `am_depth_percent: 0`, `shape: "sine"`. At depth 0, `a = 1.0` exactly, so every stub chain vector and the engine-scope hash pins stay valid. Recipe hash vectors are regenerated.
- **New fixtures:** `recipes/fixtures/valid/theta-<shape>-<rate>hz.json` for 4 shapes at 1 and 6 Hz: 450 Hz carrier, 75 percent depth, 10 s. A 100 percent depth variant of each hard-edged shape is used for the click test.
- **Frequency accuracy tool** (`tests/assertions/frequency.py`): carrier from a linear fit of the unwrapped analytic phase (weights `|analytic|^2`). Rate from the mean-removed analytic envelope: a 4-term Blackman-Harris windowed DFT peak, refined by golden-section search. The first and last 0.5 s are trimmed. Calibration: synthetic tones and synthetic AM tones of each shape at known frequencies, read within a new row `frequency-accuracy-calibration` (0.001 Hz). A tone moved 0.02 Hz must fail row `frequency-accuracy`.
- **Click tool** (`tests/assertions/clicks.py`): a zero-phase high-pass at row `click-highpass` (4th-order Butterworth, applied forward and backward as an FFT-domain magnitude on a zero-padded signal). The peak is compared with row `click-level`. The first and last 50 ms of a session are excluded: session onset and end belong to gain ramps (S4.4). Calibration: a smooth AM tone passes, and the same tone with a known 0.01 step fails. The must-fail is an unsmoothed sawtooth made in the harness.
- **Hash check:** new probe components `theta-envelopes-44100` and `theta-envelopes-48000`, scope `engine`: the 8 fixtures rendered in turn. Their expected hashes come from a green four-platform full run, per design log (kk), "Updating the engine-scope pins".
- **Rows:** `pending` cleared on `theta-depth`, `envelope-shape`, `click-level`, `click-highpass`. Every table change gets a design log entry (ll).

## Boundaries & Constraints

**Always:** §theta merges, with vectors from `tools/signal_spec_vectors.py`, before the engine or the reference implements it. Tests come first, from a fresh-context QA agent, committed failing. Every tool has a passing and a must-fail fixture made in the harness. Thresholds and ranges are read from the tables. Every existing check keeps passing.

**Never:** Change gamma, binaural, stereo bus, or master chain behavior. Add gain ramps, level fields, or rate curves. Put fault injection in `engine/`. Use libm in `engine/`. Push or open the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Each shape, 1 and 6 Hz, both rates | fixture | theta tap and output within -100 dBFS of the reference, 0 failing samples | N/A |
| Range edges | carrier 100/500, rate 1/6, depth 0/100 | accepted | 99.99, 500.01, 0.99, 6.01, -0.01, 100.01 rejected with row |
| Carrier rule | carrier 100 Hz at rate 6 Hz | accepted (24 Hz needed) | rule `carrier_rule` named on a carrier below 4 x rate |
| Custom shape | `shape: "custom"` | rejected, no plan | named rule and limit |
| Unknown shape | `shape: "square"` | schema rejection | rule from the schema enum |
| Depth 0 | stub fixtures | bytes unchanged | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new §theta after "Stub chain"; edit the stub chain theta paragraph and the "Per sample" theta line to point to §theta.
- `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/cpp/SpecTables.cmake` -- add theta vectors (envelope `e` per shape at edge, plateau, and 0 degree phases; samples at block boundaries; engine bits plus ideal values), following the stub chain pattern.
- `recipes/recipe.schema.json`, `engine/src/recipe/field_table.cpp`, `recipe.hpp` (`ThetaReference`), `recipe.cpp` -- new fields; the field-table test pins the schema.
- `engine/src/validate/validate.cpp` -- `kRows` gains `theta-rate` and `theta-depth`. `field_value` gains the new paths. Call `check_carrier_rule` for theta, and add the shape rule in compile order after ranges.
- `engine/src/plan/plan.hpp` (`ThetaOscillator`), `plan.cpp`, `render/renderer.cpp` (`theta_sample`, seek sets the envelope phase too), new `engine/src/core/envelope.{hpp,cpp}`.
- `reference/stub_chain.py` (theta), new `reference/theta.py`; `tests/python/test_reference_independent.py` must still pass.
- `tests/python/test_reference_match.py` -- pattern for tapdump renders; new `tests/python/test_theta_reference.py`, `test_frequency_tool.py`, `test_click_tool.py`.
- `tests/cpp/test_validate.cpp` (`Values` builder at line 162), `test_stages.cpp`, new `tests/cpp/test_theta.cpp`.
- `tests/hashprobe/main.cpp` (`kStubChainRecipe` gains the depth 0 fields; add the theta component), `ci/hash_expected.json`, `tests/python/test_hash_compare.py` (pins the entry count), `test_probe_*.py`.
- `tests/tables/ranges.tsv`, `thresholds.tsv`, `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md`, `docs/design-log.md` (entry (ll) and table rows), `tools/check_table_log.py --base main` gate.
- Valid fixtures that use `theta_reference` (`stub-chain-1s-beat-6`, `theta-reference-only`, `both-layers*`), `tests/data/recipe_hash_vectors.json`, `recipes/fixtures/invalid-expected.json`.

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON -- §theta with worked vectors -- the spec merges first.
- [x] tests: `tests/cpp/test_theta.cpp`, `test_validate.cpp`, `tests/python/test_theta_reference.py`, `test_frequency_tool.py`, `test_click_tool.py`, probe and hash tests -- QA agent writes failing tests -- tests first.
- [x] schema, field table, recipe, validator, plan, envelope, renderer, reference, `tests/assertions/frequency.py`, `clicks.py`, hash probe -- implementation.
- [ ] fixtures, hash vectors, tables, md, design log (ll), `ci/hash_expected.json` (after the full run) -- records.
- [ ] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given §theta, then it defines each shape, its 0 degree point, the edge smoothing, and the depth law, with vectors the engine and the reference each pass on their own.
- Given each new fixture at 44.1 and 48 kHz, when the frequency tool measures the theta tap, then the carrier and rate are within row `frequency-accuracy`.
- Given the 100 percent depth smoothed on-off, sawtooth, and reverse saw renders, when the click tool checks them, then none exceeds row `click-level`, and the harness's unsmoothed sawtooth fails.
- Given the hash probe, then the theta components equal on all four platforms and match their expected entries.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.

## Implementation Notes

### QA agent, spec and tests-first pass (2026-11-06)

Spec section (task 1, `docs/signal-spec.md` "Theta reference", generator and vectors). Settled inside the frozen intent:

- **Integer lengths:** `H = D * 0x1p63` (exact) rounded, so 2^62; `W = (E * rate_hz) * 0x1p64` rounded, with `E = 10.0 / 1000.0` (one binary64 division) and `E * rate_hz` one rounding. `D` and `E` are held in row units (`50.0` percent, `10.0` ms) by the generator, the engine (`kThetaOnSharePercent`, `kThetaEdgeMs`), and the reference (`ON_SHARE_PERCENT`, `EDGE_MS`); tests check each against the rows.
- **Clamped conversion:** the intent names "the spec's clamped conversion rule"; none existed for a ratio, so §theta defines the ratio-to-phase rule: `P = 0` when `!(r > 0)`, `2^63` when `r >= 1`, else `r * 0x1p63` rounded, ties to even. It has its own vector table (ties, NaN, zeros, 1, above 1, infinity).
- **Segments:** chosen by exact integer comparisons on the envelope phase. Smoothed on-off uses `m = p` or `2^64 - p` (plateau `m <= H - W`, edge `H - W < m < H`, off `m >= H`). Sawtooth: drop edge `p < W`, then `double(p - W) / double(2^64 - W)`. Reverse saw is the sawtooth of `2^64 - p mod 2^64`. Engine cosine is `sine(P + 2^62)`, `rc = (1.0 + c) * 0.5`.
- **Consequences written into the spec:** the engine envelope at the 0 degree point of sine, sawtooth, and reverse saw is about 1.4e-8 below 1 (engine sine at 2^62), inside the bound. At 100 percent depth the theta tap can be `-0.0` (where `a = 0` and the carrier sine is negative) and the bus is `+0.0` there; the Stub chain "no -0.0" sentence now says only stub chain fixtures never produce it. Error bound: theta `1.5 * b + 2^-47` (about -116 dBFS), theta plus binaural `2.5 * b + 2^-46`.
- **Fixture names:** kebab case, `theta-sine-1hz.json`, `theta-smoothed-on-off-6hz.json`, `theta-sawtooth-1hz.json`, `theta-reverse-saw-6hz.json`, and so on. Each is theta only (no `binaural`), 450 Hz, 75 percent, 10 s, exactly the four theta fields. The vector order (each shape in schema order, 1 Hz then 6 Hz) is the probe order.
- **Vectors:** 5 new tables (ratio to phase 14 rows, edge length 4, envelopes 76, fixtures 16, samples 224), 16 tables in all. Stub chain JSON rows gain `theta_rate_hex`, `theta_depth_hex`, `theta_shape` (JSON only; the stub chain tables are unchanged). The generator asserts the depth 0 stub chain theta equals the Story 1.5 sine bit for bit.

Tests (task 2). Contracts are pinned in each file's header:

- `tests/cpp/test_theta.cpp` (added to `tests/cpp/CMakeLists.txt`): `core/envelope.hpp` with `EnvelopeShape`, `kThetaOnSharePercent`, `kThetaEdgeMs`, `ratio_to_phase`, `theta_half_on_units`, `theta_edge_units`, `envelope(shape, phase, W, H)`. Vector bits, a 2^16-phase sweep per shape at 1 and 6 Hz (in [0, 1], within `b / 2 + 2^-48` of `std::cos`), C API renders of all 8 fixtures at both rates (theta tap, output, past end), seek to every vector index, odd-sized calls, and depth 0 equal to the unmodulated sine for every shape. Guarded by `__has_include`, so it is one failing case until the header exists. `SpecTables.cmake` generates `kRatioToPhase`, `kThetaEdges`, `kThetaEnvelopes`, `kThetaSamples`, and the constants.
- `tests/cpp/test_validate.cpp`: the `Values` builder writes all four theta fields (empty text omits one). Range edges from the I/O matrix plus next-double cases, units `percent` for depth. Custom: parameter `/theta_reference/shape`, value `custom`, rule `shape not modeled in the signal spec`, limit `sine, smoothed_on_off, sawtooth, reverse_saw`. Other text: rule `enum`, value the text, limit `sine, smoothed_on_off, sawtooth, reverse_saw, custom`; a number is rule `type`, limit `string`. Order: theta range faults in field order, then every other range fault (binaural included), then the shape rule, then `final.required`. The carrier rule's failure is unreachable through compile (100 >= 4 x 6), so it is checked through `check_carrier_rule` with the theta parameter, as Story 1.3 did for the right carrier.
- `tests/cpp/test_recipe.cpp`: `recipe::ThetaShape` (Sine, SmoothedOnOff, Sawtooth, ReverseSaw, Custom) and the three new `ThetaReference` members, checked through a template so the suite builds before they exist. The hand-written canonical hash is now `fd3e0508...a8a4c` (both-layers.json with `rate_hz` 6, `am_depth_percent` 0, `shape` sine); the same literal is in `test_recipe_hash.py`. The registration map gains `rate_hz` (theta-rate) and `am_depth_percent` (theta-depth), with a `_percent` unit fit.
- `tests/python/test_recipe_schema.py`: the three fields (shape a loudness-relevant string), the `_percent` suffix, the exact enum, and jsonschema rejecting other text with keyword `enum`.
- `tests/python/test_signal_spec_core.py`: table count 16, every §theta table re-derived with Fractions, ideal values cross-checked against `math.cos` and `reference/ideal.py`, must-fails (a mirrored shape, the unmodulated stub), and the stub chain fixture's new fields.
- `tests/python/test_frequency_tool.py`, `test_click_tool.py`: calibration on harness signals, contracts for `assertions.frequency` (`TRIM_S`, `carrier_hz`, `rate_hz`, `check`) and `assertions.clicks` (`EXCLUDE_S`, `highpass`, `peak_dbfs(x, fs, exclude_s)`, `check`). Both report in the Story 1.4 assertion shape, strict below the threshold, and fail `not finite` input. The click high-pass gain is checked by RMS of steady tones, since a sample peak at 8 kHz and 48 kHz lands 1.25 dB low.
- `tests/python/test_theta_reference.py`: the `reference/theta.py` contract (`SHAPES`, `ON_SHARE_PERCENT`, `EDGE_MS`, `half_on_units`, `edge_units`, `envelope`, `render`), `stub_chain.render` taking its theta tap from it, engine against reference per fixture and rate (reference match plus the `envelope-shape` count of samples at or above row `reference-match`), engine bits, frequency on the engine theta tap, and clicks. The 100 percent depth variants are made in the harness from the 75 percent fixtures (`am_depth_percent` set to 100) at both rates, not stored as fixtures.
- `tests/python/test_probe_theta.py` (new), `test_hash_compare.py`: components `theta-envelopes-44100` and `-48000`, scope `engine`, `2 * 8 * 10 * fs` samples each, every fixture segment within row `reference-match` of `reference.theta.render`; the probe's stub chain recipe gains the depth 0 fields.
- `tests/python/test_reference_match.py`: its two inline theta recipes gain `rate_hz` 6, `am_depth_percent` 0, `shape` sine.

Rows the tests read that task 4 must add: range rows `theta-on-share` (50, 50, inclusive, `percent`) and `theta-edge` (10, 10, inclusive, `ms`), threshold row `frequency-accuracy-calibration` (0.001, `Hz`). Clear `pending` on `theta-depth`, `envelope-shape`, `click-level`, `click-highpass`.

Risks for the implementer:

- Every fixture with a `theta_reference` (valid and about 60 invalid ones, plus `both-layers-reformatted.json`, whose layout the regex-style edits miss) needs the three new fields, or the parse error moves; then `tools/recipe_hash.py --write-vectors`.
- The two theta probe components are about 28 and 31 MB of float32 per platform per full run. That is new CI artifact and time cost; worth a cost check before the full run.

Red state at hand-off (ctest: 20 failed of 177 cases in `arcani_tests`; pytest: 99 failed, 47 errors, 1419 passed, 2 skipped, every failure in a new or changed test):

- ctest: `test_theta.cpp` (no `core/envelope.hpp`), the theta cases of `test_validate.cpp` (unknown property `rate_hz` today), the range table (8 ids), the base-recipe and fixture compile cases, and `test_recipe.cpp` (hash literal, fields).
- pytest: `test_frequency_tool.py`, `test_click_tool.py` (no tools, no calibration row), `test_theta_reference.py` (no `reference/theta.py`, no fixtures), `test_probe_theta.py`, `test_signal_spec_core.py` (rows and fixtures missing; every vector check that needs no row passes), `test_recipe_schema.py`, `test_recipe_hash.py`, `test_hash_compare.py` (real file), and the two inline-theta cases of `test_reference_match.py`.

Throwaway proof (a copy of the working tree in the system temp folder, not in the repo): I implemented minimal versions of the schema fields, field table, `ThetaShape` parse with the enum check, validator rows, carrier and shape rules, plan, `core/envelope.{hpp,cpp}`, renderer, `reference/theta.py`, the stub chain change, `assertions/frequency.py` and `clicks.py`, the three rows, the 8 fixtures, the fields on every existing theta fixture, regenerated recipe hash vectors, and the probe components. Results: ctest 100 percent (186 cases). pytest 1568 passed, 5 failed: the four hash entry tests that need the four-platform full run hashes, and `test_check_wording.py::test_repo_passes_by_default`, which scans 0 files in a copy without git. Measured margins on harness signals: carrier and rate errors under 1e-5 Hz (row 0.001 Hz); 100 percent depth smoothed on-off, sawtooth, and reverse saw peak near -112 to -127 dBFS after the high-pass (row -60 dBFS); the unsmoothed sawtooth about -36 dBFS; a 0.01 step about -50 dBFS. Engine theta against the generator ideal: at most 7.7e-8 on the vectors, inside `1.5 * b`.

### Build agent, implementation pass (2026-11-06)

Done (tasks 3 and 4 except the `ci/hash_expected.json` entries; task 5 left to the guidebook pass):

- **Recipe:** schema gains `rate_hz`, `am_depth_percent`, `shape` (enum with `custom`), all four required. Field table rows for the three (range rows `theta-rate`, `theta-depth`; `shape` a loudness-relevant string). `recipe::ThetaShape`, `recipe::kThetaShapeEnum`, and the three `ThetaReference` members; parse checks the enum (rule `enum`, limit the members in schema order).
- **Validator:** `kRows` gains `theta-rate` (1 to 6 Hz) and `theta-depth` (0 to 100 percent); `field_value` maps both paths. New `validate::check_rules()` (carrier rule on the theta reference, then the custom shape rule, with `kShapeNotModeledRule` and `kModeledThetaShapes`), called by compile after `check_ranges()` and before `final.required`.
- **Engine:** `core/envelope.{hpp,cpp}` per the test contract. `core::round_half_even` moved out of the anonymous namespace in `phase.cpp` (declared in `phase.hpp`) so the edge and ratio rules reuse it; behavior unchanged. `plan::ThetaOscillator` now holds `present`, carrier and envelope increments, `depth`, `shape`, `edge_units`, `half_on_units` (the old `amplitude` is gone: a missing theta reference is `present = false` and renders `+0.0`). Renderer keeps an envelope phase, sets it on seek, and evaluates `e`, `a = 1.0 - d * (1.0 - e)`, `a * sine(phase_T)` in the spec order.
- **Reference:** `reference/theta.py` per the test contract (integer segments on uint64 arrays, NumPy cosine, signed phase for the sine shape, one binary64 division per ratio); `stub_chain.py` takes its theta tap from it. README updated.
- **Tools:** `tests/assertions/frequency.py` (8x zero padding, main lobe of 4 bins skipped at DC, golden-section search over one padded bin each side, 40 steps) and `tests/assertions/clicks.py` (power-of-two FFT size with at least 0.1 s of zero padding).
- **Hash probe:** `render_recipe()` shared by the stub chain and the new `probe_theta()`; the eight theta recipes are built from an embedded (shape, rate) table with the fixtures' values. `kStubChainRecipe` gains the depth 0 fields.
- **Records:** 8 theta fixtures; three fields on every existing theta fixture (valid and invalid, `both-layers-reformatted.json` by hand, `missing-theta-reference-carrier-hz.json` keeps only carrier missing); new invalid fixture `theta-shape-not-in-enum.json` (rule `enum`) in `invalid-expected.json`; recipe hash vectors regenerated (`both-layers.json` hashes to the hand-written `fd3e0508...a8a4c`); `recipes/README.md`; rows and design log (ll).
- **Rows deviation:** `theta-on-share`, `theta-edge`, and `frequency-accuracy-calibration` have an empty `spec_row` and a source starting `Design log 2026-11-06 (ll)`, the README rule for rows the md does not list. Adding md rows instead would break `test_tables_loader.py::test_md_parse_sees_both_tables`, which pins the md at 13 locked-range rows; I did not change that pin. The md is unchanged.

Verification on the dev PC: the `windows-clang-cl` workflow preset passes (`arcani_tests` 186 cases, 185 passed, 1 skipped: render speed off the reference machine). `uv run pytest`: 1570 passed, 2 skipped (NDK), 4 failed, all four the expected-entry tests that need the full-run hashes (`test_hash_compare.py::test_real_expected_file_has_every_component_with_its_scope`, `test_probe_determinism.py::test_every_probe_component_has_an_expected_entry` and `::test_windows_x64_probe_matches_every_expected_entry`, `test_probe_theta.py::test_expected_entries_name_the_theta_components`). `check_engine_source.py`, `check_wording.py`, `check_fp_pragmas.py`, `check_row_coverage.py`, `check_table_log.py --base main`: exit 0. Measured: engine theta against the reference at worst -142.2 dBFS; frequency tool on the engine tap within 9.4e-9 Hz (carrier) and 3.1e-6 Hz (rate); 100 percent depth hard-edged shapes -111.8 to -127.0 dBFS after the high-pass.

Local windows-x64 probe hashes, for comparison with the full run (not to be pinned from the dev PC): `theta-envelopes-44100` `a47cf8aabde5c1fd3b4151a2bf0a3a040208327a24529fdff6d95856cca75e04`, `theta-envelopes-48000` `1ee54609a07751a9247cae75389fccf1a9d90cdc242ac9b9ddf89e8cb1fb0a48`. The stub chain probe components still match their pinned entries.

Left: the two `ci/hash_expected.json` entries (four-platform full run, needs Audio's go-ahead to push; about 28 and 31 MB of float32 per platform per run), then the guidebook and `sprint-status.yaml` (task 5).

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-06): blind hunter (BH), edge case hunter (EC), verification gap (VG), all fresh context, on diff f5c5f2f..25b306d (guidebook and `_bmad-output` left out).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | BH, EC, VG: `ci/hash_expected.json` has no `theta-envelopes-*` entries; 4 pytest cases fail and the theta components are pinned only against windows-x64 | medium | true; the spec defers the entries to a green four-platform full run, which needs Audio's go-ahead to push | CI gate before merge |
| 2 | BH: the 100 percent depth `-0.0` theta tap claim has no test | medium | every render test uses 75 percent depth | patch |
| 3 | BH, EC: `W < H - W` is not enforced; out of range the engine wraps and the reference raises | low | compile rejects any rate outside `theta-rate` before the plan is built, so it is unreachable today; a table-driven test guards a future range change | patch (test) |
| 4 | EC: click tool passes a signal shorter than the two exclusion zones (peak -inf) | low | `clicks.py:66` slices an empty interior; a silent pass breaks "silence is not evidence"; direct one-line guard | patch |
| 5 | BH: spec and design log call the half plateau "0.19 of a cycle" | low | `signal-spec.md:464`; the full plateau is 0.38 | patch |
| 6 | BH: `reference/stub_chain.py` docstring breaks mid-sentence | low | lines 27 to 30 | patch |
| 7 | BH: no CI cost estimate for the theta probe components | low | CLAUDE.md asks for one before raising CI usage | patch (design log line) |
| 8 | BH: "on share 50 percent" is ambiguous | false | `signal-spec.md:488` states the edges lie inside the on share, as for bursts | reject |
| 9 | BH: spacing and carrier rules ignore the non-sine shapes' envelope harmonics | low | the per-shape spectral component table is Story 3.1 and the spacing rule Story 3.2 | reject (owned by 3.1, 3.2) |
| 10 | BH: no 8-hour vector for the envelope phase | low | whole-session drift is Story 5.1; the phase is exact `n * inc mod 2^64`, already vectored by the Core section | reject |
| 11 | BH: custom maps to sine in `plan.cpp`, and `parse()` dereferences `shape_named` without a null check | false | parse checks the enum before it fills the recipe, and `check_rules` rejects custom before the plan is built; neither path is reachable | reject |
| 12 | BH: `recipes/README.md` lists `custom` without saying it is rejected | false | `recipes/README.md:24` states the rejection and its rule | reject |
| 13 | EC: `theta_edge_units` given NaN, negative, or 0 rates | false | only compile calls it, after the `theta-rate` check | reject |
| 14 | EC: click result `-inf` reaches report JSON | false | the click tool feeds no CLI report; row 4 removes the -inf path | reject |
| 15 | EC: frequency tool divides by zero on an all-zero signal | low | it raises loudly, which is correct for an input the tests never give it | reject |
| 16 | EC: rate search on an unmodulated envelope returns a spurious rate | low | the tool runs only on modulated fixtures; the fix adds a branch | reject |
| 17 | EC: rate search on a signal under 8 samples raises an unexplained ValueError | low | loud failure on an input never given | reject |
| 18 | VG: the carrier rule call inside `check_rules` is unreachable through compile and untested there | low | every in-range pair passes; the QA notes record this; the fix adds a test seam | reject |

- Review pass 1 patches in 91f75d0 (triage rows 2 to 7). Row 1 waits on the four-platform full run before merge. Orchestrator check: `windows-clang-cl` workflow 4/4 ctest entries pass; `uv run pytest` 1,571 passed, 2 NDK-only skips, 4 failed (exactly the row 1 hash-entry tests); engine source, wording, pragma, row coverage, and table log checks exit 0.
