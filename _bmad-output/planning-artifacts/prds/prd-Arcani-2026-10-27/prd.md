---
title: Arcani PRD
status: final
created: 2026-10-27
updated: 2026-10-27
---

# PRD: Arcani

## 0. Document Purpose

This PRD defines what Arcani must do across all five phases, with v0.1 as the first release. It is written for Audio (sole designer, producer, and tester) and for the BMAD agents downstream: architecture, epics and stories, and test design. Rigor is set for an internal tool; launch-grade detail (pricing, store copy, full analytics) is deferred to the phases that need it.

It builds on, and does not repeat:

- `docs/project-plan.md`: the project brief, including the provisional Test thresholds table that §5 references.
- `docs/research-library.md`: the evidence behind every signal choice.
- `docs/design-log.md`: the current state of every default and range.
- `research-comparables.md` in this folder: the comparable-app scan.

**Updated after the architecture step (2026-10-27):** FR-6, FR-15, FR-24, FR-27, FR-39 (new), the glossary, and §11 Q5 and Q6 reflect decisions in `_bmad-output/planning-artifacts/architecture/architecture-Arcani-2026-10-27/ARCHITECTURE-SPINE.md`. Where the two differ, the spine's AD IDs are cited.

Features are grouped, with FRs numbered globally (FR-1 to FR-N). Inferred items carry `[ASSUMPTION]` tags and are indexed in §12. Implementation detail (stack candidates, recipe file shape, stem metadata) lives in `addendum.md`.

## 1. Vision

Arcani is a procedural entrainment audio app. A designer authors sessions as small recipe files; a mobile app plays them. Every tone is synthesized live by one C++ engine, so what the designer hears while authoring is exactly what a listener hears on a phone, and the same recipe always renders the same audio.

The signal design is the product's spine. A theta reference that exists in the file gives the gamma PAC layer something real and measurable to couple to. An optional binaural layer runs on its own dichotic path that no spatial or width processing ever touches. Every rate and carrier is a recipe parameter with a locked, evidence-traced range, and every rule is enforced by an automated test rather than by memory.

Arcani describes the sound and how it was designed, not what it does to the listener. Comparable apps lean on multiplier and condition claims and do not document their signals (`research-comparables.md`). Arcani's position is the opposite: transparent, reproducible, honestly described audio.

## 2. Target User

### 2.1 Jobs To Be Done

**Audio, the designer (now):**
- Author a session by setting every signal parameter, hear it immediately, and trust that the phone will sound the same.
- Know, without listening, that a recipe is correct: isolated, coupled on time, spaced, exact, and click-free.
- Trace every default to a source, so the design can be shown to a research partner without anything needing explanation.

**Listeners (once the app ships):**
- Start a session for a moment of the day (working, after study, a break, bedtime) with almost no setup.
- Play it with the screen off, offline, for as long as the session runs, without it cutting out.
- Trust that the app does not overstate what the audio does.

### 2.2 Non-Users (v1)

- Clinicians or anyone seeking treatment. Arcani makes no health or outcome claims.
- Listeners who want to tweak signal parameters. Listener controls stay deliberately few (FR-31).
- Other sound designers, until after launch. The designer is built for Audio first.

### 2.3 Key User Journeys

- **UJ-1. Audio renders a starter recipe and signs it off (v0.1).** Audio edits the Focus recipe file, runs the command-line renderer, and gets a 48 kHz WAV in seconds plus a test report showing every signal assertion passing. Audio opens it in Reaper and RX, listens against the checklist, and approves it; the render becomes a golden file. **Edge case:** the validator rejects the recipe because the gamma PAC carrier is under 4 times the gamma rate, naming the parameter and the rule, and nothing is rendered.

- **UJ-2. Audio designs a Relax session and checks it on a real phone (Phase 1).** In the desktop designer, Audio lowers the theta rate, watches the per-ear spectrum and envelope update, auditions live, then pushes the recipe to an Android test phone on the same network and listens on earbuds. Satisfied, Audio publishes it; the guardrails run first and the publish succeeds. **Edge case:** Audio sets the binaural carrier within 50 Hz of the theta reference carrier; the designer warns before export and publishing is blocked.

- **UJ-3. Dana plays Sleep at night, offline (Phase 3).** Dana, a premium listener and a nurse winding down after a late shift, opens Arcani in bed with no network connection, picks Sleep, sets 45 minutes, and locks the phone. The session builds, plays with the screen off, and fades to silence; nothing plays after the session ends. **Edge case:** a phone call interrupts playback; the session pauses and resumes from the same point when the call ends. `[ASSUMPTION: resume after interruption, not restart]`

## 3. Glossary

Downstream documents use these terms exactly.

- **Carrier:** the audible tone of a signal, in Hz.
- **Rate:** how fast something repeats (a beat, pulse, or modulation), in Hz.
- **AM:** amplitude modulation; a carrier's volume shaped by a slower wave.
- **Engine clock:** the single sample-accurate timebase that drives every layer in a session.
- **Theta reference:** a carrier amplitude-modulated at the theta rate. It exists in the file, so its phase is measurable. It is the only thing PAC couples to. In Sleep its rate is a delta rate (below 4 Hz); the term still applies.
- **Gamma PAC layer:** a separate carrier, amplitude-modulated at the gamma rate, whose modulation depth follows the theta reference phase (computed from the engine clock) and peaks at the coupling phase.
- **Coupling phase:** where in each theta reference cycle the gamma modulation depth peaks; 0 to 360 degrees on the theta reference envelope, 0 degrees at its maximum. Per envelope shape, 0 degrees is: the peak (sine), the center of the on plateau (smoothed on-off), the top just before the drop (sawtooth), the top just after the rise (reverse saw), or the curve's maximum (custom). A recipe can also set gamma uncoupled.
- **Binaural layer:** two pure sines, one per ear, whose frequencies may follow a recipe rate curve; their difference is the beat rate. Dichotic only. The beat exists only in the listener's brain, so nothing couples to it.
- **Monaural beat / isochronic:** a rhythm that exists in the file.
- **PAC (here):** gamma PAC layer strength rising and falling with the theta reference.
- **Orbit layer:** working name for spatial motion applied to the gamma PAC layer only. Public name TBD.
- **Stem bed:** the musical and ambient background, played from audio files. Contains no entrainment signals.
- **Recipe:** a versioned data file that fully specifies a session: every layer's parameters, ramps, levels, length, engine version, and seed.
- **Mode:** a session family (Focus, Learn, Relax, Sleep). Each mode is one or more recipes.
- **Locked range:** the allowed span for a recipe parameter, traced to a source in the design log.
- **Validator:** the check that rejects a recipe breaking any locked range, the carrier rule, or the spacing rule.
- **Carrier rule:** every modulated carrier is at least 4 times its modulation rate.
- **Spectral component:** any spectral line of a layer within 40 dB of that layer's strongest line, counting harmonics from non-sine carriers, bursts, and envelope shapes. 40 dB is a placeholder, confirmed in Phase 0 with the 50 Hz spacing value.
- **Spacing rule:** in each ear, at least 50 Hz between any spectral component of one layer and any spectral component of another layer, counting modulation side frequencies. A layer's own components are exempt, and so is the binaural pair, whose carriers never share an ear. 50 Hz is a placeholder pending a critical-band source.
- **Golden file:** a render Audio has approved by ear; later renders of the same recipe must match it.
- **Engineering default:** a starting value chosen by engineering judgment, not by a study. Logged as such in the design log and never presented as a science claim.
- **Rate curve:** a scheduled change of a rate over the session, such as Sleep's cycling binaural beat rate.
- **Master chain:** the stages after the layers are mixed: master gain and the final limiter. It processes left and right without mixing them.
- **Synthesis core:** the engine parts that generate and mix tone layers (clock, oscillators, AM, ramps, master chain). Excludes stem decoding and Orbit spatialization.
- **Core zone:** the theta reference, gamma PAC layer, and binaural layer, with wiring fixed in the engine. Recipes set their parameters, never their routing.
- **Tone zone:** the stem bed plus built-in effects, routed freely per recipe. It never reads Core timing and never feeds the Core zone or the binaural path.
- **Designer:** the desktop authoring tool. **App:** the mobile listener app. **Engine:** the shared C++ DSP core both use.
- **Gate:** the pass condition that ends a phase (§8).

## 4. Features

### 4.1 Engine core and signal layers

**Description:** One engine clock drives every layer. The engine synthesizes the theta reference, the gamma PAC layer, and the binaural layer live, applies per-layer gain ramps, and passes the result through a final limiter. The binaural layer reaches the output on its own dichotic path. The engine is plain C++ with no framework dependency, so it can sit under the designer and both mobile apps. Realizes UJ-1, UJ-2, UJ-3.

#### FR-1: Single engine clock
The engine derives every rate and phase in a session from one engine clock.
- Theta reference phase error stays under 1 ms after an 8-hour render.
- Every carrier and rate is within 0.01 Hz of its recipe value. For a rate curve, the instantaneous rate is within 0.01 Hz of the scheduled curve at every point, and phase stays continuous through the sweep.

#### FR-2: Theta reference
The engine generates a carrier amplitude-modulated at the theta rate with a selectable envelope shape (sine, smoothed on-off, sawtooth, reverse saw, custom curve).
- Carrier, theta rate, and envelope shape come from the recipe; none is hard-coded.
- Hard-edged envelope shapes are edge-smoothed so no click exceeds the threshold in §5.

#### FR-3: Gamma PAC layer
The engine generates a separate carrier amplitude-modulated at the gamma rate, with modulation depth that follows the theta reference phase and peaks at the coupling phase, as a smooth swell or as short bursts per theta reference cycle.
- Each gamma envelope peak lands within 2 ms of its target coupling phase on the in-file theta reference.
- An uncoupled setting produces gamma AM at constant depth.
- The validator rejects a coupled gamma PAC layer when the recipe has no theta reference. The recipe has no field for choosing a different coupling target.
- Changing the binaural beat rate in a recipe leaves every gamma envelope peak time unchanged (tested).
- Carrier waveform selectable: sine, triangle, softened square.

#### FR-4: Binaural layer on an isolated path
The engine generates two pure sines, one per ear, whose frequencies may follow a recipe rate curve, and routes them to the output on a dichotic path that bypasses every spatial, HRTF, ambisonic, reverb, and stereo-width stage.
- The binaural layer joins the mix after every spatial, reverb, and width stage; only the master chain follows it.
- In each ear, the other ear's binaural carrier is at least 90 dB below its own at the engine output and at least 60 dB below after the master chain. Measured by rendering with one ear's binaural oscillator muted and measuring that carrier in the other channel, so the test works at any beat rate, including 0 Hz.
- The engine never sums or downmixes its output channels, on any device or output.
- Non-sine binaural waveforms are allowed only with a validator warning.
- Nothing couples to the binaural layer.

#### FR-5: Gain ramps, levels, and limiter
The engine applies per-layer gain ramps from the recipe and a final limiter that meets the recipe's loudness target.
- No layer or master gain ramp completes in under 10 ms. Modulation envelopes (theta, gamma, bursts) and the limiter's gain reduction are exempt; the click and true-peak tests cover them.
- Integrated loudness within 1 LU of target; true peak at or below -1 dBTP.

#### FR-6: Deterministic synthesis
Same recipe, engine version, seed, and sample rate produce byte-identical output on the same platform and build. No unseeded randomness anywhere in the engine, including the stem sequencer (FR-24), and output does not depend on the audio buffer size.
- Across platforms (PC, Android, iOS), renders match within the reference tolerance (-100 dBFS). This is the provisional floor.
- Decided in the architecture step: the whole engine (synthesis core, stem decoder, resampler, built-in effects, 3D renderer) is bit-exact across platforms. A component the Phase 0 spike proves cannot be exact falls back to the -100 dBFS floor, logged in the design log (spine AD-9; design log 2026-10-27 (j)).
- The engine renders natively at 44.1 and 48 kHz; byte identity holds per sample rate (spine AD-10).

**Notes:** Current proposed values: gamma rate default 40 Hz, locked range 30 to 60 Hz; coupling phase default 0 degrees (peak). Theta rate default is open. All are in the design log and need independent review before they lock (§11).

**Honesty note:** the PAC layer is designed so its coupling is exact and measurable in the sound. Whether coupled sound produces coupling in a listener's brain is untested; no FR or copy may imply it does.

### 4.2 Recipes and validation

**Description:** Recipes are small versioned data files that fully define a session. The validator is the single gate every recipe passes before it can be rendered, exported, or published. Realizes UJ-1, UJ-2.

#### FR-7: Recipe file
Audio can define a full session in one recipe file: every layer's parameters, ramps over time, levels, total length, engine version, seed, author, date, and the reason for its values.
- Every signal is named in the recipe by carrier frequency, modulation type, and modulation rate.
- A recipe can mark the session as looping. The ramp-in plays once; after it, the session body repeats until stopped, with no click at the seam and no jump in theta reference or gamma PAC phase. A looping recipe must set a maximum run time.

#### FR-8: Locked ranges
The validator rejects any parameter outside its locked range, and each locked range traces to a design log entry.
v0.1 uses these provisional ranges (design log 2026-10-27 (h)). Phase 0 widens or locks each one.

| Parameter | v0.1 range | Basis |
| --- | --- | --- |
| Theta reference rate (including delta, and along rate curves) | 1 to 6 Hz | Span of the cited studies: Lee et al. 2024 (0 to 3 Hz beat range), Lega et al. 2016 (2.5 to 5 Hz), Roberts et al. 2018 (5.5 Hz), Jirakittayakorn and Wongsawat 2017 (6 Hz) |
| Theta reference carrier | 100 to 500 Hz | Chaieb et al. 2017 (about 107 to 220 Hz), Orozco Perez et al. 2020 (about 400 Hz); 450 Hz engineering default |
| Gamma rate | 30 to 60 Hz | Design log 2026-10-27 (a) |
| Gamma PAC carrier | 200 to 500 Hz | Engineering default; the carrier rule raises the floor to 4 times the gamma rate (240 Hz at 60 Hz) |
| Coupling phase | 0 to 360 degrees, or uncoupled | Design log 2026-10-27 (b) |
| Coupling depth | 0 to 100 percent | Ross et al. 2003 (response scales with depth) |
| Burst width | 50 ms, fixed in v0.1 | Alekseichuk et al. 2016 |
| Binaural carriers | below 1000 Hz | Licklider et al. 1950, cited by López-Caballero and Escera 2017 |
| Binaural beat rate | 0 to below 30 Hz | Design log 2026-10-27 (f) |

#### FR-9: Carrier rule and spacing rule
The validator rejects any recipe where a modulated carrier is under 4 times its modulation rate, or where the spacing rule fails in either ear at any point in the session, including during rate curves.

#### FR-10: Clear rejection
When the validator rejects a recipe, it names the parameter, the value, the rule, and the limit, and produces no output.

### 4.3 Renderers

**Description:** A headless command-line renderer turns any recipe into a WAV, so every rule can be tested without ears. A Python reference renderer generates every layer the obviously correct way, so engine bugs show up as numbers. Realizes UJ-1.

#### FR-11: Command-line renderer
Audio or an agent can render a recipe to a 48 kHz, 24-bit WAV from the command line.
- Renders at least 20 times faster than real time on the development PC.
- Writes a machine-readable report of every signal assertion (§4.4) alongside the WAV.

#### FR-12: Python reference renderer
A Python reference renderer produces every layer and the master chain that v0.1 renders, from the same recipe, in double precision.
- Engine and reference differ by less than -100 dBFS, sample by sample.

### 4.4 Automated signal test suite

**Description:** Every render is checked automatically. Tests are written from acceptance criteria before code, by a QA agent with fresh context, so the agent writing the code never grades its own work. Thresholds are the provisional ones in the plan's Test thresholds table; changing one needs a logged reason, never a weakened test. Realizes UJ-1, UJ-2.

#### FR-13: Signal assertions on every render
The suite checks every render for: binaural isolation, coupling timing, envelope shape matching the recipe, carrier rule and spacing rule, frequency accuracy, 8-hour drift, reference match, determinism, clicks, dropouts, NaN or infinite values, gain ramps, loudness and true peak, hearing-safety level ceiling, and render speed.
- Pass conditions not in the plan's table: envelope shape passes through the reference match; NaN or infinite values have zero tolerance; a dropout is any run of all-zero samples longer than 1 ms in a channel where the recipe sets a non-zero level (provisional, design log 2026-10-27 (i)); in v0.1 the hearing-safety check is the true-peak and loudness targets, and the listener-level ceiling moves to Phase 3 with the device.
- v0.1 includes test recipes beyond the starters: binaural on at several beat rates including 0 Hz and a sweep, and coupled gamma with binaural on at a different beat rate, all with values that pass the spacing rule.

#### FR-14: Golden files
A render Audio approves by ear becomes a golden file; any change that alters it fails until Audio re-approves after listening.

#### FR-15: Local and CI runs
Fast tests run after every change locally and on every push in CI. The full suite (8-hour drift, full-length starters, both sample rates) runs on every pull request into main and nightly. A failure in either blocks merge (spine AD-17).

### 4.5 Starter recipes

**Description:** Four starter recipes, one per mode, built from the closest published evidence (`docs/listening-modes.md`). Each describes the sound, never an outcome. Realizes UJ-1.

#### FR-16: Four starter recipes
v0.1 ships Focus, Learn, Relax, and Sleep recipes that pass every assertion and the validator.
- Focus and Learn are looping recipes (`docs/listening-modes.md`).
- Binaural layer: off in Focus, Learn, and Relax; on in Sleep (100 Hz carrier, beat rate cycling over 0 to 3 Hz every 60 s; Lee et al. 2024). Relax keeps its low-depth gamma PAC layer, so no starter recipe runs gamma and binaural together.
- Sleep fades to silence at its end; no rhythmic signal plays after the session ends.
- Each recipe's values are logged in the design log with sources.
- Each recipe carries a plain description of when to use it, what the sound is, and how strong its evidence is, matching `docs/listening-modes.md`.

#### FR-17: Listening checklist and sign-off
A written listening checklist exists in the repo, and every new or changed recipe needs Audio's recorded sign-off against it before it becomes a golden file or is published.
- The checklist covers at least: clicks and seams, roughness of 40 Hz gamma AM, comfort over the full session length, carrier audibility on earbuds, and loudness.
- v0.1 golden files are provisional: if Phase 0 changes a threshold or default, the affected renders are re-approved by ear.

### 4.6 Session designer (Phase 1)

**Description:** A desktop tool that runs the same engine as the app. Audio sets any parameter with plain labels, sees the signal, auditions live, and publishes. Realizes UJ-2.

#### FR-18: Full parameter control
Audio can set every recipe parameter in the designer, inside its locked range, and draw ramp and rate curves over the session.
- Every control uses a plain label with its unit, and names signals by carrier, modulation type, and rate.
- One usability session with someone who is not an engineer runs before the Phase 1 gate.

#### FR-19: Signal views
The designer shows the waveform, the spectrum, and a per-ear view of the current recipe, updating as parameters change.

#### FR-20: Live audition
Audio can audition the recipe live through the shared engine; the audition sounds identical to a render.

#### FR-21: Warnings before unsafe or meaningless settings
The designer warns before a setting that would fail the validator or is flagged (for example, a sawtooth carrier), and blocks export of any failing recipe.

#### FR-22: Push to device
Audio can stream a recipe to a test phone on the same network and hear it on real earbuds before publishing.

#### FR-23: Publish
Audio can publish a recipe or stem pack to the content server. Publishing runs the validator, level ceilings, and isolation test first, and requires Audio's listening sign-off (FR-17). It refuses on any failure.

### 4.7 Stem bed (Phase 1)

**Description:** The musical and ambient bed, which forms the Tone zone. Stems are audio files; no entrainment signal lives in them. AI stems are generated offline and curated by ear first; human stems join the same library later without code changes. The Tone zone sets each track's character, while the Core zone does the entrainment work. Details in `addendum.md`.

#### FR-24: Stem sequencer
The engine picks stems per slot by metadata (role, key, tempo, mode fit, energy), seeded, so the same recipe and seed pick the same stems.
- Playback is gapless at loop points.
- Sessions evolve with no audible seams (Phase 1 gate).
- A pink or white noise option is available in the stem bed for any mode.
- Audio can route stems through a free-form chain of built-in effects per recipe. Third-party plugins are applied offline and printed into the stem file; they never run at playback (spine AD-7).
- No Tone zone parameter that varies over time (stem motion, effect LFOs, gates) runs outside its locked range, so the stem bed carries no rhythm at entrainment rates (spine AD-6).
- Tooling and tests use the recipe seed. The consumer app draws a fresh seed for each play and keeps it on the device, so stem choices vary between listens and any play can be reproduced (spine AD-25).

#### FR-25: Carrier notching
The stem bed is notch-filtered at every active carrier, so no stem masks a carrier.

#### FR-26: Stem curation and provenance
Every stem carries source (AI or human), tool or artist, date, and license, and passes a curation checklist (no loop clicks, no key drift, no carrier masking, loudness on target) before entering the library.

### 4.8 Orbit layer (Phase 2)

**Description:** 3D placement and motion, rendered by the engine. The gamma PAC layer and stems can move; the theta reference and binaural layer never do.

#### FR-27: Orbit layer and 3D stems
The engine can move the gamma PAC layer along a path (arc, full orbit, figure-eight, drift) with set period, width, depth, elevation, and anchor mix. Stems can be placed in 3D, static or moving, per recipe. The theta reference and binaural layer never move.
- The isolation test (FR-4) still passes with the Orbit layer and moving stems active.
- 3D rendering happens inside the engine, which outputs plain stereo. The app never relies on Dolby Atmos or a device spatializer, since those process the binaural pair (spine AD-8).
- Motion adds no Doppler or pitch shift. No head tracking in v1.

#### FR-28: Orbit A/B test
A blind A/B of static versus moving gamma PAC layer at the same settings decides whether motion stays (Phase 2 gate).

### 4.9 Mobile app (Phases 3 and 4)

**Description:** Android first, then iOS, both on the shared engine. Playback only. Realizes UJ-3.

#### FR-29: Mode playback
A listener can pick a mode and start a session in no more than two taps from launch. `[ASSUMPTION]`
- A looping session keeps playing until the listener stops it or a timer ends. Every looping session has a maximum run time set in the recipe. `[ASSUMPTION: value set in Phase 0 against the WHO-ITU exposure guidance]`

#### FR-30: Background and screen-off playback
A session plays to its end with the screen off and the app in the background.
- Holds a full session on Android (Phase 0 gate), including a looping session up to its maximum run time, checked on a real phone, since emulators cannot verify background playback or battery.
- Pauses on calls or other audio interruptions and resumes from the same point. `[ASSUMPTION]`

#### FR-31: Listener controls
A listener can set session length, intensity, and Orbit motion on or off, each inside ranges the designer locks in the recipe. A listener cannot turn the binaural layer on or off, or change its carrier or any rate; those come from the recipe.
- `[ASSUMPTION: intensity scales the tone layers' gain within the recipe's locked range; it does not change modulation depth]`

#### FR-32: Offline playback
Downloaded sessions play with no connection. Stems are stored encrypted, with keys tied to account and device.

#### FR-33: Content updates without app release
The app checks a versioned content manifest and downloads new recipes and stem packs without an app store update.

#### FR-34: Spatial-audio guidance
The app tells the listener to turn off phone or headphone spatial-audio features for sessions with a binaural layer, and opts out of them where the platform allows. `[ASSUMPTION: opt-out feasibility is unresearched]`

#### FR-35: Cross-platform identity
The iOS engine renders the same recipe identically to the Android engine (Phase 3 gate).

#### FR-39: Visualizer
The app shows a simple, calm visualizer during a session. It looks the same on Android and iOS.
- Motion is slow and follows the session arc. It never flashes or pulses at theta, gamma, or beat rates, and never flashes more than 3 times in any one second (WCAG 2.2, 2.3.1; spine AD-18).
- It stops drawing when the screen is off.

### 4.10 Accounts, monetization, analytics (Phases 3 and 4)

#### FR-36: Sign-in
Listeners sign in with Google, and with Apple on iOS.

#### FR-37: Freemium
The free tier offers the core modes at standard settings. Premium unlocks the full recipe library, longer sessions, the Orbit layer, artist and human-made packs, and offline downloads. Pricing and trial length are TBD.

#### FR-38: Anonymous analytics
Usage is counted by random install ID only, with no names, emails, or session content tied to a person, and the listener can opt out in settings.

## 5. Cross-Cutting NFRs

Numbers are the provisional thresholds from the plan's Test thresholds table. Phase 0 confirms or adjusts each, with the reason logged in the design log.

| NFR | Requirement |
| --- | --- |
| Determinism | Byte-identical for the same recipe, engine version, seed, and sample rate on one platform and build; within -100 dBFS across platforms (provisional floor); bit-exact synthesis core across platforms (target) |
| Accuracy | Carriers and rates within 0.01 Hz, including along rate curves; theta reference drift under 1 ms over an 8-hour render (an engine endurance test, not a session length) |
| Isolation | Binaural cross-ear leakage at least 90 dB down at engine output, 60 dB after the master chain |
| Coupling | Gamma envelope peaks within 2 ms of the coupling phase |
| Reference match | Engine versus Python reference below -100 dBFS sample by sample |
| Clicks | No discontinuity above -60 dBFS in an 8 kHz high-pass at seams, ramp edges, and burst edges |
| Ramps | No layer or master gain ramp faster than 10 ms |
| Loudness | Within 1 LU of target; true peak at or below -1 dBTP; tones -36, master -16 LUFS-I as engineering defaults |
| Hearing safety | v0.1: true peak and loudness targets on every render. Phase 3: listener output never exceeds a level ceiling `[ASSUMPTION: value set from the WHO-ITU safe listening standard]`; no sudden loud events |
| Speed | At least 20 times real time on the development PC |
| Battery | A full session at maximum length on a mid-range Android phone uses no more than a set battery share `[ASSUMPTION: value set in Phase 0]` |
| Reach | Lowest Android and iOS versions the stack supports well, set in Phase 0 from device-share data |

## 6. Constraints and Guardrails

**Claims.** UI and store copy describe the sound and how it was designed. No health, therapy, treatment, or "neurostimulation" language, no outcome promises, no condition names. Wording follows the FDA general wellness guidance (January 2026).

**Clean room.** Arcani derives its own designs from public research and similar public standards, aiming for a product that could be shown to any research partner with nothing to explain away. It never copies any third-party program's names, recipes, recordings, scripts, levels, or session arcs, and it never uses anything learned through private channels. Session arcs are designed from scratch. Specifics are in the project plan's IP and clean-room rules.

**Naming.** Avoid comparables' feature names, including Spatial Orbit, Dynamic Focus, Hibernation, and "neural effect" (`research-comparables.md`).

**Science first.** Every default and locked range traces to a published, peer-reviewed source, to a logged in-house listening test, or is declared an engineering default, and is recorded in the design log. The design log keeps an evidence register: for each cited study, its modality (audio, light, electrical), sample size, and actual finding. Every changed default or threshold gets a design log entry. Unsure means research before building. Signal architecture, defaults, and the stack get an independent review before they lock.

**Hearing safety.** Level ceilings, no sudden loud events, a maximum run time for looping sessions, and guidance aligned with the WHO-ITU safe listening standard. Mild headache, dizziness, and tinnitus were common in long-term 40 Hz studies, so in-app guidance tells listeners to stop if the sound is uncomfortable, in descriptive, non-medical wording.

**Patents.** A freedom-to-operate review on active modulated-audio patent families is required before launch (Phase 2 gate).

**Wording.** No em dashes in docs, comments, or UI copy, and every signal is named by carrier, modulation type, and rate. CI checks docs and UI strings for banned terms and em dashes; research files are exempt when citing sources.

**No summing.** Arcani never sums or downmixes its own output to mono. Every session is stereo, and the dichotic path stays dichotic to the output.

**Privacy.** Analytics are anonymous only (FR-38).

## 7. Non-Goals

- Not a medical, therapeutic, or clinical product, and no outcome claims.
- No listener-side signal editing; listeners never touch rates, carriers, or the binaural layer.
- No closed-loop or EEG-driven playback, and no sound after sleep onset detection.
- No voice guidance or scripted journeys in this PRD.
- No speaker or mono playback variants, and no headphone detection, for now. Listeners with hearing in one ear and speaker playback are a small group; support is low lift and can be added later.
- No social features or user-generated recipes.
- No coupling to a binaural beat, ever.

## 8. Release Phases and Gates

Each phase ships only after its gate passes. No dates until the Phase 0 spike shows the stack cost.

| Phase | Contents | Gate |
| --- | --- | --- |
| **Phase 0: Foundations**, part 1: **v0.1** (first release, desktop only) | Engine core (FR-1 to FR-6), recipes and validator (FR-7 to FR-10), command-line and Python reference renderers (FR-11, FR-12), test harness and full suite locally and in CI (FR-13 to FR-15), four starter recipes (FR-16, FR-17), design log traced; Phase 0 research confirms thresholds and locked ranges | Every test passes in CI; four provisional golden files; Audio signs off each render in Reaper and RX |
| **Phase 0: Foundations**, part 2: stack spike | Framework confirmed by the architecture step; background playback with screen off and battery check on a real Android phone | Background audio holds a full session on Android; isolation test passes on device |
| **Phase 1: Procedural core** | Designer (FR-18 to FR-23), stem bed with curated AI stems (FR-24 to FR-26), modes refined by listening, peak versus trough versus uncoupled comparison | Blind listening tests pass; sessions evolve with no audible seams; designer usability session held |
| **Phase 2: Spatial** | Orbit layer (FR-27, FR-28). Isochronic-only speaker modes and headphone detection deferred (§7) | A/B result supports keeping motion; freedom-to-operate review cleared |
| **Phase 3: Android release** | Mobile app (FR-29 to FR-34, FR-39), accounts and freemium (FR-36 to FR-38); closed beta, then Play Store with outcome-free copy; first human stems | Stable Android release; iOS test build matches Android DSP output (FR-35) |
| **Phase 4: iOS release** | App Store launch from the shared engine | Stable iOS release |

**Out of scope for v0.1:** designer, mobile apps, stem bed, Orbit layer, accounts, analytics, payments, content server, encryption.

**Later (post-launch):** adaptive inputs, a per-listener gamma rate within the locked range, artist packs, a design-log summary to share with a prospective research partner.

## 9. Success Checkpoints

Success is gate-based. Listener-side metrics are too far off to define and will be set before Phase 3.

- **SC-1:** v0.1 gate passed (§8). Validates FR-1 to FR-17.
- **SC-2:** Audio has used each starter mode for N sessions with no rendering fault, seam, or click heard. `[ASSUMPTION: N set by Audio before the Phase 1 gate]` Validates FR-16, FR-24.
- **SC-3:** Each later phase gate passed in order.
- **SC-C1 (counter):** do not chase subjective "it works on me" impressions as evidence of effect. Personal use checks the sound, not outcomes. Counterbalances SC-2.
- **SC-C2 (counter):** do not trade test thresholds for render speed or battery. Counterbalances the Speed and Battery NFRs.

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Spatial processing leaks into the binaural path in our own graph | Isolation test in CI on every build (FR-4) |
| Phone or headphone spatial-audio remixes the ears after our output | Device testing with features on; listener guidance; opt-out where possible (FR-34) |
| Mobile OS stops background audio | Proven in the Phase 0 spike (FR-30) |
| Long sessions drift or click | Engine clock precision; 8-hour render tests (FR-1) |
| Health claims trigger store rejection | Describe-the-sound copy only (§6) |
| Active third-party patents | Freedom-to-operate review before launch |
| Hearing exposure over long sessions | Level ceiling, looping run-time cap, and safe-listening guidance (§6) |
| Discomfort from gamma-rate AM over long sessions (no comfort data found) | Comfort on the listening checklist (FR-17); stop-if-uncomfortable guidance (§6) |
| Listeners on speakers or with the phone's mono setting lose the binaural layer | Accepted for now (§7); in-file layers still play |

## 11. Open Questions

Each question names the gate it blocks.

1. Theta rate default beyond the starter values: 6 Hz or slower (2.5 to 5 Hz). Blocks the Phase 1 gate.
2. Binaural carrier for Relax if its binaural layer is turned on later (200/206 Hz or higher); Sleep uses 100 Hz. Blocks the Phase 1 gate.
3. Final locked ranges, the minimum spacing value (50 Hz placeholder), and the spectral component threshold (40 dB placeholder), from Phase 0 research; a critical-band source may make spacing frequency-dependent. Blocks the end of Phase 0.
4. Gamma rate 40 Hz default and coupling phase 0 degrees default: independent review before lock. Blocks the end of Phase 0.
5. Resolved in the architecture step: the whole engine targets bit-exact output across platforms, with a logged -100 dBFS fallback per component (FR-6, spine AD-9).
6. Resolved in the architecture step: loudness gain is measured at export and stored in the recipe, the same live and offline (spine AD-13, design log 2026-10-27 (k)).
7. Public name for the Orbit layer. Blocks the Phase 3 gate.
8. Minimum OS versions, pricing, trial length, safety and wellness messaging, first-run headphone check. Blocks the Phase 3 gate.
9. Whether a stem-bed modulation option for Focus is used, pending a patent check on the published method. Blocks the Phase 1 gate.
10. Whether a sham-controlled EEG pilot of peak versus trough versus uncoupled sound is run in Phase 1. If it runs, it measures each listener's sound-to-cortex delay and tests PAC significance against surrogates, since PAC measures give false positives on short or noisy data. Decide before the Phase 1 gate.

## 12. Assumptions Index

Confirmed by Audio on 2026-10-27 and no longer tagged: the renderer's machine-readable report (FR-11), the 1 ms dropout definition (FR-13), and the CI check for banned terms and em dashes (§6).

Deferred, each owned by Audio, with the point to revisit it:

| Assumption | Location | Revisit at |
| --- | --- | --- |
| Two taps from launch to a playing session | FR-29 | Before Phase 3 UX work |
| Interrupted sessions resume rather than restart | UJ-3, FR-30 | Before Phase 3 UX work |
| Intensity scales tone gain, not modulation depth | FR-31 | Before Phase 3 UX work |
| Spatial-audio opt-out feasibility is unresearched | FR-34 | Before the Phase 3 gate |
| Listener-level ceiling set from the WHO-ITU standard | §5 | Before the Phase 3 gate |
| Maximum run time for looping sessions | FR-29 | Phase 0 spike |
| Battery budget value | §5 | Phase 0 spike |
| N sessions per mode for SC-2 | §9 | Before the Phase 1 gate |
