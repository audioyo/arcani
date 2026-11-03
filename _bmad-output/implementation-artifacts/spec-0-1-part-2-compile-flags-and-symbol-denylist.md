---
title: 'Story 0.1 part 2: engine compile flags and undefined-symbol denylist'
type: 'chore'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'a74a04364cffccff32938df66f3a64b0f3251d71'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** AD-9 bit-exactness needs `-ffp-contract=off`, no fast-math, and no libm, file, thread, clock, or console calls in `engine/`. Part 1 sets none of the flags and checks none of this, so the first DSP code could break cross-platform hashes unnoticed.

**Approach:** Set the AD-9 flags in CMake for the whole project, plus warnings as errors on engine and CLI. Add two stdlib-only Python checkers, run from pytest on every fast-tier job and locally: one reads the build's `compile_commands.json` for every `engine/` source, the other runs the pinned `llvm-nm` on the built engine library against a denylist data file. Each has a passing case and a must-fail case on a real configure or build.

Decisions (2026-11-02): part 2 of the Story 0.1 split (Audio). Reproducible-binary flags (`/Brepro`, `-ffile-prefix-map`) are out: no requirement asks for identical binaries, only identical output; logged in `deferred-work.md`. `sqrt` stays allowed: IEEE 754 rounds it correctly on every target (spine review-freshness).

## Boundaries & Constraints

**Always:**
- Flags: clang `-ffp-contract=off`; clang-cl `/clang:-ffp-contract=off`; it comes after any other fp option on the command line. Warnings: clang `-Wall -Wextra -Werror`, clang-cl `/W4 /WX`, on `arcani_engine` and `arcani-render` only.
- Flag check fails, naming toolchain (for example `clang-cl 23.1.4`), source file, and flag, when an `engine/` source's last `-ffp-contract` value is not `off`, or any fast-math flag appears (`-ffast-math`, `-Ofast`, `-ffp-model=fast|aggressive`, `-funsafe-math-optimizations`, `-fassociative-math`, `-freciprocal-math`, `-ffinite-math-only`, `-fno-honor-nans`, `-fno-honor-infinities`, `-fno-signed-zeros`, `-fapprox-func`, `-fcx-limited-range`, `/fp:fast`; each also behind `/clang:`). Zero `engine/` sources or an `@` response file also fail.
- Symbol check fails naming each denied symbol and its family. Families: libm transcendentals with `f` and `l` variants (trig, inverse and hyperbolic trig, exp, exp2, expm1, log, log2, log10, log1p, pow, cbrt, hypot, erf, erfc, tgamma, lgamma, sincos), file, thread, clock, console. It matches raw names after stripping `__imp_` and one leading `_`, and demangled C++ names (for example `std::cout`, `std::thread`, `std::chrono::*::now`, `std::basic_ofstream`). Windows UCRT internals count (`__stdio_common_*`, `__acrt_iob_func`, `_Thrd_*`, `_Mtx_*`, `_Xtime_get_ticks`, `_Query_perf_*`).
- `llvm-nm` is found only next to the pinned compiler; if it is missing there, configure fails.
- Tests first: a fresh-context QA agent writes failing tests, committed tests-only before implementation. No fault-injection code in `engine/`.
- No em dashes; CLAUDE.md "Never" terms stay out.

**Never:**
- Part 3 work (arm64, macOS, Android, hash compare, wall-time budget, nightly). Unseeded-randomness denylist entries (Story 1.6 adds them).
- Weakening a pattern so the current repo passes. Pushing without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Flags pass | preset configure, `ARCANI_BUILD_TESTS=OFF` | flag check exit 0 | N/A |
| Fast-math | configure with `CMAKE_CXX_FLAGS` `-ffast-math` (`/clang:-ffast-math` on Windows) | exit 1 | names toolchain, file, `-ffast-math` |
| Contract missing or overridden | synthetic compile command without the flag, or `=off` then `=fast` | exit 1 | names toolchain, file, flag |
| Symbols pass | build `arcani_engine` target | symbol check exit 0 | N/A |
| `std::sin` in engine | build with test-only cache variable `ARCANI_ENGINE_TEST_EXTRA_SOURCE` = `tests/fixtures/engine/calls_std_sin.cpp` | exit 1 | names `sin`, family libm transcendental |
| Each family | synthetic `llvm-nm` output, Linux and Windows forms | exit 1 per denied name; `sqrt`, `floor`, `memcpy` pass | names symbol and family |

</frozen-after-approval>

## Code Map

- `CMakeLists.txt` -- top-level; add the fp flag with `add_compile_options` after the language settings, before `add_subdirectory` and Catch2. Set `CMAKE_EXPORT_COMPILE_COMMANDS ON`.
- `cmake/Pins.cmake` -- reuse its pattern for test-only cache variables (`ARCANI_PIN_OVERRIDE_*`): documented header, never set in presets or CI.
- `engine/CMakeLists.txt` -- add warnings, the `ARCANI_ENGINE_TEST_EXTRA_SOURCE` hook, `find_program` for `llvm-nm` with `HINTS` the compiler directory and `NO_DEFAULT_PATH`, and `file(GENERATE)` of `build/<preset>/arcani_engine_check.json` with toolchain name and version, library path (`$<TARGET_FILE:arcani_engine>`), `llvm-nm` path, and `compile_commands.json` path.
- `cli/CMakeLists.txt` -- add warnings.
- `tests/cmake/test_pin_check.py` -- pattern for real preset configures into `tmp_path`: skip only if cmake is missing. Windows needs the VS environment for a real compile: wrap the command as `powershell -NoProfile -File tools/dev.ps1 cmake ...` on win32. Leave this file unchanged.
- `.github/workflows/fast.yml` -- already runs `uv run --locked pytest` on both jobs after the build; no change expected.
- `docs/design-log.md` -- next entry letter is (z); add a Current state row.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- append the reproducible-binary-flags entry.

## Tasks & Acceptance

**Execution:**
- [x] `tests/cmake/test_compile_flags.py`, `tests/cmake/test_engine_symbols.py`, `tests/fixtures/engine/calls_std_sin.cpp` -- QA agent: synthetic unit cases for every matrix row and family, plus real configure or build cases (share one configure per case through module fixtures). The fixture takes a non-constant argument so the call is not folded.
- [x] `tools/check_compile_flags.py`, `tools/check_engine_symbols.py` -- CLIs taking the build directory; read `arcani_engine_check.json`; exit 0 or 1 with one line per violation.
- [x] `tools/engine_symbol_denylist.json` -- families of regex patterns, split into C-name and C++-name lists.
- [x] `CMakeLists.txt`, `engine/CMakeLists.txt`, `cli/CMakeLists.txt` -- flags, hook, `llvm-nm`, check json.
- [x] `docs/design-log.md` -- entry (z): AD-9 flags set, warning flags, denylist families, `sqrt` allowed, reproducible-binary flags deferred.
- [x] `deferred-work.md` -- append the reproducible-binary-flags entry.

**Acceptance Criteria:**
- Given a clean checkout, when `uv run pytest` runs locally or in the fast workflow, then both checkers pass on the real preset build and both must-fail cases fail with the named toolchain, flag, or symbol.
- Given a later engine source that calls a denied function or a build that drops `-ffp-contract=off`, when the fast tier runs, then it fails naming the toolchain and flag or the symbol.
- Given the existing engine, CLI, and tests, when built with the new flags, then they build with no warnings and all part 1 tests still pass.

## Implementation Notes

- Failing tests committed in e686f5b (QA agent); their docstrings define the contracts. Make them pass; never edit them to pass.
- Dev PC: `C:\Program Files\LLVM\bin` was not on the user or machine PATH; added to the user PATH on 2026-11-02 at Audio's go-ahead (new shells only). In an older shell, prepend it plus `C:\Users\goegl\.local\opt\cmake-4.4.5-windows-x86_64\bin` and `C:\Users\goegl\.local\bin`.
- Review pass 1 patches (findings 1, 2, 3, 8, 9, 10, 11, 14, 22, 23): clang-cl `/clang:` ordering and fp-model reset rule, response file behind `/clang:` or `-Xclang`, posix tokenizing on Linux, value-changing fp options, `lgamma[fl]?_r` and wider denylist, llvm-nm search order, CMake comment. Local: pytest 342 passed, 0 skipped; clean `windows-clang-cl` workflow build, no warnings, ctest 1/1; both checkers pass on the build dir. Module scanning turned off (`CMAKE_CXX_SCAN_FOR_MODULES OFF`) because its `@` modmap file hides flags. Fast run 41578714584 on f9159fd passed on windows-x64 and linux-x64, so the Linux job and the Windows CI `llvm-nm` are verified.

## Spec Change Log

## Review Triage Log

Review pass 1 (blind B, edge-case E, verification-gap V layers).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | Reset rule: any `/fp:` or `-ffp-model=` after contract off fails; untested (V, B, E) | medium | `clang-cl -###` shows `/clang:` args move after `/fp:`, so `/clang:-ffp-contract=off /fp:precise` gives `off`; `/fp:strict`, `/fp:except`, `-ffp-model=strict` keep `off`; only clang `-ffp-model=precise` after gives `on`. Checker fails all of them; no test | patch |
| 2 | `lgamma_r` regex misses real `lgammaf_r`, `lgammal_r`; many denylist alternatives untested (V) | medium | regex puts `[fl]?` after `_r`; reviewer ran the checker | patch |
| 3 | Checker parse paths untested: `-Xclang`, `-clang:`, `-fp:fast`, `arguments` form (V, B) | low | unreachable with Ninja today, but tests are cheap beside 1 | patch (with 1) |
| 4 | Checks run only from pytest, not ctest or the build (B) | false | spec intent puts them in pytest, which CLAUDE.md fast tests and both CI jobs run | reject |
| 5 | Real-build tests can skip silently if cmake is missing (B, E) | low | CI installs cmake before pytest; same pattern as part 1 pin test | reject |
| 6 | Engine sources picked by path, not target (B, E) | low | flags are project-wide; no generated or out-of-tree engine source exists or is planned; fix adds a branch | reject |
| 7 | Source pragmas (`#pragma clang fp contract`, `STDC FP_CONTRACT`, `float_control`) not checked (B, E) | medium | real way to re-enable contraction with clean flags; no engine source has one; new check beyond this change | defer |
| 8 | Other value-changing flags not caught: `-fdenormal-fp-math=`, `-mdaz-ftz`, `-fcomplex-arithmetic=basic`, `-mrecip`, `-fveclib=`, `-mfpmath=387`, cc1 `-mreassociate`, `-menable-no-nans`, `-menable-no-infs` (B, E) | low | each changes output bits; adding to the flag set is a direct data change | patch |
| 9 | Checker tokenizes with `posix=False` on Linux (B, E) | low | single-quoted or escaped tokens split wrong on Linux; one-line correction | patch |
| 10 | Response file behind `/clang:@file` or `-Xclang @file` not caught (E) | low | check tests `token`, not `bare`; one-line correction | patch |
| 11 | Denylist gaps: sinpi family, Bessel, complex `c*` functions, `__std_smf_*`, vector libm `_ZGV*`; glibc `__isoc99_*`/`__isoc23_*` scanf, `*_chk` printf; MSVC `__std_fs_*`, `_Smtx_*`, `__std_atomic_wait*`, `WaitOnAddress`, `__libcpp_atomic_wait`, `sched_yield`; `localtime`, `gmtime`, `mktime`, `ctime`, `asctime`, `strftime`, `tzset` (B, E) | medium | each is a real lowering of std library calls that passes today, against AC 2 | patch |
| 12 | `__stdio_common_*` denies buffer formatting on Windows only (B, E) | low | real asymmetry, but the frozen intent names `__stdio_common_*`; fix edits the spec | reject |
| 13 | Engine-internal `U` names checked against the denylist (B, E) | low | needs an engine function named like a libc call or taking `std::thread`; fix adds a second nm pass | reject |
| 14 | `llvm-nm` HINTS search symlink dir before resolved dir (B, E) | low | CI compiler is in the pinned LLVM bin either way; swapping the order is a direct correction | patch |
| 15 | Multi-config generator breaks `file(GENERATE)` (E) | low | presets use single-config Ninja only | reject |
| 16 | `engine_library` JSON value not escaped (B, E) | low | `$<TARGET_FILE>` gives forward slashes; quote in build path unlikely | reject |
| 17 | Test-only cache variable sticks in a build dir (B, E) | low | used only in pytest temp dirs; fix adds a guard | reject |
| 18 | Guard test misses `CMakeUserPresets.json`, `.yaml` workflows (B, E) | low | neither exists; unlikely | reject |
| 19 | Relative `file` with no `directory` skipped (E) | false | compile_commands entries always carry `directory` (CMake writes it) | reject |
| 20 | Environment and locale reads (`getenv`, `setlocale`, `std::locale`) not denied (B) | medium | can change engine results by host; not one of the five spec families | defer |
| 21 | CLI not flag-checked though WAV writing will affect output bytes (B) | low | flags are project-wide and a test asserts `cli/main.cpp` has them; matters once the WAV writer lands | defer |
| 22 | CMake comment says the trailing flag "wins over any earlier fp option" (B) | low | it restores contraction only, not other fast-math effects; comment fix | patch |
| 23 | Test docstring family list omits `exp10`, `lgamma_r`, `_finite`, `stret` (B) | low | covered by the tests added under 2 | patch (with 2) |
| 24 | Design log test result has no Linux run (B) | low | Linux runs only on push; record after the fast run | reject |
| 25 | Deferred-work entry not in the diff (B) | false | diff excluded `_bmad-output/`; entry exists in `deferred-work.md` | reject |

## Design Notes

Checking `compile_commands.json` tests the commands Ninja really runs, including flags from `CMAKE_CXX_FLAGS`, so the fast-math must-fail case needs only a configure. Real configures use `ARCANI_BUILD_TESTS=OFF`, so Catch2 is not fetched. Part 3 adds presets; then both test files parametrize over the presets the host can run.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass, including the new must-fail cases.
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: configure and build pass; ctest may be blocked locally by Smart App Control (part 1 finding 20), so C++ tests are confirmed on GitHub.
