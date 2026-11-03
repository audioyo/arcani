# Epic 0 Context: A trusted toolchain

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Before any signal layer is built, Audio (the sole developer and tester) must be able to trust the toolchain: one pinned build, a CI matrix that proves one engine sine renders identical bytes on Windows x64, Windows arm64, macOS arm64, and Android NDK arm64, threshold and range tables held as data, an automated wording check, and an independent review of the architecture decisions still marked review pending. The riskiest assumption, cross-platform bit-exactness, is tested first so a failure costs little rework. Every later story is built, tested, and hash-compared through what this epic sets up.

## Stories

- Story 0.1: Build skeleton and CI matrix (split into three sequential parts, see below)
- Story 0.2: Engine sine oscillator (spike that ships)
- Story 0.3: Threshold and range tables as data
- Story 0.4: CI wording check
- Story 0.5: Independent review of the pending architecture decisions

## Requirements & Constraints

- **Determinism:** same recipe, engine version, seed, and sample rate give a byte-identical file. Cross-platform hashes must match across the four-platform matrix; a component proven unable to match falls back to a -100 dBFS tolerance, logged in the design log with platform, component, and reason. Bit-exact failure in the sine spike is a defined outcome, not a blocker.
- **Sine accuracy:** engine sine within -120 dBFS of the ideal sine over a full phase cycle; integer phase increments keep phase error under 1 ms over 8 hours; increment quantization error under 0.01 Hz for every carrier and rate in the locked ranges, at 44.1 and 48 kHz.
- **CI tiers:** fast tier locally after every change and on every push (Windows x64 and Linux); full tier on every pull request into main, nightly, and manual runs, across all four platforms with the NDK hash binary run on a physical Android phone. A failure in any job blocks merge. A skipped, cancelled, or unscheduled Android job must fail the run, never pass silently. Nightly is skipped (and logged as skipped) when main is unchanged since the last passing full-tier run.
- **Toolchain pin check:** pinned compiler versions live in the repo; a runner reporting a different version fails and names expected and found.
- **Compile flags:** CI fails, naming toolchain and flag, if `-ffp-contract=off` is missing or any fast-math flag is present (clang-cl through `/clang:`). A must-fail fast-math configuration proves the check.
- **Symbol denylist:** CI lists the engine library's undefined symbols and fails on libm transcendentals (including float variants), file, thread, clock, and console APIs. A must-fail translation unit calling `std::sin` inside `engine/` proves it.
- **Hash compare tool:** exact mode fails on a one-LSB difference; tolerance mode passes below -100 dBFS and fails at -90 dBFS. Tolerance is enabled only per platform and component through a config file where every entry cites a design log entry; an uncited entry fails CI.
- **Wall-time budget:** a per-platform, per-tier budget table; each job reports wall time against budget and fails if over. The table estimates monthly billed CI minutes with each runner's billing multiplier; any shortfall goes in the design log with the remedy.
- **Tables as data (0.3):** threshold and locked-range data files under `tests/`, every row with ID, value, unit, and source citation, matching the spec tables exactly. Loaders in C++ and Python fail on an uncited row and must return identical rows in a cross-check. A data-file change without a design log entry naming the row ID fails CI. Two-way coverage: every assertion reports its row ID; an assertion without a row fails; an unused row fails unless marked pending with its story, and a pending row whose story is done fails.
- **Wording check (0.4):** a term list data file (banned project terms from CLAUDE.md, comparables' feature names, health or outcome claim phrases) scanned against docs, code comments and strings, and recipe descriptions; matches fail with file, line, term. Em dashes fail with file and line. The term list itself and research files (research library, research runs, competitor scans) are exempt through a path exemption list in the repo. Must-fail fixtures for each case; the current repo must pass, with existing violations fixed in the story.
- **Review (0.5):** AD-4, AD-5, AD-9, AD-19, AD-20, and the Stack are each locked (tag removed) or changed with a design log entry, by a fresh-context reviewer or a human Audio names, against the PRD, SPEC, CLAUDE.md, and research library, using the S0.2 result. Findings are saved beside the spine's existing reviews. Epic 1 does not start until this is done.
- **Process rules for every story:** tests first, from acceptance criteria, by a fresh-context QA agent, landing as a failing tests-only commit before implementation. Every check ships with a passing and a must-fail fixture; no fault-injection code in `engine/`. No threshold or range is hard-coded or weakened. One story per branch; no commit with failing tests. Every changed default or threshold gets a design log entry.
- **Cost:** one-person company. The GitHub repo `audioyo/arcani` is public, so GitHub-hosted runners are free. Give a cost estimate before adding any paid service or raising CI usage. Record runner setup and the GitHub billing spending cap in the design log.

## Technical Decisions

- **Stack:** C++20 engine and CLI; CMake 4.4.5; Ninja; Catch2 3.16.1; clang-cl on Windows, Clang on arm64, Apple clang on macOS, Android NDK r30 clang (arm64-v8a only). Python 3.14 via uv 0.13.6, NumPy 2.5.4, pytest pinned in the lockfile (pin chosen in Story 0.1). Exact clang-cl, arm64 Clang, and Apple clang versions are pinned in Story 0.1. CI is GitHub Actions.
- **Local dev PC (Windows) installed:** CMake 4.4.5, LLVM 23.1.4 (clang-cl), Ninja 1.13.2, uv 0.13.6.
- **Runners:** Audio's Windows dev PC is a self-hosted runner, with an Android phone attached by USB for the NDK hash binary. GitHub-hosted runners serve Linux, Windows arm64 (`windows-11-arm` or `ubuntu-24.04-arm`), and macOS arm64. The self-hosted runner must never run code from fork pull requests.
- **Source tree:** `engine/` (pure C++ core plus C API header), `cli/`, `reference/` (Python reference), `tests/` (assertion library, C++ and Python tests, threshold and range tables), `recipes/`, `golden/` (Git LFS), `docs/`.
- **Pure core:** `engine/` depends only on the C++ standard library: no threads, clocks, devices, files, or UI. Engine-owned sine and transcendentals (no libm), 64-bit integer phase accumulators, no `long double`, `-ffp-contract=off`, no fast-math, engine-set denormal mode on entry to each render call.
- **Signal spec:** `docs/signal-spec.md` is the only formula source. Story 0.2 writes only its core and sine sections (64-bit accumulator, increment quantization rule, seconds-to-samples rule, ideal sine, -120 dBFS approximation bound), with worked test vectors that the engine test and the Python ideal-sine test each pass independently. That section merges before engine or reference implement it. The Python reference renders the ideal sine, never the engine's approximation.
- **CLAUDE.md commands:** Story 0.1 fills in the Build, C++ tests, and Render commands; `uv run pytest` runs the Python suite.
- **Secrets:** GitHub Actions secrets only; none in the repo.

## Cross-Story Dependencies

- **Story 0.1 split (decided 2026-11-02 by Audio), parts run in order:**
  - Part 1: source tree skeleton, local build on the Windows dev PC (clang-cl, CMake 4.4.5, Ninja, Catch2 3.16.1, Python via uv), fast-tier CI on push (Windows x64 and Linux), toolchain version pin check.
  - Part 2: compile-flag check and engine undefined-symbol denylist, each with its must-fail case.
  - Part 3: full four-platform matrix including the Android phone, hash compare tool, wall-time budget, nightly skip.
- Story 0.2 needs the four-platform matrix and hash compare tool (0.1 part 3) to prove cross-platform hashes; if a platform cannot match, it switches that platform to tolerance in the hash compare config citing a new design log entry and flags AD-9 in the spine's open questions.
- Story 0.3's design log gate and coverage check, and Story 0.4's wording check, run as CI jobs on the part 1 pipeline. Story 0.3's tables feed every later assertion; Story 0.4 must pass on all later docs and recipes.
- Story 0.5 needs the S0.2 bit-exactness result and closes before Epic 1 starts. Every later engine story joins the cross-platform hash check on all four platforms at both sample rates as part of its definition of done.
