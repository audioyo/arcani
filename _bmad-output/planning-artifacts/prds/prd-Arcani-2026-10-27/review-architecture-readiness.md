---
title: Arcani PRD, architecture and story readiness review
reviewed: prd.md, addendum.md (2026-10-27 draft), against CLAUDE.md and docs/project-plan.md
date: 2026-10-27
stance: adversarial
---

# Architecture and Story Readiness Review

## Verdict

**Not ready.** An architect could pick a stack from this PRD, but would have to invent the audio graph's most important invariants (what the master chain may contain, where the binaural layer joins the mix, what the coupling source is, the determinism scope, block-size invariance). A story writer could not write pass/fail acceptance criteria for the v0.1 validator, the spacing check, the isolation test, or two of the four starter recipes, because the values and measurement methods are either "set in Phase 0" or undefined.

The core signal intent is sound and mostly well stated. The gaps are concentrated in four places: unset v0.1 values, undefined measurement methods, an undefined master chain, and a coupling source that is described as "the engine clock" instead of the theta reference.

| Severity | Count |
| --- | --- |
| Critical | 4 |
| High | 12 |
| Medium | 12 |
| Low | 7 |
| **Total** | **35** |

## Critical

### C1. v0.1 validator and starter recipes depend on values the PRD defers to "Phase 0"

- **Where:** FR-8 ("Theta rate, coupling depth, burst width, theta reference carrier, and every other range: set from the literature in Phase 0 and logged before they lock"); §11 Q1 (theta default open), Q2 (binaural on or off per mode), Q3 (spacing value); §8 v0.1 row ("Phase 0 research confirms thresholds and locked ranges").
- **Problem:** v0.1 *is* Phase 0 part 1. Its gate requires four golden files and a validator that "rejects any parameter outside its locked range". A story writer cannot write a failing test for a range with no bounds, and cannot write the Focus or Learn recipe while the theta default is open. The v0.1 gate does not say whether ranges must be locked or may ship provisional.
- **Fix:** Add a "v0.1 provisional ranges" table to FR-8 now with a value for every parameter (theta rate, theta reference carrier, coupling depth, burst width, envelope shape list, ramp limits, length limits), each tagged provisional with a design log entry. State in §8 that the v0.1 gate passes on provisional ranges, and that a Phase 0 research story precedes the validator story.

### C2. The binaural isolation test can pass vacuously in v0.1, and cannot be measured at a 0 Hz beat

- **Where:** FR-4, §5 Isolation, addendum starter table (Focus "Off", Learn "Off", Relax "Optional", Sleep "Optional: beat sweeping 3 Hz to 0 on 100 Hz").
- **Problem:** If no starter recipe has the binaural layer on, every v0.1 isolation assertion runs on silence and passes. This is exactly how the earlier routing bug would return unnoticed. Separately, "the other ear's binaural carrier is at least 90 dB below its own" is a frequency-domain measurement; when the Sleep beat reaches 0 Hz both carriers are the same frequency, and below about 1 Hz the two carriers cannot be resolved in any practical analysis window.
- **Fix:** Require dedicated isolation fixture recipes in v0.1: binaural on, every other layer active at maximum depth and level, beat rate at minimum, maximum, and swept, carriers at both ends of the locked range. Specify the measurement method so it works at any beat rate, for example: render the binaural layer with one ear's oscillator muted and measure the muted channel's energy, or render with engine-tagged per-layer taps and null-test. Make "isolation fixture exists and has binaural on" itself an assertion.

### C3. "Spectral component" is undefined for every non-sine shape, so the spacing rule is not computable

- **Where:** Glossary "Spacing rule" ("counting modulation side frequencies"), FR-9, FR-2 (sawtooth, reverse saw, smoothed on-off, custom curve), FR-3 (bursts, triangle, softened square carriers).
- **Problem:** A sine carrier with sine AM has exactly two side frequencies. Bursts, sawtooth envelopes, and square or triangle carriers have unbounded harmonic series. Example from the addendum's own values: a 300 Hz gamma carrier in 50 ms bursts at 40 Hz, gated at a 6 Hz theta rate, has components at 300 +/- 160 Hz and beyond, so 460 Hz sits 10 Hz from a 450 Hz theta reference carrier. Second example: Relax with gamma at "low depth" plus a 6 Hz beat on 250 Hz puts the 256 Hz binaural carrier 4 Hz from the gamma 260 Hz side frequency. The validator cannot decide either case without an amplitude floor, and the plan's claim that "starter recipes pass because gamma and binaural never run together" is false for Relax as described.
- **Fix:** Define the component set per shape: either analytic (list harmonics up to order N) with an amplitude floor (for example components above -40 dB relative to the layer's peak count), or measured from a reference render. Alternatively restrict v0.1 to shapes whose component sets are closed-form (sine envelope, sine carrier, defined burst window) and add the others later with their component model. Resolve whether Relax runs gamma and binaural together.

### C4. The coupling source is described as "the engine clock", not the theta reference, and is not structurally fixed

- **Where:** Glossary "Gamma PAC layer" ("modulation depth follows the engine clock"), FR-3 (same), FR-4 ("Nothing couples to the binaural layer"), addendum recipe (`"clock": { "theta_hz": 6.0 }`), addendum Relax (6 Hz theta reference plus 6 Hz binaural beat).
- **Problem:** If gamma depth follows a clock rather than the theta reference's phase, nothing requires an in-file theta reference to exist when gamma is coupled; a recipe with the theta reference off and a binaural beat at the clock rate couples gamma to a beat that has no waveform in the file. The addendum names the clock by the theta rate, which invites an implementation where the clock *is* the theta rate and every rate-matched layer (including the binaural beat) is phase-locked to it. "Nothing couples to the binaural layer" has no test: it is a negative with no observable.
- **Fix:** State that gamma depth is a function of the theta reference phase only. The recipe schema has no coupling-target field. The validator rejects coupled gamma when the theta reference is absent, muted, or at zero depth at any point in the session. Test: render the same recipe with the binaural beat rate and starting phase changed; gamma peak times must be unchanged to the sample. Decide whether a binaural beat rate equal to the theta rate is allowed, and if so, whether its phase must be independent of the theta reference.

## High

### H1. Spacing rule wording contradicts CLAUDE.md, which overrides the PRD

- **Where:** Glossary "Spacing rule" (per ear, different layers only, binaural pair exempt) versus CLAUDE.md Signal facts ("at least 50 Hz between any two active spectral components, including modulation side frequencies") and the plan's Test thresholds table (same wording as CLAUDE.md). Design log 2026-10-27 (e) says "Status: proposed. CLAUDE.md's spacing rule wording needs the same change."
- **Problem:** CLAUDE.md is loaded into every dev agent as overriding instructions. Read literally it rejects every AM recipe (300 Hz at 40 Hz AM has side frequencies 40 Hz from the carrier). A dev agent will follow CLAUDE.md, not the PRD.
- **Fix:** Update CLAUDE.md and the plan's table to the PRD wording before any story is written. Add a test case to the PRD: a single layer with side frequencies under 50 Hz apart passes.

### H2. "Master chain" is undefined, and FR-4 allows 60 dB of leakage through it

- **Where:** FR-4 ("at least 60 dB below after the master chain"), FR-5 ("final limiter"), §5 Isolation.
- **Problem:** The term is not in the glossary and no FR says what the master chain may contain. A 60 dB allowance tolerates a crossfeed or mid/side stage leaking at -60 dB, which is a routing bug, not a limiter artifact. The PRD also never says where the binaural layer joins the mix relative to spatial and width stages, which is the single topology decision that prevents the earlier bug.
- **Fix:** Define master chain in the glossary. State the invariant: from oscillator to output, the binaural path contains only per-channel gain and the final summation; the master chain contains only per-channel operations plus a stereo-linked gain (no mid/side, crossfeed, width, reverb, or any matrix that mixes channels). State that the binaural layer is summed after every spatial and width stage. Add a structural test (graph inspection or per-node whitelist) alongside the signal test.

### H3. Non-sine binaural waveforms contradict the definition of the binaural layer

- **Where:** FR-4 ("Non-sine binaural waveforms are allowed only with a validator warning") versus Glossary "Binaural layer: two steady sines" and CLAUDE.md ("two steady sines"). Glossary "Validator" only rejects; "warning" is not a defined validator outcome. FR-21 says "flagged".
- **Problem:** A harmonic-rich binaural carrier adds components the spacing and isolation tests do not model, and it contradicts the project rule. The story writer cannot test "warning" because the validator has no warning channel.
- **Fix:** Delete the non-sine allowance for v1, or define a validator warning level in the glossary, add binaural harmonics to the spacing component set, and log the source.

### H4. FR-1 accuracy thresholds have no measurement method

- **Where:** FR-1 ("within 0.01 Hz of its recipe value"; "instantaneous rate is within 0.01 Hz of the scheduled curve at every point"; "phase error stays under 1 ms after an 8-hour render").
- **Problem:** 0.01 Hz resolution needs about a 100 s analysis window, which is meaningless "at every point" along a rate curve. "Phase error" has no stated reference (analytic ideal? Python reference? start of render?). Two QA agents would write two different tests.
- **Fix:** Define accuracy as accumulated phase error against the analytic integral of the scheduled rate: for every carrier and rate, |phase error| stays under X degrees (or Y ms) over the whole render, measured by a named method (Hilbert phase of the band-limited layer, or the reference renderer's phase). The 0.01 Hz figure then follows from the phase bound.

### H5. Coupling phase 0 degrees and "envelope peak" are undefined for most shapes

- **Where:** Glossary "Coupling phase" ("0 degrees at its maximum"), FR-2 shapes, FR-3 ("Each gamma envelope peak lands within 2 ms"), addendum Focus ("50 ms bursts at the theta peak").
- **Problem:** Smoothed on-off has a flat plateau, so its maximum is an interval. Sawtooth and reverse saw have their maximum at a discontinuity. A custom curve may have several maxima. A flat-topped gamma burst has no single peak. The 2 ms test cannot be written.
- **Fix:** Define phase from the theta reference's own cycle (0 degrees = start of cycle as defined per shape), not from "its maximum". Define the gamma timing point as the depth envelope's centroid or a named point (burst center). Specify the extraction method (band-pass at gamma carrier, envelope by Hilbert, low-pass at theta-relevant bandwidth).

### H6. "No gain change faster than 10 ms" conflicts with the signals themselves

- **Where:** FR-5, §5 Ramps.
- **Problem:** A 40 Hz AM cycle is 25 ms with gain changes far faster than 10 ms; a 50 ms burst has edges; a limiter's attack is normally under 10 ms. Read literally the test fails on every recipe. Also "a final limiter that meets the recipe's loudness target": a limiter controls peaks, not integrated loudness.
- **Fix:** Scope the 10 ms rule to recipe gain ramps, layer enable and disable, and session start and end. Give the limiter its own spec (attack, release, maximum gain reduction, expected to be inactive on starter recipes). Move loudness targeting to a gain stage and say how it is computed (see H7).

### H7. Which loudness target applies in v0.1, and how live rendering hits it, is left to the architect

- **Where:** FR-5, §5 Loudness ("tones -36, master -16 LUFS-I"), §11 Q5.
- **Problem:** v0.1 has no stems, so the output is tones only. Is the test checking -36 or -16? Hitting an integrated target with on-the-fly synthesis requires knowing the loudness before rendering; this is a product decision (static analytic gain, two-pass render, or per-recipe stored gain) with test consequences.
- **Fix:** For v0.1 state one target the loudness test checks, and choose the mechanism (for example: gain computed from the recipe and stored in it, verified by the test), or record the decision as an architecture input with the constraint "same gain live and offline".

### H8. Hearing-safety assertion is required on every v0.1 render with no value

- **Where:** FR-13 ("hearing-safety level ceiling"), §5 Hearing safety (value `[ASSUMPTION]` set in Phase 0; "no sudden loud events").
- **Problem:** A test with no threshold cannot be written, and "no sudden loud events" has no measurable definition.
- **Fix:** Give a provisional ceiling (for example maximum momentary loudness and maximum sample peak in dBFS) and define "sudden" (for example momentary loudness rise of more than N LU within M ms). Or move the assertion out of v0.1 explicitly.

### H9. Determinism scope is not stated: platform, compiler, and block size

- **Where:** FR-6 ("byte-identical"), FR-35 ("renders ... identically"), FR-20 ("the audition sounds identical to a render").
- **Problem:** Byte identity across compilers and CPUs is not achievable with standard libm and FMA contraction unless the architecture designs for it. The PRD also never requires output to be independent of buffer or block size, which matters because the designer and app render in host-sized blocks while the CLI does not. The architect must choose math library, precision, and compiler flags from this.
- **Fix:** State: byte identity is required for the same build on the same platform and for any block size; cross-platform identity (FR-35) and live versus offline (FR-20) are measured against the Python reference at the -100 dBFS tolerance. Add a test: render with block sizes 1, 64, 512, 4096 and compare bytes.

### H10. v0.1 shape and waveform scope is ambiguous

- **Where:** FR-2 (five envelope shapes including "custom curve"), FR-3 (sine, triangle, softened square carriers), §8 v0.1 row (FR-1 to FR-6 all in), plan MVP scope ("sine oscillators ... smooth swell and burst shapes").
- **Problem:** The PRD puts every shape and waveform in v0.1; the plan puts only sines and two depth shapes. "Custom curve" has no defined format. A story writer cannot size the engine epic.
- **Fix:** List the v0.1 shapes explicitly and move the rest (with their spacing component models, see C3) to Phase 1. If custom curve stays, define its data format at product level (points, interpolation, normalization).

### H11. Looping behavior is undefined at the level stories need

- **Where:** FR-7 ("the session body repeats until stopped, with no click at the seam and no jump in theta reference or gamma PAC phase"), FR-16, FR-29 (maximum run time is a Phase 3 assumption).
- **Problem:** "Repeats" could mean replaying the same samples (which needs the body length to be a whole number of theta and gamma periods, a validator rule not stated) or continuing synthesis (then "body" is a parameter schedule, and rate curves inside the body must restart). "Session body" and "ramp-in" are not defined. The CLI renders a file: what length does it render for a looping recipe in v0.1, and how is the seam tested?
- **Fix:** Define looping as schedule repetition with continuous phase (or as sample repetition with a length constraint), define body and ramp-in, and state the CLI behavior (for example render ramp-in plus K body repetitions, with K a CLI option) and the seam test.

### H12. Reference renderer scope and precision are unstated

- **Where:** FR-12 ("produces every layer"; "differ by less than -100 dBFS, sample by sample").
- **Problem:** Does the reference include ramps, the limiter, loudness gain, and the final sum, or only layers? If only layers, the engine must expose per-layer taps, an architecture consequence the PRD should state. -100 dBFS over 8 hours effectively forces double-precision phase accumulation, also unstated. The comparison point (float before WAV quantization, or the 24-bit file) is not given.
- **Fix:** State what the reference covers, at which point the comparison is taken (pre-quantization float), over which render lengths, and that per-layer taps are a required engine output if layers are compared separately.

## Medium

### M1. FR-13 assertions without thresholds

- **Where:** FR-13 lists "envelope shape matching the recipe", "dropouts", "NaN or infinite values", "hearing-safety level ceiling"; §5 says numbers are from the plan's table, but the table has no rows for these.
- **Fix:** Add a threshold and method for each (for example envelope shape: correlation above X with the ideal envelope; dropout: no run of more than N samples below Y dBFS while a layer is active).

### M2. The assertion report is an assumption that UJ-1 and FR-13 depend on

- **Where:** FR-11 `[ASSUMPTION]`, UJ-1 ("plus a test report showing every signal assertion passing").
- **Fix:** Promote to a firm requirement and name the minimum fields (assertion, threshold, measured value, pass or fail, recipe hash, engine version, seed). The format belongs in architecture.

### M3. Speed threshold has no reference hardware, and UJ-1 contradicts it

- **Where:** FR-11 ("on the development PC"), FR-13 (render speed checked "on every render"), UJ-1 ("gets a 48 kHz WAV in seconds").
- **Problem:** CI runners are not the development PC, so a per-render speed assertion will be flaky in CI. A 45-minute Sleep render at 20 times real time takes about 135 seconds, not seconds.
- **Fix:** Name the reference machine or a CI-relative benchmark, run the speed test only on that target, and fix the UJ-1 wording.

### M4. "Fast tests" versus "full suite" is undefined

- **Where:** FR-15, CLAUDE.md Tests.
- **Problem:** An 8-hour render at 20 times real time is 24 minutes per push. A story writer must know which tests are fast.
- **Fix:** Define the fast tier (for example everything under N seconds, short renders) and the full tier (8-hour drift, full-length starter renders).

### M5. Golden file match criterion is unstated

- **Where:** FR-14 ("any change that alters it fails").
- **Fix:** State byte-identical match (consistent with FR-6), and what happens when `engine_version` changes without an audible change.

### M6. Terms used but missing from the glossary, and synonyms

- **Missing:** master chain, dichotic path, engine output, coupling depth, modulation depth, depth (addendum), burst, burst width, smooth swell, envelope shape, session body, ramp-in, seam, level ceiling, validator warning, flagged (FR-21), intensity, tone layers (FR-31), slot (FR-24), stem pack, content server, anchor mix (FR-27), fast tests, delta rate.
- **Synonyms or overloads:** "PAC layer" (§4.1 Honesty note) for gamma PAC layer; "gamma envelope peak" (FR-3) versus "modulation depth peaks" (glossary); "coupling depth" (FR-8) versus "modulation depth" (FR-3) versus `depth` (addendum); "tone layers" versus layers; "locked range" used in FR-31 for ranges "the designer locks in the recipe", which conflicts with the glossary meaning (validator range traced to the design log); "listening checklist" (FR-17) versus "curation checklist" (FR-26), which are different things with similar names.
- **Fix:** Add the missing terms, pick one word for each synonym set, and rename the FR-31 concept (for example "listener range").

### M7. Two starter recipes are not specifiable

- **Where:** Addendum Relax ("Off or low depth", "Optional"), Sleep ("Optional"), §11 Q2.
- **Problem:** A recipe file cannot be "optional". FR-16 requires four concrete recipes with golden files.
- **Fix:** Decide binaural on or off and gamma depth for each v0.1 starter recipe, or ship two variants and say so.

### M8. FR placement and phase table disagree

- **Where:** FR-30 sits in §4.9 (Phases 3 and 4) and the Phase 3 row, but says "Holds a full session on Android (Phase 0 gate)"; the Phase 0 part 2 row lists no FR. FR-35 is the Phase 3 gate but iOS ships in Phase 4.
- **Fix:** Split FR-30 into a Phase 0 spike requirement and a Phase 3 product requirement, and list FR numbers in every phase row.

### M9. Sample rate support is unclear

- **Where:** FR-6 (determinism includes sample rate), FR-11 (48 kHz only).
- **Problem:** Phones often run at 44.1 or 48 kHz depending on device and route. Whether the engine renders natively at any rate or resamples affects every threshold.
- **Fix:** State the supported rates and whether thresholds apply at each.

### M10. The seed has no defined use in v0.1

- **Where:** FR-6, FR-7, CLAUDE.md Rule 1.
- **Problem:** v0.1 has no stems. Is there dither, noise, or random phase? Is the WAV dithered to 24 bits, and if so with a seeded generator?
- **Fix:** List what the seed drives in v0.1 (possibly nothing yet) and state the dither policy.

### M11. Real-time constraints are missing

- **Where:** FR-20, FR-22, §4.1 description.
- **Problem:** The engine must run live in the designer and app, but no FR states real-time safety (no allocation or locks on the audio thread), latency for audition, or how live parameter edits are smoothed. "Identical to a render" while the user is turning a knob is undefined.
- **Fix:** Add an engine NFR for real-time safety and a rule for live edits (for example edits apply as ramps of at least 10 ms; identity holds for an unedited recipe).

### M12. Signal naming rule for the binaural layer is undefined

- **Where:** FR-7 ("Every signal is named in the recipe by carrier frequency, modulation type, and modulation rate").
- **Problem:** The binaural layer has no modulation; the test for this FR is unclear.
- **Fix:** Give the binaural naming form (for example "binaural, 250 Hz left, 256 Hz right, 6 Hz beat rate") and make naming a schema validation test.

## Low

### L1. FR-17 breaks the naming rule

- **Where:** FR-17 ("roughness of 40 Hz gamma AM"); addendum Focus ("40 Hz rate (60 selectable)").
- **Fix:** Name the carrier: "roughness of the gamma PAC layer (carrier 200 to 500 Hz, AM at the gamma rate)".

### L2. UJ-2 and FR-21 disagree on what is blocked

- **Where:** UJ-2 ("warns before export and publishing is blocked") versus FR-21 ("blocks export of any failing recipe").
- **Fix:** Align: a spacing failure blocks both export and publishing.

### L3. Implementation choices in the PRD

- **Where:** FR-25 ("notch-filtered at every active carrier"), FR-5 ("a final limiter"), FR-32 (encryption with keys tied to account and device), FR-15 (CI wording).
- **Fix:** State outcomes (for example "stem bed energy within X Hz of an active carrier is at least Y dB below the carrier") and leave mechanisms to architecture.

### L4. Approver name differs between plan and PRD

- **Where:** Plan MVP scope ("Aaron signs off"), PRD ("Audio").
- **Fix:** Use one name everywhere.

### L5. FR-4 "on any device or output" is not testable by the engine

- **Where:** FR-4 ("The engine never sums or downmixes its output channels, on any device or output").
- **Fix:** Restate as an engine-output property; leave device behavior to FR-34.

### L6. Opposite-ear binaural carrier coverage is implicit

- **Where:** Glossary "Spacing rule"; design log 2026-10-27 (e) says the rule exists "to stop one layer from placing the other ear's binaural carrier in this ear".
- **Problem:** The rule only covers this because the beat rate (under 30 Hz) is smaller than the spacing (50 Hz). A future frequency-dependent spacing value could break that.
- **Fix:** State explicitly that in each ear, components of other layers are checked against both binaural carriers.

### L7. Binaural locked ranges lack lower bounds

- **Where:** FR-8 ("carriers below 1000 Hz; beat rate below 30 Hz").
- **Problem:** No minimum carrier, and whether a 0 Hz beat (Sleep's sweep end) is valid is not stated.
- **Fix:** Add lower bounds and state whether 0 Hz is allowed.

## What is already strong

- FR-4 names every forbidden stage and sets two numeric isolation thresholds.
- The honesty note under §4.1 and §6 Claims are clear and enforceable.
- Each FR traces to a user journey, and §12 indexes assumptions.
- The addendum correctly keeps the recipe shape illustrative and leaves field names to architecture.
