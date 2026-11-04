---
name: 'Arcani'
type: architecture-spine
purpose: build-substrate
altitude: initiative
paradigm: 'Functional core with adapters (hexagonal), split into a fixed-topology Core zone and a free-form Tone zone'
scope: 'Whole Arcani product: engine, CLI renderer, Python reference, test harness, desktop designer, Android and iOS apps, content storage. Deep for v0.1 and the Phase 0 Android spike; later phases fixed only where they shape the engine now.'
status: final
created: '2026-10-27'
updated: '2026-11-04'
binds: [FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, FR-27, FR-28, FR-29, FR-30, FR-31, FR-32, FR-33, FR-34, FR-35, FR-36, FR-37, FR-38]
sources:
  - _bmad-output/planning-artifacts/prds/prd-Arcani-2026-10-27/prd.md
  - _bmad-output/planning-artifacts/prds/prd-Arcani-2026-10-27/addendum.md
  - _bmad-output/planning-artifacts/prds/prd-Arcani-2026-10-27/review-architecture-readiness.md
  - docs/design-log.md
  - docs/listening-modes.md
  - docs/project-plan.md
  - CLAUDE.md
companions:
  - .memlog.md
  - reviews/
---

# Architecture Spine: Arcani

**Review status.** The independent review CLAUDE.md rule 4 requires closed on 2026-11-04 (Story 0.5, `reviews/review-independent-s0-5.md`, design log 2026-11-04 (ee)): AD-4, AD-19, and AD-20 locked with wording edits; AD-5, AD-9, and the Stack table changed with Audio's approval, then locked. A later change to any AD goes through the memlog and the design log.

## Design Paradigm

**Functional core with adapters (hexagonal).** The engine is a pure, deterministic function: render plan + assets + seed + sample index in, samples out. It owns no threads, devices, files, network, or UI. Every host (CLI renderer, designer, Android app, iOS app, test harness) is an adapter around the same engine through one C API.

Inside the engine, sound is split into two zones:

- **Core zone:** the entrainment signals (theta reference, gamma PAC layer, binaural layer). Topology is fixed in code. Recipes set parameters inside locked ranges and never set routing.
- **Tone zone:** stems, music, ambience, noise, and built-in effects. Routing is free-form data in the recipe, so each track gets its own character. It never reads or feeds the Core zone.

```mermaid
flowchart TB
  subgraph Hosts["Adapters (hosts)"]
    CLI["CLI renderer (v0.1)"]
    DES["Designer (Flutter desktop, Phase 1)"]
    APP["App (Flutter Android and iOS, Phase 3 and 4)"]
    TST["Test harness"]
  end
  API["Engine C API"]
  subgraph Engine["Engine (plain C++, no framework)"]
    VAL["Validator and plan compiler"]
    REN["Renderer"]
    CORE["Core zone (fixed topology)"]
    TONE["Tone zone (free-form graph)"]
  end
  IO["miniaudio (device output, hosts only)"]
  SPEC["docs/signal-spec.md"]
  REF["Python reference"]
  CLI --> API
  DES --> API
  APP --> API
  TST --> API
  API --> VAL
  API --> REN
  REN --> CORE
  REN --> TONE
  DES --> IO
  APP --> IO
  SPEC -. "only source of formulas" .-> Engine
  SPEC -. "only source of formulas" .-> REF
```

Dependency direction: hosts depend on the C API; the C API depends on the engine; the engine depends on nothing outside `engine/` except the C++ standard library (no libm transcendentals, see AD-9). miniaudio is used by hosts, never by `engine/`. The Python reference depends on the signal spec and recipe JSON, never on engine code.

## Invariants & Rules

### AD-1: The engine is a pure deterministic core [ADOPTED]

- **Binds:** engine, all hosts (FR-6, FR-11, FR-20, FR-35)
- **Prevents:** hosts embedding DSP, device or thread state leaking into output, the designer and app sounding different from a render.
- **Rule:** Code under `engine/` has no dependency on threads, clocks, devices, files, network, UI, or any framework. Its output is a function of (plan, assets, seed, sample rate, sample index) only. Seeking to a sample index is a pure function of those inputs. Audio I/O, file I/O, and UI live in host adapters. No host performs synthesis or mixing of its own.

### AD-2: Recipes reach the renderer only as validated, immutable plans [ADOPTED]

- **Binds:** validator, renderer, CLI, designer, publish (FR-7 to FR-10, FR-21, FR-23)
- **Prevents:** a code path that renders an unvalidated recipe; a second validator drifting from the first.
- **Rule:** The engine's compiler turns a recipe into an immutable render plan; the renderer accepts only a plan. Compile returns blocking errors (parameter, value, rule, limit; no plan) and non-blocking structured warnings (for example a non-sine binaural waveform, FR-4). Compile modes: `measure` (loudness gain may be absent; used only by the exporting tool), `audition` (stale gain allowed, with a warning), and `final` (everything enforced; required for render to golden, export, and publish). No host implements its own validation; the designer calls the engine compiler for every check.

### AD-3: Core zone topology is fixed in code; Tone zone routing is data [ADOPTED]

- **Binds:** engine, recipe schema, designer (FR-2 to FR-5, FR-18, FR-24)
- **Prevents:** free routing reaching an entrainment layer; the designer exposing Core wiring.
- **Rule:** The recipe schema has no routing fields for the Core zone, only parameters. The Tone zone is a directed graph of stem sources and built-in effects described in the recipe. No Tone graph node can take a Core signal, Core state, or the binaural path as input.

### AD-4: Fixed mix order, binaural joins last, limiter stays idle [ADOPTED]

- **Binds:** engine mix stage, 3D renderer, master chain (FR-4, FR-5, FR-25, FR-27)
- **Prevents:** the binaural pair passing through any spatial, HRTF, ambisonic, reverb, width, or channel-mixing stage (the bug that broke an earlier project); limiter gain modulation reaching the binaural pair.
- **Rule:** The mix order is fixed as drawn in *Signal flow*. The binaural path is two sine oscillators and per-channel gain, summed into the stereo bus after every spatial and effect stage. The master chain contains only per-channel gain and a stereo-linked limiter, with its algorithm in the signal spec; no mid/side, crossfeed, width, matrix, or any operation that mixes channels. At the stored loudness gain the limiter must stay idle: its gain reduction stays under a bound set in the design log (v0.1: zero gain reduction; master chain output equals input times master gain, bit for bit; design log 2026-10-28 (p)), asserted on every render. Any non-zero bound is a design log entry with measured gain-reduction data (design log (p), Revisit). The engine never sums or downmixes its output channels. A structural test checks the stage list; the signal isolation test (FR-4) checks the output.

### AD-5: Gamma couples only to the theta reference [ADOPTED]

- **Binds:** gamma PAC layer, recipe schema, validator (FR-3, FR-4)
- **Prevents:** gamma coupled to a binaural beat, which has no waveform in the file.
- **Rule:** Coupled gamma modulation depth is a function of the theta reference phase only, plus static recipe parameters (shape, coupling phase, coupling depth), as defined per envelope shape in the signal spec. Uncoupled gamma has constant AM depth (FR-3). The schema has no coupling-target field. The validator rejects coupled gamma wherever gamma level and depth are both non-zero while the theta reference is absent, at zero level, or at zero AM depth (design log 2026-11-04 (ee)). Zero level means the theta reference layer's gain, including its ramp, evaluated per sample, is exactly zero; master gain scales both layers alike and does not count. Gamma level uses the same definition. Test: changing the binaural beat rate or phase leaves every gamma envelope peak time unchanged to the sample.

### AD-6: The Tone zone never reads Core timing and carries no entrainment-rate rhythm

- **Binds:** Tone zone, stem sequencer, stem motion, effects, stem curation (FR-24, FR-26, FR-27)
- **Prevents:** ambience becoming an untracked entrainment signal through motion, effect LFOs, gating, or baked-in pulses.
- **Rule:** The Tone zone runs on its own musical clock and reads no Core clock, phase, or envelope state. Every time-varying Tone parameter (object motion, effect LFOs, gates, tempo-synced effects) has a locked rate range traced to the design log, enforced by the validator. The stem curation checklist screens baked stems for periodic level changes at entrainment rates. Tone sync to Core timing is revisited only after the PRD Q9 patent check.

### AD-7: No third-party plugin code runs in the engine

- **Binds:** Tone zone effects, designer, stem pipeline (FR-24, FR-26)
- **Prevents:** designer and phone sounding different; plugin output that cannot be reproduced or run on mobile.
- **Rule:** Effects come in two tiers. Baked: any third-party plugin is applied offline in a DAW and printed into the stem file; the file is the artifact. Live: only engine-owned effects run at playback. "Engine-owned" means written for the engine, or vendored source compiled under AD-9 rules and proven bit-exact. The engine links no plugin-hosting code.

### AD-8: 3D audio is rendered by the engine, never the device

- **Binds:** 3D renderer, Orbit layer, stems, app output (FR-27, FR-28, FR-34)
- **Prevents:** device or Atmos spatializers deciding the sound; HRTF applied to the binaural pair; motion shifting frequencies.
- **Rule:** One engine-owned 3D object renderer places and moves the gamma PAC layer (Orbit) and Tone zone stems (static or moving, per recipe). The theta reference and binaural layer never enter it. Motion applies no Doppler or pitch shift. The engine outputs plain stereo. No head tracking in v1. The app never hands audio to an OS or Dolby spatializer.

### AD-9: The engine is bit-exact across platforms

- **Binds:** all engine code: Core, stem decoder, resampler, built-in effects, 3D renderer (FR-6, FR-35)
- **Prevents:** PC, Android, and iOS producing different samples for the same plan.
- **Rule:** Engine code uses engine-owned math for sine and every transcendental (no libm), 64-bit integer phase accumulators, no `long double`, and no explicit fused multiply-add. Every float-to-integer conversion clamps to the target range first and never receives NaN, by a rule in the signal spec. Every toolchain compiles the engine with `-ffp-contract=off` and no fast-math (clang-cl through `/clang:`), and CI fails if the flags are missing. On entry to each C API call that does floating-point work (compile, render, seek) the engine sets IEEE denormal handling (no flush to zero, no denormals-are-zero) and restores the host's mode on every return, including an error status. x86 targets are x86-64 only; Android ships arm64-v8a only. Stems decode through an engine-owned decoder (AD-7), never the OS. CI renders on Windows x64 (clang-cl), Windows arm64 (clang-cl), macOS arm64 (Apple clang), and Android NDK arm64 (the NDK build, linked statically, run on hosted arm64 Linux; design log 2026-11-02 (aa)), and compares hashes exactly against Windows x64 and against the expected hashes in the repo. Before the Phase 0 part 2 stack spike closes, the engine library from the real Android app build matches the same hashes on a physical phone. A component that cannot be exact on a platform falls back to the -100 dBFS tolerance for that platform and component only, through a `ci/hash_tolerance.json` entry that cites a design log entry; the entry shows the cause lies outside these rules (a Core zone mismatch is a bug, not a fallback) and gets the independent review CLAUDE.md rule 4 requires. S0.2 result: byte-identical on all four platforms with no fallback (design log 2026-11-03 (bb)); rule text from design log 2026-11-04 (ee).

### AD-10: Output is independent of block size; native 44.1 and 48 kHz

- **Binds:** renderer, all hosts, stem playback (FR-6, FR-11, FR-20)
- **Prevents:** host callback size or device rate changing the samples.
- **Rule:** The renderer processes in a fixed internal block, size set in the signal spec, and buffers to whatever the host asks for. Rendering at 1, 64, 512, and 4096 frames per call yields identical bytes. The Core renders natively at 44.1 and 48 kHz and is never resampled. Tone zone stems whose rate differs from the output rate pass through an engine-owned deterministic resampler. Recipe and spec time values are in seconds and convert to samples by one rule in the spec. Byte identity is per sample rate; tests and golden files cover both.

### AD-11: Real-time contract on the audio thread

- **Binds:** engine render call, designer, app (FR-20, FR-22, FR-30)
- **Prevents:** dropouts from allocation or locks; UI work stalling audio; clicks from live edits.
- **Rule:** The render call never allocates, locks, blocks, or does I/O. Hosts change sound only by submitting a new plan; the engine swaps it at a block boundary with gain ramps of at least 10 ms and continuous Core phase. Hosts read engine state only from a snapshot the engine publishes without locks. Plans are reference-counted by the engine; a host releases its handle and the engine frees the plan off the audio thread. Render identity is guaranteed for an unedited plan.

### AD-12: One small C API is the only way into the engine

- **Binds:** engine, CLI, designer, app, C++ tests (FR-11, FR-18 to FR-22, FR-29)
- **Prevents:** hosts reaching engine internals; Flutter and the CLI using different entry points.
- **Rule:** All hosts, including Flutter through dart:ffi, use one C API with a stable ABI: provide asset, compile recipe (with mode), render frames, seek, submit plan, read state snapshot, read per-layer taps (offline only), read warnings, engine version. Errors return a status code plus a structured error (parameter, value, rule, limit).

### AD-13: Loudness gain is measured at export and stored in the recipe

- **Binds:** CLI (v0.1), designer, validator, test suite (FR-5, FR-23; resolves PRD Q6)
- **Prevents:** live playback and offline renders reaching the loudness target by different routes.
- **Rule:** The exporting tool (the CLI in v0.1, the designer from Phase 1) compiles in `measure` mode, renders, measures integrated loudness over the window the signal spec defines (the steady part, with every ramp and fade excluded: for looping recipes, the looping body only, repeated seamlessly to the length the signal spec sets; for non-looping recipes, the longest stretch with no gain ramp active; design log 2026-11-01 (w), (x)), and writes the gain and a loudness hash into the recipe. The loudness hash covers the schema fields tagged as loudness-relevant plus asset hashes. `final` compile rejects a missing gain or a mismatched hash. Live and offline use the same stored gain; listener intensity (FR-31) scales after it. Each recipe names its loudness target, set from the design log. The test suite confirms within 1 LU.

### AD-14: One seed drives all randomness, through a counter-based generator

- **Binds:** engine, stem sequencer, WAV writer (FR-6, FR-24)
- **Prevents:** unseeded randomness; draw order depending on loops, seeks, or plan swaps.
- **Rule:** All randomness comes from an engine-owned counter-based PRNG: each value is a pure function of (seed, stream name, index). Each consumer has its own named stream. No other randomness source exists in engine or render output code. v0.1 WAV output rounds to 24 bits without dither; any later dither uses its own named stream.

### AD-15: Recipes and engine are versioned; golden files are keyed and signed off

- **Binds:** recipe schema, engine, golden files, content updates (FR-7, FR-14, FR-17, FR-33)
- **Prevents:** an engine silently reinterpreting an old recipe; golden files drifting or appearing without sign-off.
- **Rule:** Every recipe declares a schema version and an engine version. The engine rejects a schema major version it does not support. A golden file is keyed by the determinism key (AD-21) and matches byte for byte; for a component on the AD-9 fallback, cross-platform comparison uses the -100 dBFS tolerance. A missing golden file fails the run. A golden file is created or replaced only after Audio's recorded sign-off against the listening checklist (Reaper and RX).

### AD-16: The Python reference is independent of the engine [ADOPTED]

- **Binds:** reference renderer, test suite (FR-12, FR-13)
- **Prevents:** the reference sharing the engine's bugs.
- **Rule:** The reference renders from the recipe JSON in double precision, implemented from the signal spec (AD-19), including its phase quantization, and never ported from or linked to engine code. It covers every layer and the master chain v0.1 renders. The comparison uses the engine's pre-quantization float output and per-layer taps, at less than -100 dBFS sample by sample.

### AD-17: One assertion library; every render produces a machine-readable report

- **Binds:** CLI, test suite, CI, designer publish, build agents (FR-11, FR-13 to FR-15, FR-23)
- **Prevents:** agents, humans, and the publish gate judging renders by different evidence.
- **Rule:** One assertion library runs every check in CLAUDE.md and FR-13: binaural isolation, coupling timing, envelope shape, carrier and spacing rules, frequency accuracy, 8-hour drift, reference match, determinism, block-size invariance, clicks, dropouts, NaN or infinite values, gain ramps, limiter idle, loudness and true peak, render speed (reference machine only). The CLI, test suite, and designer publish all call it. Each render writes a report: per assertion name, threshold, measured value, pass or fail, plus determinism key and seed. Thresholds come from one table in the repo, each row traced to the plan or design log. Fast tier (short renders) runs on every push; full tier (8-hour drift, full-length starters, both rates) runs on every pull request into main and nightly. A failure in either blocks merge.

### AD-18: The visualizer is calm and never flickers at entrainment rates

- **Binds:** app UI, designer UI (Phase 3; new scope)
- **Prevents:** visual flicker acting as an untracked entrainment stimulus or a photosensitivity risk.
- **Rule:** The visualizer reads only a slow session-arc snapshot (levels and session position, smoothed below a rate set in the design log), never raw Core phase. It never flashes or pulses at theta, gamma, or beat rates and never exceeds 3 flashes per second (WCAG 2.3.1). It stops drawing when the screen is off.

### AD-19: One signal spec is the only source of formulas

- **Binds:** engine, Python reference, validator, tests (FR-1 to FR-12)
- **Prevents:** engine and reference choosing different but reasonable formulas and failing the -100 dBFS match, or a test measuring something different from what the engine makes.
- **Rule:** `docs/signal-spec.md` defines every formula evaluated per sample: envelope shapes and their 0 degree point, coupling depth function, bursts, per-layer AM and carrier laws, ramp and rate-curve laws, phase increment quantization and accumulator width, the seconds-to-samples rule, the sine, loop seam behavior, limiter, resampler, PRNG, internal block size, loudness measurement window, and the spectral component model per shape. For each transcendental it gives the ideal function, which the reference renders, and the engine algorithm with its error bound and pinned output bits (design log 2026-10-28 (o)). Engine and reference implement it; neither defines a formula of its own. A shape or stage not in the spec does not exist.

### AD-20: Carrier and spacing rules come from one spectral component table

- **Binds:** validator, test suite, carrier guard, 3D renderer (FR-8, FR-9, FR-25)
- **Prevents:** the validator and the tests disagreeing on what collides; the carrier guard reading Core state at runtime.
- **Rule:** Every modulated carrier is at least 4 times its modulation rate. In each ear, on the signal that ear receives after the 3D renderer, at least the spacing value (50 Hz placeholder, design log (e)) separates any spectral component of one layer from any of another layer, including both binaural carriers; a layer's own components are exempt, and the two binaural carriers are exempt from each other, since they never share an ear (design log (e)). Spectral components (within 40 dB of a layer's strongest line, placeholder, design log (i)) are computed analytically from the spec's component model; the validator checks both rules across the whole session, including along rate curves. A shape with no component model is rejected. The compiler writes the carrier guard's notch schedule into the plan as static data.

### AD-21: One recipe hash and one determinism key

- **Binds:** compiler, golden files, loudness gain, report, content updates (FR-6, FR-14, FR-33)
- **Prevents:** two units hashing the same recipe differently.
- **Rule:** The recipe hash is SHA-256 over the RFC 8785 canonical JSON of the recipe, excluding the stored loudness gain and loudness hash and the non-audio metadata fields the schema marks as excluded. The determinism key is recipe hash + every asset hash the plan pins + engine version + sample rate.

### AD-22: Assets enter the engine only as hashed bytes

- **Binds:** C API, designer, app, content updates, stem encryption (FR-24, FR-32, FR-33)
- **Prevents:** each host inventing its own way to get stems into an engine with no file I/O; a content update silently changing a render.
- **Rule:** Hosts pass asset bytes (decrypted by the host) through the C API, keyed by content hash. The engine verifies the hash and decodes. A plan pins the hash of every asset it uses; a missing or mismatched asset is a compile error.

### AD-23: Hosts output exactly two channels, never downmixed

- **Binds:** designer and app audio adapters, miniaudio build (FR-4, FR-34)
- **Prevents:** a host adapter summing the binaural pair to mono after the engine got it right.
- **Rule:** Hosts open the output device with exactly 2 channels and no channel conversion. A host refuses to play a recipe with a binaural layer on a device that cannot give 2 channels, and tells the listener why. miniaudio is built with decoding and encoding disabled.

### AD-24: Core paths have matched latency

- **Binds:** Core zone, 3D renderer on gamma (FR-3, FR-27)
- **Prevents:** Orbit processing delaying gamma relative to the theta reference and breaking the 2 ms coupling budget.
- **Rule:** Every Core path reaches the stereo bus with the same latency. If the 3D renderer adds latency to gamma, the theta reference and binaural paths are delayed to match. The coupling timing test runs with Orbit on.

### AD-25: Fixed seeds for tooling, a fresh logged seed per play for listeners

- **Binds:** CLI, tests, golden files, designer, app (FR-6, FR-14, FR-24, FR-38)
- **Prevents:** tests that cannot reproduce what a listener heard; consumer sessions that never vary; seeds leaking into analytics.
- **Rule:** The CLI, tests, golden files, and designer audition and export always use the recipe seed. Consumer app builds draw a fresh seed for each play and store it on the device with that play's record, so any play can be re-rendered exactly; the seed is never sent in analytics. Internal app builds may pin a seed. The Core zone draws no random values, so only Tone zone choices vary between plays.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| Signal names | Carrier, modulation type, rate, everywhere (code, recipe, UI, docs). Binaural form: "binaural, 100 Hz left, 103 Hz right, 3 Hz beat rate". Never a bare rate. |
| Recipe fields | JSON, `snake_case`, units in the field name (`_hz`, `_deg`, `_db`, `_lufs`, `_s`). Times in seconds. Validated against a JSON Schema in the repo; schema tags loudness-relevant and hash-excluded fields. |
| C API | `arc_` prefix; plain C types; status code return; structured error and warning out-parameters. |
| Terms and copy | PRD §3 glossary is binding. CI checks docs, UI strings, and recipe descriptions for: banned terms (CLAUDE.md "Never"), comparables' feature names (PRD §6), health or outcome claims, and em dashes. Research files exempt when citing sources. |
| Clean room | No third-party program names, recipes, recordings, scripts, levels, or session arcs (PRD §6, plan IP rules). |
| Errors and logging | Validator errors name parameter, value, rule, limit. The render call never throws or logs. Hosts log. |
| Thresholds and ranges | One threshold table and one locked-range table in the repo, each row citing the plan or a design log entry. Code reads them; tests never hard-code a number. Never trade a threshold for speed or battery. |
| Workflow | Tests are written first, from acceptance criteria, by a fresh-context QA agent. Never weaken a threshold; propose a change with a reason. No commit with failing tests. Every changed default or threshold gets a design log entry. One story per branch. |
| Golden files | Stored in Git LFS, keyed by determinism key, changed only after listening sign-off. |
| Secrets | GitHub Actions secrets; none in the repo. |

## Stack

| Name | Version |
| --- | --- |
| Version source | `toolchain.json` (tools, with download SHA-256), `pyproject.toml` and `uv.lock` (Python packages); CMake configure fails on a CMake or compiler mismatch (design log 2026-11-02 (y), (aa)). A change needs a design log line and a passing full-tier hash check. |
| C++ (engine, CLI) | C++20 |
| LLVM: clang-cl (Windows x64 and arm64), clang (Linux) | 23.1.4 |
| Apple clang (macOS arm64) | 17.0.0.17000013, Xcode 16.4 on `macos-15`; re-pin to an App Store accepted Xcode (26 or later) before any iOS build |
| Android NDK (arm64-v8a) | r30 (30.0.16248370), clang 21.0.0, API level 21; the app build uses the same NDK |
| CMake | 4.4.5 |
| Ninja | 1.13.2 |
| Catch2 (C++ tests) | 3.16.1 |
| Python (reference renderer, signal tests) | 3.14, latest patch managed by uv |
| uv | 0.13.6 |
| NumPy | 2.5.4 |
| pytest | 9.2.0 |
| PyYAML (tests) | 6.0.3 |
| miniaudio (host audio I/O only) | 0.11.26 or later 0.11.x (contains the CVE-2026-32837 fix), `MA_NO_DECODING`, `MA_NO_ENCODING`; pinned exactly in the first host story |
| Flutter (designer and apps, via dart:ffi) | 3.47.8 or later 3.47.x (security fixes in 3.47.2 and 3.47.8); exact pin at the Phase 0 stack spike |
| Stem codec | Opus (fixed-point libopus build, vendored, current 1.6.1) or FLAC; proven bit-exact under AD-9 in the story that adds stem decoding (Phase 1) |
| CI | GitHub Actions, hosted runners only, public repo, $0 spending cap. Fast: `windows-2025`, `ubuntu-24.04`. Full adds `windows-11-arm`, `macos-15`, NDK build on `ubuntu-24.04`, NDK probe and contraction must-fail on `ubuntu-24.04-arm` (design log 2026-11-02 (aa)) |

## Structural Seed

### Signal flow (fixed in code)

```mermaid
flowchart LR
  subgraph TONE["Tone zone (free-form, recipe data)"]
    ST["Stems and noise (resampled if needed)"] --> FX["Built-in effects graph"]
    FX --> T3D["3D renderer: Tone objects"]
    T3D --> CG["Carrier guard (notches from plan, always last)"]
  end
  subgraph CORE["Core zone (fixed, matched latency)"]
    G["Gamma PAC layer"] --> O3D["3D renderer: Orbit"]
    TH["Theta reference"]
    BIN["Binaural pair: L and R sine oscillators, per-channel gain"]
  end
  CG --> SUM["Stereo bus"]
  O3D --> SUM
  TH --> SUM
  SUM --> BJ["Binaural joins"]
  BIN --> BJ
  BJ --> MC["Master chain: per-channel gain, stereo-linked limiter (idle)"]
  MC --> OUT["Stereo out, 2 channels"]
  TH -. "phase drives depth" .-> G
```

### Deployment and environments

```mermaid
flowchart LR
  DEV["Dev PC (Windows): build, fast tests, CLI renders, Reaper and RX sign-off"]
  CI["GitHub Actions: x64 and arm64 matrix, fast per push, full per PR and nightly, hash compare"]
  PHONE["Real Android phone: Phase 0 spike, background and battery checks"]
  STORE["Play Store and App Store (Phase 3 and 4)"]
  CDN["Cloud storage: manifest, recipes, stem packs (from Phase 1 publish)"]
  APPS["Installed apps"]
  DEV --> CI
  DEV --> PHONE
  CI --> STORE
  DEV -- "publish" --> CDN
  STORE --> APPS
  CDN -- "content updates" --> APPS
```

v0.1 runs only on the dev PC and CI. Content storage appears with publish in Phase 1; stores and accounts in Phase 3.

### Source tree

```text
arcani/
  engine/        # pure C++ core, C API header, no framework
  cli/           # recipe to WAV plus assertion report
  reference/     # Python reference renderer
  tests/         # assertion library, C++ and Python tests, threshold and range tables
  recipes/       # starter and test-fixture recipes, JSON Schema
  golden/        # approved renders (Git LFS), keyed by determinism key
  app/           # Flutter designer and apps (Phase 1 onward)
  docs/          # plan, research library, design log, signal spec, listening checklist
```

## Capability to Architecture Map

| Capability / Area | Lives in | Governed by |
| --- | --- | --- |
| FR-1 to FR-6 engine core and signal layers | `engine/` Core zone | AD-1, AD-4, AD-5, AD-9, AD-10, AD-14, AD-19, AD-24 |
| FR-7 to FR-10 recipes and validation | `engine/` compiler, `recipes/` schema | AD-2, AD-3, AD-13, AD-15, AD-20, AD-21 |
| FR-11, FR-12 renderers | `cli/`, `reference/` | AD-12, AD-16, AD-17, AD-19 |
| FR-13 to FR-15 test suite and CI | `tests/`, CI | AD-9, AD-10, AD-17 |
| FR-16, FR-17 starters and sign-off | `recipes/`, `golden/`, `docs/` | AD-15, Conventions |
| FR-18 to FR-23 designer | `app/` (desktop) over C API | AD-2, AD-11, AD-12, AD-13, AD-17, AD-23 |
| FR-24 to FR-26 stem bed | `engine/` Tone zone | AD-3, AD-6, AD-7, AD-9, AD-14, AD-20, AD-22, AD-25 |
| FR-27, FR-28 Orbit and 3D | `engine/` 3D renderer | AD-4, AD-8, AD-24 |
| FR-29 to FR-35 mobile app | `app/` (mobile) over C API | AD-1, AD-8, AD-11, AD-12, AD-18, AD-22, AD-23 |
| FR-36 to FR-38 accounts, freemium, analytics | `app/`, Phase 3 services | Deferred |
| Visualizer (new scope) | `app/` | AD-18 |

## Open Questions

| Question | Owner | Blocks |
| --- | --- | --- |
| Limiter idle bound value (AD-4): resolved for v0.1 as zero gain reduction, design log 2026-10-28 (p); revisit when the Phase 1 master level and stems arrive | Audio with build agents | Phase 1 master chain |
| Tone zone rate ranges and visualizer smoothing rate (AD-6, AD-18) | Audio | Phase 1 gate |
| Loudness target values per recipe for v0.1: resolved, -36 LUFS-I for every starter, design log 2026-10-27 (m) | Audio | none |
| Independent review of AD-4, AD-5, AD-9, AD-19, AD-20 and the Stack (CLAUDE.md rule 4): resolved 2026-11-04, Story 0.5, `reviews/review-independent-s0-5.md`, design log 2026-11-04 (ee) | Audio | none |
| Physical-phone hash run of the engine library from the real Android app build (AD-9, design log 2026-11-04 (ee)) | Audio | Phase 0 part 2 stack spike close |

## Deferred

| Item | Why it can wait |
| --- | --- |
| Manifest format, staging, and rollback for content (FR-23, FR-33) | Phase 1 publish needs only a versioned manifest on cloud storage; staging and rollback before Phase 3 release. |
| Accounts, sign-in provider, payments, analytics provider (FR-36 to FR-38) | Phase 3; nothing in the engine depends on them. |
| Stem encryption and key handling (FR-32) | Phase 3; lives in the app adapter, which passes decrypted bytes (AD-22). |
| Push to device protocol (FR-22) | Phase 1; designer sends a recipe and asset hashes over the local network, never audio. |
| Background playback mechanism (FR-30) | Phase 0 spike proves it: Android `mediaPlayback` foreground service, iOS `UIBackgroundModes` audio. |
| Custom envelope curve format and non-sine carrier models | Added to the signal spec with their component models; until then the validator rejects them (AD-19, AD-20). |
| Head tracking | Not in v1; would move only the 3D stage. |
| Plugin hosting inside the designer | Convenience only; Reaper covers baking (AD-7). |
| Dolby Atmos export as a non-app release format | Revisit if streaming releases are planned; carries its own isolation risk. |
| Tone zone synced to Core timing | Blocked by the PRD Q9 patent check (AD-6). |
| Multiple designers and designer accounts | Post-launch per PRD §2.2; the recipe already separates Core parameters from Tone design. |
| Minimum OS versions | Phase 0 spike, from device-share data. |
| Crash reporting and operations monitoring | Phase 3, with the store release. |
