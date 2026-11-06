---
title: 'Story 1.4: Command-line renderer, report, and render speed'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: '5469dffb8879d6478140362924d8d66987736fe8'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** `arcani-render` only prints the engine version. Nothing turns a recipe into a WAV or a machine-readable record of what was checked, so no rule can be checked without ears.

**Approach:** Make `arcani-render` compile a recipe file through the public C API, render it, write a 2-channel 24-bit WAV by a new signal spec rule (§24-bit rounding), and write a JSON report with per-assertion results, the determinism key, the seed, and the engine version. The first assertion is render speed.

Decisions (2026-11-05, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Usage:** `arcani-render RECIPE --out WAV [--report JSON] [--rate 44100|48000] [--mode measure|final]`, plus `--version` alone. Defaults: rate 48000, mode `measure` (starters carry no stored gain until Epic 4), report path = WAV path with its last extension replaced by `.report.json` (`a/focus.wav` to `a/focus.report.json`). Any other argument shape: usage text, exit 2.
- **Exit codes:** 0 rendered, every assertion pass or not applicable; 1 recipe or option rejected by the engine; 2 usage; 3 file or internal error; 4 rendered but an assertion failed (WAV and report still written).
- **Rate refusal:** the CLI passes `--rate` to `arc_compile`, so a numeric rate other than 44100 or 48000 is refused by the engine's existing sample-rate check (exit 1). A non-numeric `--rate` is a usage error.
- **Rejection:** compile runs before any output file is opened. Exit 1, no WAV, no report; stderr gets one line `rejected: parameter=<p> value=<v> rule=<r> limit=<l>`. The WAV is written to `<out>.partial` and renamed only after the last frame, so neither rejection nor a failed render leaves a file at the WAV path; an existing file there is never touched before that rename.
- **§24-bit rounding** (written to `docs/signal-spec.md` with worked vectors before code): for sample `s` (binary64): NaN gives 0; else `x = s * 0x1p23` (exact); `x >= 8388607` gives 8388607 (so +1.0, above full scale, and +inf); `x <= -8388608` gives -8388608 (so -1.0, below, and -inf); else nearest integer, ties to even. Written as 3 bytes, little-endian two's complement. No dither. Each step is exact, so the result does not depend on the host rounding or denormal mode.
- **WAV layout:** `WAVE_FORMAT_PCM` (tag 1), 16-byte `fmt `, 2 channels, 24 bits, block align 6, then `data`; no other chunk, no timestamp. When `36 + data bytes` exceeds `0xFFFFFFFF` (above about 4.1 h at 48 kHz; locked lengths reach 8 h) the file is RF64 (EBU Tech 3306: `RF64`, `ds64` with table length 0, 32-bit sizes `0xFFFFFFFF`). The header is a pure function of frame count and rate.
- **Render loop:** 4096 frames per `arc_render` call (a member of row `block-sizes`; the engine output does not depend on it).
- **Report:** UTF-8 JSON object with members `engine_version`, `seed`, `sample_rate`, `mode`, `frames`, `determinism_key` (object: `recipe_hash`, `asset_hashes` `[]` in v0.1, `engine_version`, `sample_rate`), `assertions` (array of objects: `name`, `row`, `threshold` (the row's value text as a JSON number), `unit`, `measured` (number, or `null` when not applicable), `result` (`pass`, `fail`, or `not_applicable`), `note` (string, empty unless not applicable)). Numbers are shortest round-trip. v0.1 Story 1.4 lists one assertion, `render speed`; later stories append theirs.
- **Public API:** add `const char* arc_plan_recipe_hash(const arc_plan*)` (64 lowercase hex digits, valid while the plan lives, `""` for NULL) and `uint64_t arc_plan_seed(const arc_plan*)` (0 for NULL). The plan stores both from parse.
- **Render speed:** measured = `(frames / rate) / (summed steady_clock time of the arc_render calls)`, an elapsed time of 0 ticks counted as 1 tick. Passes when measured >= row `render-speed` (20). The machine is the dev PC only when environment variable `ARCANI_REFERENCE_MACHINE` equals `1` (Audio sets it once on the dev PC; no CI workflow sets it, and a test checks that). Otherwise result `not_applicable`, `measured` null, note `not the reference machine`. A 0-frame render is `not_applicable`, note `no frames`.
- **Threshold source:** the CLI reads `render-speed` through the assertion library loader (`tests/assertions/tables.hpp`, `row()`), which AD-17 already names as the library the CLI and tests share. That records the row, so its `pending` field is cleared.
- **Include rule:** `cli/` sources link only `arcani::engine` (public header) and the assertion library. A check on `compile_commands.json` fails if any `cli/` compile command has an include path into `engine/src`; it has a must-fail case. The AD-9 flag check (`tools/check_compile_flags.py`) extends to `cli/` sources (deferred-work item, review pass 1 finding 21, trigger Story 1.4).

## Boundaries & Constraints

**Always:**
- Tests first, by a fresh-context QA agent, committed tests-only and failing. Every check has a passing and a must-fail case; must-fail conversions live in the test harness, never in `cli/` or `engine/`, and contain no undefined behavior (no NaN or out-of-range cast).
- Thresholds from the tables; never edit a value. Clear `pending` on `render-speed` only.
- Engine stays C++20 standard library only; the two new API functions are pure getters. All existing checks keep passing.

**Never:**
- Loudness measurement or gain writing (Epic 4), the Python reference (1.5), block-size or repeat determinism tests (1.6), isolation or other assertions in the report, dither, resampling, any rate besides 44.1 and 48 kHz.
- A CI workflow that sets `ARCANI_REFERENCE_MACHINE`, or a speed check that gates CI.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Render default | `stub-chain-1s-beat-6.json --out x.wav` | 48 kHz, 48000 frames; data bytes equal §24-bit rounding of the engine output; report beside it | exit 0 |
| 44.1 kHz | same, `--rate 44100` | 44100 frames | exit 0 |
| Other rate | `--rate 96000` | no WAV, no report | exit 1, `rejected:` line from the engine's sample-rate error |
| Bad option | `--rate fast`, missing `--out`, unknown flag | usage | exit 2 |
| Rejected recipe | `length_s` -1 | no WAV, no report, existing file at the path unchanged | exit 1, parameter, value, rule, limit printed |
| Final mode, no gain | `stub-chain-1s-no-gain.json --mode final` | no WAV | exit 1, rule `final.required` |
| Rounding vectors | +1.0, above +1, -1.0, below -1, NaN, +-inf, -0.0, ties at +-0.5, +-1.5, +-2.5 LSB | values per §24-bit rounding | must-fail naive conversion differs and is caught |
| Large file | frame count above the RIFF limit | RF64 header bytes per EBU 3306 | header unit test only, no large render |
| Speed, not reference | env unset or not `1` | `not_applicable`, `measured` null | exit 0 |
| Speed, reference | env `1`, measured 19.99 vs 20 | `fail` | exit 4 (unit test of the pass rule) |
| Zero length | `length_s` 0 | header-only WAV, speed `not_applicable` (`no frames`) | exit 0 |

</frozen-after-approval>

## Code Map

- `cli/main.cpp` -- replace the stub; keep `--version` behavior. Only `<arcani/arcani.h>` from the engine.
- `cli/wav.{hpp,cpp}` (new) -- `quantize_24(double) -> int32_t`, `wav_header(frames, rate) -> bytes` (RIFF or RF64), sample packing. Reimplement ties-to-even here (pattern: `engine/src/core/phase.cpp` `round_half_even`; do not include it).
- `cli/report.{hpp,cpp}` (new) -- JSON writer (string escaping, `std::to_chars` shortest numbers) and the speed rule as a pure function of (frames, rate, elapsed seconds, threshold, is_reference).
- `cli/CMakeLists.txt` -- static `arcani_cli_core` (wav, report) plus `arcani-render`; link `arcani::engine`, `arcani::test_tables`. `tests/assertions/CMakeLists.txt` comment: the table library is no longer test-only once the CLI links it (it then builds in every job, Android included).
- `engine/include/arcani/arcani.h`, `engine/src/api/api.cpp`, `engine/src/plan/plan.{hpp,cpp}` -- two getters; `Plan` gains `recipe_hash` and `seed`. `tests/cpp/test_api_c.c` must still compile as C.
- `docs/signal-spec.md` -- new `## 24-bit rounding` section with a vector table; `tools/signal_spec_vectors.py` (`build`, `tables`) generates it into `tests/data/signal_spec_vectors.json`; `tests/cpp/SpecTables.cmake` exposes it to C++; `tests/python/test_signal_spec_core.py` passes it in Python.
- `tests/cpp/test_cli_stub.cpp` -- becomes `test_cli.cpp` (popen pattern kept; the old "render" and "--version extra" usage cases change meaning). New `tests/cpp/test_wav.cpp`, `test_report.cpp` against `arcani_cli_core`. `tests/cpp/CMakeLists.txt` links it.
- `tools/check_compile_flags.py`, `tests/cmake/test_compile_flags.py` -- add `cli/` sources. New include check (script or test) on `compile_commands.json`.
- `tests/python/test_ci_workflows.py` -- no workflow sets `ARCANI_REFERENCE_MACHINE`.
- `tests/tables/thresholds.tsv` -- clear `pending` on `render-speed`.
- `CLAUDE.md` "Render a recipe" line, `docs/design-log.md` entry (ii), `docs/timeline-guidebook.html`, `sprint-status.yaml`, `deferred-work.md` (close the cli flag-check item).

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json` -- §24-bit rounding and vectors -- spec merges before code (AC 2).
- [x] `tests/cpp/test_cli.cpp`, `test_wav.cpp`, `test_report.cpp`, `tests/cpp/CMakeLists.txt`, Python checks -- QA agent writes failing tests -- tests first.
- [x] `engine/` getters, `cli/` sources and CMake -- implementation.
- [x] `tools/check_compile_flags.py`, include check, `thresholds.tsv` -- checks and table.
- [x] `CLAUDE.md`, design log (ii), guidebook, sprint status, deferred work -- records.

**Acceptance Criteria:**
- Given a valid recipe, when rendered at each rate, then the WAV parses as 2-channel 24-bit PCM at that rate with the plan's frame count, and its data bytes equal §24-bit rounding of `arc_render` output for the same plan.
- Given the §24-bit rounding vectors, when the C++ quantizer and the Python generator run them, then every value matches, and a naive conversion (no clamp, no NaN rule, or truncation instead of ties to even) fails on at least one vector per rule.
- Given a render, then the report has every member above, `recipe_hash` equals `tools/recipe_hash.py` for the recipe, and `seed` equals the recipe seed.
- Given the speed rule with threshold 20, then 20 passes, the next double below fails, and non-reference input is `not_applicable`; the end-to-end render on the dev PC with `ARCANI_REFERENCE_MACHINE=1` passes.
- Given the include and flag checks, then they pass on the real build and fail on their must-fail inputs.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build passes, every ctest passes.
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_wording.py`, `tools/check_fp_pragmas.py`, `tools/check_compile_flags.py build/windows-clang-cl`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.
- `build/windows-clang-cl/cli/arcani-render recipes/fixtures/valid/stub-chain-1s-beat-6.json --out build/tmp/beat6.wav` -- expected: exit 0, WAV and report written.

## Implementation Notes

QA agent, tests-first pass (2026-11-05). Execution tasks 1 and 2 only; nothing under `engine/` or `cli/` is written. `tests/cpp/test_cli_stub.cpp` is replaced by `tests/cpp/test_cli.cpp`. Settled test-side choices the implementation must follow:

- **§24-bit rounding** is in `docs/signal-spec.md` (rule, exactness, range, and a 35-row vector table). `tools/signal_spec_vectors.py` gains `quantize_24(s)` (exact `Fraction`), `pack_24(v)`, and `QUANTIZE_CASES`; the JSON gains `quantize_24` rows (`rule` clamp, nan, tie, round, or zero; `label`; `s_hex`; `x_hex`; `value` as an integer; `bytes` as 6 hex digits in file order). `tests/cpp/SpecTables.cmake` emits `kQuantize24` (`Quantize24Vector { rule, label, s, value, bytes[3] }`). The spec table count in `test_signal_spec_core.py` is 11. Python passes the vectors twice (the generator, and an independent binary64 rule using `round`), and four naive conversions (no clamp, wrapping to 24 bits; no NaN rule, clamping with `!(x < max)`; truncation; ties away from zero) each miss a vector of their rule. The same four live in the C++ harness `tests/cpp/cli_helpers.hpp`, with no NaN or out-of-range cast.
- **Header contracts** are in the comment blocks of `tests/cpp/test_wav.cpp` (`cli/wav.hpp`: `quantize_24(double) noexcept -> std::int32_t`, `append_samples(std::vector<std::uint8_t>&, std::span<const double>)` appending 3 bytes per sample, `wav_header(std::uint64_t frames, std::uint32_t rate) -> std::vector<std::uint8_t>`) and `tests/cpp/test_report.cpp` (`cli/report.hpp`: `Result`, `Assertion`, `DeterminismKey`, `Report`, `json_string`, `json_number`, `report_json`, `is_reference_machine(const char*)`, `elapsed_seconds(steady_clock::duration)`, `render_speed(const tables::Row&, frames, rate, elapsed_s, is_reference)`, `assertions_exit_code`), all in namespace `arcani::cli`. Both headers come from the static library `arcani_cli_core`, whose PUBLIC include directory is `cli/` and which links `arcani::engine` and `arcani::test_tables`; the tests write `#include "wav.hpp"` and `#include "report.hpp"`. `tests/cpp/CMakeLists.txt` links it through `$<TARGET_EXISTS:arcani_cli_core>` and defines `ARCANI_HAVE_CLI_CORE` only then, plus `ARCANI_TEST_OUT_DIR` (build tree scratch). The plan getters are found with a concept in `test_report.cpp`, and `tests/cpp/test_api_c.c` now takes the address of both, so the C header ctest fails until they are declared.
- **WAV:** RIFF while `36 + 6 * frames <= 0xFFFFFFFF` (largest RIFF count 715827876, checked on both sides); RF64 header 80 bytes with `ds64` riffSize `72 + data`, dataSize `6 * frames`, sampleCount `frames` (the frame count, as in a PCM `fact` chunk), table length 0. The end-to-end checks compare the whole file: header bytes, then data equal to the harness rounding of `arc_render` output for the same text, rate, and mode.
- **Arguments:** RECIPE first, then the options in any order, each at most once. `--rate` takes ASCII digits only (`48k`, `-48000`, and `48000.0` are usage errors); `--version` only alone; usage text contains "usage" on stdout or stderr. Report default replaces the last extension (`take.final.wav` to `take.final.report.json`; `take` to `take.report.json`). A rejection's stderr is exactly one line, compared with `arc_compile` on the same text and options. Unreadable recipe and missing WAV directory exit 3. Each case directory listing is checked exactly, so a leftover `.partial`, a stray report, or a touched file shows.
- **Report:** members in the spec's order (checked); `seed`, `sample_rate`, `frames` as plain integer digits; `measured` null exactly when `not_applicable`; `note` non-empty exactly when `not_applicable`. `json_string` escapes `"` and `\`, `\b \t \n \f \r`, other bytes below 0x20 as `\u00xx` (lowercase), nothing else. `json_number` equals `std::to_chars` output. The recipe hash is checked against `tests/data/recipe_hash_vectors.json` (written by `tools/recipe_hash.py`).
- **Speed rule:** `frames == 0` first (note `no frames`, also on the reference machine), then not the reference machine (note `not the reference machine`), else `measured = (double(frames) / rate) / elapsed_s`, pass at `>=`. `is_reference_machine` is true only for exactly `"1"`. `elapsed_seconds` of 0 ticks equals one tick. The tests read `render-speed` through `tables::row` and never assume its value; the CLI child inherits `ARCANI_ROW_USAGE_FILE` from ctest.
- **Python checks:** contract for the new `tools/check_cli_includes.py BUILD_DIR` in the `tests/cmake/test_cli_includes.py` docstring (include options `-I /I -isystem -iquote -idirafter -imsvc /imsvc -external:I /external:I`, joined or separate, bare or behind `/clang:` or `-clang:`; paths relative to the entry directory; response files, zero CLI sources, and unreadable build facts fail). A real preset configure passes; one with `CMAKE_CXX_FLAGS=-I<repo>/engine/src` fails naming `main.cpp`. The flag check applies every rule to `cli/` sources (zero-sources rule stays about `engine/`), and the real fast-math configure must also name `main.cpp`. `test_ci_workflows.py`: `ARCANI_REFERENCE_MACHINE` in no workflow and not in `CMakePresets.json`, with three must-fail texts.
- **Matrix coverage** (`test_cli.cpp` unless named): render default; 44.1 kHz; other rate (96000, 22050, 0, 44101); bad option (24 shapes); rejected recipe (`length_s` -1, existing file unchanged); final mode no gain; rounding vectors (`test_wav.cpp`, Python); large file (`test_wav.cpp` header only); speed not reference (unset, `0`, `true`, `yes`); speed reference (`test_report.cpp` pass rule and exit 4 at 19.99; end-to-end case skips unless the test process has `ARCANI_REFERENCE_MACHINE=1`); zero length (header-only, `no frames` with the variable unset and `1`).
- **Open points for the implementer:** (1) Task 4 must clear `pending` on `render-speed`: once the CLI or `test_report.cpp` reads it, `check_row_coverage.py` fails while it is pending. (2) AC 4's end-to-end pass needs one run on the dev PC with `ARCANI_REFERENCE_MACHINE=1` set; elsewhere that case skips. (3) The 4096-frame render loop is not observable from outside (output does not depend on it); Story 1.6 covers block sizes. (4) The include check is enforced through the real-configure pytest case, which CI already runs; a `full.yml` step beside `check_compile_flags.py` is optional. (5) Under clang-cl `/W4 /WX`, `getenv` and `fopen` in `cli/` raise deprecation warnings; the throwaway build defined `_CRT_SECURE_NO_WARNINGS` on the CLI targets (as `tests/assertions` does). (6) `arc_render` refuses a null buffer, so a 0-frame render must not call it with an empty buffer.
- **Red state at hand-off:** clean `windows-clang-cl` workflow builds. `arcani_tests` 140 cases: 124 pass, 15 fail (12 end-to-end CLI cases, "not implemented: cli/wav.hpp", "not implemented: cli/report.hpp", the plan getters), 1 skips (reference speed); `arcani_api_c_header` fails (getters undeclared); the other two ctest entries pass. `uv run pytest`: 1,108 passed, 39 failed (30 include check cases, script missing; 9 flag check `cli/` cases), 2 NDK-only skips. Wording, pragma, flag, row coverage, table log, and `signal_spec_vectors.py --check` exit 0. A throwaway implementation in a copy outside the repo (getters, `cli/` core and main, flag check extension, include checker) passed all 156 C++ cases (the reference case too, with the variable set) and all 141 `tests/cmake` cases. Planted bugs each caught: `nearbyint` quantizer (rounding-mode case), RF64 sampleCount as data bytes, speed checks in the other order, `>` instead of `>=`, any set variable counted as the reference machine, punctuation added to the rejected line, a `.partial` file opened before compile, and an include checker without relative-path or separate-token handling.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-05): blind hunter (BH), edge case hunter (EC), verification gap (VG), all fresh context, on diff 5469dff..824a409 (generated vectors, guidebook, and `_bmad-output` left out).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | BH, EC, VG: an exception after `<out>.partial` opens (bad_alloc in the loop, `row("render-speed")` throwing after `fclose`) leaves the partial file and an open `FILE*` | medium | `cli/main.cpp` `row()` runs after `fclose`; `main`'s catch only prints and returns 3 | patch (row read before the partial opens; guard removes the partial on every exit) |
| 2 | BH: a missing table fails only after the whole render | medium | same site as 1; an 8 h render would be thrown away | patch (folded into 1) |
| 3 | BH, VG: the CLI reads the table from a source-tree path baked in at build time | low | v0.1 is desktop and CI only; the frozen decision names the assertion library; changing it edits the spec | reject (revisit when the CLI ships beyond the dev PC) |
| 4 | BH: the usage-file startup step runs in every CLI launch | low | only acts when `ARCANI_ROW_USAGE_FILE` is set, which only ctest does | reject |
| 5 | BH, EC: concurrent read-merge-write of the usage file can lose ids | low | the parent blocks in `popen` while a child runs; `arcani_tests` is one ctest entry; the other entries never call `row()` | reject |
| 6 | BH, EC, VG: `--report` equal to `--out` or `<out>.partial`, or an output equal to RECIPE, is accepted (report lost with exit 0; recipe replaced) | medium | `parse_args` compares nothing; `fs::rename` replaces the target | patch (usage error, exit 2) |
| 7 | BH, EC: the report is not written atomically; a failure removes a report this run had just overwritten | low | a rerun overwriting its own report is expected; the rename failure is rare | reject |
| 8 | BH: non-ASCII paths fail on Windows (ANSI code page) | low | the repo and output paths on the dev PC are ASCII; the fix is a manifest or wide entry point | reject (note for the designer phase) |
| 9 | BH, VG: no end-to-end test of the report-write failure cleanup | medium | file-errors case covers only an unreadable recipe and a missing WAV dir | patch (test) |
| 10 | BH: the `rejected:` line is not escaped | low | fields come from the engine; `limit` is last and holds spaces by design; the format is a frozen decision | reject |
| 11 | BH: speed times only `arc_render` | false | the story AC says "timed over render calls only" | reject |
| 12 | BH: RF64 not tested end to end; PCM tag 1 instead of EXTENSIBLE; no JUNK chunk | low | header bytes are unit-tested against EBU 3306; tag and layout are frozen decisions | reject |
| 13 | BH: no output data hash in the report | low | not in the story AC; Stories 1.6 and 6.1 own byte comparison | reject |
| 14 | BH: rounding-mode test without `FENV_ACCESS` | low | the pragma check bans that pragma; every quantizer step is exact, so mode cannot change the result | reject |
| 15 | BH: 4096 not checked against row `block-sizes` | low | the row is pending on Story 1.6; output does not depend on block size | reject |
| 16 | BH: no fsync before rename; Ctrl-C leaves a partial; an existing `<out>.partial` is overwritten | low | unlikely in use; fixes add platform code | reject |
| 17 | VG: the reference-machine branch of `main` never runs unskipped | medium | pre-verified gap; the only case skips unless the outer env is set | patch (test) |
| 18 | VG: the usage-file inherit and merge logic is untested | low | pre-verified gap; a bug would hide stale rows on the dev PC | patch (pytest) |
| 19 | EC: an empty `--report` value renders fully, then exits 3 | low | `parse_args` accepts it; a direct check | patch (folded into 6) |
| 20 | EC: an option value that is a flag (`--out --report`) | low | the next pair then lacks a value and gives usage in most shapes; unlikely | reject |
| 21 | EC: a huge recipe is read fully before the 1 MiB cap rejects it | low | a dev tool reading a local file; unlikely | reject |
| 22 | EC: non-finite numbers in `json_number` / `render_speed` with rate 0 or elapsed 0 | false | compile rejects any rate but 44100 and 48000; elapsed is at least 1 tick | reject |
| 23 | EC: `ARCANI_ROW_USAGE_INHERITED` set in the outer shell stops truncation | low | nothing sets it outside the library; unlikely | reject |
| 24 | EC: the include check misses `--include-directory`, `-cxx-isystem`, `-iwithprefix`, `-internal-isystem` | low | a direct list addition | patch |
| 25 | EC claim: an existing WAV is touched before the rename | medium | true only when `--report` equals `--out` | patch (folded into 6) |
| 26 | EC claim: threshold written from the parsed double, not the row text | low | the table format allows only plain decimals, whose shortest round-trip equals the text for every current row | reject |

- Review pass 1 patches in 06d535f (triage rows 1, 2, 6, 9, 17, 18, 19, 24, 25). Orchestrator check: `windows-clang-cl` workflow 4/4 ctest entries pass; `arcani_tests` 158 cases pass with `ARCANI_REFERENCE_MACHINE=1`; `uv run pytest` 1,155 passed, 2 NDK-only skips; wording, pragma, compile flag, CLI include, row coverage, and table log checks exit 0. Nothing deferred.
