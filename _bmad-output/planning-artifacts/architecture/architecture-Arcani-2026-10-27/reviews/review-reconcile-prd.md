---
title: Architecture spine reconciliation against PRD inputs
reviewed: ARCHITECTURE-SPINE.md (draft, 2026-10-27)
against: prd.md (final), addendum.md, review-architecture-readiness.md, with .memlog.md as the record of intentional changes
date: 2026-10-27
stance: reconcile (what did not land, what contradicts without a logged decision)
---

# Spine vs PRD Reconciliation

## Verdict

The spine carries the PRD's signal invariants faithfully (isolation, coupling source, master chain, determinism scope, block-size independence, real-time contract, report, seed) and closes most readiness-review items addressed to architecture, but it leaves the stem asset and determinism boundary open, contradicts FR-15 and v0.1 shape scope without a logged change, under-guards the Tone zone against in-file entrainment rates, and drops several quiet product constraints (claims, clean room, comparables naming, tests-first process, independent review).

Severity counts: High 6, Medium 8, Low 5.

## What landed well

- Readiness C4 (coupling source): AD-5 states theta-phase-only coupling, no coupling-target field, validator rejection, and the beat-change test.
- Readiness H2 (master chain): AD-4 defines contents, join point, no channel mixing, plus a structural test.
- Readiness H9, M9 (determinism scope, sample rates): AD-1, AD-9, AD-10 with the 1/64/512/4096 block test; memlog records 44.1 and 48 kHz.
- Readiness H12 (reference scope): AD-16 sets pre-quantization float comparison and per-layer taps; AD-12 exposes taps.
- Readiness M2, M4, M10, M11, M12: AD-17, AD-14, AD-11, Conventions.
- Readiness H7 and PRD Q6 (loudness mechanism): AD-13 chooses stored gain, same live and offline.
- PRD Q5 (bit-exact): AD-9, recorded in memlog as an intentional widening beyond the addendum's synthesis-core scope.

## High

### R1. Stem asset boundary and the determinism key are undefined

- **Where:** AD-1 (engine has no file I/O; output is a function of plan, seed, sample rate, sample index), AD-12 (C API list), AD-9 (engine-owned decoder), AD-15 (golden key = recipe hash, engine version, sample rate), FR-24 (seeded pick from library by metadata), FR-32 (encrypted stems), FR-33 (content updates without app release).
- **Problem:** Stem audio must enter the engine somehow, but the C API has no call for providing stem data, and AD-1 forbids the engine reading files. The determinism and golden keys omit the stem library: if a content update adds a stem to the library, the same recipe and seed can pick different stems, which silently breaks FR-6 and FR-24 ("same recipe and seed pick the same stems"). Where decryption happens relative to the engine-owned decoder is also unstated. The spine says later phases are fixed "only where they shape the engine now"; this one shapes the plan type and the C API now.
- **Fix:** Add an AD (or extend AD-1 and AD-12): hosts supply encoded stem bytes to the engine through the C API (after any decryption in the adapter); the engine decodes them. The render plan pins the exact stem pack version or content hashes it may draw from; the sequencer draws only from that pinned set. Add stem pack hash to the determinism and golden keys.

### R2. FR-15 "full suite on every push" contradicted without a logged change

- **Where:** AD-17 (fast tier per push, full tier nightly and before a phase gate); memlog line 39 records the CI split as a decision but not as a change to FR-15; PRD FR-15 ("the full suite runs on every push in CI. Failing code does not merge"); §8 v0.1 gate ("Every test passes in CI").
- **Problem:** The split is sensible (readiness M4), but FR-15 still says the opposite, and the spine does not say what blocks a merge when only the nightly tier fails (8-hour drift, full-length starters). Build agents will read both documents.
- **Fix:** Log the change in the memlog as intentional vs FR-15, state in AD-17 that the fast tier gates merges and a nightly failure blocks the next merge (or the next phase gate) until fixed, and add FR-15 to the PRD update list (see R13).

### R3. The Tone zone can carry in-file entrainment rates through effects and tempo

- **Where:** AD-3, AD-6, AD-7; Glossary "Stem bed: contains no entrainment signals"; FR-24 (tempo metadata); memlog line 31 (motion rates need a locked range so motion cannot create periodic level changes at entrainment rates).
- **Problem:** AD-6 locks only stem motion rates. Free-form live built-in effects (tremolo, auto-pan, gated or modulated effects, filter LFOs) can impose periodic level changes at theta, delta, or gamma rates, which is exactly the untracked entrainment signal AD-6 says it prevents. Stem tempo (for example 120 BPM is 2 Hz) also sits in the delta range. Baked third-party effects (AD-7) bypass any live check entirely.
- **Fix:** Generalize AD-6: any periodic modulation in the Tone zone (motion, effect LFOs, tempo-locked gating) sits inside one locked Tone-modulation range from the design log, enforced by the validator, and curated stems (FR-26 checklist) are screened for periodic envelope energy at entrainment rates. Defer the range value, not the rule.

### R4. v0.1 shape and waveform scope narrowed without a logged decision; no validator warning channel

- **Where:** Spine Deferred ("Custom envelope curve format, non-sine carriers' spacing model: Phase 1"); PRD FR-2 (five envelope shapes incl. custom), FR-3 (sine, triangle, softened square carriers), FR-4 (non-sine binaural allowed with a validator warning), FR-21 (warn or flag), §8 (FR-1 to FR-6 all in v0.1); readiness H3, H10, C3.
- **Problem:** Deferring custom curves and non-sine carriers to Phase 1 is the readiness review's own recommendation, but it removes PRD v0.1 scope and the memlog does not record it. Separately, AD-2 and AD-12 define only rejection (status plus structured error); FR-4 and FR-21 need a non-blocking warning outcome. The spine also does not decide where the spacing rule's spectral component set comes from (analytic per shape, or measured from a render inside the compiler), which decides whether the validator renders audio.
- **Fix:** Log the v0.1 shape list as an intentional change (and add to R13). Extend AD-2: the compiler returns a plan plus zero or more structured warnings; rejections block, warnings do not. State in AD-2 that spectral components are computed analytically per supported shape, and that a shape without a component model is rejected by the validator until it has one.

### R5. Looping time model is not decided, though the pure-function engine depends on it

- **Where:** AD-1 (sample-index function), AD-10, AD-11; PRD FR-7 (ramp-in once, body repeats, no click, no phase jump, maximum run time), FR-29, FR-30 (resume from the same point); readiness H11.
- **Problem:** Readiness H11 asked for schedule repetition with continuous phase vs sample repetition, and the CLI's render length for a looping recipe. Neither is decided. This is an engine time-model decision, not story detail: it determines whether "sample index" maps to a schedule position by modulo, how integer phase accumulators continue across the seam, and who enforces the maximum run time (engine stops output, or the host stops calling).
- **Fix:** Add a rule: looping repeats the parameter schedule while every oscillator phase continues from the engine clock; the engine itself ends output (with the recipe's fade) at the maximum run time, independent of the host; the CLI renders ramp-in plus K body repetitions with K a CLI option, and the seam test runs on that render.

### R6. Loudness: which target v0.1 checks, and how length, looping, and intensity interact with the stored gain

- **Where:** AD-13; PRD FR-5, §5 Loudness ("tones -36, master -16 LUFS-I"), FR-31 (intensity scales tone gain); readiness H7.
- **Problem:** AD-13 picks the mechanism but not which target v0.1 asserts (v0.1 output is tones only, so -36 and -16 cannot both hold). Integrated loudness depends on render length, so a looping recipe or a listener-chosen session length needs a defined measurement span. Listener intensity (FR-31) changes gain after the stored loudness gain; it is unclear whether that is a plan parameter covered by the hash, and whether the -1 dBTP ceiling still holds at maximum intensity.
- **Fix:** State in AD-13: the v0.1 assertion target (one value), the measurement span (full recipe length, or ramp-in plus one body for looping), and that listener controls are bounded plan overrides applied after the stored gain, with the validator proving true peak at the top of the listener range.

## Medium

### R7. Golden files keyed by engine version force re-approval on every engine bump

- **Where:** AD-15; readiness M5 ("what happens when engine_version changes without an audible change"); FR-14.
- **Problem:** Keying goldens by engine version means a version bump with byte-identical output has no golden to match, so either every release needs a listening pass or the key is silently re-pointed. Also unstated: what an app on engine 1.3 does with a recipe that declares engine 1.2.
- **Fix:** Keep byte comparison against the previous golden across versions; a byte-identical render carries the approval forward automatically; only a changed byte requires re-approval. State the engine's policy for recipes declaring an older or newer engine minor version.

### R8. AD-8 promises something the app cannot fully guarantee and drops FR-34

- **Where:** AD-8 ("The app never hands audio to an OS or Dolby spatializer"); FR-34 (guidance, opt-out where allowed, feasibility unresearched); memlog line 29 (Apple applies Spatial Audio to the whole program).
- **Problem:** OS and headphone spatializers can act on any app's stereo output. The rule as written is not testable and hides the residual risk the PRD handles with guidance (FR-34, Risks table).
- **Fix:** Reword: the app requests the platform's opt-out from system spatialization where available and shows FR-34 guidance for sessions with a binaural layer; record opt-out feasibility as a Phase 0 spike item in Deferred.

### R9. Quiet product constraints from PRD §6 are absent

- **Where:** PRD §6 Claims, Clean room, Naming, Hearing safety (stop-if-uncomfortable guidance); FR-16 (recipe descriptions shipped as UI text); spine Conventions "Terms" covers only CLAUDE.md banned terms and em dashes.
- **Problem:** Build agents read the spine. It never states the claims rule (describe the sound, no health, therapy, treatment, neurostimulation, outcome, or condition language), the clean-room rule (no third-party names, recipes, recordings, levels, or session arcs), or the comparables' feature names to avoid (Spatial Orbit, Dynamic Focus, Hibernation, "neural effect"). Recipe description strings are UI copy but are not named as covered by the CI check.
- **Fix:** Add a Conventions row "Copy and claims" citing PRD §6, extend the CI banned-term list to the §6 Naming list and claims terms, and state that recipe description fields are checked as UI copy.

### R10. Tests-first by a fresh-context QA agent is not carried into the spine

- **Where:** PRD §4.4 description ("Tests are written from acceptance criteria before code, by a QA agent with fresh context"); CLAUDE.md Rule 6; spine AD-17 and Conventions.
- **Problem:** This is a process invariant that shapes how build agents work, and the spine's audience is build agents. Also missing: "changing a threshold needs a logged reason, never a weakened test" and SC-C2 (no trading thresholds for speed or battery), which matter for AD-9's -100 dBFS fallback and the battery work.
- **Fix:** Add a Conventions row: tests from acceptance criteria first by a separate QA agent; threshold changes only by design log entry; thresholds never traded for speed or battery.

### R11. Independent review before lock is not reflected

- **Where:** PRD §6 Science first and CLAUDE.md Rule 4 ("Signal architecture, defaults, and the stack get an independent review before they lock"); several ADs carry [ADOPTED]; stack marked confirmed in memlog.
- **Problem:** The spine does not say the stack (Flutter, miniaudio, Clang, CMake) and the signal architecture ADs are pending independent review, nor record that one happened.
- **Fix:** Add a status note or memlog entry: which ADs and stack rows lock only after the independent review, and record the review outcome when it runs.

### R12. Render speed assertion has no reference machine or tier

- **Where:** AD-17 (report per render), FR-11, FR-13 ("render speed" on every render); readiness M3.
- **Problem:** CI runners are not the development PC, so a per-render speed assertion will be flaky or meaningless in CI.
- **Fix:** In AD-17, state that the speed assertion runs only on the named reference machine (the dev PC) or as a CI-relative benchmark, and is reported but not merge-gating in CI.

### R13. PRD changes owed are scattered and untracked

- **Where:** memlog lines 17, 23, 32 ("Offer PRD update once the spine settles"); spine adds Tone zone free routing, moving stem objects (contradicts FR-27 "stem bed gets width without motion"), the visualizer (AD-18), whole-engine bit-exactness (vs addendum), 44.1 kHz support (vs FR-11 48 kHz only and the "four golden files" gate), CI tier split (R2), v0.1 shape scope (R4).
- **Problem:** Each change is recorded somewhere, but neither the spine nor the memlog lists them together, so the PRD will drift from the spine.
- **Fix:** Add a short "PRD changes owed" list (spine section or memlog entry) and run the PRD update before epics and stories.

### R14. Hearing-safety items have no home in the spine

- **Where:** PRD §5 Hearing safety (Phase 3 listener-level ceiling, no sudden loud events), §6, FR-29 (looping maximum run time against WHO-ITU guidance).
- **Problem:** Not decided, not deferred. Whether the level ceiling is enforced in the engine master chain or the app adapter affects AD-4's master chain contents.
- **Fix:** Add to Deferred with owner and phase, and state now whether a listener-level ceiling, if added, lives in the master chain (per-channel, stereo-linked) or in the host.

## Low

### R15. Limiter spec unstated

- **Where:** AD-4 (stereo-linked limiter); FR-5 ("final limiter that meets the recipe's loudness target"); readiness H6.
- **Fix:** One line in AD-4 or AD-13: the limiter controls peaks only, is expected inactive on starter recipes, and its state is deterministic under AD-9.

### R16. Binaural beat rate equal to theta rate

- **Where:** Readiness C4 ("Decide whether a binaural beat rate equal to the theta rate is allowed, and if so, whether its phase must be independent").
- **Fix:** Note in AD-5 that it is allowed and the binaural oscillators share no phase state with the theta reference.

### R17. Build, test, and render commands

- **Where:** CLAUDE.md "Commands (fill in once the architecture step creates the build)"; memlog line 35 ("one command each for build, test, render").
- **Fix:** Name the three commands in the spine or defer them explicitly to the first build story, with CLAUDE.md updated in that story.

### R18. Python and uv on the dev machine

- **Where:** Stack row "Python 3.12, managed by uv"; local note that uv is not installed on the dev PC.
- **Fix:** Make installing uv (or the fallback) part of the first build story.

### R19. Listener controls vs "locked range" vocabulary

- **Where:** FR-31 ("ranges the designer locks in the recipe"); readiness M6 (rename to "listener range"); spine Conventions "Thresholds and ranges".
- **Fix:** Use "listener range" in the recipe schema for designer-set listener bounds, distinct from design-log locked ranges.

## Not flagged (per-story detail)

Accuracy measurement method (H4), coupling timing point extraction (H5), dropout and NaN methods (M1), isolation fixture recipes (C2), opposite-ear spacing wording (L6), binaural lower bounds (L7), push-to-device and publish protocols (already deferred).
