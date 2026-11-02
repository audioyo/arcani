---
status: draft
stepsCompleted: [1, 2]
scope: v0.1
inputDocuments:
  - _bmad-output/specs/spec-arcani-v0-1/SPEC.md
  - _bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md
  - _bmad-output/specs/spec-arcani-v0-1/starter-recipes.md
  - _bmad-output/specs/spec-arcani-v0-1/glossary.md
  - _bmad-output/planning-artifacts/prds/prd-Arcani-2026-10-27/prd.md
  - _bmad-output/planning-artifacts/prds/prd-Arcani-2026-10-27/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-Arcani-2026-10-27/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/epics/epics-arcani-v0-1-draft.md
  - docs/design-log.md
  - docs/listening-modes.md
  - CLAUDE.md
---

# Arcani - Epic Breakdown (v0.1)

## Overview

This document provides the complete epic and story breakdown for Arcani v0.1: engine core, command-line renderer, Python reference, four starter recipes, and the full signal test suite, desktop and CI only. The v0.1 SPEC and its companions are the canonical contract; the PRD and architecture spine are cited for traceability. Later phases (designer, mobile apps, stems, Orbit, accounts) are out of scope. The party-mode draft (`epics/epics-arcani-v0-1-draft.md`) is the starting structure and the record of the decisions made in that session.

## Requirements Inventory

### Functional Requirements

IDs match the PRD. Wording follows the SPEC capability that refines each one.

FR-1: Engine clock (CAP-2). One engine clock drives every rate and phase. Theta reference phase error under 1 ms after an 8-hour render. Every carrier and rate within 0.01 Hz of the recipe; along a rate curve, instantaneous rate within 0.01 Hz of the schedule with continuous phase.
FR-2: Theta reference (CAP-3). A carrier AM at the theta rate with a sine, smoothed on-off, sawtooth, or reverse saw envelope; carrier, rate, and shape come from the recipe. Shape matches the reference renderer; hard-edged shapes pass the click test. Custom curves are rejected until the signal spec models them.
FR-3: Gamma PAC layer (CAP-4). A separate sine carrier AM at the gamma rate whose depth follows theta reference phase and peaks at the coupling phase, as a smooth swell, as 50 ms bursts (full width, 10 ms raised-cosine edges inside, depth-gated), or uncoupled at constant depth. The carrier plays continuously. Every gamma envelope peak within 2 ms of its coupling phase. Changing binaural beat rate or phase leaves every gamma peak time unchanged to the sample. Coupled gamma is rejected when the theta reference is absent or at zero depth. Non-sine gamma carriers are rejected in v0.1.
FR-4: Binaural layer on an isolated path (CAP-5). Two pure sines, one per ear, whose frequencies may follow a recipe rate curve, joining the stereo bus after every other stage with only the master chain after them. Muted-ear isolation at least 90 dB at engine output and 60 dB after the master chain, at any beat rate including 0 Hz. Structural stage-list test. A non-sine binaural waveform is rejected with a named rule (`binaural.waveform`, "non-sine binaural not modeled", limit sine). The engine never sums or downmixes channels.
FR-5: Gain ramps, loudness gain, limiter (CAP-6). Per-layer and master gain ramps from the recipe; loudness gain measured at export and stored in the recipe; stereo-linked limiter idle at that gain. No gain ramp completes in under 10 ms. Integrated loudness within 1 LU of target; true peak at or below -1 dBTP. Limiter gain reduction exactly zero on every v0.1 render. `final` compile rejects a missing gain or a mismatched loudness hash.
FR-6: Deterministic synthesis (CAP-7). Output is a pure function of recipe, engine version, seed, and sample rate. Repeat renders byte-identical; identical bytes at 1, 64, 512, 4096 frames per call; identical hashes across the AD-9 matrix or a logged -100 dBFS fallback; native 44.1 and 48 kHz with no resampling; every report carries the determinism key.
FR-7: Recipe file (CAP-8). One JSON recipe fully defines a session: every layer's parameters, gain ramps, rate curves, levels, length, looping flag and max run time, schema and engine version, seed, author, date, rationale, loudness target, stored gain and loudness hash, and describe-the-sound notes. A JSON Schema in the repo validates every starter and fixture. Looping recipes repeat the body with no click and no theta or gamma phase jump at the seam. An unsupported schema major version is rejected. Recipe hash is SHA-256 over RFC 8785 canonical JSON minus schema-excluded fields.
FR-8: Locked ranges (CAP-9). The compiler rejects any value outside the locked-range table (`thresholds-and-ranges.md`).
FR-9: Carrier rule and spacing rule (CAP-9, AD-20). Rejects any modulated carrier under 4 times its modulation rate, and any spacing failure (50 Hz per ear, 40 dB component threshold, both placeholders) in either ear at any point, including along rate curves. Computed analytically from the spectral component table; a shape with no component model is rejected.
FR-10: Clear rejection (CAP-9, CAP-10). Each rejection names parameter, value, rule, and limit, and produces no output. The renderer accepts only compiled plans (`measure` or `final` mode).
FR-11: Command-line renderer (CAP-11). Renders a recipe to 24-bit WAV (48 kHz default, 44.1 kHz selectable) plus a machine-readable report (per assertion: name, threshold, measured, pass or fail; plus determinism key and seed). Measures and writes the loudness gain. At least 20 times real time on the dev PC. A rejected recipe writes no WAV.
FR-12: Python reference renderer (CAP-12). Independent double-precision renderer of every v0.1 layer and the master chain, implemented from the signal spec only, using the ideal sine. Engine pre-quantization float output and per-layer taps within -100 dBFS sample by sample. Imports no engine code.
FR-13: Assertion library (CAP-13). One library checks every render against one threshold table and runs every assertion in it. Fixtures beyond the starters: binaural at several beat rates including 0 Hz and a sweep; coupled gamma with binaural at a different beat rate; all passing the spacing rule.
FR-14: Golden files (CAP-14, design log (q)). Approved renders become golden files keyed by determinism key in Git LFS. Any change that alters a golden fails; a missing golden fails; a golden is created or replaced only with a recorded sign-off (stage, signer, date, SHA-256 of the file heard); a hash change reverts it to unsigned.
FR-15: Local and CI runs (CAP-15). Fast tier locally after every change and on every push; full tier (8-hour drift, full-length starters, both sample rates) on every pull request into main and nightly, across the AD-9 matrix. A failure in either blocks merge. CI fails when `-ffp-contract=off` or no-fast-math flags are missing. CI checks docs and recipe descriptions for banned terms, comparables' feature names, health or outcome claims, and em dashes.
FR-16: Starter recipes (CAP-16). Focus, Learn, Relax, Sleep per `starter-recipes.md`. Each passes the validator and every assertion. Focus and Learn loop with a max run time (45 and 20 min). Only Sleep has a binaural layer. Sleep fades to silence. Every value traced in the design log. Each carries a describe-the-sound note matching `docs/listening-modes.md`.
FR-17: Listening checklist and sign-off (CAP-17). A checklist in the repo covering clicks and seams, roughness of 40 Hz gamma AM, comfort over the full session length, carrier audibility on earbuds, and loudness. Every golden has a Reaper and RX sign-off record. v0.1 closes on Audio's provisional sign-off (design log (q)).

### NonFunctional Requirements

Values are provisional (thresholds-and-ranges.md). Code and tests read them from one table; never hard-coded, never weakened.

NFR1: Determinism. Same recipe, engine version, seed, sample rate: byte-identical file.
NFR2: Cross-platform. Identical hashes on Windows x64 (clang-cl), arm64 (Clang), macOS arm64 (Apple clang), Android NDK arm64; a component proven unable falls back to -100 dBFS, logged in the design log.
NFR3: Block-size invariance. Identical bytes at 1, 64, 512, 4096 frames per call.
NFR4: Frequency accuracy. Every carrier and rate within 0.01 Hz, including along rate curves with continuous phase.
NFR5: Long-session drift. Theta reference phase error under 1 ms after an 8-hour render.
NFR6: Binaural isolation. At least 90 dB at engine output, 60 dB after the master chain, muted-ear method, any beat rate including 0 Hz.
NFR7: Coupling timing. Each gamma envelope peak within 2 ms of its coupling phase, measured from audio taps.
NFR8: Coupling independence. Binaural beat rate or phase changes leave gamma peak times unchanged to the sample.
NFR9: Reference match. Engine vs Python reference below -100 dBFS sample by sample, output and per-layer taps. Engine sine within -120 dBFS of the ideal sine (design log (o)).
NFR10: Clicks. No discontinuity above -60 dBFS in an 8 kHz high-pass at loop seams, ramp edges, burst edges.
NFR11: Dropouts. No all-zero run longer than 1 ms in a channel where the recipe sets a non-zero level.
NFR12: NaN or infinite values. Zero tolerance.
NFR13: Gain ramps. No layer or master gain ramp completes in under 10 ms; modulation envelopes and limiter exempt.
NFR14: Limiter idle. Zero gain reduction: master chain output equals input times master gain, bit for bit.
NFR15: Loudness and true peak. Integrated loudness within 1 LU of target (-36 LUFS-I for every starter); true peak at or below -1 dBTP. This is v0.1 hearing safety.
NFR16: Render speed. At least 20 times real time, dev PC only. Never traded against a threshold.
NFR17: Copy and naming. No CLAUDE.md "Never" terms, no comparables' feature names, no health or outcome claims, no em dashes; every signal named by carrier, modulation type, and rate.
NFR18: Traceability. Every default, range, and threshold traces to the research library, a logged listening test, or a declared engineering default in the design log; every change gets an entry.
NFR19: Clean room. No third-party program names, recipes, recordings, scripts, levels, or session arcs.

### Additional Requirements

From the architecture spine and SPEC constraints.

- **No starter template.** Greenfield C++20 and Python. The first story builds the skeleton: CMake 4.4.5, Clang toolchains pinned (clang-cl, Apple clang, NDK r30), Catch2 3.16.1, Python 3.14, uv 0.13.6, NumPy 2.5.4, pytest pinned, GitHub Actions matrix. Source tree per spine: `engine/`, `cli/`, `reference/`, `tests/`, `recipes/`, `golden/`, `docs/`.
- **Signal spec (CAP-1, AD-19).** `docs/signal-spec.md` is the only formula source: envelope shapes and 0 degree points, coupling depth function, bursts, ramp and rate-curve laws, phase increment quantization and accumulator width, loop seam behavior, limiter, internal block size, seconds-to-samples rule, loudness window, spectral component model per shape. Each story writes the section it needs; it merges before engine or reference implement it.
- **C API (CAP-10, AD-12).** One `arc_`-prefixed C API with plain C types: compile (`measure`, `final`), render frames, seek, per-layer taps, warnings, engine version. Status code plus structured error (parameter, value, rule, limit). CLI and C++ tests use only the public header.
- **Pure core (AD-1).** `engine/` depends only on the C++ standard library. Seek is a pure function of (plan, seed, sample rate, sample index). No threads, clocks, devices, files, or UI.
- **Bit-exact math (AD-9).** No libm transcendentals (engine-owned sine), 64-bit integer phase accumulators, no `long double`, `-ffp-contract=off`, no fast-math, engine-set denormal mode on entry to each render call. CI fails if the flags are missing.
- **Real-time contract (AD-11).** The render call never allocates, locks, blocks, or does I/O, and never throws or logs.
- **Fixed internal block (AD-10).** Renderer processes in a fixed internal block sized by the signal spec and buffers to the host's request.
- **Fixed topology (AD-3, AD-4).** Schema has no routing fields and no coupling-target field. Stage order: theta, gamma, stereo bus, binaural join, master chain (per-channel gain plus stereo-linked limiter). No channel-mixing operation anywhere.
- **Coupling input (AD-5).** The gamma depth function takes theta reference phase as its only input.
- **Loudness (AD-13).** The CLI compiles in `measure` mode, renders, measures integrated loudness (BS.1770, gated) over the spec's window (the steady part, ramps and fades excluded; design log 2026-11-01 (w), (x)), and writes gain plus a loudness hash over loudness-relevant schema fields.
- **Seed and randomness (AD-14, AD-25).** All randomness from an engine-owned counter-based PRNG keyed by (seed, stream, index). In v0.1 the Core draws no random values and WAV output rounds to 24 bits with no dither, so v0.1 has no random consumer; tooling always uses the recipe seed and the report carries it.
- **Hashing (AD-21).** Recipe hash SHA-256 over RFC 8785 canonical JSON excluding stored gain, loudness hash, and schema-marked non-audio fields. Determinism key = recipe hash + pinned asset hashes (none in v0.1) + engine version + sample rate.
- **Tables as data.** One threshold table and one locked-range table in the repo, each row citing its source, with loaders in C++ and Python.
- **Recipe conventions.** JSON, `snake_case`, units in field names (`_hz`, `_deg`, `_db`, `_lufs`, `_s`), times in seconds; schema tags loudness-relevant and hash-excluded fields.
- **Golden storage (AD-15).** Git LFS under `golden/`, keyed by determinism key.
- **Workflow.** Tests first from acceptance criteria by a fresh-context QA agent. Each assertion ships with a passing fixture and a must-fail fixture. Silence is not evidence: reference matches compare real waveforms. One story per branch. No commit with failing tests.
- **REVIEW PENDING.** AD-4, AD-5, AD-9, AD-19, AD-20 and the Stack bind v0.1 as written; their independent review is Story 0.5, which closes before Epic 1 starts.

### UX Design Requirements

None. v0.1 has no user interface. The listening checklist (FR-17) is a document for a listener and follows the copy rules in NFR17.

### FR Coverage Map

FR-1: Epic 2 (clock, frequency accuracy, rate curves); Epic 5 (whole-session 8-hour drift)
FR-2: Epic 2 (theta reference envelopes)
FR-3: Epic 2 (gamma uncoupled, swell, bursts)
FR-4: Epic 1 (stage-order and isolation assertion on stubs); Epic 2 (binaural layer)
FR-5: Epic 4 (loudness, true peak, gain ramps, limiter idle)
FR-6: Epic 0 (cross-platform sine); Epic 1 (determinism, block-size invariance)
FR-7: Epic 1 (core schema, hash, version rejection); Epic 2 (rate curves, looping); Epic 6 (describe-the-sound fields)
FR-8: Epic 1 (locked-range checks)
FR-9: Epic 1 (carrier rule); Epic 3 (spacing rule)
FR-10: Epic 1 (structured rejection, plans only)
FR-11: Epic 1 (CLI, WAV, report, render speed); Epic 4 (loudness gain writing)
FR-12: Epic 1 (reference for the stub chain); Epic 2 (reference for every layer); Epic 4 (master chain)
FR-13: Epic 1 (assertion library core); Epic 2 (extra fixtures); Epic 5 (clicks, dropouts, NaN)
FR-14: Epic 6 (golden records, Git LFS, sign-off)
FR-15: Epic 0 (build, CI matrix, flag and copy checks); Epic 5 (full tier sharding)
FR-16: Epic 6 (four starters)
FR-17: Epic 6 (listening checklist, provisional sign-off)

## Rules for Every Story

- Tests are written first, from the acceptance criteria, by a fresh-context QA agent. Each story branch carries a tests-only commit by the QA agent that fails before any implementation commit lands; review checks for it.
- Every assertion ships with a passing fixture and a must-fail fixture. Must-fail fixtures are made by doctoring audio or taps in the test harness; no fault-injection code ever enters `engine/`.
- Every measurement tool (coupling demodulator, isolation, spacing spectrum, loudness, clicks) is first calibrated against Python-synthesized signals with closed-form answers, in the story that introduces it, before it judges any engine render.
- Each story writes only the `docs/signal-spec.md` section it needs; that section merges before either the engine or the reference implements it, and it includes worked test vectors (exact sample values from the closed form) that the engine and the reference each test against independently.
- Silence is not evidence: a reference match must compare a real waveform.
- Definition of done for every engine story: its fixture joins the cross-platform hash check on all four AD-9 platforms (including the NDK hash binary), at both 44.1 and 48 kHz.
- Code and tests read every threshold and range from the tables; nothing is hard-coded, and no threshold is weakened.

## Epic List

### Epic 0: A trusted toolchain
Audio can trust that one sine renders identical bytes on Windows x64, arm64, macOS arm64, and Android NDK arm64, with the build, CI matrix, tables, and wording checks in place. The riskiest assumption is tested first.
**FRs covered:** FR-6 (cross-platform), FR-15
**Stories:** S0.1 build skeleton (CI time budget per platform, hash compare tool with exact and tolerance modes, engine symbol denylist); S0.2 sine spike (ships; bit-exact failure is a defined outcome); S0.3 tables as data (design log gate on table changes, two-way assertion and row coverage); S0.4 CI wording check; S0.5 independent review of the pending architecture decisions (closes before Epic 1).

### Epic 1: Render a recipe end to end
Audio or an agent can render a minimal recipe from the CLI to a WAV and a report, byte-identical at any block size, matched against the Python reference, with a failing test if anything leaks between ears and every field range-checked from the start.
**FRs covered:** FR-4 (structure), FR-6, FR-7 (core), FR-8, FR-9 (carrier rule), FR-10, FR-11, FR-12 (stub chain), FR-13 (core)
**Stories:** S1.1 minimal schema, version rejection, recipe hash, hash-excluded tag; S1.2 C API, stage stubs, seek, no-allocation check, isolation assertion; S1.3 validator framework, locked ranges and carrier rule; S1.4 CLI, report, render speed; S1.5 Python reference for the stub chain; S1.6 determinism and block-size invariance.

### Epic 2: Every Core layer, exact and on time
Audio can render the theta reference, the gamma PAC layer (uncoupled, smooth swell, bursts), and the binaural layer, each proven on timing, frequency, isolation, and reference match, with rate curves and seamless loops.
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-7 (rate curves, looping), FR-12, FR-13 (fixtures)
**Stories (order fixed):** S2.1 theta envelopes; S2.2 gamma uncoupled; S2.3 gamma coupled, smooth swell; S2.5 binaural layer and fixtures; S2.4 gamma coupled, 50 ms bursts; S2.6 rate curves on theta and gamma rates; S2.7 looping body and seams.

### Epic 3: The validator catches collisions
Any recipe whose layers collide in either ear, at any point including along rate curves, is rejected with parameter, value, rule, and limit. The four starters' layer configurations are proven to pass here, not in Epic 6.
**FRs covered:** FR-9 (spacing rule)
**Stories:** S3.1 spectral component table per shape, cross-checked against the reference spectrum; S3.2 spacing rule per ear, whole session; S3.3 early listening preview of the four starter configurations.

### Epic 4: Safe, steady loudness
Every render hits its loudness target under the true-peak ceiling, gain ramps are smooth, the limiter provably never acts, and the CLI measures and stores the loudness gain.
**FRs covered:** FR-5, FR-11 (loudness gain), FR-12 (master chain)
**Stories (order fixed):** S4.1 loudness meter; S4.2 stored loudness gain (CI never writes it); S4.3 true peak; S4.4 gain ramps; S4.5 limiter idle.

### Epic 5: Holds up for hours
Eight-hour renders stay on time and no render has a click, dropout, or invalid sample, with the full tier sharded to fit CI limits.
**FRs covered:** FR-1 (whole-session drift), FR-13, FR-15 (full tier)
**Stories:** S5.1 whole-session 8-hour drift and full-tier sharding; S5.2 clicks, dropouts, NaN and infinite values.

### Epic 6: Four starters you have heard and signed
Focus, Learn, Relax, and Sleep render and pass every check, and each carries Audio's provisional sign-off bound to the exact file heard. Closes v0.1.
**FRs covered:** FR-14, FR-16, FR-17
**Stories:** S6.1 golden records and Git LFS (sign-off survives a re-key when bytes match); S6.2 listening checklist; S6.3 Focus; S6.4 Learn; S6.5 Relax; S6.6 Sleep; S6.7 provisional sign-off session and v0.1 gate report.

## Epic 0: A trusted toolchain

Audio can trust that one sine renders identical bytes on Windows x64, arm64, macOS arm64, and Android NDK arm64, with the build, CI matrix, tables, and wording checks in place. The riskiest assumption is tested first.

### Story 0.1: Build skeleton and CI matrix

As a build agent,
I want one pinned build and a CI matrix covering every AD-9 platform,
So that every later story is built, tested, and hash-compared the same way everywhere.

**Acceptance Criteria:**

**Given** a clean checkout on the Windows dev PC
**When** the engine, CLI stub, and Catch2 3.16.1 test binary are configured and built with CMake 4.4.5 and clang-cl
**Then** all three build, the source tree matches the spine (`engine/`, `cli/`, `reference/`, `tests/`, `recipes/`, `golden/`, `docs/`), and `uv run pytest` runs the Python suite with Python 3.14, uv 0.13.6, NumPy 2.5.4, and a pinned pytest from the lockfile
**And** the Build, C++ tests, and Render commands in CLAUDE.md are filled in

**Given** the pinned toolchain versions (clang-cl, arm64 Clang, Apple clang, NDK r30) recorded in the repo
**When** a CI runner reports a different compiler version
**Then** that job fails and names the expected and found versions

**Given** a push to any branch
**When** CI runs the fast tier
**Then** it builds and tests on Windows x64 and Linux
**And** a failure in any job blocks merge

**Given** a pull request into main, the nightly schedule, or a manual run started from GitHub
**When** CI runs
**Then** it builds and tests on all four AD-9 platforms: Windows x64, Windows arm64, macOS arm64, and Android NDK arm64, with the NDK hash binary run on a physical Android device
**And** a failure in any job blocks merge

**Given** a one-person company (CLAUDE.md, Context)
**When** runners are set up
**Then** Audio's Windows dev PC is a self-hosted runner for Windows x64 jobs, an Android phone connected to it by USB runs the NDK hash binary, and GitHub-hosted runners serve Linux, Windows arm64, and macOS arm64 until Audio adds an own Mac
**And** the setup, and the spending cap set in GitHub billing, are recorded in the design log

**Given** the NDK arm64 hash binary
**When** this story closes
**Then** a passing job proves it runs on the connected Android phone, or the chosen alternative (such as a device-farm wrapper) is recorded in the design log and running
**And** a CI run in which the Android job is skipped, cancelled, or not scheduled fails instead of passing silently

**Given** the engine compile flags
**When** `-ffp-contract=off` is missing or any fast-math flag is present on any toolchain (clang-cl through `/clang:`)
**Then** CI fails and names the toolchain and flag
**And** a must-fail build configuration with fast-math enabled is rejected by the check

**Given** the built engine library
**When** CI lists its undefined symbols against the denylist (libm transcendentals including their float variants, file, thread, clock, and console APIs)
**Then** any match fails CI with the symbol name
**And** a must-fail translation unit calling `std::sin` inside `engine/` is caught

**Given** render hashes uploaded as artifacts from every matrix job
**When** the hash compare tool runs
**Then** in exact mode a one-LSB difference fails, and in tolerance mode a difference below -100 dBFS passes and one at -90 dBFS fails
**And** tolerance mode is enabled only per platform and component through a config file whose every entry cites a design log entry; an entry with no citation fails CI

**Given** a per-platform, per-tier wall-time budget table in the repo
**When** a CI job finishes
**Then** the job reports its wall time against its budget and fails if it exceeds it

**Given** the budget table
**When** it is filled in
**Then** it estimates monthly billed CI minutes per platform, with each runner's billing multiplier, against the account's allowance, and any shortfall is recorded in the design log with the chosen remedy

**Given** the nightly full-tier schedule
**When** nothing has changed on main since the last passing full-tier run
**Then** that night's run is skipped and logged as skipped

### Story 0.2: Engine sine oscillator (spike that ships)

As Audio,
I want the engine's sine oscillator proven exact and bit-identical across platforms before anything is built on it,
So that the project's riskiest assumption is settled first and every later layer stands on a known-good tone.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** the §core and §sine sections merge
**Then** they define the 64-bit phase accumulator, the phase increment quantization rule, the seconds-to-samples rule, the ideal sine, and the engine approximation's error bound of -120 dBFS (design log 2026-10-28 (o))
**And** each section includes worked test vectors (exact sample values from the closed form) that the engine test and the Python ideal-sine test each pass independently

**Given** the engine sine
**When** it is evaluated over one full phase cycle at the spec's test resolution
**Then** its maximum error against the ideal sine is at most -120 dBFS

**Given** a fixed sine render at 44.1 kHz and at 48 kHz
**When** it runs on Windows x64, arm64, macOS arm64, and Android NDK arm64
**Then** the SHA-256 of each render is identical across all four platforms

**Given** integer phase increments over an 8-hour session
**When** phase error is computed analytically from the increments
**Then** it is under 1 ms

**Given** every carrier and rate in the locked ranges
**When** increment quantization error is computed at both sample rates
**Then** it is under 0.01 Hz everywhere

**Given** a platform whose render hash differs and cannot be made identical
**When** the spike concludes
**Then** a design log entry records the platform, component, and reason, the hash compare config switches that platform to the -100 dBFS tolerance citing that entry, and the AD-9 independent review is flagged in the spine's open questions
**And** the story closes on this defined outcome rather than blocking

### Story 0.3: Threshold and range tables as data

As a build agent,
I want the threshold table and the locked-range table as data files with C++ and Python loaders,
So that no number is ever hard-coded and every value traces to its source.

**Acceptance Criteria:**

**Given** `thresholds-and-ranges.md`
**When** the threshold and range data files are created under `tests/`
**Then** every row carries an ID, value, unit, and source citation, and the values match the spec tables exactly

**Given** a row with no source citation
**When** either loader reads the table
**Then** it fails and names the row

**Given** both loaders
**When** a cross-check test loads every row in C++ and in Python
**Then** both return identical IDs, values, and units

**Given** a change to either data file in a branch
**When** the same branch adds no design log entry naming the changed row ID
**Then** CI fails
**And** a must-fail fixture change without a log entry is caught

**Given** the assertion library and the tables
**When** the two-way coverage check runs
**Then** every assertion reports the row ID it used, CI fails on an assertion that runs without a row, and CI fails on a row no assertion uses unless the row is marked pending with the story that will use it
**And** a pending row whose named story is marked done fails CI

### Story 0.4: CI wording check

As Audio,
I want CI to catch banned terms, comparables' feature names, health or outcome claims, and em dashes,
So that the copy and naming rules hold without anyone reading every line.

**Acceptance Criteria:**

**Given** a term list data file holding the CLAUDE.md "Never" terms, the PRD §6 comparables' feature names, and health or outcome claim phrases
**When** the check scans docs, code comments and strings, and recipe descriptions
**Then** any match fails CI with file, line, and the matched term
**And** the term list file itself is exempt

**Given** any scanned file
**When** it contains an em dash
**Then** CI fails with file and line

**Given** the research library, research runs, and competitor scans
**When** they cite or describe sources using a listed term
**Then** they pass, through a path exemption list kept in the repo

**Given** must-fail fixtures (a doc with an em dash, a recipe description with a health claim, a code comment with a banned term)
**When** the check runs on them
**Then** each fails
**And** the current repo passes, with any existing violations fixed in this story

### Story 0.5: Independent review of the pending architecture decisions

As Audio,
I want the architecture decisions still marked review pending checked by an independent reviewer before Epic 1,
So that a change to any of them costs a little rework now instead of a lot after Epic 5.

**Acceptance Criteria:**

**Given** AD-4, AD-5, AD-9, AD-19, AD-20, and the Stack table, marked `[REVIEW PENDING]` in the architecture spine, and the S0.2 bit-exactness result
**When** an independent reviewer (a fresh-context agent with no part in writing them, or a human Audio names) reviews each against the PRD, the SPEC, CLAUDE.md, and the research library
**Then** each is either locked, with its `[REVIEW PENDING]` tag removed, or changed, with a design log entry giving the reason and the affected stories updated
**And** the review findings are saved beside the spine's existing reviews

**Given** S0.2 closed on the defined fallback for any platform
**When** AD-9 is reviewed
**Then** the review confirms or changes the fallback and its scope, with a design log entry

**Given** this story
**When** Epic 1 is about to start
**Then** this story is done; Epic 1 does not start while any of these decisions is still pending

## Epic 1: Render a recipe end to end

Audio or an agent can render a minimal recipe from the CLI to a WAV and a report, byte-identical at any block size, matched against the Python reference, with a failing test if anything leaks between ears and every field range-checked from the start.

### Story 1.1: Minimal recipe schema and recipe hash

As Audio,
I want a versioned recipe format with a stable hash,
So that a recipe means one thing to every tool and any change to its sound is detectable.

**Acceptance Criteria:**

**Given** the JSON Schema in `recipes/`
**When** it defines the minimal recipe (schema version, engine version, seed, author, date, rationale, length in seconds, loudness target, and the stub chain's fields)
**Then** every field is `snake_case` with its unit in the name, and every field is tagged loudness-relevant, hash-excluded, or neither
**And** the schema forbids unknown properties, so a `routing` or `coupling_target` field is rejected

**Given** the engine compiler
**When** it parses a recipe
**Then** it uses an engine-owned strict JSON parser with no dependency outside the C++ standard library
**And** every fixture the JSON Schema rejects, the engine compiler also rejects, and every fixture the schema accepts, the compiler accepts (consistency test)

**Given** a recipe whose schema major version the engine does not support
**When** it is compiled
**Then** it is rejected with parameter `schema_version`, the value, the rule, and the supported versions as the limit

**Given** a recipe
**When** its hash is computed in the engine and independently in Python
**Then** both give the SHA-256 of its RFC 8785 canonical JSON, excluding the stored loudness gain, the loudness hash, and hash-excluded fields
**And** the RFC 8785 test vectors pass, and changing key order, whitespace, or number formatting leaves the hash unchanged

**Given** a recipe
**When** a hash-excluded field is edited
**Then** the hash is unchanged
**And** editing any audio-relevant field changes it

### Story 1.2: C API, fixed stage list, seek, and isolation assertion

As a build agent,
I want one `arc_` C API over a fixed stage list, with seek and a binaural isolation assertion from day one,
So that every host uses the same entry point and a leak between ears fails a test before any real layer exists.

**Acceptance Criteria:**

**Given** the public header
**When** a host calls it
**Then** it offers compile (`measure`, `final`), render frames, seek, read per-layer taps, read warnings, engine version, and plan release, with plain C types and `arc_` names
**And** every failing call returns a status code plus a structured error (parameter, value, rule, limit), and the render call never throws or logs

**Given** a compiled plan
**When** the structural test reads its stage list
**Then** the order is theta reference, gamma PAC layer, stereo bus, binaural join, master chain (per-channel gain, stereo-linked limiter), as stubs
**And** no stage type exists that mixes, sums, or swaps channels

**Given** the binaural join stub carrying the S0.2 sine at a fixed carrier in each ear
**When** the isolation assertion renders with one ear's oscillator muted
**Then** the muted carrier is at least 90 dB down in the other channel at engine output and at least 60 dB down after the master chain
**And** the assertion is first calibrated against Python-synthesized signals with known leakage, and a must-fail render doctored in the harness to 0.1 percent crosstalk fails

**Given** a plan
**When** rendering from sample 0 to N is compared with seeking to sample k and rendering to N
**Then** the samples from k onward are byte-identical, for k at 0, inside a block, and on a block boundary

**Given** a test binary that counts heap allocations
**When** render frames is called after compile
**Then** zero allocations occur during render calls

**Given** a render call
**When** it starts
**Then** the engine sets its own denormal mode on entry, verified by a test that renders identically after the host sets a different mode

### Story 1.3: Validator framework, locked ranges, and carrier rule

As Audio,
I want every recipe value checked against its locked range and the carrier rule from the start,
So that no out-of-range or under-ratio recipe can ever render, and each new layer arrives already guarded.

**Acceptance Criteria:**

**Given** the locked-range table from S0.3
**When** a recipe field is registered with the compiler
**Then** it names its range row ID, and a test fails for any range-governed field registered without a row

**Given** a value outside its locked range
**When** the recipe is compiled in `measure` or `final` mode
**Then** compile returns no plan and an error naming parameter, value, rule, and limit, and no output of any kind is produced
**And** values exactly at an inclusive bound pass, values just outside fail, and exclusive bounds ("below 1000 Hz", "below 30 Hz") reject the bound itself

**Given** the carrier rule check
**When** it is given a carrier and a modulation rate, or a rate interval for a rate curve
**Then** it rejects any carrier under 4 times the worst-case rate, naming parameter, value, rule, and limit
**And** unit tests cover a pass at exactly 4 times, a fail just under, and an interval whose maximum alone breaks the rule

### Story 1.4: Command-line renderer, report, and render speed

As Audio,
I want to render any recipe from the command line to a WAV plus a machine-readable report,
So that every rule can be checked without ears and every render carries its own evidence.

**Acceptance Criteria:**

**Given** a valid recipe
**When** the CLI renders it
**Then** it writes a 2-channel, 24-bit WAV at 48 kHz by default or 44.1 kHz when selected, rounding to 24 bits with no dither per the signal spec, and any other rate is refused
**And** the CLI includes only the public engine header, enforced by its build target

**Given** a render
**When** the report is written
**Then** it is JSON listing, per assertion, name, threshold row ID, threshold, measured value, and pass or fail, plus the determinism key, seed, and engine version

**Given** a rejected recipe
**When** the CLI runs
**Then** it writes no WAV, prints parameter, value, rule, and limit, and exits non-zero

**Given** the dev PC
**When** the render speed assertion runs
**Then** it passes at 20 times real time or faster, timed over render calls only
**And** on any other machine the report marks it not applicable instead of passing or failing

### Story 1.5: Python reference renderer for the stub chain

As Audio,
I want an independent Python renderer that agrees with the engine sample by sample,
So that engine bugs show up as numbers instead of slipping past by ear.

**Acceptance Criteria:**

**Given** `reference/`
**When** it renders a recipe
**Then** it reads recipe JSON, works in double precision, implements §core and §sine of the signal spec including phase increment quantization, uses the ideal sine, and passes the spec's worked test vectors
**And** a test proves it imports no engine code and loads no engine binary

**Given** the stub chain with the S0.2 sine routed through the theta reference stub as an unmodulated carrier
**When** engine pre-quantization float output and per-layer taps are compared with the reference
**Then** they differ by less than -100 dBFS sample by sample at 44.1 and 48 kHz

**Given** the reference match assertion
**When** either signal is below a minimum level set in the threshold table
**Then** the assertion fails as silent instead of passing
**And** a must-fail engine output doctored in the harness with a -90 dBFS error fails

### Story 1.6: Determinism and block-size invariance

As Audio,
I want every render to be a pure function of recipe, engine version, seed, and sample rate,
So that any render can be reproduced exactly, today or years from now, on any host.

**Acceptance Criteria:**

**Given** a recipe
**When** it is rendered twice, in one process and in two separate processes
**Then** the WAV files are byte-identical

**Given** the signal spec's internal block size section
**When** the same recipe is rendered at 1, 64, 512, and 4096 frames per call, and at an odd size such as 997
**Then** every output is byte-identical

**Given** a render report
**When** the determinism key is read
**Then** it equals recipe hash plus engine version plus sample rate (v0.1 pins no assets)

**Given** the engine symbol denylist from S0.1
**When** it is extended with every unseeded randomness source (`rand`, `std::random_device`, time-based seeding)
**Then** CI fails on any use inside `engine/` or the WAV writer
**And** this story's fixture joins the cross-platform hash check at both sample rates

## Epic 2: Every Core layer, exact and on time

Audio can render the theta reference, the gamma PAC layer (uncoupled, smooth swell, bursts), and the binaural layer, each proven on timing, frequency, isolation, and reference match, with rate curves and seamless loops.

Story order is fixed and is not numeric: 2.1, 2.2, 2.3, 2.5, 2.4, 2.6, 2.7. Story 2.5 runs before 2.4 so the AD-5 behavioral test exists before bursts. IDs are kept because the design log cites them.

### Story 2.1: Theta reference envelopes

As Audio,
I want the theta reference as a carrier AM at the theta rate with a sine, smoothed on-off, sawtooth, or reverse saw envelope,
So that the file carries a measurable theta phase for gamma to couple to.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §theta merges
**Then** it defines each envelope shape, its 0 degree point (sine peak, center of the on plateau, top before the drop, top after the rise), the edge smoothing of hard-edged shapes, and the theta AM depth law, with worked test vectors

**Given** a recipe with a theta reference
**When** it is compiled
**Then** carrier (100 to 500 Hz), rate (1 to 6 Hz), and AM depth (0 to 100 percent, design log 2026-10-29 (s)) are range-checked from the table, and the carrier rule is checked
**And** a custom envelope curve is rejected with a named rule ("shape not modeled in the signal spec")

**Given** each of the four shapes at the low and high ends of the rate range
**When** engine theta tap and output are compared with the reference
**Then** they differ by less than -100 dBFS sample by sample at both sample rates

**Given** the frequency accuracy tool, first calibrated on Python-synthesized tones with known frequencies
**When** it measures the theta carrier and theta rate
**Then** both are within 0.01 Hz of the recipe

**Given** the click tool (8 kHz high-pass, -60 dBFS), first calibrated on Python-synthesized signals with and without a known discontinuity
**When** it checks the smoothed on-off, sawtooth, and reverse saw renders
**Then** none has a discontinuity above -60 dBFS
**And** a must-fail unsmoothed sawtooth made in the harness fails

### Story 2.2: Gamma PAC layer, uncoupled

As Audio,
I want a separate gamma carrier AM at the gamma rate at constant depth,
So that the gamma layer exists on its own and an uncoupled control is available.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §gamma merges
**Then** it defines the gamma AM law and the uncoupled setting, with worked test vectors

**Given** a recipe with gamma set uncoupled
**When** it is compiled
**Then** carrier (200 to 500 Hz), rate (30 to 60 Hz), and depth (0 to 100 percent) are range-checked from the table
**And** the carrier rule rejects a 200 Hz carrier at a 60 Hz rate (limit 240 Hz) and accepts 240 Hz

**Given** a triangle or softened square gamma carrier
**When** it is compiled
**Then** it is rejected with a named rule ("non-sine carrier not modeled")

**Given** uncoupled gamma at 40 Hz and at 60 Hz, at 25 and 100 percent depth
**When** engine gamma tap and output are compared with the reference
**Then** they differ by less than -100 dBFS, the gamma carrier and rate are within 0.01 Hz, and AM depth is constant across the render

### Story 2.3: Gamma coupled, smooth swell

As Audio,
I want gamma depth to rise and fall with the theta reference and peak at the coupling phase,
So that the coupling is exact and measurable in the sound itself.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §coupling merges
**Then** it defines the depth function per theta shape, taking theta reference phase as its only input, with worked test vectors
**And** a structural test confirms the engine's gamma depth function takes theta phase as its only input (AD-5)

**Given** the coupling timing tool, which demodulates the gamma envelope from the gamma tap and recovers theta phase from the theta tap
**When** it is first calibrated on Python-synthesized signals with known peak times
**Then** it reports those peak times within the calibration tolerance in the threshold table, with any filter delay compensated
**And** it never reads the engine's internal depth value

**Given** smooth swell renders for each theta shape at coupling phases 0, 90, 180, and 270 degrees, at 25 and 100 percent depth
**When** coupling timing is measured
**Then** every gamma envelope peak is within 2 ms of its coupling phase
**And** must-fail renders doctored in the harness with the swell shifted 3 ms fail, while a 1 ms shift passes, at 25 and 100 percent depth

**Given** coupled gamma with no theta reference, or with theta reference AM depth at zero
**When** it is compiled
**Then** it is rejected with a named rule

**Given** coupled gamma renders
**When** compared with the reference
**Then** the gamma tap and output differ by less than -100 dBFS
**And** the gamma carrier plays continuously: only its AM depth varies

### Story 2.5: Binaural layer

As Audio,
I want two pure sines, one per ear, whose beat rate can follow a rate curve, joining after every other stage,
So that the binaural layer stays dichotic and exact, with nothing coupled to it.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §binaural and §rate-curve merge
**Then** they define right carrier = left carrier + beat(t), the rate-curve law and its closed-form phase integral, and the Sleep-style sinusoidal cycle with its start phase, with worked test vectors

**Given** a recipe with a binaural layer
**When** it is compiled
**Then** carriers (below 1000 Hz) and beat rate (0 to below 30 Hz, worst case over any rate curve) are range-checked
**And** a `binaural.waveform` other than sine (must-fail: `triangle`) is rejected with parameter `binaural.waveform`, rule "non-sine binaural not modeled", limit sine

**Given** binaural fixtures at several fixed beat rates including 0 Hz, and a sinusoidal cycle over 0 to 3 Hz every 60 s
**When** the isolation assertion renders with each ear's oscillator muted in turn
**Then** the muted carrier is at least 90 dB down in the other channel at engine output and at least 60 dB down after the master chain

**Given** the rate-curve fixture
**When** the frequency accuracy tool compares unwrapped tap phase with the closed-form integral of the schedule
**Then** the instantaneous rate is within 0.01 Hz of the schedule throughout, with continuous phase

**Given** a fixture with coupled gamma and binaural at a different beat rate, with values hand-checked against the spacing rule (re-confirmed by the validator in Epic 3)
**When** the binaural beat rate and phase are swept across renders
**Then** every gamma envelope peak time is unchanged to the sample (AD-5)

**Given** binaural renders
**When** compared with the reference
**Then** each ear's tap and the output differ by less than -100 dBFS

### Story 2.4: Gamma coupled, 50 ms bursts

As Audio,
I want gamma as 50 ms bursts centered on the coupling phase, depth-gated with soft edges,
So that the Focus layer has its burst shape without clicks or spectral spread into the theta reference.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §bursts merges
**Then** it defines a 50 ms full-width burst with 10 ms raised-cosine edges inside it (30 ms plateau), depth-gated so the carrier plays continuously, centered on the coupling phase (design log 2026-10-28 (o)), with worked test vectors

**Given** burst renders at gamma rates of 40, 45, and 60 Hz on a 250 Hz carrier beside a 450 Hz theta reference
**When** the spectrum is measured from the reference render
**Then** the worst gamma line at or above 394 Hz reproduces the research run `burst-edge-taper-2026-10-28` figures (about -51 dB at 60 Hz), within the tolerance stated in that run
**And** a must-fail carrier-gated rectangular 40 Hz burst made in the harness shows about -21 dB there and fails the click test

**Given** burst renders
**When** coupling timing is measured
**Then** each burst's center is within 2 ms of its coupling phase

**Given** burst renders
**When** the click tool checks burst edges
**Then** no discontinuity exceeds -60 dBFS

**Given** burst renders
**When** compared with the reference
**Then** the gamma tap and output differ by less than -100 dBFS

### Story 2.6: Rate curves on theta and gamma rates

As Audio,
I want the theta and gamma rates to follow recipe rate curves with the same law as the binaural beat,
So that every rate is variable, as rule 2 requires, with no new formula.

**Acceptance Criteria:**

**Given** the §rate-curve law from S2.5
**When** a recipe sets a rate curve on the theta rate or the gamma rate
**Then** the engine and reference use that law unchanged, and no new formula enters the spec

**Given** a rate curve
**When** it is compiled
**Then** its worst-case values over the whole curve are range-checked and carrier-rule-checked
**And** a must-fail gamma curve whose maximum alone breaks the carrier rule is rejected

**Given** theta and gamma rate-curve fixtures
**When** frequency accuracy is measured along each curve
**Then** the instantaneous rate is within 0.01 Hz of the schedule with continuous phase

**Given** coupled gamma over a theta rate curve
**When** coupling timing is measured along the curve
**Then** every gamma envelope peak is within 2 ms of its coupling phase

**Given** rate-curve renders
**When** compared with the reference
**Then** taps and output differ by less than -100 dBFS

### Story 2.7: Looping body and seams

As Audio,
I want looping recipes to play the ramp-in once and repeat the body seamlessly until the max run time,
So that Focus and Learn can run as long as needed with no click and no phase jump.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §loop merges
**Then** it defines how body length is set so theta and gamma phase are continuous at the seam, and how the session ends at the max run time, with worked test vectors

**Given** a looping recipe
**When** it is compiled without a max run time
**Then** it is rejected with a named rule
**And** a max run time outside its locked-range row is rejected

**Given** a looping fixture with a ramp-in and coupled gamma
**When** it is rendered across several seams to the max run time
**Then** the ramp-in plays once, the click tool finds no discontinuity above -60 dBFS at any seam or at the end, theta and gamma phase recovered from the taps show no jump at any seam, and coupling timing stays within 2 ms across seams

**Given** a looping plan
**When** a seek lands inside a later loop iteration
**Then** the samples are byte-identical to a continuous render at that point

**Given** looping renders
**When** compared with the reference
**Then** taps and output differ by less than -100 dBFS

## Epic 3: The validator catches collisions

Any recipe whose layers collide in either ear, at any point including along rate curves, is rejected with parameter, value, rule, and limit. The four starters' layer configurations are proven to pass here, not in Epic 6.

### Story 3.1: Spectral component table per shape

As a build agent,
I want one analytic table of every layer's spectral components, computed from the signal spec,
So that the validator and the tests agree on exactly what each layer puts in each ear.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §components merges
**Then** it gives the spectral component model for every v0.1 shape (each theta envelope, uncoupled gamma, smooth swell, bursts, binaural), with a spectral component defined as any line within 40 dB of the layer's strongest line (threshold table row), and worked test vectors

**Given** a compiled recipe
**When** the compiler builds its component table
**Then** it lists, per ear and per layer, every component's frequency or frequency interval (for rate curves) and level relative to the layer's strongest line
**And** a shape with no component model is rejected with a named rule

**Given** the spectrum tool, first calibrated on Python-synthesized multi-tone signals with known lines and levels
**When** it measures reference renders of every shape in Epic 2's fixtures
**Then** every measured line within 40 dB of its layer's strongest appears in the analytic table within the frequency and level tolerances in the threshold table, and no analytic component is missing from the measurement
**And** a must-fail component model doctored in the harness to drop one side frequency is caught by the cross-check

### Story 3.2: Spacing rule per ear, whole session

As Audio,
I want the validator to reject any recipe whose layers come within 50 Hz of each other in either ear, at any point in the session,
So that no layer beats against or leaks into another, and I know before rendering.

**Acceptance Criteria:**

**Given** a recipe's component table
**When** the spacing rule runs
**Then** in each ear it checks at least 50 Hz (threshold table row) between every component of one layer and every component of another, exempting a layer's own components and the binaural pair
**And** exactly 50 Hz passes and anything less fails

**Given** a rate curve on any layer
**When** the spacing rule runs
**Then** it checks the closed-form worst case over the curve's whole range, so a collision at any instant is found without sampling the session

**Given** a spacing failure
**When** compile returns
**Then** it produces no plan and an error naming the parameter, value, rule, and limit, plus both colliding components, their layers, the ear, and where in the session or rate range the minimum distance occurs

**Given** a must-fail fixture with a 250/256 Hz binaural pair beside a gamma PAC layer whose side frequency is at 260 Hz
**When** it is compiled
**Then** it is rejected for spacing in the right ear

**Given** the layer configurations of all four starters (Focus, Learn, Relax, Sleep, per `starter-recipes.md`), and Epic 2's coupled gamma plus binaural fixture
**When** they are compiled
**Then** every one passes the spacing rule
**And** if Focus fails, the story does not close until the cause is logged in the design log and resolved through the signal spec, never by weakening the rule

### Story 3.3: Early listening preview

As Audio,
I want to hear short renders of the four starter configurations as soon as every layer exists,
So that a harsh carrier or a rough gamma pulse is caught four epics before sign-off, not at it.

**Acceptance Criteria:**

**Given** the layer configurations of Focus, Learn, Relax, and Sleep that passed S3.2
**When** preview renders are made with the CLI
**Then** each is about 3 minutes long at 48 kHz, includes any ramp or seam the configuration has within that span, is marked unsigned and preview in its report, and is never stored as a golden

**Given** no loudness gain exists before Epic 4
**When** a preview is rendered
**Then** its level is set so the analytic sample peak of the summed layers is -30 dBFS (an engineering default for previews only, logged in the design log in this story), and Audio raises playback level in Reaper to comfort

**Given** the preview renders
**When** Audio listens on earbuds and on headphones
**Then** every observation is recorded in plain words, and any proposed change to a default or range is logged in the design log and routed to the story that owns it before Epic 4 starts
**And** if nothing needs changing, the story closes on that recorded result

## Epic 4: Safe, steady loudness

Every render hits its loudness target under the true-peak ceiling, gain ramps are smooth, the limiter provably never acts, and the CLI measures and stores the loudness gain.

Story order is fixed: the loudness meter comes first because stored gain, true peak, and the limiter all depend on it, and gain ramps come before the limiter so a ramp cannot trip it.

### Story 4.1: Loudness meter

As Audio,
I want a loudness meter proven against the broadcast compliance signals before it judges any render,
So that every loudness number in a report can be trusted.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §loudness merges
**Then** it defines integrated loudness per ITU-R BS.1770 (K-weighting, 400 ms blocks, absolute gate at -70 LUFS, relative gate at -10 LU) and the measurement window: the steady part of the session, with every ramp and fade excluded: for a looping recipe, the looping body only, repeated seamlessly a whole number of times to at least the length the spec sets; for a non-looping recipe, the longest stretch where no layer or master gain ramp is active (AD-13, design log 2026-11-01 (w), (x)); with worked test vectors
**And** a recipe whose steady part is shorter than the spec's minimum is rejected in `measure` mode with a named rule

**Given** a meter in the Python assertion library and a meter in the CLI tooling (outside `engine/`)
**When** each measures the EBU Tech 3341 compliance signals
**Then** each reads every signal within the tolerance Tech 3341 states for it
**And** the signals are fetched from the EBU at a pinned address and checked against a pinned SHA-256 before use; they are committed to the repo only if the EBU licence allows redistribution, and a hash mismatch fails the run
**And** a must-fail meter with gating turned off in the harness fails the gating cases

**Given** any render
**When** both meters measure it over the spec window
**Then** they agree within the Tech 3341 integrated loudness tolerance (threshold table row)

**Given** the loudness assertion
**When** it checks a render against the recipe target
**Then** integrated loudness within 1 LU passes
**And** a must-fail render doctored in the harness to 1.5 LU above target fails

### Story 4.2: Stored loudness gain

As Audio,
I want the CLI to measure each recipe's loudness once and store the gain in the recipe,
So that every render plays at its target level and nothing can silently change it.

**Acceptance Criteria:**

**Given** a recipe without a stored gain
**When** the CLI runs its measure command
**Then** it compiles in `measure` mode, renders, measures integrated loudness over the spec window, and writes the gain and a loudness hash into the recipe (AD-13)
**And** measuring the same recipe twice writes identical bytes

**Given** a recipe compiled in `final` mode
**When** its stored gain is missing, or any loudness-relevant field has changed since the loudness hash was written
**Then** compile is rejected with parameter, value, rule, and limit
**And** editing a field that is neither loudness-relevant nor audio-relevant leaves the recipe compilable

**Given** a recipe with a stored gain
**When** it is rendered in `final` mode
**Then** integrated loudness is within 1 LU of the recipe target
**And** a must-fail recipe whose stored gain is 1.5 LU off target fails the loudness assertion

**Given** any recipe rendered with its stored gain over its whole session (to the max run time for a looping recipe)
**When** integrated loudness is measured over the whole render, ramps and fades included
**Then** the report records it, and it is never more than 1 LU above the recipe target
**And** a must-fail looping fixture whose gain was measured over ramp-in plus one body (the superseded window) plays its body above target and fails

**Given** any CI run
**When** it finishes
**Then** no recipe file in the checkout has changed, so CI never writes a gain; a must-fail CI step that writes one is caught

### Story 4.3: True peak

As Audio,
I want every render's true peak measured with oversampling and held at or below -1 dBTP,
So that no render clips between samples on any playback device.

**Acceptance Criteria:**

**Given** the true-peak tool in the assertion library, per ITU-R BS.1770 Annex 2 oversampling
**When** it measures the EBU Tech 3341 true-peak signals and Python-synthesized signals with known inter-sample peaks
**Then** it reads each within its stated tolerance

**Given** a must-fail signal whose sample peak is below -1 dBFS but whose inter-sample peak is above -1 dBTP
**When** it is checked
**Then** the true-peak assertion fails while a sample-peak check would pass

**Given** every render, measured on the final 24-bit output
**When** the true-peak assertion runs
**Then** true peak is at or below -1 dBTP (threshold table row)

**Given** a recipe whose measured gain would put true peak above -1 dBTP
**When** the CLI measure command runs
**Then** it writes no gain and reports the target, the gain needed, and the resulting true peak

### Story 4.4: Gain ramps

As Audio,
I want per-layer and master gain ramps from the recipe, none faster than 10 ms,
So that fades and ramp-ins are smooth and click-free.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §ramps merges
**Then** it defines the gain ramp law for layer and master ramps, start and end alignment through the seconds-to-samples rule, and behavior at the end of a fade to silence, with worked test vectors

**Given** the per-layer taps from S1.2
**When** layer gain is added
**Then** each layer exposes a tap before its gain and a tap after it; coupling timing, frequency accuracy, and phase measurements read the tap before gain, and loudness reads the tap after gain
**And** at unity gain the two taps are bit-identical

**Given** a recipe ramp shorter than 10 ms (threshold table row)
**When** it is compiled
**Then** it is rejected with parameter, value, rule, and limit
**And** a ramp of exactly 10 ms passes

**Given** the ramp tool, first calibrated on Python-synthesized gain changes of known duration
**When** it checks layer taps and master output of ramp fixtures (a 5 min ramp-in, a 10 min layer ramp from silence, a 5 min master fade to silence)
**Then** no layer or master gain change completes in under 10 ms, with modulation envelopes and limiter gain reduction exempt
**And** a must-fail 5 ms layer fade doctored in the harness fails

**Given** ramp fixtures
**When** the click tool checks every ramp start and end
**Then** no discontinuity exceeds -60 dBFS

**Given** a fade to silence
**When** the fade ends
**Then** that layer or the master outputs exact zeros from then on, so no rhythmic signal remains after the end

**Given** ramp renders
**When** compared with the reference
**Then** taps and output differ by less than -100 dBFS

### Story 4.5: Limiter idle

As Audio,
I want proof that the stereo-linked limiter never acts on any v0.1 render,
So that every render is exactly the sound the recipe describes, with no hidden gain changes.

**Acceptance Criteria:**

**Given** `docs/signal-spec.md`
**When** §limiter merges
**Then** it defines the stereo-linked limiter, its ceiling, and its gain-reduction tap, with worked test vectors

**Given** every v0.1 render, starters and fixtures
**When** the limiter idle assertion runs
**Then** the gain-reduction tap is exactly unity on every sample, and master chain output equals input times master gain, bit for bit (design log 2026-10-28 (p))

**Given** a must-fail recipe whose stored gain is raised far enough to drive the limiter
**When** it is rendered
**Then** the limiter idle assertion fails
**And** the limiter applies the same gain reduction to both channels on every sample, and muted-ear binaural isolation after the master chain is still at least 60 dB

**Given** the must-fail limiter render
**When** compared with the reference
**Then** output differs by less than -100 dBFS, so the limiter is fully specified even though v0.1 never uses it

## Epic 5: Holds up for hours

Eight-hour renders stay on time and no render has a click, dropout, or invalid sample, with the full tier sharded to fit CI limits.

Two tiers. The fast tier runs on every change: drift is computed analytically from integer increments, and clicks, dropouts, and invalid samples are checked on 60 s renders. The full tier runs on every pull request into main and nightly: real 8-hour renders and full-length starters at both sample rates.

### Story 5.1: Whole-session 8-hour drift and full-tier sharding

As Audio,
I want an 8-hour render to stay on time at hour eight, with the long renders split to fit CI,
So that a session left running all night is as exact at the end as at the start.

**Acceptance Criteria:**

**Given** an 8-hour fixture with a theta reference on a rate curve, coupled gamma, and a binaural layer on a rate curve, all passing the spacing rule
**When** it is rendered in the full tier
**Then** at hour eight theta reference phase error measured from the tap against the closed form is under 1 ms, every gamma envelope peak is within 2 ms of its coupling phase, and every carrier and rate is within 0.01 Hz of the schedule

**Given** the session length row in the locked-range table (up to 8 h, design log 2026-11-01 (u))
**When** a recipe is compiled
**Then** a length of exactly 8 h passes and one sample longer is rejected with parameter, value, rule, and limit

**Given** a must-fail theta tap doctored in the harness to lose one sample per hour
**When** drift is measured
**Then** it fails at hour eight and passes at minute one

**Given** every fixture and starter
**When** the fast tier runs
**Then** drift at the full session length, or the max run time for a looping recipe, is computed analytically from the integer phase increments and is under 1 ms

**Given** the full tier
**When** an 8-hour render is split into shards across CI jobs using seek
**Then** the shards joined in order are byte-identical to one continuous render, and every shard finishes within its S0.1 wall-time budget
**And** the full tier runs across the AD-9 matrix on every pull request into main and nightly, and a failure blocks merge

**Given** the 8-hour fixture
**When** the reference renders windows at the start, hour four, and hour eight by seeking
**Then** engine taps and output in each window differ from the reference by less than -100 dBFS

### Story 5.2: Clicks, dropouts, NaN and infinite values

As Audio,
I want every render scanned end to end for clicks, dropouts, and invalid samples,
So that no flaw anywhere in a session goes unnoticed, not only at the places we expected.

**Acceptance Criteria:**

**Given** every render in both tiers
**When** the click assertion runs
**Then** it scans the whole render, not only seams and edges, and finds no discontinuity above -60 dBFS in an 8 kHz high-pass
**And** a must-fail render doctored with a single-sample step fails

**Given** the dropout tool, first calibrated on Python-synthesized signals with zero runs of known length
**When** it checks a channel where the recipe sets a non-zero level
**Then** an all-zero run of 1 ms passes and one sample longer fails (threshold table row)
**And** stretches where the recipe sets the level to zero, such as after a fade to silence, are exempt, read from the recipe's level schedule

**Given** engine pre-quantization float output and every per-layer tap
**When** the invalid-sample assertion runs
**Then** any NaN or infinite value fails
**And** must-fail taps doctored with one NaN and with one infinite value each fail

## Epic 6: Four starters you have heard and signed

Focus, Learn, Relax, and Sleep render and pass every check, and each carries Audio's provisional sign-off bound to the exact file heard. Closes v0.1.

### Story 6.1: Golden records and Git LFS

As Audio,
I want approved renders stored as golden files with a sign-off record bound to the exact bytes I heard,
So that any change to a sound I approved is caught, and nothing becomes golden without my ears.

**Acceptance Criteria:**

**Given** `golden/` tracked in Git LFS
**When** a golden is stored
**Then** it is keyed by determinism key and carries a record of stage (`provisional` or `full`), signer, date, the SHA-256 of the file heard, and coverage (`full`, or the time ranges heard in a spot check) (design log 2026-10-29 (q), 2026-11-01 (v))

**Given** a recipe listed in the golden manifest
**When** CI renders it
**Then** CI compares the render's SHA-256 with the hash in the golden's record; a mismatch fails, and a missing golden fails
**And** CI accepts both stages, and never downloads golden WAVs from Git LFS (LFS smudge off in CI); the WAVs are fetched only for listening

**Given** a platform the hash compare config runs in -100 dBFS tolerance mode (S0.2 fallback)
**When** CI checks its starter renders
**Then** it compares them sample by sample with the Windows x64 render of the same recipe from the same CI run, within -100 dBFS, instead of with the golden hash
**And** only platforms in exact mode check the golden hash

**Given** the expected golden storage for v0.1 (about 4.6 GB for eight renders at 24 bits)
**When** this story closes
**Then** it is checked against the repo's Git LFS storage and bandwidth quota, and any shortfall is recorded in the design log with the chosen remedy

**Given** a golden whose file hash no longer matches its record
**When** CI checks it
**Then** it is reported unsigned and fails, whatever its stage was
**And** a must-fail `full` golden with one byte changed is reported unsigned

**Given** a change that alters the determinism key, such as an engine version bump, while the render bytes stay identical
**When** CI checks the golden
**Then** the sign-off carries over, because it is bound to the file hash

**Given** the sign-off tool
**When** a golden is created or replaced
**Then** it requires a sign-off record, computes the SHA-256 itself, and no CI path can write a golden or a record

**Given** a starter whose story is in progress
**When** it is listed in the manifest as awaiting sign-off
**Then** CI reports it pending instead of failing, and a pending entry fails CI once Story 6.7 is marked done

### Story 6.2: Listening checklist

As Audio,
I want a listening checklist that an alpha tester with no signal background can follow,
So that every sign-off checks the same things in plain words.

**Acceptance Criteria:**

**Given** `docs/listening-checklist.md`
**When** it is read
**Then** it covers clicks and seams, roughness of the 40 Hz gamma AM, comfort over the full session length, carrier audibility on earbuds, loudness, one ear louder than the other, and unevenness over time
**And** every item asks about the sound only, never about feelings or outcomes, and passes the S0.4 wording check

**Given** a listening session
**When** the checklist is followed
**Then** it names the setup (Reaper for playback at full length, RX spectral view for clicks, earbuds and headphones) and produces a result file per render that the sign-off record links to

**Given** a recipe
**When** the transition list tool runs on it
**Then** it lists the time of the opening, every loop seam, every gain ramp or fade start and end, and the ending, so a spot check can cover each one
**And** a test confirms the list for a fixture with a ramp-in, a layer fade-in, three loop seams, and a fade to silence

### Story 6.3: Focus starter

As Audio,
I want the Focus starter as a recipe that passes every check,
So that the first mode is ready to hear and sign.

**Acceptance Criteria:**

**Given** `recipes/focus.json` with the values in `starter-recipes.md` (450 Hz theta reference carrier, sine AM at 6 Hz, 75 percent depth; 250 Hz gamma PAC carrier, AM at 40 Hz, 50 ms bursts at coupling phase 0 degrees, depth 100 percent; no binaural layer; 5 min ramp-in, looping body, max run time 45 min; -36 LUFS-I)
**When** it is compiled in `final` mode with its stored gain
**Then** it passes the validator, including the spacing rule between the burst components and the 450 Hz theta reference
**And** if it fails, the story closes only after the cause is logged in the design log and resolved through the signal spec, never by weakening the rule

**Given** the Focus recipe
**When** it is rendered at 44.1 and 48 kHz to the max run time
**Then** it passes every assertion from Epics 1 to 5, its hashes match across the AD-9 matrix, and it matches the reference

**Given** the recipe file
**When** its rationale and describe-the-sound note are read
**Then** the rationale cites the design log entry for every value, the note matches `docs/listening-modes.md`, and both pass the wording check
**And** the render is listed in the golden manifest as awaiting sign-off

### Story 6.4: Learn starter

As Audio,
I want the Learn starter as a recipe that passes every check,
So that the second mode is ready to hear and sign.

**Acceptance Criteria:**

**Given** `recipes/learn.json` with the values in `starter-recipes.md` (450 Hz theta reference carrier, sine AM at 5.5 Hz, 75 percent depth; 250 Hz gamma PAC carrier, AM at 40 Hz, smooth swell peaking at coupling phase 0 degrees, depth 100 percent; no binaural layer; 5 min ramp-in, looping body, max run time 20 min; -36 LUFS-I)
**When** it is compiled in `final` mode with its stored gain
**Then** it passes the validator

**Given** the Learn recipe
**When** it is rendered at 44.1 and 48 kHz to the max run time
**Then** it passes every assertion from Epics 1 to 5, its hashes match across the AD-9 matrix, and it matches the reference

**Given** the recipe file
**When** its rationale and describe-the-sound note are read
**Then** the rationale cites the design log entry for every value, the note matches `docs/listening-modes.md`, and both pass the wording check
**And** the render is listed in the golden manifest as awaiting sign-off

### Story 6.5: Relax starter

As Audio,
I want the Relax starter as a recipe that passes every check,
So that the third mode is ready to hear and sign.

**Acceptance Criteria:**

**Given** `recipes/relax.json` with the values in `starter-recipes.md` (450 Hz theta reference carrier, sine AM at 6 Hz, 75 percent depth, layer level ramping from silence to full over the first 10 min (design log 2026-10-29 (r)); 250 Hz gamma PAC carrier, AM at 40 Hz, smooth swell at coupling phase 0 degrees, depth 25 percent, layer level ramping from silence to full over the first 2 min (design log 2026-11-01 (t)); no binaural layer; 30 min, not looping; -36 LUFS-I)
**When** it is compiled in `final` mode with its stored gain
**Then** it passes the validator

**Given** the Relax recipe
**When** it is rendered at 44.1 and 48 kHz
**Then** it passes every assertion from Epics 1 to 5, its hashes match across the AD-9 matrix, and it matches the reference
**And** coupling timing during the theta and gamma level ramps is measured on the theta and gamma taps before layer gain, and every gamma envelope peak is within 2 ms of its coupling phase from the first theta cycle

**Given** the recipe file
**When** its rationale and describe-the-sound note are read
**Then** the rationale cites the design log entry for every value, the note matches `docs/listening-modes.md`, and both pass the wording check
**And** the render is listed in the golden manifest as awaiting sign-off

### Story 6.6: Sleep starter

As Audio,
I want the Sleep starter as a recipe that passes every check,
So that the only starter with a binaural layer is ready to hear and sign.

**Acceptance Criteria:**

**Given** `recipes/sleep.json` with the values in `starter-recipes.md` (450 Hz theta reference carrier, sine AM at a steady 2 Hz, 75 percent depth; no gamma PAC layer; binaural layer at 100 Hz left and 100 Hz plus beat rate right, beat rate cycling sinusoidally over 0 to 3 Hz every 60 s (design log (n)); 45 min with the last 5 min a master fade to silence, not looping; -36 LUFS-I)
**When** it is compiled in `final` mode with its stored gain
**Then** it passes the validator, including the spacing rule between the binaural pair and the theta reference

**Given** the Sleep recipe
**When** it is rendered at 44.1 and 48 kHz
**Then** it passes every assertion from Epics 1 to 5, its hashes match across the AD-9 matrix, and it matches the reference
**And** muted-ear binaural isolation passes across the whole beat-rate cycle, the final sample is exactly zero, and the output runs no longer than 45 minutes

**Given** the recipe file
**When** its rationale and describe-the-sound note are read
**Then** the rationale cites the design log entry for every value, the note matches `docs/listening-modes.md`, and both pass the wording check
**And** the render is listed in the golden manifest as awaiting sign-off

### Story 6.7: Provisional sign-off session and v0.1 gate report

As Audio,
I want to listen to every starter render against the checklist, sign the ones I approve, and see one report that says whether v0.1 is done,
So that v0.1 closes on my ears and on evidence, not on anyone's word.

**Acceptance Criteria:**

**Given** the eight starter renders (four starters at 44.1 and 48 kHz)
**When** Audio listens in Reaper and RX against the listening checklist: each starter in full at 48 kHz, and the 44.1 kHz copy as a spot check of every entry in its transition list (design log 2026-11-01 (v))
**Then** each approved render gets a provisional sign-off record bound to its SHA-256 with its coverage, is committed as a golden in Git LFS, and leaves the awaiting sign-off list
**And** a 44.1 kHz record whose spot-check ranges miss any entry in the transition list is refused by the sign-off tool

**Given** a listening session that stops partway
**When** it resumes later
**Then** the sign-off tool shows which renders and which transition-list entries are already heard and signed and which remain, so no listening is repeated or skipped

**Given** a checklist item that fails by ear
**When** Audio records it
**Then** it is logged in the design log, fixed in the story that owns the cause, re-rendered, and listened to again, and any changed default or threshold gets its own design log entry

**Given** CI artifacts from the full tier
**When** the gate report is generated
**Then** it lists every assertion for all four starters at both sample rates on all four AD-9 platforms with pass or fail, the matching render hashes, and the eight goldens with their sign-off records
**And** it shows the S0.5 review outcome for AD-4, AD-5, AD-9, AD-19, AD-20, and the Stack, and fails if any is still pending

**Given** the gate report
**When** every assertion passes, every hash matches, and all eight goldens carry Audio's provisional sign-off
**Then** v0.1 is done (design log 2026-10-29 (q)); full sign-off by a second listener follows in Phase 1
