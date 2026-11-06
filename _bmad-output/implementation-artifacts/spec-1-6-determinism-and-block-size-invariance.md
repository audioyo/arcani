---
title: 'Story 1.6: Determinism and block-size invariance'
type: 'feature'
created: '2026-11-06'
status: 'in-review'
baseline_commit: '9f2425b6284ff3f5bac4ceeaf205d3d7510187b2'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Nothing proves a render is byte-identical across repeat runs or host block sizes. The symbol denylist does not cover randomness, `fma`, or quad-precision helpers, and does not look at the WAV writer. Constant-folded libm calls, `long double`, and `L` literals leave no symbol. And `ci/hash_expected.json` pins only `probe-arith`, so a toolchain change that shifts every platform alike still passes.

**Approach:** Add determinism and block-size tests that read their rows from the tables, extend the symbol check and add an engine source scan (each with must-fail fixtures), and pin the sine and stub chain hashes.

Decisions (2026-11-06, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Block sizes:** row `block-sizes` becomes `1 64 512 4096 997` (997 is the AC's odd size, a prime that never lines up with the 64-frame internal block). The md "Block-size invariance" line and design log (kk) are updated to match. No other row changes; `pending` is cleared on `determinism`, `block-sizes`, and `block-size-invariance`.
- **In-process tests (`tests/cpp/test_determinism.cpp`):** for the beat-0 and beat-6 stub chain fixtures at 44.1 and 48 kHz, build the full WAV bytes in memory (`cli::wav_header` + `cli::append_samples`, public header only) at every `block-sizes` member. Count differing bytes against the 4096-frame bytes; pass when the count is at most row `block-size-invariance`. Two compiles and renders in one process: count against row `determinism`. Must-fail: a harness copy with one doctored byte, and one with a frame dropped, both fail.
- **Separate processes (`tests/cpp/test_cli.cpp`):** `arcani-render` run twice on the same recipe and rate gives byte-identical WAVs (row `determinism`). The report's `determinism_key` has exactly `recipe_hash`, `asset_hashes` (empty), `engine_version`, and `sample_rate`. It is equal across block sizes and separate runs, and changes when the rate changes.
- **Denylist families (`tools/engine_symbol_denylist.json`):**
  - `randomness`: `rand`, `srand`, `rand_r`, `rand_s`, `random`, `srandom`, `initstate`, `setstate`, the `rand48` family, `arc4random*`, `getrandom`, `getentropy`, `BCryptGenRandom`, `SystemFunction036`, `CryptGenRandom`, `ProcessPrng`, and C++ `std::random_device` and `std::_Random_device` forms.
  - `fused multiply-add`: `fma`, `fmaf`, `fmal`.
  - `quad precision`: the AC's compiler-rt `tf` helpers plus `__negtf2` and `__powitf2`.
  - Time-based seeding is the existing `clock` family.
- **WAV writer:** the checker also checks `arcani_cli_core` (wav.cpp, report.cpp) against the `randomness` and `clock` families only. Its path goes into `arcani_engine_check.json` as `wav_writer_library`. A test-only cache variable `ARCANI_CLI_TEST_EXTRA_SOURCE` mirrors the engine one and is never set in presets or CI.
- **Source scan (`tools/check_engine_source.py`, default `engine/`):** comments and string literals are stripped first, so `sine` and comment text pass. It fails on `long double`, `L`/`l`-suffixed float literals (decimal and hex; integer `10L` passes), any `<cmath>` transcendental or `fma` name used as a call (bare, `std::`, `::`, or `__builtin_`), and `#include <random>`. `sqrt` passes. Each failure prints `path:line: text: reason`. It runs in both fast jobs and every full job next to `check_fp_pragmas.py`.
- **Real-build must-fails:**
  - one engine fixture with runtime calls to `rand`, `std::random_device`, and `std::fma`, plus `__float128` arithmetic under `#if defined(__SIZEOF_FLOAT128__)`;
  - one CLI fixture calling `rand`.
  - On x86-64, `fma` stays a libcall: there is no `-mfma`, and arm64 runs no real-build symbol tests. The quad helper is asserted only where the compiler defines `__SIZEOF_FLOAT128__`; synthetic nm rows cover every pattern.
- **Hash entries:** `ci/hash_expected.json` gains `sine-44100`, `sine-48000`, `stub-chain-44100`, `stub-chain-48000` (full run 42236304155, all four platforms equal). It also gains new probe components `stub-chain-blocks-44100` and `stub-chain-blocks-48000`: the same recipe rendered in calls cycling through the `block-sizes` members, which must equal the one-call hashes. This proves block-size invariance on Android, which runs no ctest. The probe embeds the sizes, and a pytest checks them against the row.
- **Contract must-fail:** an entry gains `"scope": "probe"` or `"engine"`. `--must-differ` requires every `probe` component to differ (only `probe-arith`) and every `engine` component to equal its entry, since the extra flags reach only the probe file.

## Boundaries & Constraints

**Always:** Tests first by a fresh-context QA agent, committed failing. Every new denylist pattern gets a synthetic nm row. Every source-scan rule gets a must-fail file under `tests/fixtures/engine_source/mustfail/`, and a clean file holds the near-misses (`sine(`, `sqrt(`, `10L`, a comment naming `sin(` and `long double`). The real `engine/` scans clean. All existing checks keep passing.

**Never:** Fault-injection code in `engine/` or `cli/` sources. A determinism assertion in the CLI report. The env/locale family or the CI enforcement of the narrowed fallback (they stay deferred). Weakening any row. Pushing or opening the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Block sizes | each fixture and rate, each row size | 0 differing bytes | doctored byte or dropped frame fails |
| Repeat | two renders, one process and two processes | identical WAVs | N/A |
| Denied symbol | nm text or real build with a denied name | exit 1, names symbol and family | N/A |
| WAV writer | `rand` in cli_core | exit 1, family randomness | `fopen` in cli_core passes |
| Source scan | `long double`, `1.0L`, `std::sin(`, `__builtin_exp(`, `fma(`, `#include <random>` | exit 1, file and line | `sine(`, `sqrt(`, `10L`, comments pass |
| Contracted probe | probe-arith differs, engine components equal | exit 0 | an engine component differing fails |

</frozen-after-approval>

## Code Map

- `tools/engine_symbol_denylist.json`, `tools/check_engine_symbols.py` (`normalize_c_name` strips one `_`, so Mach-O `___addtf3` arrives as `__addtf3`), `tests/cmake/test_engine_symbols.py` (`DENIED`, `configure_and_build_engine`, the fixture pattern at `FENV_FIXTURE`).
- `engine/CMakeLists.txt:89` writes `arcani_engine_check.json`; check `tests/cmake/test_compile_flags.py` for an exact key list. `cli/CMakeLists.txt` has the `arcani_cli_core` target.
- `tools/check_fp_pragmas.py` + `tests/python/test_fp_pragmas.py` + `tests/fixtures/fp_pragmas/`: the pattern for the new scanner. `.github/workflows/fast.yml:98,197` and `full.yml:163,276,381,480` show where it runs. `tests/python/test_ci_workflows.py` may pin the step lists.
- `tests/hashprobe/main.cpp` (`probe_stub_chain`, the "expected entries stay with Story 1.6" comment), `tools/hash_compare.py` `must_differ` (line 284), `tests/python/test_hash_compare.py` (must-differ tests at 509, expected-file test at 681), `ci/hash_expected.json`.
- `tests/cpp/api_helpers.hpp`, `tests/cpp/cli_helpers.hpp`, `tests/cpp/test_cli.cpp:297` `check_report_members` (asset_hashes already checked empty), `tests/cpp/test_seek.cpp:113` (the uneven-chunk pattern), `tests/cpp/CMakeLists.txt`.
- `tests/tables/thresholds.tsv` rows 16, 19, 20; `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md:21`; `docs/design-log.md` (new entry (kk) on top, plus the decision table rows); `_bmad-output/implementation-artifacts/deferred-work.md` (mark the `sine-*` expected entry, the cli-denylist part, and nothing else as closed).
- Do not change `engine/src/` (no code change is expected; any change found needed goes in Implementation Notes first).

## Tasks & Acceptance

**Execution:**
- [x] `tests/cpp/test_determinism.cpp`, `test_cli.cpp`, `tests/cmake/test_engine_symbols.py`, `tests/python/test_engine_source.py`, `tests/fixtures/engine{,_source,/cli}/`, `test_hash_compare.py`, probe cross-check test -- QA agent writes failing tests -- tests first.
- [x] `tools/engine_symbol_denylist.json`, `check_engine_symbols.py`, `check_engine_source.py`, CMake extra-source and check-JSON key, `tests/hashprobe/main.cpp`, `tools/hash_compare.py` -- implementation.
- [x] `thresholds.tsv`, md, `ci/hash_expected.json`, workflows, design log (kk), deferred-work -- records and CI.
- [x] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given each stub chain fixture at both rates, when rendered at every `block-sizes` member and twice in one process, then the WAV bytes differ in 0 bytes.
- Given `arcani-render` run in two processes, then the WAVs are byte-identical and the determinism key is recipe hash + empty assets + engine version + sample rate.
- Given the real engine build, then the symbol check and the source scan pass. Given each must-fail fixture, then each fails and names the file and line or the symbol and its family.
- Given the hash probe, then `stub-chain-blocks-*` equals `stub-chain-*`, and every component has an expected entry that the windows-x64 build matches locally.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass.
- `uv run --no-project python tools/check_engine_source.py`, `tools/check_fp_pragmas.py`, `tools/check_wording.py`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.
- Local hash probe plus `tools/hash_manifest.py`, then `tools/hash_compare.py --must-differ` semantics checked by its tests -- expected: the windows-x64 manifest equals `ci/hash_expected.json` for every component.

## Implementation Notes

### QA agent, tests-first pass (2026-11-06)

Settled test-side choices (each contract is pinned in the test file's docstring or header comment):

- **In-process (`tests/cpp/test_determinism.cpp`, new `tests/cpp/determinism_helpers.hpp`, added to `tests/cpp/CMakeLists.txt`):** `differing_bytes(a, b)` counts differing positions plus the length difference, so a dropped frame always counts. The row check requires 1, 64, 512, 4096 and at least one odd member above 1; it does not hard-code 997. WAV bytes are `cli::wav_header` plus `cli::append_samples` after each `arc_render` call. The dropped-frame must-fail rebuilds the header for frames - 1.
- **Separate processes (`test_cli.cpp`, two new cases):** two runs per fixture and rate, compared against row `determinism`. The key is checked for its exact members, `recipe_hash|0|engine_version|rate`, equality across runs, and change with rate. The CLI always renders in 4096-frame calls, so "equal across block sizes" is tested by comparing the CLI WAV with the in-process render (harness rounding) at every `block-sizes` member, against row `block-size-invariance`.
- **Symbol check (`tests/cmake/test_engine_symbols.py`):** family names `randomness`, `fused multiply-add`, `quad precision`. New CLI option `--wav-writer-nm-output FILE` (randomness and clock only). `BUILD_DIR` mode fails when `wav_writer_library` is absent or names no file. Real builds now build `arcani_engine arcani_cli_core`. Fixtures: `tests/fixtures/engine/calls_rand_fma_quad.cpp` (defines the marker `arc_test_float128_present` under `__SIZEOF_FLOAT128__`; the quad line is required only when llvm-nm lists that marker) and `tests/fixtures/engine/cli/calls_rand.cpp`. Quad patterns must accept both `__addtf3` and Mach-O `___addtf3` after `normalize_c_name` (so `__?addtf3`, not `_addtf3`).
- **Source scan (`tests/python/test_engine_source.py`, `tests/fixtures/engine_source/`):** 14 must-fail files, one violation each, plus 2 clean files (one with a raw string). The reason vocabulary is pinned: `long double`, `long double literal`, `transcendental call`, `fused multiply-add call`, `random header`. `<text>` is the original line, stripped. The scanner uses the same suffix set as `check_fp_pragmas.py`. Workflow tests require the scan in both fast jobs and in every full job that runs `check_fp_pragmas.py`.
- **Hash compare (`test_hash_compare.py`):** in must-differ mode a missing, empty, or unknown `scope` fails (case-sensitive), a missing or short engine component fails, and so does a run with no probe component. Compare mode ignores scope. The real-file test pins exactly seven entries and their sample counts, and requires `stub-chain-blocks-*` to equal `stub-chain-*`.
- **Probe (`tests/python/test_probe_determinism.py`, new):** the probe source holds exactly one `constexpr std::size_t kBlockSizes[] = {...};`, equal in order to the row. `stub-chain-blocks-<fs>.f32` must equal `stub-chain-<fs>.f32`. The set of probe components must equal the set of expected entries. A windows-x64 host must match every entry; other hosts skip that one test.
- **Outside the code map:** `test_probe_sine.py` had two "no sine or stub-chain entry yet" tests that contradict this story, so I replaced them with entry tests. `test_probe_reference.py::test_write_then_check` now expects `--write` to emit `"scope": "probe"`. That means `tools/probe_reference.py` (not in task 2's list) needs a one-line change, or `--write` drops the scope and must-differ breaks.

Red state at hand-off (ctest: 1 failure in 168 cases; pytest: 189 failed, 1215 passed, 2 skipped, all failures in new or changed tests):

- ctest `row block-sizes holds ... an odd size`: the row has no 997 yet. The other new C++ cases already pass, because the engine is already deterministic.
- `test_engine_symbols.py`: 91 new synthetic rows (families missing), the 12 WAV-writer synthetic cases (unknown option), `test_cli_cmake_declares_the_test_only_extra_source`, the check-JSON key, both real-build must-fails (the CLI variable is ignored, and the engine build has the new symbols but no family), and the two missing-key or missing-library cases.
- `test_engine_source.py`: the whole file fails because there is no `tools/check_engine_source.py`, and no workflow step runs it.
- `test_hash_compare.py`: the scope cases and the real expected-file test.
- `test_probe_determinism.py`, `test_probe_sine.py` (entries), `test_probe_reference.py` (scope on write).
- After ctest and pytest record their row usage, `tools/check_row_coverage.py` will flag `determinism`, `block-sizes`, and `block-size-invariance` as used but still pending, until task 3 clears them.

Throwaway proof (a copy of the working tree in the system temp folder, not in the repo):

- I implemented minimal versions of the denylist families, the WAV-writer option and key, the CLI extra-source variable, a source scanner, must-differ scopes, the `kBlockSizes` probe components, and the 997 row.
- Results: `test_engine_symbols.py` 357 passed, including the real clang-cl builds (rand, `std::_Random_device`, and fma all named). `test_engine_source.py` passed except the workflow cases. `test_hash_compare.py` passed except the real-file case, which needs the CI hashes. `test_probe_determinism.py` block equality passed. ctest passed 100% with the 997 row.
- Planted bugs in the scanner (hex-literal branch removed, `__builtin_` form removed) each failed 4 or 5 tests.

### Build agent, implementation pass (2026-11-06)

- No change to `engine/src/` was needed: every new C++ case passed before implementation, and the real `engine/` scans clean.
- `tools/probe_reference.py --write` now writes `"scope": "probe"` (the one-line change the QA notes named).
- `tools/hash_compare.py --must-differ` now walks the expected entries, not the manifest: an expected entry with no data file fails, whatever its scope. The contract-mustfail job builds with `linux-clang`, so the engine components there must equal the windows-x64 hashes; this holds today (bit-exact engine) but is first exercised by this PR's full run.
- The randomness family also lists `RtlGenRandom` (the documented name of `SystemFunction036`) and the `_r` forms of the `rand48` family; the `arc4random` pattern covers `_uniform`, `_buf`, `_stir`, and `_addrandom`.
- `ci/hash_expected.json` hashes come from the full run 42236304155 manifests (all four platforms equal) and match the local windows-x64 probe; `source` now says so.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-06): blind hunter (BH), edge case hunter (EC), verification gap (VG), all fresh context, on diff 9f2425b..62bf4e9 (guidebook and `_bmad-output` left out).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | BH, EC, VG: fma real-build must-fail asserts an `fma` symbol on every host | high | `test_engine_symbols.py:705` is unconditional; windows-arm64 and macos-arm64 full jobs run the full pytest with cmake, where `std::fma` lowers to `fmadd` and leaves no symbol | patch |
| 2 | BH: quad must-fail never runs where binary128 `long double` exists (Linux or Android arm64) | low | no test host is aarch64 Linux; the synthetic nm rows cover every pattern | reject |
| 3 | BH: source scan misses hardware randomness and timer intrinsics (`_rdrand*_step`, `_rdseed*_step`, `__rdtsc`, `__builtin_readcyclecounter`, `__rndr`) | medium | they compile to instructions, so no symbol exists; the intent bans every unseeded randomness source | patch |
| 4 | BH: `<random>` engines and distributions banned only by the include line | low | header-only templates leave no symbol and could arrive through a transitive include; adding the names to the scan is a direct addition | patch (with 3) |
| 5 | BH, EC: scan misses extended precision types (`__float128`, `_Float128`, `__float80`, `__ibm128`, `_Float64x`) | medium | folded or inline arithmetic on them leaves no `tf` symbol, the same reason `long double` is scanned | patch |
| 6 | BH, EC: scan transcendental list misses C++17 special math, Bessel `j0`..`yn`, `lgamma_r`, `sinpi`/`cospi`/`tanpi`, `sincospi` | medium | `TRANSCENDENTALS` in `check_engine_source.py` is shorter than the libm family; a folded special-math call passes both checks | patch |
| 7 | BH, EC, VG: member calls (`obj.log(`, `p->exp(`) fail as transcendental calls | low | the lookbehind rejects only a word character; direct correction to the lookbehind | patch |
| 8 | VG, EC: `(std::sin)(x)` or a macro alias bypasses the scan | low | unlikely in engine code; the fix adds a broader rule | reject |
| 9 | BH: WAV writer not checked for fenv; source scan does not cover `cli/wav.cpp` | low | the frozen decision fixes the WAV writer families at randomness and clock; the flag check already covers `cli/` | reject |
| 10 | BH, EC: WAV writer family filter passes silently if a family is renamed | low | needs a family rename in the JSON; the fix adds a guard branch | reject |
| 11 | BH: no stated way to update the engine-scope pins when Epic 2 changes the stub chain | medium | `probe_reference.py --write` rewrites only `probe-arith`; nothing says the source or approval for the other pins | patch (design log) |
| 12 | BH, EC: contract job requires engine equality on linux-arm64, not one of the four proven platforms | maybe-false | settled by this PR's full run; if it differs, the engine has a Core zone mismatch, which AD-9 calls a bug | CI gate before merge |
| 13 | BH: must-differ ignores manifest components with no expected entry | low | `test_every_probe_component_has_an_expected_entry` guards it wherever cmake runs, which includes CI | reject |
| 14 | BH: block-size invariance not tested after a seek | false | `tests/cpp/test_seek.cpp:113` seeks to 37 and renders in chunks 1, 26, 64, 65, 1, 4000 against the full render | reject |
| 15 | BH: determinism evidence uses only 1 s fixtures | low | long-session drift is Story 5.1; the engine output is a pure function of the sample index | reject |
| 16 | BH: two-process test varies no locale or environment | low | the env and locale family is deferred by the intent | reject |
| 17 | BH: CLI block-size comparison uses only beat-6 | low | `test_cli.cpp:816`; direct change to loop both fixtures | patch |
| 18 | BH: odd-size check and the "prime" rationale do not match | low | the property that matters is a member above 64 that is not a multiple of 64; direct test and text correction | patch |
| 19 | BH: `#else` fallback in `test_determinism.cpp` is dead scaffolding | low | `ARC_ERROR_FIELD_BYTES` is defined in `arcani.h:34`; deletion | patch |
| 20 | VG: probe block components cannot show they came from cycled calls | medium | a loop bug that renders in one call passes every equality and pin check; closing it needs a probe output change | defer |
| 21 | EC: must-differ traceback when a manifest component is not an object | low | needs a hand-made bad manifest; the fix adds a guard | reject |
| 22 | EC: `arc_error e;` uninitialized in `determinism_helpers.hpp:48` | low | read only on the failure path; direct correction `arc_error e{};` | patch |
| 23 | EC: non-integer `block-sizes` value truncated | low | the table loader and row are integers; the fix adds a guard | reject |
| 24 | EC: determinism key equality across block sizes never measured | low | `arcani-render` has no block-size input, and the key comes from the plan only | reject |

- Review pass 1 patches in 6e39e7f (triage rows 1, 3 to 7, 11, 17 to 19, 22). Row 20 deferred to `deferred-work.md`. Row 12 is settled by this PR's full run before merge. Orchestrator check: `windows-clang-cl` workflow 4/4 ctest entries pass; `uv run pytest` 1,419 passed, 2 NDK-only skips; engine source, pragma, wording, vector, row coverage, and table log checks exit 0.
