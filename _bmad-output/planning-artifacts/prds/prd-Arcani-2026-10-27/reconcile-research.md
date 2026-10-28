---
title: PRD reconciliation against research inputs
prd: prd.md, addendum.md
created: 2026-10-27
status: draft
---

# PRD reconciliation: research inputs

## Inputs checked

- `docs/research-library.md` (the library)
- `_bmad-output/planning-artifacts/research/academic-lit-gamma-rate-and-coupling-phase-2026-10-27/research.md` (the gamma report, refs written as [n])
- `docs/design-log.md` (the log), as the allowed third trace target
- `docs/project-plan.md` and `docs/listening-modes.md` were read only to see where untraced PRD values came from.

Severity key: **High** = would block v0.1, break a CLAUDE.md rule, or contradict a source. **Medium** = a research recommendation or trace the PRD drops, which downstream agents will need. **Low** = wording, completeness, or a later-phase item.

## Summary of top gaps

1. **High.** The spacing rule as written in FR-9 rejects every recipe, including all four starters, because each AM layer's own side frequencies and the binaural pair sit under 50 Hz apart.
2. **High.** The gamma carrier range 200 to 500 Hz (FR-8) and the v5 levels and 450 Hz theta carrier trace to the v5 reference and challenge reviewer feedback, not to the library or log, and may conflict with the PRD's own clean-room rule.
3. **High.** Hearing safety cites WHO-ITU but sets no ceiling, test, or session cap; FR-30's "8-hour Sleep session" also contradicts the 30 to 45 minute Sleep design that the library's Ngo et al. (2013) entry supports.
4. **Medium.** Research recommendations missing from the PRD: per-listener gamma rate as a future feature, EEG pilot design, comfort over long sessions, and reported adverse events.
5. **Medium.** FR-8 omits most locked ranges (theta rate, gamma rate, coupling depth, theta carrier), and its binaural beat limit (30 Hz) contradicts the log (about 35 Hz) with no log entry.

## Part 1: trace check of every default, range, and threshold

### 1.1 Values that trace cleanly

| PRD value | Where in PRD | Trace |
| --- | --- | --- |
| Gamma rate default 40 Hz, range 30 to 60 Hz | FR-6 Notes, §11 Q4 | Log 2026-10-27 (a); gamma report rec 1, refs [1] to [8] |
| Coupling phase 0 to 360 degrees, 0 at envelope maximum, default 0, uncoupled option | Glossary, FR-3, FR-6 Notes | Log 2026-10-27 (b); gamma report rec 3, refs [13] to [23] |
| Learn at 0 degrees (peak) | Addendum starter table | Log 2026-10-27 (d) |
| Carrier rule, at least 4 times | Glossary, FR-9 | Log (provisional, plan Test thresholds); gamma report rec 1 restates it at 60 Hz |
| Binaural carriers below 1000 Hz | FR-8 | Log 2026-10-21; library, Licklider (1950) via Lopez-Caballero and Escera |
| Isolation 90 dB / 60 dB, coupling 2 ms, 0.01 Hz, 1 ms over 8 h, -100 dBFS, -60 dBFS clicks, 10 ms ramps, 1 LU and -1 dBTP, 20 times real time | FR-1 to FR-5, FR-11, FR-12, §5 | Log row "All other test thresholds: provisional, project plan". Engineering thresholds, not research values; trace is acceptable |
| Relax optional 6 Hz beat on 250 Hz | Addendum | Library, Jirakittayakorn and Wongsawat (2017) |
| Sleep beat sweeping 3 Hz to 0 on 100 Hz; fade to silence; no sound after sleep onset | Addendum, FR-16, §7 | Library, Lee et al. (2024) and Ngo et al. (2013) |
| Learn 5.5 Hz theta | Addendum | Library, Roberts et al. (2018) |
| FDA wellness wording boundary | §6 | Library, FDA General Wellness guidance (January 6, 2026) |
| Roughness check on 40 Hz gamma AM | FR-17 | Log 2026-10-27 (a) listening check; gamma report refs [10][11] |

### 1.2 Values that do not trace, or contradict a source

| # | PRD value | Problem | Severity | Suggested fix |
| --- | --- | --- | --- | --- |
| T1 | FR-9 and Glossary: "at least 50 Hz between any two active spectral components, counting modulation side frequencies" | Read literally, this rejects every valid recipe. A 300 Hz gamma carrier at 40 Hz AM has components at 260, 300 and 340 Hz, 40 Hz apart. A 450 Hz theta reference at 6 Hz has 444, 450 and 456 Hz. The binaural pair (250 and 256 Hz in Relax, 100 and 103 Hz in Sleep) is 6 Hz or less apart by design. The plan's intent (plan, signal design, carrier spacing rule) is spacing between *different* layers so that they do not beat against each other or leak across ears. The 50 Hz value itself is a placeholder in the log, with no research source. | High | Restate FR-9: spacing applies between components of different layers, checked per ear; a layer's own carrier and its own side frequencies are exempt; the two binaural carriers are exempt from each other because they are in different ears. Add acceptance tests for each starter. Keep 50 Hz marked as a placeholder (§11 Q3) and log the rewording. |
| T2 | FR-9 interacting with Relax: "gamma off or low depth" plus "6 Hz beat on 250 Hz" | If Relax turns gamma on at the 300 Hz starter carrier, the 40 Hz lower side frequency (260 Hz) sits 4 Hz from the right binaural carrier (256 Hz), and at 60 Hz (240 Hz) it sits 10 Hz from the left (250 Hz). Under any reading of the rule this fails. | Medium | State in the addendum that Relax with gamma on needs a different gamma carrier or binaural carrier, and add a validator test for this exact case. |
| T3 | FR-8: gamma PAC carrier 200 to 500 Hz | No library or log entry. In the plan, the range comes from challenge reviewer guidance (plan, Gaps check quote and Signal design table). The plan's own clean-room rule 2 excludes "anything learned only through the hiring challenge or private feedback", and PRD §6 says Arcani "never uses anything learned through private channels". The library does support the low end (Ross et al. 2003, lower carriers give larger 40 Hz responses), and the carrier rule sets a floor of 4 times the rate. Neither supports the 500 Hz ceiling. | High | Audio confirms whether the reviewer guidance counts as private feedback. Either way, re-derive the range from public sources: floor from the carrier rule (120 Hz at 30 Hz, 240 Hz at 60 Hz), upper bound from Ross et al. (2003) and comfort (Schutze et al. 2026, preliminary). Log it as a new entry with status proposed. |
| T4 | Addendum and §5: tones -36 LUFS-I, master -16 LUFS-I; addendum: theta reference carrier 450 Hz | These are "kept from v5" in the plan. The library lists EBU R128 and the -16 LUFS figure as context and convention only, and says to describe -16 as a convention, not a standard. No log entry. PRD §6 forbids copying any third-party program's levels. | High | Log each level with an independent rationale (convention, headroom against the -1 dBTP ceiling, WHO-ITU exposure). Label -16 LUFS as a convention in the PRD. Give the 450 Hz theta carrier its own rationale (audible on small drivers, spacing from gamma side frequencies) or mark it open. |
| T5 | FR-8: binaural beat rate "below about 30 Hz" | The log and library say "under about 35 Hz" (Licklider via Lopez-Caballero and Escera). 30 Hz is the plan's designer limit with no source. The PRD tags it as an assumption but no log entry exists. Also "about" is not a validator limit. | Medium | Add a log entry choosing one number with its source. If 30 Hz is kept as a safety margin under the 35 Hz perception limit, say so. Write the limit as an exact value. |
| T6 | FR-8 lists only binaural and gamma carrier ranges | Missing locked ranges for theta rate (Sleep goes to about 1 Hz, Learn 4 to 5.5 Hz, Focus 6 Hz), gamma rate (30 to 60 Hz is only in Notes), coupling phase, coupling depth (plan: 0 to 100 percent), burst width (50 ms in Focus), theta carrier, binaural carrier floor, and ramp lengths. CLAUDE.md rule 2 says every rate has a locked safe range. | Medium | List every recipe parameter in FR-8 with its range and log entry, marking open ones as open. Theta rate range is a research item (library: 2.5 to 5 Hz from Lega; 5.5 Hz Roberts; 6 Hz Jirakittayakorn; 1 to 3 Hz Lee). |
| T7 | FR-30 and §6: "8-hour Sleep session"; "Sleep sessions can run for hours" | The Sleep design is 30 to 45 minutes then silence, with no stimulation after sleep onset (listening-modes; library, Ngo et al. 2013). An 8-hour Sleep playback requirement contradicts that. The 8-hour figure is valid only as an engine drift test. | High | Change FR-30 to "holds the longest session a recipe allows" and keep 8 hours only as the FR-1 drift render. Remove "run for hours" from §6 or reword it to looping Focus and Learn sessions, which have no cap (see G1). |
| T8 | Addendum Focus: "40 Hz rate, 50 ms bursts at the theta peak", rationale Alekseichuk et al. (2016) | The library and gamma report both say Alekseichuk found low gamma (40 Hz) ineffective; the benefit was 80 to 100 Hz electrical bursts. Citing it as support for 40 Hz Focus bursts overstates it. | Medium | In the Focus rationale, cite Alekseichuk only for the burst shape and peak option, and state that its rate and modality do not transfer (gamma report, Cross-dimension insights). |
| T9 | FR-3: gamma carrier waveform triangle and softened square; FR-2 sawtooth and other theta envelopes; FR-4 non-sine binaural with warning | No source. Non-sine waveforms add harmonics, and hard-edged envelopes add side frequencies at many multiples of the rate. The spacing rule (FR-9) does not say whether harmonics count. A 300 Hz triangle puts energy at 900 and 1500 Hz. | Low | Say in FR-9 that harmonics above a stated level count as spectral components. Mark the non-sine options as design choices without a research source, to be checked by ear. |
| T10 | Library vs gamma report on Ross et al. (2003) | The library marks it Verified (about 30 percent per octave, 250 Hz gives 3 times the 4000 Hz response). The gamma report rates the same claim low confidence, "authors and year unverified". | Low | Reconcile the two entries; the library verified the full PDF, so update the gamma report's [12] or note why the confidence differs. |

## Part 2: research recommendations the PRD does not carry

| # | Recommendation | Source | What the PRD has | Severity | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| G1 | **Hearing safety with numbers.** WHO-ITU: 80 dB for 40 hours a week for adults. | Library, Standards; plan, Gaps check | §6 says "guidance aligned with WHO-ITU" and FR-23 mentions "level ceilings", but there is no value, no FR, no NFR row, and no test. Focus and Learn loop until stopped (FR-29) with no cap. | High | Add an NFR row and an FR: a master level ceiling, no sudden loud events (tied to the 10 ms ramp rule), an optional session cap for looping recipes, and first-run safe-listening guidance referencing the WHO-ITU figure. Note that the app sets digital level, not SPL, so guidance must cover device volume. Phase 3 gate includes it. |
| G2 | **Per-listener gamma rate**, within the locked range, as a future feature, not a v0.1 default. | Gamma report rec 2, refs [5][6]; log 2026-10-27 (a) | Absent. FR-31 forbids listeners changing any rate, and the "Later" list does not mention it. | Medium | Add to §8 "Later": per-listener gamma rate within 30 to 60 Hz. Note it needs a way to find the listener's peak (the studies used EEG chirps), which touches the §7 non-goal on EEG, and that FR-31 would need a designer-locked exception. |
| G3 | **EEG pilot design.** Compare sound-domain peak, trough, and uncoupled head to head, with a sham control; measure each listener's sound-to-cortex delay; use a standard PAC metric with significance testing. | Gamma report rec 6; log 2026-10-27 (b); library, Tort et al. and Onslow et al. (2011) | §11 Q9 asks only whether to run it. Phase 1 lists a "peak vs trough vs uncoupled comparison" with no method. | Medium | Expand Q9 or add a Phase 1 item stating the pilot's minimum design: three sound conditions plus sham, per-listener delay measured, modulation index with significance testing on adequate data length, and a rule that its result is the only path for the coupling phase to become an evidence-based default. |
| G4 | **Comfort over long sessions.** No data exists on 30 to 60 Hz AM comfort over long or overnight listening; check by ear, then with users. | Gamma report, Open questions and Perception and comfort | Absent. SC-2 counts faults, seams, and clicks, not comfort. | Medium | Add a comfort item to the FR-17 checklist covering a full-length play of each starter, and a listener comfort check in the Phase 3 closed beta before launch. |
| G5 | **Reported adverse events.** Mild headache, dizziness, and tinnitus were common in long-term 40 Hz studies. | Gamma report, ref [7] | Absent. | Medium | Feed into G1 safety messaging (stop if uncomfortable) and into §10 Risks. Wording stays descriptive, not medical. |
| G6 | **Lower gamma carriers give larger responses**, but sound rougher at 40 Hz. | Library summary point 6 and Ross et al. (2003); gamma report refs [11][12] and Cross-dimension insights | FR-8 gives 200 to 500 Hz with no guidance; the trade-off is not stated. | Low | Add a note to FR-8 or the addendum: prefer the low end (250 to 300 Hz) and swing depth fully, then check roughness by ear (FR-17). Do not claim larger responses in copy. |
| G7 | **Roughness check across the range**, not only at 40 Hz. | Log 2026-10-27 (a); gamma report refs [10][11] | FR-17 checks 40 Hz only; Focus and Learn offer 60 Hz. | Low | Change FR-17 to "a roughness check on every gamma rate and carrier the recipe uses". |
| G8 | **Plan doc correction** from trough to "the recipe's coupling phase". | Gamma report rec 4; log 2026-10-27 (c), "apply when the PRD is written" | Not mentioned. The plan still says trough in its signal assertions, its signal design text, its recipe example (`"phase": "trough"`, `"gamma_hz": 60`), and its Learn row. It also still estimates a 30 to 50 ms brain delay, where the gamma report finds roughly 80 to 160 ms [21][22][23]. | Medium | Apply the log (c) correction to `docs/project-plan.md` before architecture, since the PRD tells downstream agents to read the plan's thresholds table. Update the delay estimate with refs [21][22][23]. |
| G9 | **No outcome claims for any rate or phase of sound.** FDA general wellness boundary. | Gamma report rec 5; library, FDA (2026) | §6 covers claims in general. No step makes the copy check happen, and nothing says the coupling phase is a sound-design convention, not a brain target. | Low | Add to §6: the coupling phase and gamma rate are described only as sound properties. Add a copy review against the FDA guidance to the Phase 3 gate. |
| G10 | **Re-check the preprint [23]** for a version of record before the coupling phase locks. | Gamma report, Staleness map (due 2026-10-01) | §11 Q4 asks for independent review only. | Low | Add to §11 Q4: the review includes a refresh of [23]. |
| G11 | **Extended 60 to 80 Hz band**, unlockable only on new auditory evidence; open question on 80 Hz for sleep (less arousal-sensitive response). | Gamma report rec 1 and Open questions, ref [2]; log 2026-10-27 (a) | Absent. | Low | Add to §11 as an open research item, with no v0.1 impact. |
| G12 | **Per-listener binaural carrier.** Comfort fell as carrier rose, with large person-to-person variation (preliminary). | Library, Schutze et al. (2026); log row "Binaural carrier: open, listener-adjustable" | FR-31 forbids listeners changing the binaural carrier, which contradicts the log's open "listener-adjustable" option. | Medium | Either keep FR-31 and update the log row, or allow a designer-locked carrier choice and record it in §11 Q2. |
| G13 | **Rhythmic panning mode worth testing in Phase 2.** | Library, Sudre et al. (2024) | FR-27 lists path shapes but not a rhythmic panning option. | Low | Add to Phase 2 as a candidate for the FR-28 A/B. |

## Part 3: suggested order of work

1. Fix T1 (spacing rule wording), because the v0.1 validator and every starter recipe depend on it.
2. Resolve T3 and T4 (clean-room trace for the carrier range, levels, and theta carrier) and log new entries.
3. Add G1 hearing safety numbers and fix T7 (8-hour Sleep).
4. Fill FR-8 with every locked range (T6) and settle the binaural limit (T5).
5. Apply the plan correction (G8).
6. Add the remaining Medium and Low items to the PRD, §8 Later, and §11.
