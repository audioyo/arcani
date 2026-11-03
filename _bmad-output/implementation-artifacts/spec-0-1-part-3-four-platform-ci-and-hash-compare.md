---
title: 'Story 0.1 part 3: four-platform full tier, hash compare tool, wall-time budget, nightly skip'
type: 'chore'
created: '2026-11-02'
status: 'review'
baseline_commit: 'a6d512aff76740da56c1f38711f8621ea80a69e8'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** AD-9 needs proof that one build gives identical output bytes on Windows x64, Windows arm64, macOS arm64, and Android NDK arm64. Today CI covers only Windows x64 and Linux on push, has no hash compare, no time budget, and no nightly run, so Story 0.2's sine spike has nothing to prove itself on.

**Approach:** Add a `full` workflow (pull request into main, nightly, manual) that builds and tests on all four platforms, runs a host-side hash probe on each, and compares the results with a new stdlib-only Python tool. A final verdict job fails the run when any job, the Android one included, did not succeed, except a nightly skip. Every job, fast and full, checks its wall time against a budget table in the repo.

Decisions (2026-11-02, Audio): part 3 of the Story 0.1 split; one change, not split further (spec about 3,000 tokens). Independent spec review fixes accepted 2026-11-02 (expected-hash check, Python-side hashing, reference platform, float64 bound, NDK API level, exact runner labels, testable gate and verdict).
- No Android phone for now. The NDK arm64 build runs as a static binary on GitHub's free hosted arm64 Linux runner: real arm64 hardware and the real NDK compiler, without the Android OS, which the engine never touches. This is the epic's "chosen alternative", recorded in the design log; running on a physical phone is a deferred-work entry for when one is available.
- No self-hosted runner in part 3. Windows x64 full tier runs on GitHub-hosted `windows-2025` (Smart App Control on the dev PC blocks test binaries). The epic's PC runner layout is superseded by a design log entry.
- Nightly at 03:00 UTC (9 pm Audio's time).

## Boundaries & Constraints

**Always:**
- Hash probe: a test-only C++ binary under `tests/hashprobe/` (not `engine/`), built with the project flags, writing one raw little-endian float32 file per component. No hashing in C++: a stdlib Python step on the host (`tools/hash_manifest.py`) writes `manifest.json` (platform, toolchain id and version from the build's `arcani_engine_check.json`, per component: sample count, SHA-256). Part 3 component `probe-arith`: a fixed sequence of float32 multiplies and adds whose bits change if contraction or fast-math is on. Its expected SHA-256 comes from a Python float32 reference (numpy, each operation rounded separately) and is stored in `ci/hash_expected.json`; every platform must match it, so four identically wrong results fail. A must-fail run builds the probe with `-ffp-contract=fast` on an arm64 job and must differ from that hash. On Android it links statically. Story 0.2 adds the engine sine to the same binary.
- Compare tool, exact mode: `windows-x64` is the reference platform; every other platform is compared against it, and every platform against `ci/hash_expected.json` where a component has an entry. Any byte difference fails, naming platforms, component, first differing sample index. Tolerance mode: passes only when `20*log10(max|a-b|)` (full scale 1.0, computed in float64 on the decoded samples; a zero difference counts as minus infinity and passes) is strictly below the configured bound; the bound (-100 dBFS) lives in `ci/hash_tolerance.json` with its source (AD-9, design log 2026-10-27 (j)), not in code. Tolerance applies only to a (platform, component) entry in that file, measured against the reference platform; an entry with no `design_log` citation, or one naming an entry heading absent from `docs/design-log.md`, fails. A missing platform manifest, differing component sets, or differing sample counts fail.
- Verdict and nightly-gate decisions live in stdlib Python (`tools/ci_verdict.py`, `tools/nightly_gate.py`) that the workflow calls, so each has passing and must-fail fixture tests over JSON inputs.
- Verdict job (`if: always()`): fails unless every build, test, probe, and compare job reports `success`; a skipped, cancelled, or never-scheduled Android job fails it. Only a nightly skip passes, with a notice.
- Nightly skip: a gate job reads the last successful `full` run on `main` from a schedule or manual event; if its head commit equals current `main`, all jobs skip and the summary says "skipped: main unchanged since run <id> (<sha>)". Manual and pull request runs never skip.
- Wall-time budget `ci/wall_time_budget.json`: per tier and job, budget minutes, runner label, billing multiplier, runs per month, plus the account allowance. Each job records its start in its first step and runs `tools/check_wall_time.py` in a last `always()` step: prints wall time against budget, exits 1 if over. `--estimate` prints monthly billed minutes per platform (zero billed for the public repo).
- Pins: `toolchain.json` gains Windows arm64 LLVM, CMake, Ninja assets, the Apple clang version with its Xcode path, and NDK r30 (URL, SHA-256, its clang version, `api_level` used as `ANDROID_PLATFORM`). Runner labels are exact (no "or newer"), so the Apple clang and Xcode pins hold. If NDK r30 or the pinned Xcode is not available on the hosted runner, stop and report rather than picking another version. `cmake/Pins.cmake` checks the matching pin per platform and names expected and found. Third-party actions pinned by full commit SHA.
- Compile-flag and symbol checks run on every toolchain, NDK included.
- Tests first by a fresh-context QA agent, committed tests-only before implementation. Passing and must-fail fixture for every check. No em dashes; CLAUDE.md "Never" terms stay out.

**Never:**
- Engine signal code, render code, or the signal spec (Story 0.2). Tables-as-data work (Story 0.3). Paid services, emulators, or device farms. Pushing, or touching GitHub settings, without Audio's go-ahead.
- Weakening any threshold or check so a platform passes; a platform that cannot match goes to tolerance only through a cited design log entry (Story 0.2's job).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| All match | four identical manifests, exact mode | exit 0 | N/A |
| One LSB | one float32 sample's lowest bit flipped, no tolerance entry | exit 1 | names platforms, component, sample index |
| Tolerance pass | cited entry, diff at -100.5 dBFS | exit 0 | N/A |
| Tolerance fail | cited entry, diff at -90 dBFS; also exactly -100 (float64) | exit 1 | names measured dBFS and bound |
| All wrong alike | four identical manifests not matching `ci/hash_expected.json` | exit 1 | names component, expected and found hash |
| Contraction on | probe built with `-ffp-contract=fast` on arm64 | hash differs from expected (must-fail job succeeds only if it differs) | names the hash |
| Uncited entry | entry with empty or unknown `design_log` | exit 1 | names the entry |
| Missing platform | three manifests | exit 1 | names the missing platform |
| Over budget | start 50 min ago, budget 40 | exit 1 | prints wall and budget minutes |
| Android not run | Android run job skipped or cancelled, gate says run | verdict fails | names the job and its result |
| Nightly unchanged | last passing scheduled or manual run has current main sha | all skip, verdict passes | summary names run id and sha |

</frozen-after-approval>

## Code Map

- `.github/workflows/fast.yml` -- add the wall-time start and check steps to both jobs; job names and branch rule stay.
- `.github/workflows/full.yml` -- new. Triggers `pull_request` to `main`, `schedule` `0 3 * * *`, `workflow_dispatch`. Jobs: `gate`, `windows-x64` (`windows-2025`), `windows-arm64` (`windows-11-arm`), `macos-arm64` (`macos-15` exactly, Xcode chosen with `xcode-select` from the pin), `android-build` (`ubuntu-24.04`, NDK r30 from `toolchain.json`, configures `android-arm64`, then runs `tools/check_compile_flags.py` and `tools/check_engine_symbols.py` directly on that build's `arcani_engine_check.json`; the host-side must-fail fixtures already prove the checkers, so no NDK must-fail run; uploads the probe), `android-arm64` (`ubuntu-24.04-arm`, runs the downloaded probe), `contract-mustfail` (`ubuntu-24.04-arm`, builds the probe with `-ffp-contract=fast` via the `linux-clang` preset plus an extra-flags cache variable, succeeds only if its hash differs from `ci/hash_expected.json`), `hash-compare`, `verdict`. Reuse the pinned-download and SHA-256 steps from `fast.yml` (the step at fast.yml:118 reads `windows_x64`; Windows arm64 reads `windows_arm64`). Every job runs `astral-sh/setup-uv` (pinned SHA, uv from `toolchain.json`) so `tools/*.py` run on the same Python everywhere. `permissions: contents: read`, plus `actions: read` on `gate` only. `concurrency` group per ref with cancel-in-progress for pull requests only; every job sets `timeout-minutes` at twice its budget. Each probe job runs `tools/hash_manifest.py` and uploads `hashprobe-<platform>` as an artifact.
- `CMakePresets.json` -- add `macos-appleclang` (Darwin) and `android-arm64` (Linux host, toolchain file `$env{ANDROID_NDK_ROOT}/build/cmake/android.toolchain.cmake`, `ANDROID_ABI=arm64-v8a`, `ANDROID_PLATFORM` per the pin, `ARCANI_BUILD_TESTS=OFF`, since Catch2's CLI test needs the build-machine path). Windows arm64 reuses `windows-clang-cl`.
- `tools/dev.ps1` -- pick `vcvarsarm64.bat` and the ARM64 VC component when `PROCESSOR_ARCHITECTURE` is `ARM64`; otherwise unchanged.
- `toolchain.json` -- new keys: `windows_arm64` under `llvm`, `cmake`, `ninja` (LLVM: use the `woa64` tar.xz asset if LLVM publishes no arm64 `.msi`, extracted with `tar`, and record which in the design log); `apple_clang` (`version`, `xcode_path`); `android_ndk` (`version`, `url`, `sha256`, `clang_version`, `api_level`).
- `cmake/Pins.cmake` -- pass 2: expected id, version, and name per platform (`AppleClang` with the Apple clang pin on Apple, the NDK clang pin when `ANDROID`, llvm pin otherwise). Keep the test-only override variables; `ARCANI_PIN_OVERRIDE_LLVM` overrides whichever compiler pin is active on that platform (document this in the header comment at Pins.cmake:11).
- `engine/CMakeLists.txt` -- `llvm-nm` search also finds Xcode's on Apple (`xcrun --find llvm-nm`, else `nm` next to the compiler, which is llvm-nm based); the NDK `llvm-nm` already sits next to its clang.
- `CMakeLists.txt` -- `add_subdirectory(tests/hashprobe)`, always built so the NDK build has it.
- `tests/cmake/test_pin_check.py`, `test_compile_flags.py`, `test_engine_symbols.py` -- preset choice gains `darwin` -> `macos-appleclang` (deferred-work entry, part 1 finding 18). Expected values become per platform: on Darwin, `toolchain_name` is `AppleClang` and `toolchain_version` equals the `apple_clang` pin (test_compile_flags.py:74, :464-465); the `llvm-nm` location test (:469-486) accepts, on Darwin only, the path `xcrun --find llvm-nm` returns, else `nm` next to the compiler. No threshold or check is relaxed on Windows or Linux.
- `tests/python/test_toolchain.py` -- `EXPECTED_PINS` (line 29) gains the new pin keys.
- `tests/hashprobe/` -- new probe binary and CMake (warnings as errors like the CLI).
- `tools/hash_compare.py`, `tools/hash_manifest.py`, `tools/check_wall_time.py`, `tools/ci_verdict.py` (input: the `needs` JSON and the gate output), `tools/nightly_gate.py` (input: the run list JSON from the GitHub API and the current `main` sha) -- new, stdlib only, pattern of `tools/check_compile_flags.py` (argparse, one line per violation, exit 0 or 1). The workflow only fetches inputs and calls them.
- `tools/probe_reference.py` -- new: numpy float32 reference of `probe-arith`; writes the expected hash into `ci/hash_expected.json`. Same operation order as the C++ probe, documented side by side.
- `ci/hash_tolerance.json` (bound and source, empty entry list), `ci/hash_expected.json`, `ci/wall_time_budget.json` -- new data files.
- `docs/design-log.md` -- entry (aa): runner layout (all hosted, PC runner superseded; marks the runner paragraph of entry (y) superseded), Android on hosted arm64 Linux, budget table and estimate, spending cap, nightly rule, hash compare rule; Current state rows. `docs/ci-setup.md` -- new: Audio's manual steps (spending cap at $0 in GitHub billing, branch rule adding `verdict` from `full`).
- Do not change: `tools/check_compile_flags.py`, `tools/check_engine_symbols.py`, the denylist, engine sources.

## Tasks & Acceptance

**Execution:**
- [x] `tests/python/test_hash_compare.py`, `tests/python/test_wall_time.py`, `tests/python/test_ci_gate_verdict.py`, `tests/python/test_ci_workflows.py`, `tests/python/test_probe_reference.py` -- QA agent: every matrix row on synthetic files; gate and verdict passing and must-fail fixtures over JSON inputs; probe reference reproduces `ci/hash_expected.json`, and the host-built probe's output matches it; workflow structure (verdict `always()` and needs every job, triggers and cron, actions pinned by SHA, exact runner labels, setup-uv and wall-time steps in every job of both workflows, `timeout-minutes` set, no `self-hosted` label); probe manifest schema; budget table covers every job of both workflows.
- [x] `tests/hashprobe/`, `tools/probe_reference.py` -- probe binary, CMake, and reference.
- [x] `tools/hash_compare.py`, `tools/hash_manifest.py`, `tools/check_wall_time.py`, `tools/ci_verdict.py`, `tools/nightly_gate.py`, `ci/*.json` -- tools and data.
- [x] `toolchain.json`, `cmake/Pins.cmake`, `CMakePresets.json`, `CMakeLists.txt`, `engine/CMakeLists.txt`, `tools/dev.ps1`, `tests/cmake/*.py` per-platform expectations, `tests/python/test_toolchain.py` -- platform support.
- [x] `.github/workflows/full.yml`, `.github/workflows/fast.yml` -- workflows.
- [x] `docs/design-log.md`, `docs/ci-setup.md`, `deferred-work.md` (close the macOS preset entry; add the physical phone run) -- records.

**Acceptance Criteria:**
- Given a clean checkout, when `uv run pytest` runs locally, then all tests pass, including every hash compare and wall-time must-fail case.
- Given Audio's go-ahead to push, when the full workflow runs manually on GitHub, then all four platforms build and pass the flag and symbol checks, the hosted platforms pass ctest and pytest, the probe runs on each including the arm64 Linux runner, the compare passes in exact mode against `windows-x64` and `ci/hash_expected.json`, the contraction must-fail job sees a different hash, and every job prints wall time against budget.
- Given the budget table, when `tools/check_wall_time.py --estimate` runs, then it prints monthly billed minutes per platform with multipliers against the allowance, and the design log records the result and any shortfall remedy.

## Implementation Notes

- Failing tests committed in d809eea (fresh-context QA agent); their docstrings define the contracts. PyYAML 6.0.3 added to the dev group to parse workflows.
- Added beyond the Code Map, because the jobs need them: `linux_arm64` LLVM, CMake, Ninja pins (the `contract-mustfail` job's `linux-clang` preset checks the LLVM pin) and `macos_arm64` CMake and Ninja pins. LLVM publishes `LLVM-23.1.4-woa64.msi`, so Windows arm64 uses the `.msi` (design log (aa)).
- Pins: Apple clang `17.0.0.17000013` is CMake's version string for Xcode 16.4 (`__apple_build_version__` 17000013), the default Xcode on the `macos-15` image; not verified on a Mac yet. NDK r30 is 30.0.16248370 with clang 21.0.0; API level 21 is the NDK minimum. The API level check uses `ANDROID_PLATFORM_LEVEL` (else `CMAKE_SYSTEM_VERSION`).
- Probe `probe-arith`: float32 logistic map (`t = R*s; s = t - t*s; out = s*A + B`), constants exact in float32 and decimal. Host build on the dev PC matches the NumPy reference (`933f0602...`). Local check: a `/clang:-ffp-contract=fast /clang:-mfma` build gives `3f4fdae9...`, so `--must-differ` passes on it and fails on the normal build.
- `hash_compare.py`: a (platform, component) with a tolerance entry is exempt from the expected-hash check, since its bytes differ by definition; it is still compared to the reference in tolerance mode.
- Workflow uses no YAML anchors (repeated Windows steps are written out) and literal platform names in artifact and manifest steps.
- Local: `uv run pytest` 546 passed, 0 skipped; `cmake --workflow --preset windows-clang-cl` builds the probe, ctest 1/1 passed (Smart App Control did not block it this time); `check_wall_time.py --estimate` exit 0.
- Not verified until Audio's go-ahead to push: everything on GitHub (Windows arm64, macOS, NDK, arm64 Linux, artifact flow, gate API call, verdict).

## Spec Change Log

## Review Triage Log

## Design Notes

The probe lives outside `engine/` so part 3 adds no signal code ahead of Story 0.2's signal spec. A static bionic binary needs only Linux syscalls, so it runs on the hosted arm64 Linux kernel; if it does not start there, stop and report rather than switching to an emulator. Budget minutes start from fast run 41578714584 (both jobs about 3 minutes); full-tier budgets are first estimates, corrected after the first full run with a design log note.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass.
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: builds including the probe; ctest may be blocked locally by Smart App Control.
- `uv run python tools/check_wall_time.py --estimate` -- expected: table printed, exit 0.

**Manual checks:**
- After Audio's go-ahead to push: one manual `full` run passes every job.
