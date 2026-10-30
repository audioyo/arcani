---
id: SPEC-arcani-v0-1
companions:
  - thresholds-and-ranges.md
  - starter-recipes.md
  - glossary.md
  - ../../planning-artifacts/architecture/architecture-Arcani-2026-10-27/ARCHITECTURE-SPINE.md
  - ../../../docs/design-log.md
  - ../../../docs/research-library.md
  - ../../../docs/listening-modes.md
sources:
  - ../../planning-artifacts/prds/prd-Arcani-2026-10-27/prd.md
  - ../../planning-artifacts/prds/prd-Arcani-2026-10-27/addendum.md
  - ../../../docs/project-plan.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate in v0.1. Sources are for traceability; consult them only for narrative rationale or for later phases, which this contract omits.

# Arcani v0.1: Engine Core and Signal Test Suite

## Why

Arcani is a vision to realize: procedural entrainment audio whose signal design is transparent, reproducible, and honestly described, where comparable apps make outcome claims and document nothing. Every later phase (designer, Android and iOS apps, stems, Orbit) sits on one C++ engine, so v0.1 proves that engine correct first, on the desktop, before anything is built on it. Audio, the sole designer and tester, needs to know without listening that a recipe is isolated, coupled on time, spaced, exact, and click-free, and to trace every default to a source. An earlier project broke when spatial processing reached its binaural carriers; v0.1 makes that class of bug fail a test within seconds.

## Capabilities

- **CAP-1** Signal spec
  - **intent:** `docs/signal-spec.md` is the single source of every v0.1 formula, implemented by both the engine and the Python reference (AD-19).
  - **success:** It defines envelope shapes and their 0 degree point, the coupling depth function, bursts, ramp and rate-curve laws, phase increment quantization and accumulator width, loop seam behavior, the limiter, internal block size, the seconds-to-samples rule, the loudness window, and the spectral component model per shape. The validator rejects any shape the spec does not model.
- **CAP-2** Engine clock (FR-1)
  - **intent:** One engine clock drives every rate and phase in a session.
  - **success:** Theta reference phase error under 1 ms after an 8-hour render. Every carrier and rate within 0.01 Hz of the recipe; along a rate curve, instantaneous rate within 0.01 Hz of the schedule with continuous phase.
- **CAP-3** Theta reference (FR-2)
  - **intent:** The engine generates a carrier AM at the theta rate with a sine, smoothed on-off, sawtooth, or reverse saw envelope, all set by the recipe.
  - **success:** Envelope shape matches the reference renderer; hard-edged shapes pass the click test.
- **CAP-4** Gamma PAC layer (FR-3, AD-5)
  - **intent:** The engine generates a separate carrier AM at the gamma rate whose depth follows the theta reference phase and peaks at the coupling phase, as a smooth swell or 50 ms bursts, or uncoupled at constant depth. Swells and bursts are depth-gated: the carrier plays continuously. A burst's 50 ms is its full width, with 10 ms raised-cosine edges inside it (design log 2026-10-28 (o)).
  - **success:** Every gamma envelope peak within 2 ms of its coupling phase. Changing the binaural beat rate or phase leaves every gamma peak time unchanged to the sample. The validator rejects coupled gamma when the theta reference is absent or at zero depth.
- **CAP-5** Binaural layer on an isolated path (FR-4, AD-4)
  - **intent:** The engine generates two pure sines, one per ear, whose frequencies may follow a recipe rate curve, that join the stereo bus after every other stage, with only the master chain after them.
  - **success:** With one ear's oscillator muted, its carrier is at least 90 dB down in the other channel at engine output and 60 dB down after the master chain, at any beat rate including 0 Hz. A structural test confirms the stage list. A non-sine binaural waveform is rejected in v0.1 with a named rule; the compile warning applies once the signal spec models it (design log 2026-10-28 (o)).
- **CAP-6** Gain ramps, loudness gain, limiter (FR-5, AD-4, AD-13)
  - **intent:** The engine applies per-layer and master gain ramps from the recipe and a loudness gain measured at export and stored in the recipe, with a stereo-linked limiter that stays idle at that gain.
  - **success:** No gain ramp completes in under 10 ms. Integrated loudness within 1 LU of the recipe target; true peak at or below -1 dBTP. Limiter gain reduction stays under the design-log bound on every render. `final` compile rejects a missing gain or a mismatched loudness hash.
- **CAP-7** Deterministic synthesis (FR-6, AD-9, AD-10, AD-14, AD-21)
  - **intent:** Output is a pure function of recipe, engine version, seed, and sample rate, on every platform and at any host block size.
  - **success:** Repeat renders are byte-identical. Rendering at 1, 64, 512, and 4096 frames per call gives identical bytes. Hashes match across the full AD-9 CI matrix, or a component uses a logged -100 dBFS fallback. Native 44.1 and 48 kHz with no resampling. Every report carries the determinism key.
- **CAP-8** Recipe file (FR-7, AD-15, AD-21)
  - **intent:** One JSON recipe fully defines a session: every layer's parameters, gain ramps, rate curves, levels, length, looping flag and max run time, schema and engine version, seed, author, date, rationale, loudness target, and stored gain and hash.
  - **success:** A JSON Schema in the repo validates every starter and fixture. Signals are named by carrier, modulation type, and rate. Looping recipes repeat the body with no click and no theta or gamma phase jump at the seam. An unsupported schema major version is rejected. The recipe hash is SHA-256 over RFC 8785 canonical JSON, minus the fields the schema excludes.
- **CAP-9** Validator and compiler (FR-8, FR-9, FR-10, AD-2, AD-20)
  - **intent:** The engine compiles a recipe into an immutable render plan, in `measure` or `final` mode, or rejects it.
  - **success:** Rejects any value outside the locked-range table, any carrier under 4 times its modulation rate, and any spacing failure in either ear at any point including rate curves. Each rejection names parameter, value, rule, and limit and produces no output. The renderer accepts only plans.
- **CAP-10** C API (AD-12)
  - **intent:** One `arc_`-prefixed C API is the only way into the engine for the CLI and C++ tests.
  - **success:** The CLI and tests use only the public header. Errors return a status code plus a structured error (parameter, value, rule, limit).
- **CAP-11** Command-line renderer (FR-11, AD-13, AD-17)
  - **intent:** Audio or an agent renders a recipe to a 24-bit WAV (48 kHz default, 44.1 kHz selectable) plus a machine-readable assertion report, and the CLI measures and writes the loudness gain.
  - **success:** At least 20 times real time on the dev PC. The report lists per assertion: name, threshold, measured value, pass or fail, plus determinism key and seed. A rejected recipe writes no WAV.
- **CAP-12** Python reference renderer (FR-12, AD-16)
  - **intent:** An independent Python renderer produces every v0.1 layer and the master chain from recipe JSON in double precision, implemented from the signal spec only.
  - **success:** Engine pre-quantization float output and per-layer taps differ from the reference by less than -100 dBFS, sample by sample. The reference imports no engine code.
- **CAP-13** Assertion library (FR-13, AD-17)
  - **intent:** One assertion library checks every render against one threshold table (`thresholds-and-ranges.md`).
  - **success:** It runs every assertion in that table. Test fixtures beyond the starters include binaural at several beat rates including 0 Hz and a sweep, and coupled gamma with binaural at a different beat rate, all passing the spacing rule.
- **CAP-14** Golden files (FR-14, AD-15)
  - **intent:** Renders Audio approves become golden files, keyed by determinism key and stored in Git LFS.
  - **success:** Any change that alters a golden render fails; a missing golden file fails the run; a golden file is created or replaced only with a recorded sign-off.
- **CAP-15** Local and CI runs (FR-15, AD-9, AD-17)
  - **intent:** The fast tier runs locally after every change and in CI on every push; the full tier (8-hour drift, full-length starters, both sample rates) runs on every pull request into main and nightly, across the full AD-9 matrix.
  - **success:** A failure in either tier blocks merge. CI fails when `-ffp-contract=off` or no-fast-math flags are missing. CI checks docs and recipe descriptions for banned terms, comparables' feature names, health or outcome claims, and em dashes.
- **CAP-16** Starter recipes (FR-16)
  - **intent:** v0.1 ships Focus, Learn, Relax, and Sleep recipes per `starter-recipes.md`.
  - **success:** Each passes the validator and every assertion. Focus and Learn loop with a max run time. Only Sleep has a binaural layer. Sleep fades to silence. Every value is traced in the design log. Each carries a describe-the-sound note (when to use it, what the sound is, evidence strength) matching `docs/listening-modes.md`.
- **CAP-17** Listening checklist and sign-off (FR-17)
  - **intent:** A listening checklist lives in the repo, and Audio records a sign-off against it for every render before it becomes a golden file.
  - **success:** The checklist covers clicks and seams, roughness of 40 Hz gamma AM, comfort over the full session length, carrier audibility on earbuds, and loudness. Every golden file has a Reaper and RX sign-off record.

## Constraints

- Same recipe, engine version, seed, and sample rate give byte-identical output. No unseeded randomness; all randomness comes from the engine's counter-based PRNG (seed, stream name, index). No dither in v0.1.
- `engine/` depends only on the C++ standard library: no libm transcendentals, 64-bit integer phase accumulators, no `long double`, `-ffp-contract=off`, no fast-math, engine-set denormal mode. The render call never allocates, locks, blocks, or does I/O (AD-1, AD-9, AD-11).
- Every rate, carrier, coupling phase, depth, and beat rate is a recipe parameter inside a locked range traced to the design log. Nothing is hard-coded.
- Core topology is fixed in code: the schema has no routing fields and no coupling-target field.
- The binaural pair never passes through any spatial, HRTF, ambisonic, reverb, width, or channel-mixing stage. The master chain is per-channel gain plus a stereo-linked limiter only. The engine never sums or downmixes channels.
- Gamma couples only to the in-file theta reference, never to a binaural beat.
- Carrier rule (at least 4 times) and spacing rule (50 Hz per ear, 40 dB component threshold, both placeholders) are computed analytically across the whole session.
- `docs/signal-spec.md` is the only formula source. The reference is never ported from or linked to engine code.
- Tests are written first from acceptance criteria by a fresh-context QA agent. Never weaken a threshold; propose a change with a reason. Code and tests read thresholds and ranges from one table each, never hard-coded. Never trade a threshold for speed.
- Golden files change only after Audio's recorded listening sign-off. v0.1 golden files are provisional: if Phase 0 changes a threshold or default, Audio re-approves the affected renders by ear.
- Every default, range, and threshold traces to the research library, a logged listening test, or a declared engineering default in the design log. Every change gets a design log entry. Unsure means stop and ask.
- No term from CLAUDE.md's "Never" list or PRD §6's comparables' feature names, no health or outcome claims, and no em dashes. Every signal is named by carrier, modulation type, and rate.
- Clean room: no third-party program names, recipes, recordings, scripts, levels, or session arcs, and nothing learned through private channels.
- Stack and conventions follow the architecture spine (C++20, Clang toolchains, CMake 4.4.5, Catch2 3.16.1, Python 3.14, uv 0.13.6, NumPy 2.5.4; recipe JSON `snake_case` with units in field names).

## Non-goals

- Desktop designer, mobile apps, and device audio output (miniaudio).
- Stem bed, Tone zone, resampler, 3D renderer, and Orbit layer.
- Accounts, analytics, payments, content server, and encryption.
- Custom envelope curves and non-sine carriers (rejected until the signal spec models them).
- Listener-level ceiling (Phase 3).
- Locking any provisional range, threshold, or default; Phase 0 research and the independent review do that.
- Any health or outcome claim, and any coupling to a binaural beat.

## Success signal

- Every assertion passes in CI across the full AD-9 matrix (Windows x64, arm64, macOS arm64, Android NDK arm64) for all four starters at 44.1 and 48 kHz, with matching render hashes, and eight provisional golden files exist, each with Audio's recorded Reaper and RX sign-off.

## Assumptions

- v0.1 theta envelopes are sine, smoothed on-off, sawtooth, and reverse saw; gamma and binaural carriers are sine only. FR-3's triangle and softened square carriers and FR-4's non-sine binaural are rejected until the signal spec models them (spine Deferred, AD-20).
- The v0.1 C API covers what the CLI and tests need: compile (`measure`, `final`), render frames, seek, per-layer taps, warnings, engine version. Provide asset, submit plan, `audition` mode, and state snapshot arrive with their first host in Phase 1.
- v0.1 builds on the REVIEW PENDING ADs (AD-4, AD-5, AD-9, AD-19, AD-20) and the Stack as written; their independent review is due by the end of Phase 0.
- Hearing safety in v0.1 means loudness and true-peak targets on every render.
- Every starter uses a sine theta reference envelope, and Focus and Learn run gamma at 100 percent depth; `listening-modes.md` names neither.

## Open Questions

- None open. The limiter idle bound is zero gain reduction in v0.1 (design log 2026-10-28 (p)).
