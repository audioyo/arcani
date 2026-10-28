# Review: Spine reconciliation against rules and design log

- **Target:** `ARCHITECTURE-SPINE.md` (status: draft, 2026-10-27) and `.memlog.md`
- **Inputs checked:** `CLAUDE.md`; `docs/design-log.md`; `docs/listening-modes.md`; `docs/project-plan.md` (IP and clean-room rules, Build and test workflow, MVP scope (v0.1), Test thresholds (provisional))
- **Date:** 2026-10-27
- **Spine edited:** no

## Verdict

The spine follows the binaural isolation and gamma coupling rules well and is clean of banned terms and em dashes. But it leaves out the carrier and spacing rules and most of the required test list. It also makes several decisions that change design-log values without logging them, so it is not yet consistent with the project rules.

## Mechanical checks on the spine

| Check | Result |
| --- | --- |
| Em dashes (U+2014) or en dashes (U+2013) in spine or memlog | None found |
| Banned names (CLAUDE.md Never list) | None found |
| Health, therapy, treatment, neurostimulation wording | None found |
| Bare-rate signal names ("60 Hz isochronic tone" style) | None found. The one named signal follows the convention |

## Findings

Severity: **High** means the rule is dropped or contradicted in a way that would let a build agent ship a violation. **Medium** means the rule is implied but not bound, or the status is overstated. **Low** means wording or completeness.

### F1 (High): Carrier rule and spacing rule are missing

- **Source:** CLAUDE.md Signal facts (carrier rule, spacing rule); plan Test thresholds (carrier-to-rate ratio, carrier spacing); design log 2026-10-27 (e), (i).
- **Spine:** No AD, convention, or validator rule mentions "at least 4 times its modulation rate" or "50 Hz per ear between layers." AD-2 says the validator rejects bad recipes but lists no rules. The plan's MVP scope says recipes are "validated against every locked range and the carrier spacing rule." The spine drops that.
- **Also missing:**
  - The spacing rule's scope: per ear, between layers, including modulation side frequencies, with a layer's own components and the binaural pair exempt.
  - The spectral component definition: within 40 dB of the layer's strongest line, provisional, entry (i).
  - The 50 Hz placeholder status: entry (e) is still proposed.
- **Carrier guard:** the spine adds a "Carrier guard (always last, not removable)" node in the Tone zone but never says what it does. It is presumably the spacing rule enforced on stems (notching at Core components per ear), but that is not written down. Broadband stems and noise cannot satisfy a 50 Hz spacing rule unless the guard is defined.
- **Fix:** Add an AD such as "Validator enforces the carrier rule and per-ear spacing rule." It should:
  - State both rules exactly as CLAUDE.md does, with the exemptions.
  - Cite design log (e) and (i) as provisional.
  - Bind the validator, the plan compiler, and the Tone zone carrier guard.
  - Define the guard: which Core components it protects, per ear, and the minimum distance, read from the locked-range table.
  - Require the check after the 3D stage, because Orbit can place gamma in both ears.

### F2 (High): The required test list is incomplete

- **Source:** CLAUDE.md Tests (11 checks on every render); plan Build and test workflow item 3; plan Test thresholds.
- **Spine coverage:**

| CLAUDE.md test | Spine | Status |
| --- | --- | --- |
| Binaural isolation | AD-4 (structural plus FR-4 output test) | Covered. The two thresholds (90 dB at engine output, 60 dB after the master chain) are not named |
| Coupling timing | AD-5 tests that gamma peaks do not move when the binaural beat changes. The 2 ms peak-to-target test is not named | Partial |
| Carrier ratio and spacing | None | Missing (see F1) |
| Frequency accuracy | None | Missing |
| 8-hour drift | AD-17 full tier | Covered |
| Python reference match | AD-16 | Covered |
| Determinism | AD-1, AD-9, AD-10, AD-14, AD-15 | Covered |
| Clicks | AD-11 names clicks as a risk only. No loop-seam, ramp-edge, or burst-edge test | Missing |
| Gain ramps | AD-11 (10 ms on plan swaps only) | Partial. The plan threshold covers every gain change, including recipe fades and burst edges |
| Loudness and true peak | AD-13 (1 LU) | Partial. The -1 dBTP true-peak limit is missing |
| Render speed | None | Missing (plan: at least 20 times real time) |

- **Also dropped:** dropouts and NaN checks (plan item 3; design log (i) defines a dropout).
- **Fix:** In AD-17, list every assertion the report must contain, one per CLAUDE.md test plus dropouts and NaN. Name the threshold-table row each one reads, and say which tier runs it (fast or full).

### F3 (High): Changed defaults and thresholds are not in the design log, and settled status is overstated

- **Rule:** CLAUDE.md Workflow says to "Log every changed default or threshold in the design log." Rule 4 says stack, signal architecture, and defaults get an independent review before they lock. Design log status values are proposed, locked, and superseded.
- **Items the spine fixes that change or extend a logged or planned value, with no design-log entry:**

| Spine | Changes | Design log or plan today |
| --- | --- | --- |
| AD-9: bit-exact across platforms is the rule; -100 dBFS is only a fallback | Determinism scope | Entry (i): provisional. -100 dBFS cross-platform is the floor and bit-exact is a target "confirmed or dropped in the architecture step and Phase 0 spike." This is a threshold change, so it needs its own entry that supersedes (i) |
| AD-10: native 44.1 and 48 kHz; golden files at both | Output format and v0.1 scope | Plan MVP: "48 kHz 24-bit WAV." Not logged. It doubles the golden set and the sign-off work |
| AD-14: 24-bit rounding, no dither | Output quantization | Not logged |
| AD-13: loudness gain stored in the recipe, with a hash | Loudness method (resolves PRD Q6) | The -16 LUFS target is an "engineering default" (entry (g)). The method is not logged |
| AD-18: no more than 3 flashes per second | New numeric limit | No design-log entry. Rule 3 says every default traces to `docs/research-library.md`; WCAG is cited only in the memlog |
| AD-6: stem motion "locked range" | New range, deferred | Correctly deferred. Should appear as "open" in the design log Current state table |

- **Status overstatement:** AD-1 to AD-5 and AD-16 are tagged [ADOPTED]. AD-4 and AD-5 are signal architecture, and the memlog records the stack as "confirmed by Audio." Neither record shows the independent review that rule 4 requires before locking. The tag makes them read as locked. Meanwhile AD-6 to AD-15, AD-17, and AD-18 are untagged, although the memlog shows Audio decided them. The tags carry no consistent meaning.
- **No proposed value is restated as locked.** The spine does not hard-code the 40 Hz gamma rate, the 30 to 60 Hz range, the 0 degree coupling phase, or the binaural limits, which is correct. But it also never says that these signal values are proposed or provisional and must be read from the range table.
- **Fix:**
  - Add design-log entries for AD-9 (superseding the determinism row of (i)), AD-10, AD-13, AD-14, and AD-18, each with source and status. Add the AD-18 source to the research library.
  - Give each AD a status matching the design log vocabulary (proposed or locked). Record the independent review that rule 4 requires, or downgrade [ADOPTED] to proposed until it happens.
  - Add a line to the spine saying every signal value comes from the locked-range table, and that most rows are proposed or provisional.

### F4 (High): Golden-file keys conflict with the cross-platform fallback; sign-off for new golden files is not stated

- **Source:** CLAUDE.md "Golden files change only after a human listening sign-off"; plan MVP "Done when" (all four starter renders have golden files, with Reaper and RX sign-off).
- **Conflict:** AD-15 keys a golden file by recipe hash, engine version, and sample rate, and requires a byte-for-byte match. AD-9 allows a component that cannot be bit-exact to fall back to a -100 dBFS cross-platform tolerance. If any fallback is used, the ARM render cannot byte-match the x86 golden file. CI then fails permanently, or someone loosens the comparison without a log entry, which rule 6 forbids.
- **Gap:** AD-15 covers a code change that alters an existing golden file. It does not say that creating a golden file (first approval, a new recipe, or the new 44.1 kHz set) also needs a listening sign-off. It also does not name Reaper and RX checks or the listening checklist (plan item 6, design log (a) roughness check).
- **Fix:**
  - Key golden files by platform as well, or state that the cross-platform check compares against the reference at -100 dBFS while byte identity holds per platform. Make AD-15 and AD-9 say the same thing.
  - Extend AD-15: "A golden file is created or replaced only after Audio's listening sign-off (Reaper, RX, listening checklist), recorded beside the file."

### F5 (Medium): The stereo-linked limiter couples the two ears, including the binaural path

- **Source:** CLAUDE.md "It must reach the output on its own dichotic path"; plan threshold of 60 dB isolation after the master chain.
- **Spine:** AD-4 puts the binaural pair through a "stereo-linked limiter" after it joins the bus. No signal crosses channels, so isolation can pass. But linked gain reduction lets one ear's level, and the in-file theta reference AM, change the gain on both binaural carriers. Whenever the limiter engages, this can:
  - impose theta-rate amplitude modulation on the binaural carriers
  - create side frequencies the spacing check does not model
  - move gamma envelope peaks
- **Fix:**
  - State that at the stored loudness gain (AD-13), the limiter is a safety stage that should not engage.
  - Add an assertion that limiter gain reduction stays at 0 dB, or under a logged small bound, for every starter render.
  - Log the limiter design (linked or per-channel, attack and release) in the design log.

### F6 (Medium): Workflow rules are not carried into the spine

- **Source:** CLAUDE.md rule 6 and Tests/Workflow; plan item 2.
- **Spine:** The Conventions table has "Branches and commits." It omits:
  - Tests before code: failing tests written from acceptance criteria first, by a fresh-context QA agent.
  - Never weaken a threshold to make a test pass; propose the change with a reason.
  - Do not commit with failing tests; run the fast tests after every change.
  - Golden files change only after sign-off (see F4).
  - Log changed defaults in the design log. This is only implied by "each row citing a design log entry."
- **Fix:** Add a "Workflow" convention row stating these five rules. Build agents read the spine as their substrate.

### F7 (Medium): Orbit and the 3D renderer have no limits on the gamma layer

- **Source:** CLAUDE.md rule 2 (every rate is variable with locked safe ranges); rule 3; frequency accuracy (0.01 Hz) and coupling timing (2 ms) thresholds.
- **Spine:** AD-8 moves the gamma PAC layer as a 3D object. AD-6 gives a deferred locked range for stem motion only. Orbit motion of gamma has no range and no constraint, although motion can:
  - create periodic level changes at entrainment rates
  - add Doppler shift, which breaks the 0.01 Hz frequency-accuracy test
  - add per-ear delay (ITD up to about 0.7 ms), which eats into the 2 ms coupling-timing budget
- **Fix:**
  - Add to AD-8: no Doppler or pitch change; Orbit motion rate in a locked range traced to the design log (listening-modes.md cites Sudre et al., 2024 for Relax).
  - Run the coupling timing and spacing checks per ear after the 3D stage.
  - List the Orbit range in Deferred next to the stem motion range.

### F8 (Low): Claims ban and clean-room rules are only partly carried

- **Source:** CLAUDE.md Never (no health, therapy, treatment, or neurostimulation claims in UI or store copy; no session arcs modeled on banned third-party programs); plan IP rules 2 and 4.
- **Spine:**
  - The Terms convention covers banned names and em dashes with a CI check, but not the outcome-claims ban. The app UI, visualizer, and store copy are in scope.
  - Deferred mentions the PRD Q9 patent check only for Tone-to-Core sync. The pre-launch freedom-to-operate review (Brain.fm and Endel families) is not listed, although the PAC layer, AD-8 3D motion, and the memlog's "Endel-like" UI direction are the areas closest to that risk.
  - The session-arc origin rule is not mentioned, though the designer authors arcs.
- **Fix:**
  - Extend the Terms row: no health, therapy, treatment, or neurostimulation claims in UI or store copy, checked in CI.
  - Add "Freedom-to-operate review before Phase 3 store release (plan IP rule 4)" to Deferred.
  - Add one line to the designer row: arcs are designed from scratch (plan IP section).

### F9 (Low): Naming convention example and coverage

- **Source:** CLAUDE.md rule 5.
- **Spine:** The convention gives only a binaural example. Its 250/256 Hz pair is the one design log (i) shows breaking the spacing rule next to gamma, so as a model it could be copied into a recipe that fails. There is also no AM example.
- **Fix:**
  - Add an AM example: "450 Hz carrier, AM at 6 Hz (theta reference)".
  - Optionally use a pair that passes spacing, such as the Sleep pair: "binaural, 100 Hz left, 103 Hz right, 3 Hz beat rate".

### F10 (Low): Binaural "two steady sines" vs swept beat

- **Source:** CLAUDE.md "two steady sines"; listening-modes Sleep and design log (i): beat sweeping 3 Hz to 0 on a 100 Hz carrier.
- **Spine:** AD-4 says "two oscillators," which is correct for a sweep. The CLAUDE.md wording ("steady") and the Sleep starter conflict. The spine does not cause this, but it should say which one holds so the frequency-accuracy test knows how to treat a swept carrier.
- **Fix:** Add one line saying the binaural carriers are pure sines whose frequencies may follow a recipe curve. Ask Audio to align the CLAUDE.md wording.

## Items checked and consistent

- Binaural never enters spatial, HRTF, reverb, width, or channel-mixing stages: AD-4 and AD-8, and the Signal flow diagram, match CLAUDE.md.
- Gamma couples only to the theta reference and never to a binaural beat: AD-5 matches.
- The theta reference is in-file and stays out of the 3D stage: AD-8 and the diagram match.
- Seeded randomness only: AD-14 matches rule 1.
- The engine core is plain C++ with no framework: AD-1 and Stack match.
- Python reference independent, at -100 dBFS: AD-16 matches the plan threshold.
- v0.1 scope is desktop only, with designer, app, stems, Orbit, and accounts out: Deployment and Deferred match. The exception is AD-10's 44.1 kHz addition (F3).
- Open design-log items are not treated as settled: theta rate default and binaural carrier.
