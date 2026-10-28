# PRD Reconcile: Design Log, Listening Modes, CLAUDE.md

Date: 2026-10-27
PRD checked: `prd.md` and `addendum.md` in this folder.
Inputs:

- `docs/design-log.md` (working copy, including the uncommitted 2026-10-27 (d) entry)
- `docs/listening-modes.md`
- `CLAUDE.md`

Also consulted where an input points to it: `docs/project-plan.md` (Starter modes footnote, Build and test workflow) and `research-comparables.md` in this folder.

Severity scale:

- **High:** a contradiction with a locked or proposed value, or a CLAUDE.md "Never" rule, that would lead a story or test to build the wrong thing.
- **Medium:** a requirement or input detail that is missing, so downstream agents would have to guess.
- **Low:** wording, traceability, or completeness that does not change what gets built.

## Summary

| # | Gap | Source | Severity |
| --- | --- | --- | --- |
| 1 | Sleep length: PRD requires an 8-hour Sleep session; listening-modes says 30 to 45 min then silence | listening-modes, FR-30, §6 | High |
| 2 | Sleep binaural carrier of 100 Hz contradicts the design log's open value of 200/206 Hz or higher | design log, listening-modes, addendum | High |
| 3 | No requirement for rates that sweep over a session (Sleep 3 Hz to about 1 Hz delta, beat 3 Hz to 0); "theta reference" is defined only at theta rates | listening-modes, FR-1, FR-2, FR-7, glossary | High |
| 4 | Gamma PAC carrier range 200 to 500 Hz (FR-8) has no design log entry, yet FR-8 says every locked range traces to one | design log, FR-8 | High |
| 5 | Banned term "Monroe" appears in `research-comparables.md`, which the PRD cites as an input | CLAUDE.md Never list | High |
| 6 | FR-8 omits the gamma rate range (30 to 60 Hz) and the coupling phase range (0 to 360 degrees) | design log | Medium |
| 7 | Binaural beat limit: PRD assumes 30 Hz, design log says under about 35 Hz, with no log entry for the change | design log, FR-8 | Medium |
| 8 | Design log entry (c) (plan says "trough") is still unapplied; PRD does not carry it | design log (c), plan line 304 | Medium |
| 9 | Noise option (pink or white) in the stem bed is missing from the PRD | plan, Starter modes footnote | Medium |
| 10 | Stem-bed modulation option for Focus conflicts with the glossary ("stem bed contains no entrainment signals") and has no FR | plan, Starter modes footnote; PRD §11 Q8 | Medium |
| 11 | "When to use" column is missing from PRD and addendum | listening-modes | Medium |
| 12 | Relax "Orbit motion added in Phase 2" conflicts with Orbit on gamma only while Relax gamma is off by default | listening-modes, FR-27 | Medium |
| 13 | Evidence and strength per mode, and per-recipe design log entries, are missing; the design log has no starter-recipe entries yet | listening-modes, design log, FR-16 | Medium |
| 14 | Logging every changed default, range, or threshold is not an FR | CLAUDE.md Workflow | Medium |
| 15 | Signal naming rule covers recipes only; the PRD and addendum break it themselves | CLAUDE.md rule 5 | Medium |
| 16 | No automated check for banned terms or em dashes in code, docs, and UI copy | CLAUDE.md Never list | Medium |
| 17 | Independent review is not a v0.1 gate, yet starter recipes rest on proposed values | CLAUDE.md rule 4, design log statuses | Medium |
| 18 | Tests before code and "never weaken a threshold" are prose only, not requirements | CLAUDE.md rule 6 | Low |
| 19 | "Do not commit with failing tests" is weakened to "failing code does not merge" | CLAUDE.md Tests | Low |
| 20 | Every rate variable: FR-3 and FR-4 do not say gamma rate, depth, coupling phase, and beat rate come from the recipe | CLAUDE.md rule 2 | Low |
| 21 | Future design-log items (60 to 80 Hz extended band, per-listener gamma rate) are not in §8 Later | design log (a) | Low |
| 22 | Focus "start about 10 minutes before a task" and Learn "right after study" timing are not reflected anywhere | listening-modes | Low |
| 23 | Learn 60 Hz gamma needs a carrier of at least 240 Hz; addendum does not note it | design log (a), carrier rule | Low |
| 24 | "neurostimulation" appears in the PRD only inside the prohibition; acceptable | CLAUDE.md Never list | Info |

## Findings

### 1. Sleep length contradiction (High)

- **Input:** `listening-modes.md` Sleep row: "30 to 45 minutes, then a fade to silence. No stimulation after sleep onset."
- **PRD:** FR-30 requires playback "through an 8-hour Sleep session on target devices". §6 Hearing safety says "Sleep sessions can run for hours". UJ-3 and FR-16 match the 45-minute version.
- **Risk:** a story builds an 8-hour Sleep recipe that plays rhythmic sound long after sleep onset, which listening-modes rules out (Ngo et al., 2013 reasoning).
- **Fix:** in FR-30, separate the 8-hour background-playback endurance test from Sleep length: "holds a full session on Android and an 8-hour test render or playback on target devices". State in FR-16 that Sleep is 30 to 45 min and ends in silence. Reword §6 to "long sessions or all-night playback of a non-rhythmic bed, if added later". If an all-night option is wanted, raise it as an open question with a source.

### 2. Sleep binaural carrier below the open floor (High)

- **Design log current state:** binaural carrier "open (200/206 Hz or higher, listener-adjustable)".
- **listening-modes and addendum:** Sleep binaural beat "on a 100 Hz carrier". Relax uses 250 Hz.
- **PRD:** §11 Q2 repeats "200/206 Hz or higher". FR-31 also says the listener cannot change the binaural carrier, which contradicts "listener-adjustable" in the design log.
- **Fix:** log a design log entry for the Sleep 100 Hz carrier with its source (Lee et al., 2024), or raise the Sleep carrier. Make Q2 a per-mode question. Resolve "listener-adjustable" vs FR-31 in the design log and the PRD together.

### 3. Rate sweeps and delta-rate reference (High)

- **Input:** Sleep uses "Delta rate instead of theta: 3 Hz sweeping down to about 1 Hz" and a binaural beat "sweeping 3 Hz down to 0".
- **PRD:** FR-7 mentions "ramps over time" only generally. FR-1 says every rate is within 0.01 Hz "of its recipe value", which is undefined for a moving rate. The glossary defines the theta reference only at the theta rate. No design log entry covers a delta-rate reference or its locked range.
- **Fix:** add an FR: "Any rate or carrier can follow a recipe curve over time; the engine keeps phase continuous through the sweep." Restate FR-1 accuracy as "within 0.01 Hz of the recipe curve at each analysis window". Extend the glossary entry to "theta reference (runs at a delta rate in Sleep)" or rename it "rhythm reference". Add a design log entry for the 3 to about 1 Hz delta range and the 3 to 0 Hz beat sweep. Note that the coupling and carrier rule checks must hold at every point in a sweep.

### 4. Gamma PAC carrier range untraced (High)

- **PRD FR-8:** "Gamma PAC carrier: 200 to 500 Hz", while FR-8 itself requires every locked range to trace to a design log entry.
- **Design log:** no entry for it.
- **Fix:** add a design log entry with its source, or tag it `[ASSUMPTION]` and move it to §11 until sourced (CLAUDE.md rule 3). Note the interaction with the carrier rule: at 60 Hz the floor is 240 Hz, so 200 to 239 Hz is valid only for rates up to 50 Hz.

### 5. Banned term in a PRD input (High)

- **Scan result:** `prd.md` and `addendum.md` contain no Monroe, Hemi-Sync, Gateway, Focus-level, or SAM terms, and no em or en dashes.
- **But:** `research-comparables.md` in this folder, which PRD §0 lists as a building block, uses "Monroe" at lines 23, 28 (URL), and 58. CLAUDE.md bans these names "anywhere: code, comments, docs".
- **Also outside the PRD:** `docs/project-plan.md` uses "Monroe" many times (lines 11, 12, 14, 27, 41, 61, 65, 69) and "Gateway" at line 93. Not a PRD gap, but the PRD references this doc.
- **Fix:** rename the comparables entry to the product name only ("Expand") and replace "all Monroe Institute terms" with "all terms from that comparable". Drop the org slug URL or keep only the App Store link. Raise the plan doc wording with Audio as a separate cleanup, since it records history.

### 6. FR-8 missing locked ranges (Medium)

- **Design log:** gamma AM rate locked range 30 to 60 Hz (proposed); coupling phase 0 to 360 degrees (proposed).
- **PRD:** these appear only in the FR-6 note and §11 Q4, not in FR-8, so the validator story would miss them.
- **Fix:** add both to FR-8 as bullets with their design log entries, marked proposed.

### 7. Binaural beat limit (Medium)

- **Design log:** "difference under about 35 Hz" (2026-10-21).
- **PRD FR-8:** 30 Hz, tagged as an assumption.
- **Fix:** keep the assumption, but add a design log entry once Audio decides, as CLAUDE.md requires for any changed range. Add this to §12 as "needs log entry".

### 8. Plan coupling wording still says trough (Medium)

- **Design log (c):** apply "peaks at the recipe's coupling phase" to the plan "when the PRD is written".
- **Plan line 304:** still says "peaks at the in-file theta trough". Line 54 (Lessons table) says the same for the test.
- **Fix:** apply entry (c) now, or add a PRD note that FR-3 supersedes the plan wording, so test-design agents reading the plan do not test for trough.

### 9. Noise option missing (Medium)

- **Input:** plan Starter modes footnote: "a pink or white noise option in the stem bed, since Melnichuk et al. (2025) found background noise changed results". (This line sits in the plan, not in `listening-modes.md`; the mode file should carry it too.)
- **PRD:** no FR; §4.7 covers only stems.
- **Fix:** add an FR under 4.7: "A recipe can add pink or white noise to the stem bed at a set level; noise is generated from the recipe seed." Note that broadband noise cannot satisfy the 50 Hz spacing rule, so state that FR-25 carrier notching applies to noise and that the spacing rule counts tonal components only. Copy the footnote into `listening-modes.md`.

### 10. Stem-bed modulation option for Focus (Medium)

- **Input:** plan footnote: "a stem-bed modulation option for Focus, pending a patent check on the method in Woods et al. (2024)".
- **PRD:** §11 Q8 only. The glossary says the stem bed "contains no entrainment signals", which this option would break.
- **Fix:** keep it in §11, add the patent check to the Phase 2 freedom-to-operate gate, and reword the glossary: "Stem bed: contains no entrainment signals in its files; any modulation applied by the engine is a recipe parameter (pending Q8)."

### 11. "When to use" missing (Medium)

- **Input:** Focus: start about 10 minutes before a task and keep it running. Learn: right after studying or practice. Relax: meditation, breaks, winding down. Sleep: pre-sleep, in bed.
- **PRD and addendum:** the addendum mode table drops this column. UJ-3 alludes to it.
- **Fix:** add a "When to use" column to the addendum table. Add an FR-29 bullet: "each mode shows a one-line when-to-use note, describing the sound and timing, never an outcome".

### 12. Relax Orbit vs gamma-only Orbit (Medium)

- **Input:** Relax "Orbit motion added in Phase 2"; Relax gamma "Off by default, or low depth"; evidence is Sudre et al. (2024) on moving sounds at 6 Hz.
- **PRD FR-27:** Orbit moves the gamma PAC layer only. In default Relax there is nothing to move.
- **Fix:** add §11 question: "What does Orbit move in Relax when gamma is off?" Do not widen Orbit to the binaural layer or theta reference (CLAUDE.md Never list). Carry the Relax arc note into the addendum.

### 13. Evidence and recipe entries (Medium)

- **Input:** each mode lists sources and strength (Moderate; Weak, preliminary; low to medium for phase).
- **Design log:** no entries yet for the starter values (6 Hz, 5.5 Hz, 50 ms bursts, 250 Hz and 100 Hz binaural carriers, lengths, arcs).
- **PRD:** FR-16 requires them, which is correct, but the addendum table drops the evidence column.
- **Fix:** add the evidence column to the addendum table. Add a v0.1 story task: one design log entry per starter recipe before golden-file sign-off.

### 14. Logging every changed default (Medium)

- **CLAUDE.md:** "Log every changed default or threshold in the design log with its source or test result."
- **PRD:** only implied (FR-8 traceability, §5 intro, FR-16).
- **Fix:** add an FR or §6 guardrail: "Any change to a default, locked range, or test threshold needs a design log entry with its source or test result; CI fails if a threshold file changes without one." `[ASSUMPTION: CI check is feasible]`

### 15. Signal naming rule (Medium)

- **CLAUDE.md rule 5:** name every signal by carrier frequency, modulation type, and modulation rate.
- **PRD:** FR-7 applies it to recipe files only. The PRD and addendum break it: FR-17 "40 Hz gamma AM" (no carrier); addendum mode table lists gamma and theta reference rates without carriers; §8 Phase 2 "Isochronic-only speaker modes".
- **Fix:** extend the FR-7 bullet to test reports, designer labels, docs, and logs. Add carriers to the addendum table or mark them "carrier set in recipe, see design log". Reword FR-17 to "a roughness check on gamma AM at 40 Hz on its recipe carrier".

### 16. Never-list enforcement (Medium)

- **CLAUDE.md:** banned program names and terms anywhere; no em dashes in docs, comments, or UI copy; no health claims.
- **PRD:** §6 Claims and Clean room cover the intent but name no banned list and no check. No em dash rule at all.
- **Fix:** add a §6 guardrail and an FR-15 bullet: "CI runs a text check over code, docs, and UI strings for the banned term list and em dashes, and fails on a match." Keep the banned list itself in one config file, not in UI-facing text.

### 17. Independent review not gated (Medium)

- **CLAUDE.md rule 4** and every design log entry: proposed until independently reviewed.
- **PRD §8:** v0.1 gate has tests, golden files, and sign-off, but no review. Starter recipes would ship on proposed values.
- **Fix:** add to the v0.1 gate: "gamma rate, coupling phase, and every starter-recipe default are locked after independent review, or the golden files are marked provisional."

### 18. Tests before code (Low)

- **PRD:** §4.4 description says it; no FR.
- **Fix:** add to FR-15: "Each story's failing tests are committed before its implementation. A threshold is never relaxed to pass; a change is proposed with a reason and logged (FR for item 14)."

### 19. Commit vs merge (Low)

- **CLAUDE.md:** do not commit with failing tests. **FR-15:** failing code does not merge.
- **Fix:** add "and is not committed" or a pre-commit hook for fast tests.

### 20. Every rate variable (Low)

- **Fix:** add one FR-3 and one FR-4 bullet each: "gamma rate, carrier, depth, shape, and coupling phase come from the recipe" and "carriers and beat rate come from the recipe; none is hard-coded".

### 21. Future design-log items (Low)

- **Design log (a):** 60 to 80 Hz as a possible extended band; per-listener gamma rate within range.
- **Fix:** list both under §8 Later, each with "only if new evidence appears" and its design log entry.

### 22. Timing guidance (Low)

- Covered by the fix in item 11.

### 23. Learn 60 Hz carrier floor (Low)

- **Fix:** add a note to the addendum Learn row: "60 Hz rate needs a gamma carrier of at least 240 Hz".

### 24. "neurostimulation" (Info)

- Appears at PRD line 291 only as a quoted prohibited word, mirroring CLAUDE.md. No change needed. No banned terms or em dashes were found anywhere else in `prd.md` or `addendum.md`.

## Items checked with no gap

- Gamma rate default 40 Hz, coupling phase default 0 degrees with uncoupled option, Learn at peak: match the design log.
- Theta rate default and binaural on/off default: correctly left open (§11 Q1, Q2).
- Carrier rule, spacing rule, binaural isolation, no coupling to a binaural beat, no summing: carried as FRs.
- Golden files change only after listening sign-off: FR-14.
- Roughness listening check: FR-17.
- Session arcs designed from scratch, describe-the-sound copy: §6.
- Focus and Learn looping, Sleep fade to silence, Focus 5-minute ramp, Relax 10-minute theta build: addendum and FR-16.
