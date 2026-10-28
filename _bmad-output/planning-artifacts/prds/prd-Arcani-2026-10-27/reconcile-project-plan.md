# Reconciliation: PRD vs project plan

Input: `docs/project-plan.md` (project brief, Oct 17, 2026) and `docs/Screenshots/Arcani-Phases.png` (phase roadmap).
Checked against: `prd.md` and `addendum.md` in this folder.
Date: 2026-10-27.

Deliberate PRD decisions were excluded from findings: no third-party program names, speaker and mono variants and headphone detection deferred, no mono summing, Learn uses peak coupling, no listener binaural controls, the coupling assertion names "coupling phase", and internal-tool rigor with launch details deferred.

Severity scale:

- **High:** a test, guardrail, or rule from the plan is missing or weaker, and a downstream agent following the PRD would build or test the wrong thing.
- **Medium:** a principle or qualitative requirement is dropped or only implied, so it will likely vanish when stories are written.
- **Low:** detail or rationale lost; easy to restore, small risk.

## Summary

| # | Gap | Severity |
| --- | --- | --- |
| 1 | NaN, dropout, and envelope-shape assertions dropped from the test suite | High |
| 2 | Listening checklist undefined and limited to starter renders, not every new recipe | High |
| 3 | Phase order: v0.1 feature work precedes the Phase 0 spike that confirms defaults and thresholds | High |
| 4 | Sample rate dropped from the determinism key, which matters for FR-35 cross-platform identity | Medium |
| 5 | Honesty principle reduced to a copy rule; evidence strength per mode and the "untested with sound" caveat dropped | Medium |
| 6 | "Easy designer" reduced to a description line; plain labels and the non-engineer usability test have no FR | Medium |
| 7 | Independent QA agent (fresh context, dev never grades its own work) dropped | Medium |
| 8 | "Binaural layer is never required" rule dropped, while listeners cannot turn binaural off | Medium |
| 9 | Speaker, mono earbud, and OS mono-setting risk deleted from Risks instead of kept as an accepted risk | Medium |
| 10 | Evidence register (modality, sample size, finding) dropped | Medium |
| 11 | Partnership-ready principle not stated as a guardrail | Medium |
| 12 | "Peer-reviewed" source requirement weakened to "a source in the research library" | Medium |
| 13 | Freedom-to-operate scope lost its named families | Low |
| 14 | Pink or white noise option in the stem bed dropped | Low |
| 15 | Orbit layer: entry and exit ramp curves, rhythmic panning test, and A/B measures dropped | Low |
| 16 | Rule precedence and "every claim maps to a test or listening check" dropped | Low |
| 17 | Double-check scope narrowed (drops "anything costly to undo") | Low |
| 18 | Smaller dropped details (sawtooth theta envelope test, recent-phone features, encryption expectation, Apple rule check, binaural in-phase start note, WHO number) | Low |

## Findings

### 1. NaN, dropout, and envelope-shape assertions dropped (High)

**Plan:** Build and test workflow, signal assertions: "No clicks at loop seams or envelope edges, no dropouts, no NaN values" and "the envelope shape matches the recipe".

**PRD:** FR-13 lists binaural isolation, coupling timing, carrier rule and spacing, frequency accuracy, drift, reference match, determinism, clicks, gain ramps, loudness and true peak, render speed. No NaN check, no dropout check, no envelope-shape check. CLAUDE.md copies the same reduced list, so the gap will propagate.

**Why it matters:** NaN and dropouts are classic DSP failures that loudness and click tests can miss (a NaN can be clamped by a limiter; a short dropout may not trip an 8 kHz high-pass test). Envelope shape is the only check that the selected theta envelope (sine, smoothed on-off, sawtooth, reverse saw, custom) and the gamma shape (swell vs burst) are what the recipe asked for; coupling timing only checks peak position. The reference match test partly covers shape, but only if the Python reference is itself right.

**Fix:** Add to FR-13: "no NaN or infinite samples", "no dropouts (define: no run of digital silence or gain collapse longer than X ms where the recipe expects signal)", and "theta reference and gamma PAC envelope shapes match the recipe within a set tolerance". Add matching NFR rows in §5, with provisional thresholds proposed for Phase 0 confirmation. Update CLAUDE.md's test list to match.

### 2. Listening checklist undefined and too narrow (High)

**Plan:** Human gates: "Your ears on every new recipe, using a short listening checklist, and a real Android phone for background playback and battery behavior, which emulators can't verify." Rule 1: every claim maps to "an automated test or a listening check".

**PRD:** FR-17 requires a written checklist only for the four starter renders (adding a 40 Hz roughness check). FR-23 Publish runs validator, level ceilings, and isolation, but no listening sign-off. No FR says the checklist must be written, versioned, or what it covers. The real-device human gate for battery is only an assumption in the Battery NFR.

**Why it matters:** The checklist is the one control for everything machines cannot judge (roughness, fatigue, masking, buzz from flagged waveforms, stem consonance). Without an FR that creates it, no story will, and Phase 1 recipes could be published without anyone listening.

**Fix:** Add an FR: "A written, versioned listening checklist exists before the first golden file. It covers at minimum: roughness or buzz on gamma AM, audible clicks at seams and burst edges, carrier masking by stems, comfort at target level, and per-ear check of the binaural layer on headphones." Extend FR-23: publishing requires a recorded listening sign-off against the checklist for every new or changed recipe. Add a human-gate line to Phase 0 and Phase 3: background playback and battery verified on a real Android phone, not an emulator.

### 3. Phase order contradicts the plan and roadmap (High)

**Plan and roadmap:** "Phase 0 is next: a short spike that proves background audio and the carrier isolation test before any feature work." Phase 0 contents in the roadmap image: DSP core, background playback with screen off, battery check, framework confirmed, headless render CLI, Python reference renderer, test harness. Defaults and test thresholds are "checked in Phase 0 ... before [they are] locked".

**PRD:** §8 puts v0.1 (engine core, four starter recipes, four golden files) before Phase 0, and its `[ASSUMPTION]` moves the Android spike after the architecture step. The Phase 0 row lost the CLI, reference renderer, and test harness.

**Why it matters:** Golden files would be signed off on defaults and thresholds the plan says Phase 0 must confirm first, so they will likely need re-approval. Building engine features before proving background playback is the risk the plan's ordering was designed to avoid. This also conflicts with "Phase 0 is next" while CLAUDE.md says v0.1 is current.

**Fix:** Either (a) state that v0.1 is Phase 0's desktop half and record that golden files are provisional until Phase 0 confirms defaults and thresholds, or (b) move the Android background spike to run in parallel with v0.1, before the starter recipes are signed off. In both cases restore CLI, reference renderer, and test harness to the Phase 0 row as delivered by v0.1, and get Audio's explicit sign-off on the reordering (it is a plan change, so it belongs in the design log).

### 4. Sample rate dropped from the determinism key (Medium)

**Plan:** Rule 1: "The same recipe, engine version, and sample rate always render the same output." The test threshold table adds seed.

**PRD:** FR-6 and §5: "same recipe, engine version, and seed". Sample rate missing.

**Why it matters:** The CLI is fixed at 48 kHz, but phones may run at 44.1 kHz or other device rates. FR-35 (iOS matches Android) and FR-20 (audition identical to render) are undefined unless sample rate is part of the key or the engine always runs at a fixed internal rate.

**Fix:** FR-6: "Same recipe, engine version, seed, and sample rate produce byte-identical output." Add to FR-35 and FR-20 the sample rate at which identity is asserted, and ask the architecture step to decide whether the engine renders at a fixed internal rate.

### 5. Honesty principle reduced to a copy rule (Medium)

**Plan:** "Honest claims. We describe what the audio is and how it was designed." Signal architecture: auditory cortex following is "well supported"; memory-network coupling from sound is "not yet tested with sound ... the open question this app's design should be honest about"; trough coupling is "a hypothesis, not a proven default"; the brain's 30 to 50 ms delay means "a trough in the file does not mean a trough in the brain". Session modes carry an "Evidence and strength" column (Moderate, Moderate, Moderate for relaxation and none for PAC, Weak and preliminary). Gaps check: "Cite for what it found, nothing broader."

**PRD:** §6 Claims and §1 Vision keep the wording rule. The addendum mode table drops the evidence and strength column and the "when to use" column. Nothing states the two-level evidence picture or the delay caveat, and no requirement says internal docs and the design log rate evidence strength.

**Why it matters:** The honesty principle governs design rationale and internal documents, not only store copy. A downstream agent writing mode descriptions or a design-log summary has no instruction to state evidence strength or the untested PAC question.

**Fix:** Restore the evidence-strength and "when to use" columns in the addendum mode table. Add to §6: "Honesty in design: every mode and default records its evidence strength and modality. Any description of the PAC layer states that sound-driven memory-network coupling is untested, and that file phase does not equal brain phase. Studies are cited only for what they found."

### 6. "Easy designer" has no testable requirement (Medium)

**Plan:** Rule 6: "uses plain labels, shows the signal it is making (waveform, spectrum, per-ear view), and warns before an unsafe or meaningless setting." Gaps check: "Usability test of the designer: one session with someone who isn't an engineer, per rule 6."

**PRD:** FR-19 (views) and FR-21 (warnings) are kept. "Plain labels" appears only in the §4.6 description, not in an FR. The non-engineer usability session is gone. Rule 7 naming (carrier, modulation type, rate) is required in the recipe (FR-7) but not in designer labels.

**Fix:** Add FR: "Every designer control uses a plain-language label and names signals by carrier frequency, modulation type, and modulation rate, with the unit shown." Add to the Phase 1 gate: "one usability session with a non-engineer completes a recipe edit and export without help." Make "meaningless" settings explicit in FR-21 (for example a coupling phase set while gamma is uncoupled, or a binaural beat above the perception limit).

### 7. Independent test authorship dropped (Medium)

**Plan:** "a QA agent with fresh context turns each story's acceptance criteria into tests before the dev agent writes code, so the dev agent never grades its own work."

**PRD:** §4.4 says tests are written before code but drops the independence. FR-15 says nothing about who writes tests.

**Fix:** Add to FR-15 or §6: "Tests for a story are written by an agent or person other than the one implementing it, from the acceptance criteria, before implementation."

### 8. "Binaural layer is never required" dropped (Medium)

**Plan:** Session modes, shared: "the binaural layer is never required". Risks: fall back to modes without the binaural layer. Gaps check: listeners with hearing in one ear can still use in-file modes.

**PRD:** Listeners cannot toggle binaural (deliberate). Relax and Sleep have it optional. Nothing requires that every mode's core rhythm comes from in-file layers, or that each mode has a binaural-off recipe.

**Why it matters:** With no listener toggle and no headphone detection, the only protection for mono, speaker, and one-ear listeners is a recipe rule. The deliberate deferral removed the detection, not the rule.

**Fix:** Add to FR-16 or §6: "No mode depends on the binaural layer; every mode's rhythm exists in the file, and each mode with a binaural layer also ships a binaural-off recipe." This does not add a listener control.

### 9. Mono and speaker risk deleted rather than accepted (Medium)

**Plan risk:** "Binaural beats fail on speakers, mono earbuds, or the phone's mono-audio setting."

**PRD:** The risk row is gone. §7 defers the mitigation, and §6 "No summing" covers only Arcani's own output. An OS mono accessibility setting sums the ears after our output and recreates a monaural beat from the binaural carriers, the same failure as the original bug.

**Fix:** Keep the row in §10 marked "Accepted for now; mitigation deferred (§7)". Extend FR-34 guidance to mention the phone's mono-audio setting alongside spatial audio.

### 10. Evidence register dropped (Medium)

**Plan:** Gaps check: "a table in the design log for every cited study, with modality (audio, light, electrical), sample size, and what it actually found. It would have caught the Alamalhoda mismatch."

**PRD:** Not present. "Every default traces to a source" does not catch a source tested in the wrong modality.

**Fix:** Add to §6 Science first: "The design log keeps an evidence register: for each cited study, modality, sample size, and actual finding. A default may cite a study only if its modality is recorded."

### 11. Partnership-ready not a guardrail (Medium)

**Plan:** "The app should be something we could show [a research partner] with pride and no awkwardness. Nothing in it should need explaining away." Handoff: the design-log summary is "the natural thing to share".

**PRD:** Survives as a JTBD bullet and a "Later" item. §6 has no matching guardrail.

**Fix:** Add to §6: "Partnership-ready. Every signal choice, claim, and recipe must be presentable to a research partner without caveats or explanations. The design log is kept in a state that could be summarized and shared at any gate." Keep the wording free of third-party names.

### 12. "Peer-reviewed" weakened (Medium)

**Plan:** Rule 4: every default and range traces to "a published, peer-reviewed source logged in the design log". IP rule 3 also allows "our own listening tests".

**PRD:** §6: "traces to a source in the research library". Drops peer review and does not say listening-test evidence is allowed or how it is logged.

**Fix:** §6: "Every default and locked range traces to a published, peer-reviewed source, or to a logged in-house listening test, recorded in the design log."

### 13. Freedom-to-operate scope lost its names (Low)

**Plan:** FTO by a patent attorney on the Brain.fm and Endel patent families "plus newer filings on earphone brainwave induction". Also a patent check on the Woods et al. (2024) stem-bed modulation method.

**PRD:** §6: "active modulated-audio patent families". Open question 8 keeps the stem-bed check but not the method name.

**Fix:** Name the families in the addendum (company names here are patent holders, not program names, so the naming rule is not affected), state that a patent attorney performs it, and cite Woods et al. (2024) in open question 8.

### 14. Noise option dropped (Low)

**Plan:** "a pink or white noise option in the stem bed, since Melnichuk et al. (2025) found background noise changed results".

**PRD:** Absent. **Fix:** Add to FR-24 or the addendum as a Phase 1 stem-bed option, with the source.

### 15. Orbit layer details dropped (Low)

**Plan:** Parameters include "ramp curves for entering and leaving motion"; period "slow enough to hold attention without becoming a panning effect"; a rhythmic panning mode "worth testing in Phase 2" (Sudre et al., 2024); the A/B is "measured by session completion and self-report, and by a consumer EEG headband if one is available". Also "our motion uses standard object panning rather than" the abandoned spatial method.

**PRD:** FR-27 omits ramps and the clean-room motion method; FR-28 omits the measures.

**Fix:** Add entry and exit ramps to FR-27, state the method is object panning with interaural level and time differences or an HRTF spatializer, and list the A/B measures in FR-28.

### 16. Rule precedence and claim traceability dropped (Low)

**Plan:** "Where a rule and a later section disagree, the rule wins and the section gets fixed." Rule 1: "every claim in this doc maps to an automated test or a listening check."

**Fix:** Add both to §0 or §6.

### 17. Double-check scope narrowed (Low)

**Plan:** Rule 5 covers "anything that would be costly to undo", reviewed by "a fresh agent or outside expert".

**PRD:** §6 lists signal architecture, defaults, and stack only. **Fix:** Restore "and anything costly to undo" and the reviewer definition.

### 18. Smaller dropped details (Low)

- Sawtooth theta envelope as a real design option to test against sine (mirrors natural theta asymmetry). Add to Phase 1 listening work.
- Platforms: "avoids features that only work on recent phones". Add to the Reach NFR.
- Encryption expectation: "the goal is to stop easy copying, not all copying". Add to FR-32 so no story over-builds DRM.
- Accounts: confirm Apple's current sign-in rule before building. Add to FR-36.
- Binaural layer: if its beat rate matches theta, it may start in phase with the clock, but nothing is claimed about alignment. Add to FR-4 notes.
- Hearing safety: name the WHO-ITU figure (80 dB for 40 hours a week for adults) so the level ceiling has a number to derive from.
- Risk "health claims draw regulators or store rejection": the PRD dropped "regulators". Restore.
- Device testing with spatial-audio features on was scheduled for Phase 2; the PRD risk row gives no phase.
- Starter Focus and Learn: the plan gives fixed lengths (30 to 45 and 15 to 20 minutes), the PRD makes them looping per `docs/listening-modes.md`. Not a contradiction if the length becomes the default timer, but say so in FR-16.

## Items checked and found consistent

Binaural isolation thresholds (90 and 60 dB), coupling timing (2 ms), carrier rule (4x), spacing (50 Hz placeholder), frequency accuracy (0.01 Hz), 8-hour drift (1 ms), reference match (-100 dBFS), clicks (-60 dBFS, 8 kHz high-pass), gain ramps (10 ms), loudness (1 LU, -1 dBTP, -36 and -16 LUFS-I), speed (20x), golden files, CI, carrier notching, stem metadata and codecs, Orbit on gamma only, content manifest, push to device, publish guardrails, anonymous analytics, freemium tiers, offline encryption, no sound after sleep, clean-room session arcs, spatial-audio guidance, open decisions on theta rate, binaural default and carrier, locked ranges, loudness mapping, Orbit public name, and the sham-controlled EEG pilot.
