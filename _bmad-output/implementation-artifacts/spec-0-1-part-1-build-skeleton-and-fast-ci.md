---
title: 'Story 0.1 part 1: build skeleton, local build, fast-tier CI, toolchain pin check'
type: 'chore'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '7031b28c15579a62bcac49f77f4b78ef1c2c233d'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent â€” do not modify unless human renegotiates">

## Intent

**Problem:** The repo has plans but no code, no build, and no CI, so no later story can be built, tested, or checked the same way on every machine.

**Approach:** Create the spine's source tree with a minimal engine library, CLI stub, Catch2 test binary, and uv-managed Python suite; build them with pinned CMake 4.4.5, Ninja, and clang-cl on the Windows dev PC; run the fast tier on every push on Windows x64 and Linux; fail any build whose compiler or CMake version differs from the pins in the repo.

Decisions (2026-11-02, Audio): Story 0.1 is split into three parts; this is part 1. Parts 2 and 3 are in `deferred-work.md`. The repo stays public; GitHub-hosted runners are free.

## Boundaries & Constraints

**Always:**
- One pin file is the single source for tool versions: CMake 4.4.5, LLVM/clang 23.1.4 (clang-cl on Windows, clang on Linux), Ninja 1.13.2, Catch2 3.16.1, Python 3.14, uv 0.13.6, NumPy 2.5.4, pytest 9.2.0. CMake and CI read it; nothing else restates a version.
- Configure fails, naming expected and found, when the C++ compiler or CMake version differs from the pin.
- Third-party downloads (LLVM in CI, Catch2) are fetched by exact version and checked against a SHA-256 recorded in the repo.
- `engine/` uses only the C++ standard library. CLI and tests reach the engine only through its public header.
- Tests first: a fresh-context QA agent writes failing tests from the ACs, committed tests-only before any implementation.
- No em dashes; CLAUDE.md "Never" terms stay out of code, comments, and docs.

**Never:**
- Compile-flag check, symbol denylist (part 2); arm64, macOS, Android jobs, self-hosted runner, hash compare tool, wall-time budget, nightly (part 3).
- Any signal code, C API design beyond an engine version query, recipe schema, or WAV writing (later stories).
- Third-party GitHub Actions beyond `actions/checkout` and `astral-sh/setup-uv`, each pinned by commit SHA.
- Paid services. Pushing or changing GitHub settings without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Clean local build | Windows dev PC, pinned tools | engine lib, CLI stub, test binary build; ctest and `uv run pytest` pass | N/A |
| Wrong compiler | clang 22.x or MSVC cl as CXX | configure stops | message names expected 23.1.4 and found version |
| Wrong CMake | CMake other than 4.4.5 | configure stops | message names expected and found |
| CLI stub run | `arcani-render --version` | prints engine version, exit 0 | any other argument: usage text, exit 2 |
| Push to any branch | GitHub | fast tier runs on windows x64 and ubuntu-24.04 x64, both build and test | any job failure fails the workflow |

</frozen-after-approval>

## Code Map

Greenfield: only `docs/`, `_bmad*/`, `.claude/`, `.agents/`, `.gitignore`, `CLAUDE.md` exist. Do not touch `_bmad*/`, `.claude/`, `.agents/`, planning artifacts.

- `CLAUDE.md` -- Commands block holds three `TBD` lines to fill in.
- `docs/design-log.md` -- newest entries at top, `### YYYY-MM-DD (letter): Title`; last letter is (x).
- `.gitignore` -- append build outputs.
- Spine source tree: `engine/ cli/ reference/ tests/ recipes/ golden/ docs/`.

## Tasks & Acceptance

**Execution:**
- [x] `toolchain.json` -- pin file with versions and SHA-256s (LLVM Windows x64 installer, LLVM Linux x64 tarball, Catch2 source archive) -- single source of truth.
- [x] `CMakeLists.txt`, `cmake/Pins.cmake`, `CMakePresets.json` -- C++20 project; read pins with `string(JSON)`; fail on version mismatch; Catch2 via FetchContent by URL plus hash; presets `windows-clang-cl` and `linux-clang` (Ninja, build dir `build/<preset>`).
- [x] `engine/include/arcani/arcani.h`, `engine/src/version.cpp`, `engine/CMakeLists.txt` -- static lib, `arc_engine_version()` returning a C string -- minimal public surface S1.2 builds on.
- [x] `cli/main.cpp`, `cli/CMakeLists.txt` -- `arcani-render` stub per the matrix; links only the public header target.
- [x] `tests/cpp/` -- Catch2 tests: engine version string, CLI stub behavior; registered with ctest.
- [x] `pyproject.toml`, `uv.lock`, `.python-version`, `tests/python/` -- Python 3.14 project, NumPy and pytest pinned; tests assert pinned versions match `toolchain.json` and the source tree exists.
- [x] `reference/`, `recipes/`, `golden/` -- placeholder README each; `.gitattributes` routes `golden/**` to Git LFS.
- [x] `tools/dev.ps1` -- enters the VS developer environment via vswhere, then runs the given cmake/ctest command, so clang-cl finds the Windows SDK and STL.
- [x] `.github/workflows/fast.yml` -- on push: windows-2025 and ubuntu-24.04 jobs install pinned LLVM, CMake, Ninja (checksum-verified), uv; configure, build, ctest, `uv run pytest`.
- [x] `CLAUDE.md` -- fill Build, C++ tests, Render commands.
- [x] `docs/design-log.md` -- entry (y): toolchain pins chosen for Story 0.1 (LLVM 23.1.4, Ninja 1.13.2, pytest 9.2.0), Windows x64 fast tier on a hosted runner until part 3 adds the guarded self-hosted runner, and the manual branch-protection step.

**Acceptance Criteria:**
- Given a clean checkout on the dev PC, when `tools/dev.ps1` configures and builds the `windows-clang-cl` preset, then the engine, CLI stub, and test binary build, ctest passes, and `uv run pytest` passes on Python 3.14 from the lockfile.
- Given CLAUDE.md, when read, then Build, C++ tests, and Render commands are real commands that work.
- Given a push, when the fast workflow runs, then Windows x64 and Linux jobs build and test, and either failing fails the run.
- Given `main` on GitHub, when Audio applies the branch rule written in the design log entry (require the fast workflow's jobs to pass), then a failing job blocks merge.

## Design Notes

Windows x64 fast tier uses a hosted runner here because the repo is public (free) and the guarded self-hosted runner arrives with the Android work in part 3; the epic AC's runner layout is met when part 3 closes. Branch protection is a GitHub setting, so this story documents it and Audio applies it.

Dev PC state (2026-11-02): uv `C:\Users\goegl\.local\bin\uv.exe`, CMake `C:\Users\goegl\.local\opt\cmake-4.4.5-windows-x86_64\bin`, Ninja via `uv tool` in `C:\Users\goegl\.local\bin`, LLVM `C:\Program Files\LLVM\bin`, VS 2022 Community with MSVC 14.44 and Windows SDK 10.0.26100. These are on the user PATH but may be missing from an already-open shell; prepend them when running locally. The QA agent's tests are committed (8288f1d) and define the contracts: `ARCANI_RENDER_PATH`, `toolchain.json` shape, `ARCANI_PIN_OVERRIDE_LLVM` / `ARCANI_PIN_OVERRIDE_CMAKE` (test-only cache variables), pin check firing before the compiler sanity try_compile. Make them pass; never edit them to pass.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: configure, build, test all pass.
- `uv run pytest` -- expected: all pass.
- Configure with `-DCMAKE_CXX_COMPILER=cl` -- expected: fails naming expected and found compiler.

## Implementation Notes

- Pin check lives in `cmake/Pins.cmake`, included before `project()` (CMake check) and registered as `CMAKE_USER_MAKE_RULES_OVERRIDE`, so CMake re-includes it from `CMakeCXXInformation.cmake` after compiler identification and before the sanity try_compile (compiler ID, version, and frontend check). Verified: `-DCMAKE_CXX_COMPILER=cl` fails with "expected clang-cl 23.1.4, found MSVC 19.44.35222.0".
- Catch2 tests are registered as one ctest entry (`arcani_tests`). Per-case discovery was dropped: Catch2 parses the test name "--version prints ..." as a command-line option.
- LLVM on the Windows runner comes from the release `.msi` (there is no `.exe` installer for 23.1.4), unpacked with `msiexec /a` into a private folder so the runner's preinstalled LLVM is untouched. Verified locally: the result has `LLVM/bin/clang-cl.exe` 23.1.4.
- On Linux CI the 2 GB LLVM tarball is extracted without static libraries and LLVM development headers.
- `toolchain.json` also records URL and SHA-256 for CMake and Ninja, since the workflow verifies them. `pyproject.toml` and `.python-version` restate the Python, NumPy, and pytest pins because uv requires it; `tests/python/test_toolchain.py` holds them equal to `toolchain.json`.
- `tools/dev.ps1` keeps the caller's PATH (plus user and machine PATH) ahead of the VS environment's additions, because VS ships its own CMake and Ninja.
- `golden/README.md` is exempted from the LFS rule so the folder README stays plain text.
- Not verified here: the GitHub workflow itself (no push without Audio's go-ahead). The Linux job could not be run locally (no WSL or Docker).
- 2026-11-02: Smart App Control on the dev PC blocks `arcani_tests.exe` ("An Application Control policy has blocked this file"); pytest passes locally. Audio chose GitHub for C++ tests: fast run #1 on 8143c3b passed on windows-x64 and linux-x64. Fast run #2 on 4118675 (after review fixes) passed on both.
- Review pass 1 patches (findings 1, 2, 3, 5, 7, 12, 16, 17): Linux fetch no longer runs in a command substitution and every failure stops the step; dev.ps1 errors use stderr plus the intended exit code; unused output removed; MSVC toolset, Windows SDK, glibc, libstdc++ versions printed; `* text=auto eol=lf`; URL-carries-version test; `toolchain.json` in `CMAKE_CONFIGURE_DEPENDS`. Local: pytest 27 passed, clean build passes, dev.ps1 with no arguments exits 2.

## Spec Change Log

## Review Triage Log

Review pass 1 (blind, edge-case, verification-gap layers).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | fast.yml Linux `fetch()` runs inside `$(...)`; errexit is cleared there, so a checksum mismatch does not stop the step | high | bash clears `-e` in command substitution without `inherit_errexit`; the final `echo` returns 0 and `tail` succeeds, so a mismatched archive is extracted | patch |
| 2 | fast.yml `sha256sum -c` output shares stdout with the path, separated by `tail -n1` | low | real fragility, same root cause and fix as 1 | patch (with 1) |
| 3 | dev.ps1 `Write-Error` under `ErrorActionPreference=Stop` throws, so `exit 2` / `exit 1` never run | low | terminating error exits 1 with a stack trace; usage case returns 1, not 2 | patch |
| 4 | dev.ps1 header claims pinned tools stay ahead of everything | false | the comment says ahead of what VS adds, which the code does (caller PATH first, VS additions last); the pin check catches any other order | reject |
| 5 | Linux job writes an unused `python` output | low | nothing reads it; direct deletion | patch |
| 6 | uv picks the newest 3.14.x patch | low | pin is 3.14 by design; engine determinism does not depend on the Python patch | reject |
| 7 | MSVC STL, Windows SDK, glibc/libstdc++ are unpinned and unrecorded | low | no current harm; part 3 hash compare detects drift; printing their versions in the Tool versions step is a trivial record | patch |
| 8 | No warning, fp, or reproducibility flags in CMake | medium | AD-9 requires `-ffp-contract=off` and no fast-math; intent assigns the flag check to part 2 | defer |
| 9 | Project version in CMake and pyproject not checked | low | pyproject has `package = false`; only the CMake version feeds the engine; fix adds a test | reject |
| 10 | Catch2 cases not discoverable one by one | low | single entry works and reports failing cases in output; renaming is optional | reject |
| 11 | CI checkout lacks `lfs: true` | false | Story 6.1 requires CI never downloads golden WAVs (LFS smudge off); hashes come from records | reject |
| 12 | No line-ending rule in `.gitattributes` | low | every commit warns LF to CRLF; byte-sensitive text fixtures are coming (test vectors, tables); one-line `* text=auto eol=lf` | patch |
| 13 | CLAUDE.md commands not checked against presets or the binary path | medium | text-only check; documented Render path can go stale | defer |
| 14 | Only `push` trigger; forks and manual reruns | low | solo repo, own branches get checks; GitHub UI re-run exists; part 3 adds PR and nightly triggers | reject |
| 15 | Windows LLVM bin path not checked after `msiexec /a` | low | CI run 1 proves the layout; a change would surface as a named pin mismatch | reject |
| 16 | Ninja, Catch2, uv `version` pins not tied to what is downloaded | medium | changing `version` without the URL passes every test | patch |
| 17 | `toolchain.json` not in `CMAKE_CONFIGURE_DEPENDS` | low | `file(READ)` does not trigger reconfigure; local build dirs keep stale pins | patch |
| 18 | `test_pin_check.py` fails on hosts other than Windows or Linux | low | unreachable now; part 3 adds a macOS job running pytest | defer |
| 19 | `test_repo_layout.py` raises StopIteration if no Commands line | low | cosmetic error message only | reject |
| 20 | AC1 local ctest not met on the dev PC | medium | environment (Smart App Control), not code; recorded in Implementation Notes | defer |
