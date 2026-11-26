---
title: 'Story 4.4: Gain ramps'
type: 'feature'
created: '2026-11-26'
status: 'in-progress'
baseline_commit: '9ff038fd358f3196bd4d4d433561da13c05f0a61'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Every layer plays at unit level from the first sample to the last. No recipe can ramp a layer in, fade the session out, or stop a looping session without a hard cut at the cap. The loudness window cannot exclude ramps because none exist, and the coupled-gamma zero-theta rejection (AD-5) has no level to test.

**Approach:** Add optional gain schedules to each layer (theta reference, gamma PAC, binaural) and to the master. Each schedule is an initial gain plus non-overlapping ramps. Every ramp follows one law from a new `## Gain ramps` section of `docs/signal-spec.md`, is evaluated per sample, is aligned by the seconds-to-samples rule, and holds its end value exactly after its last sample. Add a tap before and a tap after each layer's gain. Narrow the loudness window to the steady part. Add a ramp tool calibrated on Python signals, and match the Python reference.

Decisions (planning, 2026-11-26; Audio can overrule any of them at approval):

1. **Recipe shape.** Each layer object and a new top-level `master` gets an optional `gain`: `{ "initial": g0, "ramps": [ { "start_s", "duration_s", "to" } ] }`. Gains are linear, 0 (silence) to 1 (full): a new `ranges.tsv` row `layer-gain`, so a ramp never boosts, as `loudness-gain` only turns down. Ramps are sorted and must not overlap (rule `gain.overlap`). Each ramp lies inside the session (rule `gain.outside_session`). Each schedule has at most 8 ramps (row `gain-ramp-count`), so the plan stays a fixed size. An absent `gain` means unity throughout, so every existing fixture keeps its recipe hash, loudness hash, and probe pins. The new fields are audio- and loudness-relevant.
2. **Minimum duration.** `duration_s < 0.010` is rejected (rule `gain.ramp_min`, limit `>= 10 ms (row gain-ramp-min)`). Exactly 10 ms passes. Modulation envelopes, burst edges, and the limiter are exempt.
3. **Looping recipes.** Each ramp ends at or before the opening end O, or starts at or after O + B (rule `gain.loop_body`). That keeps the first body pass, which the loudness window repeats, ramp-free. An end fade is a master ramp that ends at the cap.
4. **Loudness window.** A looping recipe keeps [O, O + kB). For a non-looping recipe, the window is the longest stretch with no layer or master ramp active, ties to the earliest. The `loudness-window-min` rule still applies. The CLI `--loudness` and `--store-gain` paths share it.
5. **Taps.** The existing `theta_reference` and `gamma_pac` taps become the before-gain taps, so every coupling, frequency, and phase test reads them unchanged. New after-gain taps for theta, gamma, and binaural, plus a before-gain binaural tap, are added to `arc_taps`. The stereo bus sums the after-gain layers. Master = join x loudness gain x master ramp gain. The limiter stays an identity stub (4.5).
6. **Coupled gamma at zero theta (deferred from 2.3).** Reject coupled gamma (rule `coupling.theta_silent`) at any sample where the gamma gain and depth are non-zero while the theta gain is exactly zero. The check is in closed form over the schedules, and master gain does not count. Must-fail fixture: a theta fade to silence that ends before a coupled gamma fade.
7. **Exact zeros.** At and after a ramp's end sample the gain is its `to` value exactly. A fade to silence therefore multiplies by 0, and the 24-bit output is exact zeros from then on.
8. **Ramp law** (Audio, 2026-11-26). Every layer and master ramp uses a raised cosine in linear gain: for samples [n0, n1) from a to b, `g[n] = a + (b - a) * (1 - cos(pi (n - n0) / (n1 - n0))) / 2`, with the engine cosine. This is the shape of the burst and theta edges, and it is flat at both ends. It is an engineering default and is logged as one.
9. **End fade at the cap** (Audio, 2026-11-26). Focus and Learn fade to silence over the last 5 min before their max run time. That is the Epic 6 starter value, logged in the design log, and the 4.4 looping end-fade fixture uses it. It mirrors the 5 min ramp-in and Sleep's 5 min fade. It is an engineering default.
10. **Spec size** (Audio, 2026-11-26): kept whole, deferred items included.
11. **Out of scope, left deferred:** the denormal-guard fixture, the short-session spacing note, and the 4.3 store refusal hook.

## Boundaries & Constraints

**Always:** Formulas are written first in `docs/signal-spec.md` with worked vectors, merged before engine or reference code. Engine-owned transcendentals only. `-ffp-contract=off`. The engine reads no files. Every new row gets a design-log line, and `gain-ramp-min` is cleared from pending. Every check has a passing fixture and a must-fail fixture doctored in the harness. Tests go first as a tests-only commit by a fresh-context QA agent. The binaural gain is one per-layer scalar applied equally to both ears, with no width or spatial stage. Keep added CI time near 3 min of CPU per platform.

**Never:** No limiter behavior (4.5), no starter recipes (Epic 6), no per-ear or pan gain, no gain above 1, no change to the bytes of renders without `gain`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ramp exactly 10 ms | `duration_s` 0.010 | compiles | N/A |
| Ramp 9.9 ms | `duration_s` 0.0099 | rejected, `gain.ramp_min` | parameter, value, rule, limit |
| Overlap / outside / count / gain > 1 | doctored fixtures | rejected by the named rule | parameter, value, rule, limit |
| Looping ramp inside first body | ramp crosses (O, O + B) | rejected, `gain.loop_body` | as above |
| Theta silent under coupled gamma | theta fade ends before gamma fade | rejected, `coupling.theta_silent` | as above |
| Fade to silence | 5 min master fade | exact zeros from its end sample | N/A |
| Unity schedule | `gain` with initial 1, no ramps | before- and after-gain taps bit-identical; output equals the no-`gain` render | N/A |
| Loudness, non-looping | 10 min layer ramp from silence, then steady | window = steady stretch, within 1 LU; whole render never above target + 1 LU | N/A |
| Loudness, looping, superseded window | gain measured over ramp-in plus one body (harness) | body plays above target, loudness fails | N/A |
| Window starts at O | looping fixture whose ramp-in makes the opening differ from the body | reading over [O, O + B) differs from [0, B) | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md`: new `## Gain ramps` before `## Loudness` (4548). Edit `Coupling` :1251 (zero-level rule), `Loop, End at the cap` :2810, `Loudness, Window` :4661-4671, and `Core, Seconds-to-samples rule` :44 (reuse, do not change).
- `recipes/recipe.schema.json`: `gain` on `theta_reference` :74, `gamma_pac` :128, `binaural` :193, and new top-level `master`. Every object keeps `additionalProperties: false`. `recipes/README.md` :41 and :126 text.
- `engine/src/recipe/recipe.{hpp,cpp}` (parse near :433) and `engine/src/validate/field_table.cpp` :25 (row mapping).
- `engine/src/validate/validate.cpp`: `kRows` :31-82 (new rows), `check_row` :200 (error shape), `check_loop` :276 (`gain.loop_body`), `check_rules` :406 (overlap, outside, ramp_min, `coupling.theta_silent`).
- `engine/src/plan/plan.{hpp,cpp}`: a fixed-size `GainSchedule` per layer plus master, with ramp sample bounds from `core::seconds_to_samples` (`engine/src/core/phase.cpp:42`). `master_gain` :171 stays the loudness gain.
- `engine/src/render/renderer.{hpp,cpp}` :50-136: apply the layer gains after each layer sample, before the bus (:110) and join (:112), and the master ramp at :113. `Taps` struct (`renderer.hpp:28`).
- `engine/include/arcani/arcani.h` :84-93 `arc_taps`, `engine/src/api/api.cpp` :343-358, `tests/tapdump/main.cpp` :201-218: the new taps.
- `reference/stub_chain.py` :114-169 (`KEYS` :66) and `reference/ideal.py:49`: the same law in binary64 with ideal cos.
- `cli/loudness.{hpp,cpp}` :81-101, 161-203 `loudness_window`: non-looping steady stretch. Callers `cli/main.cpp` :375-413 (store) and :579-594 (`--loudness`).
- `tests/assertions/clicks.py` (`check` :74; the docstring at :8 names 4.4) and `tests/python/test_loop_render.py` :204-215 (window builder pattern): click windows around every ramp edge.
- New `tests/assertions/gain_ramps.py`: the ramp tool, which estimates gain as after-gain tap over before-gain tap (master: output over join x loudness gain) and the shortest completed change.
- `tests/tables/thresholds.tsv:31` `gain-ramp-min` (pending 4-4). `ranges.tsv`: new `layer-gain`, `gain-ramp-count`.
- `ci/hash_expected.json`: new probe components for the ramp fixtures at 44.1 and 48 kHz. Existing pins must not move.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/tables/*.tsv`, `docs/design-log.md`: Gain ramps section, vectors, rows, and log entries. Merged before code.
- [ ] Failing tests (QA agent, tests-only commit): `tests/cpp/test_gain_ramps.cpp`, `tests/python/test_gain_ramp_tool.py`, `test_gain_ramps_reference.py`, `test_gain_ramps_loudness.py`, invalid fixtures plus `invalid-expected.json`, and taps in `test_api.cpp`/`test_stages.cpp`.
- [ ] Schema, parser, validator, plan, renderer, API taps, tapdump, Python reference, CLI window.
- [ ] Fixtures `recipes/fixtures/valid/gain-*.json`: 5 min ramp-in (looping, opening differs from body), 10 min layer ramp from silence (non-looping), 5 min master fade to silence, and a looping end fade at the cap. Probe pins.

**Acceptance Criteria:**
- Given every ramp fixture at 44.1 and 48 kHz, when the ramp tool and click tool check every layer tap and the master output, then no gain change completes in under 10 ms, no ramp edge exceeds -60 dBFS after the 8 kHz high-pass, and a harness-doctored 5 ms layer fade fails.
- Given ramp renders, when compared with the Python reference, then taps and output differ by less than -100 dBFS.
- Given the full suite on the dev PC and in CI, when it runs, then everything passes, existing pins are unchanged, and `tools/check_row_coverage.py` sees every new row in use.

## Implementation Notes

Everything below follows `docs/signal-spec.md`, Gain ramps (and the edits it makes to Stub chain, Output and taps; Coupling, Compile order; Loop, Compile order rule 8 and End at the cap; Loudness, Window, Report, and Agreement set; Loudness gain, Store step 4), and its vectors (`tests/data/signal_spec_vectors.json`, keys `gain_constants`, `gain_law`, `gain_fixture_ramps`, `gain_windows`, `gain_compile_cases`; C++ `kGain_*`, `kGainLaw`, `kGainFixtureRamps`, `kGainWindows`, `kGainCompileCases` in the generated `spec_tables.hpp`). Vector constants are cross-checked against the rows, never used in their place. Rows: `gain-ramp-min` (thresholds, 10 ms), `layer-gain` (ranges, 0 to 1, unit ratio), and `gain-ramp-count` (ranges, 0 to 8, unit ramps), all pending on this story; clear `pending` once a test reads each through `row()`.

**Recipe shape.** `gain` is the last member of `theta_reference`, `gamma_pac`, and `binaural`; `master` (an object whose only member is an optional `gain`) is the last top-level member, after `loop`. `gain`: `initial` (required number), `ramps` (optional array of at most 8 ramp objects; empty allowed). Ramp: `start_s`, `duration_s`, `to`, all required numbers. Every object keeps `additionalProperties: false`; every member is tagged `loudness-relevant`. Not `maxItems` in the schema: the count is the compile range check on row `gain-ramp-count`.

**Field table (`engine/src/recipe/field_table.{hpp,cpp}`).** `FieldType` gains `Array`. Array items are listed with a `*` path segment: `/theta_reference/gain` (Object), `/theta_reference/gain/initial` (Number, row `layer-gain`), `/theta_reference/gain/ramps` (Array, no row: the count is checked by name), `/theta_reference/gain/ramps/*/start_s` and `/duration_s` (Number, no row: bounded by the gain rules, on the range exemption list), `/theta_reference/gain/ramps/*/to` (Number, row `layer-gain`); the same under `/gamma_pac/gain`, `/binaural/gain`, and `/master/gain`, with `/master` (Object) first. The schema walk of `tests/cpp/test_recipe.cpp` follows `items` of an `array` property with the path segment `*`; the registration test fits `initial` and `to` (no unit suffix) to unit `ratio`. Parse: `ramps` not an array is rule `type`, limit `array`, at `/.../gain/ramps`; an element not an object is rule `type`, limit `object`, at `/.../gain/ramps/<i>`; unknown or missing members inside an element are named with the index (`/theta_reference/gain/ramps/0/to`, rule `required`, limit `present`).

**Recipe (`engine/src/recipe/recipe.hpp`):**

```
struct GainRampField { double start_s = 0.0; double duration_s = 0.0; double to = 0.0; };
struct Gain { double initial = 1.0; std::vector<GainRampField> ramps; };   // the parsed member
// std::optional<Gain> gain in ThetaReference, GammaPac, and Binaural;
// struct Master { std::optional<Gain> gain; }; std::optional<Master> master in Recipe.
```

**Validator (`engine/src/validate/validate.{hpp,cpp}`).** `range_rows()` gains `{"layer-gain", 0.0, 1.0, false, "ratio"}` and `{"gain-ramp-count", 0.0, 8.0, false, "ramps"}` (the range table test compares them with `ranges.tsv`). Constants: `kGainRampMinMs = 10.0` (threshold row `gain-ramp-min`, as `kCarrierRatio` is for `carrier-rule`), `kGainRampMinRule = "gain.ramp_min"`, `kGainOutsideRule = "gain.outside_session"`, `kGainOverlapRule = "gain.overlap"`, `kGainLoopBodyRule = "gain.loop_body"`, `kThetaSilentRule = "coupling.theta_silent"`, `kThetaSilentLimit` (the spec text). Order exactly as the spec's Compile order: range walk (initial, count, each `to`), loop rule 8 inside `check_loop()`, then rules 9 to 11 and 12 at the end of `check_rules()`. Every frame test runs at both native rates.

**Plan and core (`engine/src/plan/plan.hpp`, `engine/src/core/gain.{hpp,cpp}`):**

```
namespace arcani::core {
// Gain ramps, Law, engine: a + (b - a) * h, h = (1.0 - sine(ratio_to_phase(k / L) + 2^62)) * 0.5; 0 <= k < L.
double gain_ramp(double a, double b, std::uint64_t k, std::uint64_t length) noexcept;
}
namespace arcani::plan {
inline constexpr std::size_t kMaxGainRamps = 8;   // row gain-ramp-count
struct GainRamp { std::uint64_t start_frame; std::uint64_t length_frames; std::uint64_t end_frame; double from; double to; };
struct GainSchedule { double initial = 1.0; std::size_t count = 0; std::array<GainRamp, kMaxGainRamps> ramps{}; };
double gain_at(const GainSchedule& s, std::uint64_t n) noexcept;   // Gain ramps, Law; 1.0 for a default schedule
// Plan gains: GainSchedule theta_gain, gamma_gain, binaural_gain, master_ramp; master_gain stays the loudness gain.
}
```

**Renderer and C API.** `render::Taps` and `arc_taps` gain, after `master` and in this order, `theta_reference_gained`, `gamma_pac_gained`, `binaural` (before gain), `binaural_gained`; the existing five keep their names and positions (the before-gain theta and gamma taps). Per sample in the spec's order; master = `(join * master_gain) * gM`. New C API for the command-line window:

```
typedef enum arc_gain_target { ARC_GAIN_THETA_REFERENCE = 0, ARC_GAIN_GAMMA_PAC = 1, ARC_GAIN_BINAURAL = 2, ARC_GAIN_MASTER = 3 } arc_gain_target;
typedef struct arc_gain_ramp { arc_gain_target target; uint64_t start_frame; uint64_t end_frame; double from; double to; } arc_gain_ramp;
size_t arc_plan_gain_ramp_count(const arc_plan* plan);   /* every ramp of every schedule; 0 for NULL */
arc_status arc_plan_gain_ramp(const arc_plan* plan, size_t index, arc_gain_ramp* out_ramp, arc_error* error);
/* schedule order theta, gamma, binaural, master, each in array order; ARC_ERR_INVALID_ARGUMENT for NULL or an index at or past the count */
```

**Tap dump (`tests/tapdump/main.cpp`).** Every rendering form that writes taps writes ten files: the six of today plus `theta_gained.f64`, `gamma_gained.f64`, `binaural.f64`, `binaural_gained.f64` (same layout). `--output-only` is unchanged. The printed line is unchanged.

**Reference (`reference/gain.py`, `reference/stub_chain.py`).** `gain.frames(gain, fs)` returns `[(n0, L, n1, a, b)]`; `gain.values(gain, fs, n)` returns the binary64 gains of a uint64 frame index array (1.0 for `gain` None). `stub_chain.render` returns `KEYS = ("output", "theta", "gamma", "bus", "join", "master", "theta_gained", "gamma_gained", "binaural", "binaural_gained")`, each interleaved stereo; `theta`/`gamma` stay before gain.

**Command-line window (`cli/loudness.{hpp,cpp}`, `cli/main.cpp`).**

```
struct FrameSpan { std::uint64_t start; std::uint64_t end; };   // one ramp [n0, n1)
// LoudnessWindow gains std::uint64_t steady_frames: without a loop, the length of the longest steady
// stretch, set whether accepted or not (N without ramps); 0 with a loop.
LoudnessWindow loudness_window(const arc_loop_frames& loop, std::uint64_t end_frame, std::uint64_t min_frames,
                               std::span<const FrameSpan> ramps) noexcept;   // the existing overload = no ramps
```

The window rule's rejection value is `steady_frames / fs`. `--loudness` with a non-looping window that is not `[0, N)` meters the window in its own pass by `arc_seek` (like a looping body, one repeat); the whole meter still reads `[0, N)`. `--store-gain` step 4 renders `[s, e)` by `arc_seek`. The report member shape is unchanged.

**Ramp tool (`tests/assertions/gain_ramps.py`, NumPy and standard library):** `HOLD_TOL = 1e-9` (gain units), `MIN_DIVISOR = 2**-30`; `estimate(before, after)` (one channel, float64; NaN where `|before| < MIN_DIVISOR`); `changes(est, fs)` returns each completed change as `{"start": last frame at the old held value, "end": first frame of the new held value, "from", "to", "frames": end - start}`, a new value being held when every valid estimate in the next `round(0.010 * fs)` frames (or to the end) is within `HOLD_TOL` of it; `check(name, before, after, fs)` returns the assertion dict (name, row `gain-ramp-min`, threshold, unit `ms`, measured the shortest change in ms or None, result pass when every change lasts at least the row (inclusive) or there is none (note `no change`), a non-finite input fails with note `not finite`). The master is checked with `before = join * g` (the loudness gain `g`, 1.0 in measure mode) and `after = output`.

**Fixtures.** `gain_fixture_text(name)` in `tools/signal_spec_vectors.py` gives each file's exact text: `gain-ramp-in-loop.json`, `gain-layer-ramp-10min.json`, `gain-master-fade.json`, `gain-end-fade-loop.json` (render fixtures) and `gain-theta-silent.json` (rejected, `coupling.theta_silent`), all in `recipes/fixtures/valid/`. `gain-layer-ramp-10min-stored.json` is the 10 min fixture with its loudness gain stored by `--store-gain` on the dev PC at 48 kHz (implementation phase; it is the final-mode render of the loudness checks). `tests/data/recipe_hash_vectors.json` gains every new file (`tools/recipe_hash.py --write-vectors`). Probe: `gain-ramps-44100` and `gain-ramps-48000` (scope `engine`), the four render fixtures embedded, windows per `gain_windows.probe_starts`, measure mode, output only, float32, pinned from the dev PC probe, confirmed by the next full run. Existing pins never move.

**Test contracts (the QA agent may split differently; keep the added CI time to about 3 minutes of CPU per platform; delete each large file as soon as it is read; prefer windows (`--window`) to whole-session dumps for the 20 min fixtures):**

- `tests/cpp/test_gain_ramps.cpp` (guarded by `__has_include("core/gain.hpp")` where it calls internal code): `core::gain_ramp` bit for bit on every `kGainLaw` row; `plan::gain_at` on every `kGainFixtureRamps` row at `n0 - 1`, `n0`, `n1 - 1`, `n1`, and after (holds exact); compile every `kGainCompileCases` recipe in both modes at both rates through `arc_compile` (accepted, or the exact four error texts); the `gain-*.json` fixtures through the C API: `arc_plan_gain_ramp_count`/`arc_plan_gain_ramp` equal `kGainFixtureRamps`; unity schedule (`initial` 1, no ramps) renders byte-identical output and before-gain taps equal after-gain taps; `gain-master-fade.json` output exactly 0 from the master fade's `n1`; seek into a ramp equals the continuous render.
- `tests/cpp/test_api.cpp`, `tests/cpp/test_stages.cpp`: the four new taps exist, equal their before-gain partners bit for bit on every pre-4.4 fixture, the bus is the sum of the after-gain taps, the join adds the after-gain binaural tap, the master is `(join * g) * gM`; a muted ear stays `+0.0` before and after gain.
- `tests/cpp/test_recipe.cpp`, `tests/cpp/test_validate.cpp`: the schema walk with arrays, the field table, registration (`initial`, `to` on `layer-gain`; `start_s`, `duration_s` exempt), the range table with the two new rows, and the parse errors above; invalid fixtures for the schema faults (`ramps` as an object, a ramp missing `to`, an unknown member in `gain`, `initial` as a string, a ramp element that is a number) with `recipes/fixtures/invalid-expected.json` entries.
- `tests/python/test_gain_ramp_tool.py`: calibration on Python-synthesized signals (a 450 Hz sine times raised-cosine ramps of 441, 480, and 13230000 frames, linear ramps, and steps, with known change lengths; master through `join * g`): measured lengths as constructed, every 10 ms ramp passes at both rates; must-fail: a 5 ms raised-cosine fade (`gain_constants.must_fail_fade_s`) and a step fail; the click tool on 10 ms raised-cosine fades of a full-scale tone passes and on a step fails.
- `tests/python/test_gain_ramps_reference.py`: every render fixture at both rates, windows around every ramp edge (and the loop join and seams for the looping ones): every tap (before and after gain, bus, join, master) and the output match `reference/stub_chain.py` below row `reference-match`; the ramp tool on every layer tap pair and the master; the click tool around every edge on each after-gain tap and the output; must-fail doctored in the harness: a 5 ms fade spliced into a layer tap fails the ramp tool.
- `tests/python/test_gain_ramps_loudness.py`: both meters agree on each render fixture's window (`gain_windows`); `gain-layer-ramp-10min-stored.json` in final mode with `--loudness` passes `loudness` (window `[600 s, 720 s)`, within 1 LU) and `loudness_whole` (never above target + 1 LU); superseded-window must-fail: a gain computed in the harness from the reading over `[0, O + B)` of `gain-ramp-in-loop.json` and applied to the body reads above target + 1 LU (fails `check_loudness`); the reading over `[O, O + B)` differs from `[0, B)` by more than row `loudness-meter-agreement`; a non-looping window shorter than 60 s is refused with value `steady_frames / fs` (a harness recipe).
- `tests/python/test_probe_gain_ramps.py` (or in an existing probe test): the `gain-ramps-<fs>` component's segments match `reference/stub_chain.py` windows below `reference-match`.
- `tools/check_row_coverage.py` sees `gain-ramp-min`, `layer-gain`, and `gain-ramp-count` in use.

**Gaps settled in the implementation phase (QA flags on 4043edb):**

- **Ramp tool at signal edges and inside ramps.** A change is measured only between two held values. A window that opens inside a ramp, or a ramp at the first frames of a session where the before-gain carrier is 0 (the 10 ms binaural ramp of `gain-master-fade.json` at 0 s), reads from its first held value; a change still running at the signal end is not completed. Neither is counted, so those edges are judged by the reference match and the click tool, not the ramp tool. After a change the next one is judged from the last valid estimate of the new hold window. A change no larger than row `sine-error` as a gain (1e-6) is not a gain change: the engine law starts and ends 2.8e-8 of the ramp height off its end values (the engine cosine at 0 and pi is `sine(2^62)`), so a long ramp creeps within `HOLD_TOL` of a value 2.8e-8 short of `to` and steps onto it at `n1`. Without this floor the 10 min ramp's last window failed with a 2-frame change. The spec section (Law, Ramp tool) says so.
- **Superseded-window must-fail margin.** Measured on the engine render of `gain-ramp-in-loop.json`: body window -3.7813 LUFS-I at 44.1 kHz (-3.7814 at 48 kHz), superseded window `[0, O + B)` -5.2310 LUFS-I, first `[0, B)` -17.7299 LUFS-I. The gain from the superseded window plays the body 1.4498 LU above target at both rates, against row `loudness-tolerance` (1 LU): a 0.45 LU margin, the same on every platform (the render is bit-exact).
- **CI cost.** See the story report: the added test time and the whole-session output dump of the superseded-window test (847 MB at 44.1 kHz, read through `np.memmap`).

## Design Notes

**Phased handoff,** as in 4.1 to 4.3, on branch `story/4-4-gain-ramps`. The implementation agent writes the spec section, vectors, rows, and log, then commits. A fresh-context QA agent commits the failing tests. The implementation agent then implements without editing a test expectation. No push until review.

**Ramp law** (decision 8): `g[n] = b` exactly for n >= n1, and `g[n] = a` for n < n0. Because the curve is flat at both ends, a 10 ms ramp of a full-scale tone stays far below the click level. The spec section must give the cosine argument's exact binary64 evaluation order, so the engine and reference agree below -100 dBFS.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl`: expected build passes and ctest is green.
- `uv run --locked pytest -n auto`: expected all pass.
- `git status --porcelain -- recipes` after the suite: expected only committed fixture edits.
