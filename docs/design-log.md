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
| Theta rate, default | open (6 Hz or slower) | open | project plan, Open decisions |
| Binaural layer on by default | open | open | project plan, Open decisions |
| Binaural carrier | open (200/206 Hz or higher, listener-adjustable) | open | project plan, Open decisions |
| Binaural locked ranges | carriers below 1000 Hz, difference under about 35 Hz | in plan | 2026-10-21 |
| Carrier-to-rate ratio | at least 4 times | provisional | project plan, Test thresholds |
| Carrier spacing | at least 50 Hz, including side frequencies | provisional (placeholder) | project plan, Test thresholds |
| All other test thresholds | see project plan, Test thresholds (provisional) | provisional | project plan |

## Entries

### 2026-10-27 (c): Plan doc wording for the coupling assertion

- **Change:** `docs/project-plan.md`, Build and test workflow, signal assertion 3 says gamma depth "peaks at the in-file theta trough". It should say "peaks at the recipe's coupling phase", matching CLAUDE.md.
- **Why:** trough coupling in the brain is region- and task-specific. Stimulation evidence leans away from trough, and the sound phase does not map onto the brain phase.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, recommendation 4.
- **Status:** proposed. Apply the change when the PRD is written.

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
