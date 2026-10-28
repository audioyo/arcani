# Design Log

Every changed default, range, or test threshold gets an entry here, with its source or test result (CLAUDE.md, Workflow). Newest entries go at the top of the log.

**Status values:**
- **proposed:** recommended, not yet in force
- **locked:** independently reviewed and in force
- **superseded:** replaced by a later entry, which it names

Sources point to `docs/research-library.md`, a research run under `_bmad-output/planning-artifacts/research/`, or a test result.

## Current state

| Parameter | Value | Status | Entry |
| --- | --- | --- | --- |
| Gamma AM rate, default | 40 Hz | proposed | 2026-10-27 (a) |
| Gamma AM rate, locked range | 30 to 60 Hz | proposed | 2026-10-27 (a) |
| Coupling phase, definition | 0 to 360 degrees on the in-file theta reference envelope, 0 degrees at its maximum | proposed | 2026-10-27 (b) |
| Coupling phase, default | 0 degrees (peak), with an uncoupled option | proposed | 2026-10-27 (b) |
| Learn mode coupling phase | 0 degrees (peak), was trough | proposed | 2026-10-27 (d) |
| Theta rate, default | open (6 Hz or slower) | open | project plan, Open decisions |
| Binaural layer in v0.1 starter recipes | off in Focus, Learn, Relax; on in Sleep (100 Hz, beat rate cycling sinusoidally over 0 to 3 Hz every 60 s) | proposed | 2026-10-27 (i), (n) |
| Binaural carrier | open (200/206 Hz or higher), set per recipe; not listener-adjustable | open | project plan, Open decisions; 2026-10-27 (g) |
| Binaural locked ranges | carriers below 1000 Hz; beat rate below 30 Hz (perception limit about 35 Hz) | proposed | 2026-10-21; 2026-10-27 (f) |
| Carrier-to-rate ratio | at least 4 times | provisional | project plan, Test thresholds |
| Carrier spacing | at least 50 Hz per ear between components of different layers, including side frequencies | provisional (value is a placeholder) | project plan, Test thresholds; 2026-10-27 (e) |
| Gamma carrier range, theta carrier, levels | 200 to 500 Hz; 450 Hz; tones -36, master -16 LUFS-I | engineering defaults | 2026-10-27 (g) |
| v0.1 provisional ranges | theta rate 1 to 6 Hz; theta carrier 100 to 500 Hz; depth 0 to 100 percent; burst 50 ms fixed | provisional | 2026-10-27 (h) |
| Spectral component threshold (spacing rule) | within 40 dB of the layer's strongest line | provisional (placeholder) | 2026-10-27 (i) |
| Dropout threshold | more than 1 ms of all-zero samples where signal is expected | provisional | 2026-10-27 (i) |
| Determinism scope | bit-exact across PC, Android, and iOS for the whole engine; a component proven unable falls back to -100 dBFS | proposed | 2026-10-27 (j), supersedes (i) on this point |
| Sample rates | Core renders natively at 44.1 and 48 kHz, never resampled; stems use an engine-owned deterministic resampler | proposed | 2026-10-27 (j) |
| WAV output dither | none in v0.1 (24-bit rounding) | engineering default | 2026-10-27 (j) |
| Loudness gain | measured at export, stored in the recipe, same live and offline | proposed | 2026-10-27 (k) |
| Limiter at stored gain | stays idle; gain-reduction bound open | open | 2026-10-27 (k) |
| Visualizer | no more than 3 flashes per second; never pulses at theta, gamma, or beat rates; smoothing rate open | proposed | 2026-10-27 (k) |
| Tone zone time-varying rates (stem motion, effect LFOs, gates) | locked ranges required; values open | open | 2026-10-27 (k) |
| Seed policy | recipe seed for tooling and tests; fresh seed per play in consumer app, stored on device | proposed | 2026-10-27 (l) |
| v0.1 starter values | gamma PAC 250 Hz carrier, AM at 40 Hz; theta reference 450 Hz carrier; Learn 5.5 Hz; Relax 30 min, depth 25 percent; Sleep 45 min with 5 min fade, steady 2 Hz delta | provisional | 2026-10-27 (m), (n) |
| Looping max run time (v0.1) | Focus 45 min, Learn 20 min | engineering default | 2026-10-27 (m) |
| v0.1 starter loudness target | -36 LUFS-I | engineering default | 2026-10-27 (m) |
| All other test thresholds | see project plan, Test thresholds (provisional) | provisional | project plan |

## Entries

### 2026-10-27 (n): Sleep beat rate cycles, correcting the Lee et al. reading

- **Correction:** Lee et al. (2024) did not sweep the beat rate once from 3 Hz to 0 Hz. The right-ear carrier "continuously fluctuated between 100 and 103 Hz over a duration of one minute", so the beat rate cycled over 0 to 3 Hz every 60 s, played before sleep onset and in 20 minute windows after it. The waveform of the change is not stated, and the authors say pattern and form were not optimized. Entries (i) and (m), `docs/listening-modes.md`, the project plan, PRD FR-16, and the addendum carried the misreading; all are corrected.
- **Decision:** Sleep's binaural beat rate cycles over 0 to 3 Hz every 60 s for the session body, as a sinusoid. The range and cycle come from Lee et al.; the sinusoid shape and its start phase are engineering defaults. Supersedes the Sleep binaural sweep in entries (i) and (m).
- **Decision:** Sleep's theta reference holds a steady 2 Hz delta rate (450 Hz carrier, sine AM). Engineering default; no study sets it. Supersedes the 3 Hz to 1 Hz sweep in entry (m).
- **Unchanged:** 100 Hz left carrier; 45 min with a 5 min fade; no sound after the session ends. Arcani has no counterpart to Lee's post-onset windows (PRD non-goals).
- **Source:** research run `academic-lit-lee-2024-dynamic-binaural-beat-sweep-law-2026-10-27` (Lee et al. 2024, Sleep 47(10) zsae097; Thomas 2024 editorial, zsae190).
- **Decided by:** Audio, during the v0.1 spec session.
- **Status:** provisional.

### 2026-10-27 (m): v0.1 starter recipe values and loudness target

- **Decision:** the four v0.1 starters use these values. All are provisional; Phase 0 may change them, and affected golden files are re-approved by ear.
  - Gamma PAC layer (Focus, Learn, Relax): 250 Hz carrier, AM at 40 Hz. 40 Hz per entry (a). 250 Hz because the gamma response falls about 30% per octave of carrier (Ross et al., 2003); it passes the carrier rule at 40 and 60 Hz, and its 210 to 290 Hz side frequencies sit far from the 450 Hz theta reference.
  - Focus: 450 Hz carrier, sine AM at 6 Hz; gamma as 50 ms bursts at 0 degrees, depth 100 percent; 5 min ramp-in, then looping.
  - Learn: 450 Hz carrier, sine AM at 5.5 Hz (Roberts et al., 2018); gamma as a smooth swell at 0 degrees (entry (d)), depth 100 percent; 5 min ramp-in, then looping.
  - Relax: 450 Hz carrier, sine AM at 6 Hz, building over the first 10 min; gamma as a smooth swell at 0 degrees, depth 25 percent; 30 min (Jirakittayakorn and Wongsawat, 2017, ran 30 min sessions).
  - Sleep: 450 Hz carrier, sine AM on a delta rate curve from 3 Hz to 1 Hz; binaural 100 Hz left, 100 Hz plus beat rate right, beat rate 3 Hz to 0 Hz (Lee et al., 2024); 45 min, the last 5 min a fade to silence. The theta reference carrier must be at least 156 Hz to clear the binaural pair by 50 Hz.
  - Looping max run time: Focus 45 min, Learn 20 min, the top of each mode's length range in `docs/listening-modes.md`. Phase 0 sets the value from the WHO-ITU safe listening standard.
  - Loudness target: -36 LUFS-I for every v0.1 starter (tones level, entry (g)), so sign-off judges the tones at the level they will have in the product.
- **Engineering defaults (no study sets them):** Relax depth 25 percent, Sleep length and fade, Learn ramp-in, loop max run times, the 450 Hz theta reference carrier, -36 LUFS-I.
- **Assumed:** a sine theta reference envelope in every starter, and 100 percent gamma depth in Focus and Learn; `docs/listening-modes.md` names neither.
- **Open:** the law and timing of Sleep's two rate curves.
- **Source:** v0.1 spec session (`_bmad-output/specs/spec-arcani-v0-1/`); research library entries named above.
- **Decided by:** Audio, during the v0.1 spec session.
- **Status:** provisional.

### 2026-10-27 (l): Seed policy

- **Decision:** the CLI, tests, golden files, and designer audition and export use the recipe seed, so every check is reproducible. Consumer app builds draw a fresh seed for each play, so stem choices vary between listens. The play's seed stays on the device with the play record, so any play can be re-rendered exactly. It is never sent in analytics (FR-38). Internal app builds may pin a seed.
- **Note:** the Core zone draws no random values, so the entrainment signals are identical on every play; only Tone zone choices vary.
- **Source:** architecture step, spine AD-25.
- **Decided by:** Audio, during the architecture session.
- **Status:** proposed.

### 2026-10-27 (k): Loudness gain, limiter, visualizer, and Tone zone rates

- **Loudness gain:** the exporting tool (the CLI in v0.1, the designer from Phase 1) measures integrated loudness and stores the gain in the recipe with a hash of the loudness-relevant fields. Live and offline playback use the same gain. Resolves PRD Q6. Targets stay at the engineering defaults in entry (g).
- **Limiter:** at the stored gain, the master limiter must stay idle, so it never adds gain changes to the binaural pair. The allowed gain-reduction bound is open and is set from the v0.1 starter renders.
- **Visualizer (new scope, Phase 3):** no more than 3 flashes in any one second (WCAG 2.2, 2.3.1, research library Standards), and no flashing or pulsing at theta, gamma, or beat rates, so it never adds a visual flicker stimulus. Its smoothing rate is open.
- **Tone zone rates:** every time-varying Tone parameter (stem motion, effect LFOs, gates) needs a locked range so ambience cannot carry rhythm at entrainment rates. Values are open; set from research in Phase 1 or 2.
- **Source:** architecture step, spine AD-4, AD-6, AD-13, AD-18; reviewer gate.
- **Decided by:** Audio, during the architecture session.
- **Status:** proposed for the rules; open for the values.

### 2026-10-27 (j): Determinism scope, sample rates, and dither

- **Determinism:** the whole engine (Core, stem decoder, resampler, built-in effects, 3D renderer) targets identical samples on PC, Android, and iOS. Method: engine-owned math, 64-bit integer phase, strict compiler flags, and CI hash checks on x64 and ARM. A component the Phase 0 spike proves cannot be exact falls back to the -100 dBFS tolerance, logged here with the reason. Supersedes the determinism scope in entry (i). Resolves PRD Q5.
- **Sample rates:** the Core renders natively at 44.1 and 48 kHz and is never resampled. Stems whose rate differs from the output pass through an engine-owned deterministic resampler, since Opus decodes only at 48 kHz-family rates. Tests and golden files cover both rates. The plan's 48 kHz CLI default stays.
- **Dither:** v0.1 WAV output rounds to 24 bits with no dither. Engineering default, chosen so renders stay byte-identical; any later dither draws from a named seeded stream.
- **Source:** architecture step, spine AD-9, AD-10, AD-14; freshness review (Opus decode rates).
- **Decided by:** Audio, during the architecture session.
- **Status:** proposed. The bit-exact target needs the independent review in CLAUDE.md rule 4 before it locks.

### 2026-10-27 (i): Starter binaural choice, spacing component threshold, dropouts, determinism scope

- **Binaural in v0.1 starters:** off in Focus, Learn, and Relax; on in Sleep with a 100 Hz carrier and a beat sweeping 3 Hz to 0 (Lee et al., 2024). Relax keeps low-depth gamma, and gamma plus a 250/256 Hz binaural pair would break the spacing rule (256 Hz sits 4 Hz from gamma's 260 Hz side frequency). No starter runs gamma and binaural together.
- **Spectral component:** for the spacing rule, any spectral line within 40 dB of the layer's strongest line, including harmonics from bursts, envelope shapes, and non-sine carriers. Placeholder, confirmed in Phase 0 with the 50 Hz value.
- **Dropout:** more than 1 ms of all-zero samples in a channel where the recipe sets a non-zero level. Placeholder.
- **Determinism scope:** byte-identical on one platform and build; within -100 dBFS (the reference-match tolerance) across platforms as the provisional floor; a bit-exact synthesis core across platforms as the target, confirmed or dropped in the architecture step and Phase 0 spike.
- **Source:** PRD reviewer pass, 2026-10-27 (`review-architecture-readiness.md`, `review-rubric.md`).
- **Decided by:** Audio, during the PRD session.
- **Status:** provisional.

### 2026-10-27 (h): Provisional v0.1 ranges

- **Decision:** v0.1's validator uses these provisional ranges, spanning the values the starter recipes and their cited studies use. Phase 0 widens or locks each one.
  - Theta reference rate, including delta and rate curves: 1 to 6 Hz. Lee et al. (2024) 0 to 3 Hz sweep; Lega et al. (2016) 2.5 to 5 Hz; Roberts et al. (2018) 5.5 Hz; Jirakittayakorn and Wongsawat (2017) 6 Hz.
  - Theta reference carrier: 100 to 500 Hz. Chaieb et al. (2017) about 107 to 220 Hz; Orozco Perez et al. (2020) about 400 Hz; 450 Hz engineering default (entry (g)).
  - Coupling depth: 0 to 100 percent. Ross et al. (2003): the response scales with depth.
  - Burst width: 50 ms, fixed in v0.1. Alekseichuk et al. (2016).
- **Why:** v0.1 is Phase 0 part 1, so the validator and starter recipes need testable ranges before Phase 0 research finishes.
- **Decided by:** Audio, during the PRD session.
- **Status:** provisional.

### 2026-10-27 (g): Engineering defaults, and no listener binaural control

- **Decision:** the 200 to 500 Hz gamma PAC carrier range, the 450 Hz theta reference carrier, and the -36 (tones) and -16 (master) LUFS-I levels are engineering defaults, not science claims. They came from an earlier internal reference and private review feedback, which the clean-room rules do not accept as sources.
  - Supporting public context: lower carriers give larger gamma responses (Ross et al., 2003), and -16 LUFS is a common streaming convention (research library, Standards).
  - They stay until Phase 0 replaces or confirms them.
- **Decision:** listeners cannot change the binaural layer on or off or its carrier. The designer sets both per recipe. This closes the "listener-adjustable carrier" option in the plan's open decisions.
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed.

### 2026-10-27 (f): Binaural beat-rate limit is 30 Hz

- **Decision:** the binaural beat rate's locked range is below 30 Hz.
- **Why:** binaural beats are perceived with differences under about 35 Hz (Licklider et al., 1950, cited by López-Caballero and Escera, 2017). 30 Hz keeps a margin inside that limit.
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed.

### 2026-10-27 (e): Spacing rule applies between layers, per ear

- **Change:** the spacing rule compares spectral components of different layers in the same ear. A layer's own components (carrier and its modulation side frequencies) are exempt, and so is the binaural pair, whose carriers never share an ear.
- **Why:** read literally, the old wording rejected every recipe: a 300 Hz carrier modulated at 40 Hz has side frequencies at 260 and 340 Hz, and the binaural carriers sit a beat rate apart. The rule exists to stop unintended beating and roughness between layers, and to stop one layer from placing the other ear's binaural carrier in this ear.
- **Value:** 50 Hz is still a placeholder. A critical-band source, checked in Phase 0, may replace it with a frequency-dependent minimum.
- **Source:** PRD reconciliation, 2026-10-27; project plan, Signal architecture (carrier spacing rule).
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed. CLAUDE.md spacing rule wording updated to match, 2026-10-27.

### 2026-10-27 (d): Learn mode coupling phase changed from trough to peak

- **Change:** the Learn starter recipe's gamma PAC layer peaks at 0 degrees (theta reference peak) instead of the theta trough. `docs/listening-modes.md` is updated to match.
- **Why:** the Learn table predates the research run. Its trough rationale was Lega et al. (2016), brain recordings that are region-specific and biphasic in the hippocampus. The only coupled-stimulation evidence (tACS) favors peak, and sound phase does not map onto brain phase. Learn now follows the general default in entry (b) rather than being an exception.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, refs [13], [14], [17], [21], [23]; entry (b).
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed. Locks with entry (b) after independent review. The Phase 1 peak vs trough vs uncoupled comparison can revisit it.

### 2026-10-27 (c): Plan doc wording for the coupling assertion

- **Change:** `docs/project-plan.md`, Build and test workflow, signal assertion 3 says gamma depth "peaks at the in-file theta trough". It should say "peaks at the recipe's coupling phase", matching CLAUDE.md.
- **Why:** trough coupling in the brain is region- and task-specific. Stimulation evidence leans away from trough, and the sound phase does not map onto the brain phase.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, recommendation 4.
- **Status:** applied 2026-10-27 during the PRD session, in signal assertion 3, the Lessons table guard, and the Signal architecture automated-checks line.

### 2026-10-27 (b): Coupling phase definition and default

- **Decision:** the coupling phase is a recipe parameter from 0 to 360 degrees, defined on the in-file theta reference envelope, with 0 degrees at the envelope maximum.
  - Default: 0 degrees (peak).
  - Recipes can choose uncoupled gamma as a control.
  - The coupling timing test checks this phase in the sound, which is the only phase that is measurable and reproducible.
- **Evidence:**
  - **tACS studies:** peak-coupled gamma helped in some of them, and trough-coupled gamma was ineffective or impaired performance. But the direct peak vs trough contrast was not significant, and one peak-coupled study reduced accuracy.
  - **Brain recordings:** they show no single preferred phase.
  - **Sound:** no study has tested theta-gamma coupled sound.
  - **Delay:** cortical tracking of theta AM lags the sound by roughly 80 to 160 ms, and the lag varies by listener. So the sound phase is a design convention, not a brain target.
- **Confidence:** low to medium.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, refs [13] to [23].
- **Status:** proposed. Needs an independent review before it locks (CLAUDE.md rule 4). The Phase 1 EEG pilot (peak vs trough vs uncoupled sound, with each listener's delay measured) would make it evidence-based.
- **No claims:** no source supports an outcome claim for any coupling phase delivered by sound.

### 2026-10-27 (a): Gamma AM rate default and range

- **Decision:** default 40 Hz, locked range 30 to 60 Hz. Any rate in the range is valid.
  - Treat 60 to 80 Hz as a possible extended band later, only if auditory behavioral evidence appears.
  - With the 4 times carrier rule, a 60 Hz rate needs a carrier of at least 240 Hz.
- **Evidence:**
  - The human auditory steady-state response peaks in the 30 to 40 Hz region.
  - Individual peak rates measured 36 to 53 Hz, with a mean of about 42 to 46 Hz.
  - About 58 of 62 auditory gamma studies used 40 Hz. Data outside 40 Hz is sparse: 60 Hz mainly from one lab, and one study at 80 Hz.
  - Behavioral effects in healthy adults are inconsistent even at 40 Hz.
- **Confidence:** high for the response peak, low for behavioral relevance.
- **Listening check:** on carriers of a few hundred Hz, roughness peaks broadly at 20 to 50 Hz, so 40 Hz may sound rough. Add this to the starter recipe listening checklist.
- **Future feature:** a per-listener gamma rate within the range is supported (refs [5][6]). It is not a v0.1 default.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, refs [1] to [12].
- **Status:** proposed. Needs an independent review before it locks.

### 2026-10-21: Gaps check outcomes (baseline)

These are recorded from `docs/project-plan.md`, Gaps check. The design log started on 2026-10-27, so this is the earliest baseline entry.

- **Theta reference:** added as an in-file AM carrier, the only thing PAC couples to (Orozco Perez et al., 2020).
- **Binaural layer:** kept as an optional layer, with its default still open (Orozco Perez et al., 2020; López-Caballero and Escera, 2017).
- **Binaural locked ranges:** carriers below 1000 Hz and a difference under about 35 Hz (Licklider et al., 1950, as cited by López-Caballero and Escera). So a gamma-rate beat can never be binaural.
- **Carrier spacing rule and validator:** added, so that a theta reference sharing a carrier with the binaural layer cannot leak the other ear's tone.
- **Alamalhoda et al. (2025):** dropped as support for audio, because it used light flicker.
