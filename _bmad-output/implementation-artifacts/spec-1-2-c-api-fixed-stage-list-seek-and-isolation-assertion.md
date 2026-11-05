---
title: 'Story 1.2: C API, fixed stage list, seek, and isolation assertion'
type: 'feature'
created: '2026-11-04'
status: 'in-progress'
baseline_commit: '786d1b1b4fed13a5aa8cd63adc10b8747a761f7c'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The engine has a recipe parser but no way for a host to turn a recipe into sound: no plan, no render call, no stage list, and nothing that fails a test if one ear leaks into the other.

**Approach:** Add one `arc_` C API (compile in `measure` or `final` mode, renderer with render frames, seek, and per-layer taps, warnings, stage list, engine version, release) over a fixed stub stage list. The binaural join stub plays the S0.2 sine in each ear. A test-side isolation assertion uses the muted-ear method and is calibrated on Python-synthesized signals. Every floating-point call guards the denormal mode.

Decisions (2026-11-04, build agent, under Audio's standing "settle tech forks yourselves" preference):
- Plan and renderer are separate handles. `arc_compile(utf8, len, options, &plan, &error)` returns an immutable, reference-counted plan (`arc_plan_retain` and `arc_plan_release`). Options are mode, sample rate (44100 or 48000, anything else rejected), and `mute_binaural_ear` (none, left, or right; an offline measurement control for FR-4 that is stored in the plan, not a fault hook). `arc_renderer_create(plan, &renderer, &error)` does every allocation. `arc_render(renderer, out, frames, taps, &error)` writes interleaved stereo binary64 and never allocates or throws. `arc_seek(renderer, frame, &error)` is pure. `arc_renderer_destroy` frees the renderer. Past the session end (`arc_plan_frame_count`, from `length_s` by the seconds-to-samples rule), output is exact zeros.
- Errors use a plain C struct with fixed `char` buffers (parameter, value, rule, limit), truncated with a trailing `...`. Status codes: ok, invalid argument, rejected, out of memory, internal. Compile catches every exception at the boundary. Input over 1 MiB is rejected with rule `input.max_bytes` (closes 1.1 triage finding 18).
- `final` mode in this story requires `loudness_gain_db` and `loudness_hash` to be present (rule `final.required`). The hash match is Story 4.2. The warning list exists and is empty in v0.1.
- Stub chain (written into `docs/signal-spec.md` first): theta reference and gamma PAC stubs output exact zeros (Story 1.5 routes the sine through theta). The stereo bus adds layers within each channel. Binaural join: the left ear is `sine` at `carrier_left_hz`, the right ear at `carrier_left_hz + beat_rate_hz` (range row `binaural-carrier-right`), both at unit amplitude from phase 0, each added only to its own channel. The master chain stub applies per-channel gain 1.0 (stored gain is Epic 4) and an identity stereo-linked limiter. Internal block size: 64 frames, a fixed constant in the new signal spec section. No layer field means that stage outputs zeros.
- Taps: theta reference, gamma PAC, stereo bus, binaural join (the "engine output" point), and master (the render output). Each is stereo and optional per call.
- Isolation measurement lives in the C++ test harness: a Hann-windowed single-bin DFT at the active ear's carrier, giving the muted channel's level relative to the active channel's own carrier, in dB. The assertion fails as silent if the active carrier measures zero. Calibration signals come from `tools/isolation_calibration.py` and are stored as base64 float32 in JSON (the wording check rejects binary files).
- Denormal guard: engine-internal RAII using `_mm_getcsr`/`_mm_setcsr` (clears FTZ and DAZ) on x86-64 and the clang FPCR builtins (clears FZ) on AArch64. The symbol denylist gains a `fenv` family (`fesetenv`, `fegetenv`, `feholdexcept`, `feupdateenv`, `fesetround`, `_controlfp`, `_control87`, and their variants) with a must-fail case.
- The stub-chain render joins the hash probe as components `stub-chain-44100` and `stub-chain-48000`, compared per run against windows-x64. Expected-file entries stay with Story 1.6.

## Boundaries & Constraints

**Always:**
- The CLI and every C++ API test include only `arcani/arcani.h`. Internal-header tests are limited to the denormal guard and the stage descriptor table.
- Thresholds come from rows `binaural-isolation-engine` and `binaural-isolation-master`. Clear their `pending` field, and never edit their values.
- Tests come first, written by a fresh-context QA agent and committed tests-only and failing. Every check has a passing and a must-fail case. Must-fail audio is doctored in the harness, never in `engine/`.
- Engine stays C++20 standard library only, with no I/O, threads, clocks, or logging. All existing checks keep passing: symbols, flags, pragmas, wording, table log, and row coverage.
- Name signals by carrier, modulation type, and rate in docs and comments ("400 Hz unmodulated sine, left ear").

**Never:**
- Validation against locked ranges or the carrier rule (Story 1.3), the CLI or WAV (1.4), the Python reference renderer (1.5), the determinism key or expected hashes (1.6), real layer signals (Epic 2), or loudness gain (Epic 4).
- Submit plan, state snapshot, or provide asset calls (later phases).
- Any stage that reads one channel to write the other. Routing fields in the recipe.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Compile valid | binaural fixture, `measure`, 48000 | plan, 5 stages in order, 0 warnings | N/A |
| Parse fault | any invalid 1.1 fixture | no plan | 1.1 rule and parameter passed through |
| Bad rate | 32000 | no plan | `sample_rate`, "32000", `sample_rate`, "44100 48000" |
| Final, no gain | fixture without `loudness_gain_db` | no plan | `/loudness_gain_db`, rule `final.required` |
| Too large | 1 MiB + 1 byte | no plan | `input.max_bytes` |
| Null pointer | null plan or out buffer | invalid argument status | host FP mode unchanged |
| Isolation 0 Hz | beat 0, each ear muted in turn | passes 90 dB at the binaural join tap and 60 dB at master | N/A |
| Doctored | 0.1 % of active channel added to muted channel | engine-output assertion fails | N/A |
| Silent | both ears silent (no `binaural`) | isolation assertion fails as silent | N/A |
| Seek | k = 0, 37, 64, 1000 | samples from k byte-identical to the full render | N/A |
| Past end | render beyond the frame count | exact zeros | N/A |

</frozen-after-approval>

## Code Map

- `engine/include/arcani/arcani.h` -- only `arc_engine_version` today. Extend it with the C API; keep the `extern "C"` and include-guard pattern.
- `engine/src/version.cpp` -- keep as it is. Add `engine/src/api/api.cpp` (C boundary, error struct filling, exception catch), `engine/src/plan/plan.{hpp,cpp}` (compile, stage descriptors), `engine/src/render/renderer.{hpp,cpp}` (64-frame blocks, seek, taps), and `engine/src/core/fp_mode.hpp` (denormal guard).
- `engine/src/recipe/recipe.hpp` -- reuse `parse()` and `Error` as they are. `engine/src/core/phase.hpp` -- reuse `phase_increment` and `seconds_to_samples`. `core/sine.hpp` -- reuse `sine(phase)`. Seek uses phase = inc * n mod 2^64.
- `engine/CMakeLists.txt:10-19` -- add the sources. Do not touch the nm or check-JSON logic.
- `tests/cpp/CMakeLists.txt:13-21` -- add the test files. Add a second executable, `arcani_alloc_tests`, that replaces global `operator new` with a counter, plus its `add_test`.
- `tests/cpp/spec_helpers.hpp` -- add a dB row helper next to `dbfs_row`. `tests/assertions/tables.hpp` `row()` records the row usage.
- `tools/engine_symbol_denylist.json` -- add the `fenv` family. `tests/cmake/test_engine_symbols.py` -- add a must-fail extra source for it (existing pattern).
- `tests/hashprobe/main.cpp:105-110` -- add two components that render an embedded recipe literal through the C API. `tests/hashprobe/CMakeLists.txt` -- link `arcani::engine`.
- `recipes/fixtures/valid/` -- add short (1 s) binaural fixtures at beat 0 and 6 Hz, and one without a gain. Rerun `tools/recipe_hash.py --write-vectors`.
- `tests/tables/thresholds.tsv:4-5` -- clear `pending` only.
- `docs/signal-spec.md` -- new sections "Internal block size" and "Stub chain", with vectors from `tools/signal_spec_vectors.py`.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json` -- block size and stub chain sections with vectors -- spec merges before code (AD-19).
- [ ] `tests/cpp/test_api.cpp`, `test_stages.cpp`, `test_seek.cpp`, `test_isolation.cpp`, `test_fp_mode.cpp`, `test_alloc.cpp`, `tests/cpp/isolation.hpp`, `tools/isolation_calibration.py`, `tests/data/isolation_calibration.json`, `tests/python/test_isolation_calibration.py`, fixtures -- QA agent writes the failing tests -- tests first.
- [ ] `engine/include/arcani/arcani.h`, `engine/src/api/*`, `plan/*`, `render/*`, `core/fp_mode.hpp`, `engine/CMakeLists.txt` -- the API and the stub chain.
- [ ] `tools/engine_symbol_denylist.json`, `tests/hashprobe/*`, `tests/tables/thresholds.tsv` -- checks and probe.
- [ ] `docs/design-log.md` entry (gg) (API shape, block size, stub levels, 1 MiB cap, measurement method), `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given the public header, when a C test compiles against it alone, then every call listed in the decisions exists with `arc_` names and plain C types, and every failing call returns a non-ok status with all four error fields filled.
- Given a compiled plan, when the stage list is read, then the kinds are theta reference, gamma PAC, stereo bus, binaural join, master chain in that order. Every stage kind's descriptor declares per-channel processing, or a linked gain for the limiter only, and no kind maps one channel's input to another channel.
- Given Python calibration signals with known leakage of -100, -91, -89, and -60 dB, when the C++ measurement reads them, then each measures within 0.5 dB of its known value and the 90 dB verdicts are pass, pass, fail, fail.
- Given the isolation assertion at beat 0 and 6 Hz, with each ear muted in turn, then the binaural join tap passes the engine row and the master output passes the master row. A render doctored to 0.1 % crosstalk fails the engine row. A render doctored to 1 dB above the master threshold's crosstalk fails the master row.
- Given seek to k and render to N, then the samples from k onward equal the full render byte for byte, for k at 0, inside a block, and on a block boundary.
- Given `arcani_alloc_tests`, when render runs after compile and renderer creation, then the counter shows zero allocations during render calls. A must-fail case that allocates inside the counted window is counted.
- Given the host sets FTZ and DAZ, when compile, render, and seek run (including an error return), then the output is identical to an IEEE-mode render and the host's mode is unchanged after every call. An internal test shows that a denormal survives inside the guard while host FTZ is set.
- Given the denylist, when a must-fail extra source calls `fesetenv`, then the symbol check fails. The engine library built without it passes.

## Spec Change Log

## Review Triage Log

## Design Notes

Muting is a compile option, so the render path has no test branch: the muted oscillator's increment and gain are zero in the plan. Isolation level = 20 log10(|X_muted(f)| / |X_active(f)|) at the active carrier f, over the whole render with a Hann window. The assertion passes when that level is at or below minus the row value.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build passes and every ctest passes (both test executables).
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_wording.py`, `tools/check_fp_pragmas.py`, `tools/check_row_coverage.py` -- expected: exit 0.

## Implementation Notes

QA agent, tests-first pass (2026-11-04). Execution tasks 1 and 2 only; nothing under `engine/` is written. Settled test-side choices the implementation must follow:

- **Header** (`arcani/arcani.h`, contract in the comment block of `tests/cpp/test_api.cpp`): macro `ARC_ERROR_FIELD_BYTES` (256; the tests use it as the "API is declared" guard, so each test file compiles to one failing case until it exists). Enums `arc_status` (`ARC_OK` 0, `ARC_ERR_INVALID_ARGUMENT`, `ARC_ERR_REJECTED`, `ARC_ERR_OUT_OF_MEMORY`, `ARC_ERR_INTERNAL`), `arc_mode` (`ARC_MODE_MEASURE`, `ARC_MODE_FINAL`), `arc_mute_ear` (`ARC_MUTE_NONE`, `ARC_MUTE_LEFT`, `ARC_MUTE_RIGHT`), `arc_stage_kind` (`ARC_STAGE_THETA_REFERENCE` 0 .. `ARC_STAGE_MASTER_CHAIN` 4). Structs `arc_error {parameter, value, rule, limit}`, `arc_compile_options {mode, sample_rate, mute_binaural_ear}`, `arc_taps {theta_reference, gamma_pac, stereo_bus, binaural_join, master}` (each `double*`, NULL or 2 * frames interleaved). Calls: `arc_compile(utf8, length, options, &plan, error)`, `arc_plan_retain`, `arc_plan_release`, `arc_plan_frame_count`, `arc_plan_stage_count`, `arc_plan_stage(plan, index, &kind, error)`, `arc_plan_warning_count`, `arc_plan_warning(plan, index, &warning, error)` (a warning is an `arc_error`), `arc_renderer_create(plan, &renderer, error)` (the renderer holds a plan reference), `arc_render(renderer, out, frames, taps, error)`, `arc_seek(renderer, frame, error)`, `arc_renderer_destroy`. NULL is a no-op for retain, release, and destroy; the count and frame-count queries return 0 for NULL.
- **Errors:** `error` may be NULL. A failing call writes all four fields NUL-terminated ("filled" = written; the tests poison the struct and check every field got a terminator, and `rule` is never empty; `parameter` may be `""` for the whole document, as 1.1 does). Failing compile and renderer_create set the out handle to NULL. Rules fixed by the tests: `argument.null` (parameter = argument name: `utf8`, `options`, `out_plan`, `plan`, `out_renderer`, `renderer`, `out`, `out_kind`, `out_warning`; value `null`; limit `non-null`), `argument.index` (parameter `index`, value the index, limit the count), `argument.enum` (parameter `mode` or `mute_binaural_ear`, value in decimal), `sample_rate` (`ARC_ERR_REJECTED`, value the rate, limit `44100 48000`), `final.required` (`/loudness_gain_db` first, then `/loudness_hash`), `input.max_bytes` (parameter `""`, value the length, limit `1048576`; exactly 1048576 bytes compiles). Parse faults are `ARC_ERR_REJECTED` with the 1.1 parameter and rule, and value and limit as `invalid-expected.json` lists them. Truncation: a long field is `ARC_ERROR_FIELD_BYTES - 1` bytes ending in `...`.
- **Internal headers** (the only two): `engine/src/plan/plan.hpp` with `arcani::plan::StageKind` (values equal `arc_stage_kind`), `ChannelUse {PerChannel, LinkedGain}`, `StageDescriptor {kind, channel_use, std::array<int, 2> input_channel}`, `std::span<const StageDescriptor> stage_descriptors() noexcept`; `engine/src/core/fp_mode.hpp` with RAII `arcani::core::FpModeGuard` (non-copyable). Host mode comparisons ignore the x86-64 MXCSR status flags (low six bits), since arithmetic sets them.
- **Fixtures** (`recipes/fixtures/valid/`, hash vectors rewritten): `stub-chain-1s-beat-0.json` (400 Hz each ear), `stub-chain-1s-beat-6.json` (400 Hz left, 406 Hz right, plus a 450 Hz `theta_reference` that the stub ignores), `stub-chain-1s-no-gain.json`, `stub-chain-1s-no-layers.json` (the silent case). All but no-gain carry `loudness_gain_db` and `loudness_hash`, so they also compile in `final` mode.
- **Signal spec:** sections "Internal block size" and "Stub chain" with three vector tables (internal blocks, stub chain increments, stub chain samples). JSON keys `block_frames`, `blocks`, `stub_chain`; generated C++ `kBlockFrames`, `kBlocks`, `kStubChain` (`tests/cpp/SpecTables.cmake`). Operation order per sample: `bus = theta + gamma`, `bin = a_c * sine(phase)`, `join = bus + bin`, `master = join * 1.0`, limiter identity; muted ear `inc = 0`, `a = 0.0`. `test_spec_tables_equal_json` now expects 10 generated tables (was 7).
- **Isolation harness** (`tests/cpp/isolation.hpp`): periodic Hann `0.5 - 0.5 cos(2 pi n / N)`, single-bin DFT at the active carrier over the whole render, `level = 20 log10(|X_muted| / |X_active|)`, pass when `level <= -row`, silent when `|X_active| == 0`. Row helper `spec::db_row(id)` (unit must start with `dB `). Calibration: `tools/isolation_calibration.py` writes `tests/data/isolation_calibration.json` (two setups: 400 Hz at 48 kHz left active, 406 Hz at 44.1 kHz right active; 0.1 s each; levels -100, -91, -89, -60 dB; muted channel phase offset 1 rad).
- **Checks:** `arcani_alloc_tests` (own executable, replaces every global `operator new`/`delete` form; counts render calls only, including an error return). ctest `arcani_api_c_header` compiles `tests/cpp/test_api_c.c` as C11, syntax only, warnings as errors; `arcani_api_c_header_mustfail` (WILL_FAIL) compiles `tests/fixtures/c_api/cpp_reference.c`. Symbol family name `fenv` with cases `fesetenv`, `fegetenv`, `feholdexcept`, `feupdateenv`, `fesetround`, `_controlfp`, `_controlfp_s`, `_control87`, `__control87_2`, plus `__imp_` and Mach-O `_` forms; real-build must-fail source `tests/fixtures/engine/calls_fesetenv.cpp` (its Windows build lists `__imp_fesetenv`). Hash probe tests (`tests/python/test_probe_sine.py`) expect `stub-chain-44100.f32` and `stub-chain-48000.f32`, interleaved stereo float32, not silent, and no `stub-chain-*` entry in `ci/hash_expected.json` yet.
- **Red state at hand-off:** C++ suites build; the API, stage, seek, isolation-engine, fp-mode, and alloc cases fail with "not declared yet" messages, and `arcani_api_c_header` fails to compile. pytest: 18 expected failures (fenv denylist rows and the fesetenv build, three probe stub-chain tests); everything else passes, including calibration. `check_row_coverage.py` flags the two isolation rows as used while pending until Task 4 clears them. A throwaway stub-chain implementation built outside the repo passed every new C++ test, and three planted bugs (render allocation, 1e-4 crosstalk, a seek off by one and a seek without the guard) were each caught.
