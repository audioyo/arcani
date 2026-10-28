# Procedural Entrainment App: Project Plan v1

Oct 17, 2026 · @Aaron Goeglein

## Summary

We are building an Endel-style procedural soundscape app with an original entrainment engine: an in-file theta reference, a gamma layer coupled to it, an optional binaural layer, and later a moving spatial layer. Android ships first, then iOS. Code is built in Claude Code with the BMAD method.

Guiding principles:

- **Clean room.** Every signal design comes from public science and our own engineering, never from Monroe recipes, recordings, names, or confidential material.
- **Partnership-ready.** The app should be something we could show the Monroe Institute with pride and no awkwardness. Nothing in it should need explaining away.
- **Honest claims.** We describe what the audio is and how it was designed. We do not claim proven brain or health effects.
- **Lessons kept.** The QC failure from the Monroe challenge (carriers summed to a monaural beat) becomes an automated test, not a memory.

## Project rules

These rules apply to every phase, every agent, and every recipe. Where a rule and a later section disagree, the rule wins and the section gets fixed.

1. **Testable and reproducible.** Every signal is generated deterministically from a recipe file. The same recipe, engine version, and sample rate always render the same output, and every claim in this doc maps to an automated test or a listening check.
2. **Variable PAC rates.** The theta rate, the gamma rate, the gamma carrier, the coupling phase, and the modulation depth are all adjustable parameters, each with a locked safe range.
3. **Variable binaural rates.** The carrier frequency and the beat rate are adjustable parameters, each with a locked safe range.
4. **Science first.** Every default and every range traces to a published, peer-reviewed source logged in the design log. When a choice is unsure or unclear, research it before building it.
5. **Double-check big decisions.** Stack choice, signal architecture, defaults, and anything that would be costly to undo get an independent review (a fresh agent or outside expert) before they are locked.
6. **Easy designer.** The desktop designer uses plain labels, shows the signal it is making (waveform, spectrum, per-ear view), and warns before an unsafe or meaningless setting.
7. **No ambiguity.** Every signal is named by role and spelled out as carrier frequency, modulation type, and modulation rate. Words like "60 Hz isochronic tone" are never used alone, because they can be read two ways.
8. **Lessons stay fixed.** The Monroe challenge mistakes (next section) each have a guard in the engine or test suite, so they cannot recur.

Vocabulary used in this doc:

| Term | Meaning here |
| --- | --- |
| Carrier | The audible tone that carries a signal, in Hz |
| Rate | How fast something repeats: a beat, a pulse, or a modulation, in Hz |
| Binaural beat | Two carriers, one per ear, whose difference sets the beat rate; the beat exists only in the listener's brain |
| Monaural beat | Two carriers mixed in both ears; the beat exists in the audio file as an amplitude pattern |
| Isochronic | One carrier switched on and off at a set rate; the pulse exists in the audio file |
| AM | Amplitude modulation: a carrier's volume shaped by a slower wave |
| PAC | The gamma layer's strength rises and falls with a theta-rate wave that exists in the file |

## Lessons from the Monroe challenge

The reviewer found three design errors in the submitted track. Each is now a rule with a guard, and the v5 values that caused them are replaced below.

Reviewer feedback, as received:

> The most consequential one is that the rendered theta carrier is actually a monaural beat rather than a binaural beat. Both 200 Hz and 206 Hz end up in both channels in the final file, so the frequencies sum acoustically before reaching the listener instead of being processed dichotically. That changes the underlying neurophysiology of what the track is doing. Related to this, the trough-coupling claim that the design narrative is organized around isn't actually verifiable in the DAW with a binaural-beat carrier. The theta wave only exists as a perceived frequency in the listener's brain, not in the audio file, so there's no observable theta phase on the timeline to align the gamma LFO to. In this case, an intentional choice of a monaural beat or isochronic tone would have made it possible to precisely align the gamma LFO to the phase of the theta wave.
>
> On the gamma layer, a 60 Hz carrier amplitude-modulated at 60 Hz creates a degenerate condition. When the carrier and the modulation rate share the same period, the AM envelope can land on the zero crossings of the carrier and partially cancel the audible signal in unpredictable ways. A higher gamma carrier (somewhere in the 200 to 500 Hz range) modulated at 60 Hz would have avoided that interaction.

| Mistake | Cause | Rule now | Guard |
| --- | --- | --- | --- |
| Binaural carriers became a monaural beat | Carriers routed through the ambisonic HRTF decoder, which mixed each ear into the other | Binaural carriers never enter any spatial, reverb, or stereo-width stage | CI isolation test: each ear's spectrum holds only its own carrier, cross-leakage below a set threshold |
| Trough coupling could not be verified | Theta existed only as a binaural beat, which has no waveform in the file to align to | PAC always couples to a theta wave that exists in the file (monaural or isochronic theta, or the engine's own theta clock driving both) | Test measures gamma envelope peaks against the recipe's coupling phase on the in-file theta reference, within a set timing tolerance |
| 60 Hz carrier modulated at 60 Hz | Gamma rate and gamma carrier were the same frequency | Gamma is a separate audible carrier, amplitude-modulated at the gamma rate; the carrier must be several times the rate | Recipe validator rejects a carrier below a minimum multiple of the modulation rate |

One wording lesson too: v5 described the gamma layer as a "60 Hz isochronic tone", which can be read as a 60 Hz carrier or a 60 Hz pulse rate. Rule 7 exists so no signal is described that way again.

## Source materials

The signal plan is reconciled against Monroe Technical Reference v5, shared in this conversation. Values that appear only in earlier discussion, not in v5, are marked as open decisions.

| Source | What it supplied | Confidence |
| --- | --- | --- |
| Monroe Technical Reference v5 | Carrier and gamma frequencies, PAC coupling, static-carrier rule, mix levels, research citations | High; source document |
| Theta-gamma conversation, post-feedback analysis | Ambisonic decoder crosstalk caused the monaural beat; carriers must bypass spatial processing | High |
| This conversation | Endel model, phases, AI-then-human stems, offline stem generation, Android first | High |
| [US 2013/0010967 A1, Google Patents](https://patents.google.com/patent/US20130010967A1) | SAM application status and scope | High, as reported by Google; not a legal opinion |
| [Monroe Sound Science page](https://www.monroeinstitute.org/pages/monroe-sound-science) | Public description of MSS technique families | High |

Every study cited in v5, plus those added since, is checked one by one in Research library, with what it actually tested and whether it supports how we use it.

## IP and clean-room rules

The Monroe patents are not the real legal risk: the old binaural patents have expired by term, and the SAM application was abandoned without ever being granted. The live risk is other companies' active patents on audio modulation, which need a freedom-to-operate review before launch. This is a working read, not legal advice.

| Item | Status | What it means for us |
| --- | --- | --- |
| Monroe binaural patents (US 3884218, 5213562, 5356368) | Expired by term | Basic binaural beat generation is free to use |
| [SAM application US 2013/0010967](https://patents.google.com/patent/US20130010967A1) and its divisional US 2015/0016613 | Abandoned in 2015 for failure to respond to an office action; never granted | No enforceable rights, but we still design our own spatial method and never use the SAM name |
| Brain.fm patents citing the SAM family (US 11205414, 11957467, 11966661, 11392345) | Active, per the citing list | Cover neural stimulation through modulated audio; closest risk to our PAC and isochronic layers |
| Endel patents | Endel says its tech is patented | Check claims on adaptive, input-driven soundscape generation |
| Monroe, Hemi-Sync, Monroe Sound Science, Gateway, Focus levels | Brand names | Never in the app, store listing, or marketing |
| Monroe recordings, scripts, voice guidance | Copyrighted | Never sampled, imitated, or referenced |

Our rules:

1. No Monroe names, terms, recordings, scripts, or level settings, even where unprotected.
2. No use of anything learned only through the hiring challenge or private feedback. Public research and the patent record are fine.
3. Every signal choice traces to a published study or our own listening tests, recorded in a design log.
4. Before launch, a patent attorney runs freedom-to-operate on the Brain.fm and Endel families plus newer filings on earphone brainwave induction.

One v5 element stays out of the app: its session arc was modeled on Gateway Voyage exercises, including resonant tuning and a pink-sound onboarding drawn from the Gateway guidance manual. The app's session arcs are designed from scratch, so nothing in them reads as a Gateway imitation. Generic elements like pink noise and a gentle fade-in are fine on their own.

## Signal architecture

One engine clock drives everything: it generates an in-file theta reference, and the gamma layer's modulation depth follows that same clock, so trough coupling is exact and measurable. Binaural beats are an optional extra layer on their own dichotic path, never the PAC reference. This replaces the v5 design, which coupled gamma to a binaural beat that has no waveform in the file.

What the PAC layer is: coupled-rhythm entrainment. Like a binaural beat, it is sound designed for brain activity to follow, but its rhythm is a theta-rate swell with gamma pulses nested inside it, and that rhythm exists in the file. Two levels of following matter:

- **Auditory cortex following the sound:** well supported. The hearing brain tracks a sound's pulsing at its own rate, so a coupled sound should produce a coupled response there.
- **Memory networks coupling the way the PAC papers describe:** not yet tested with sound. The trough and peak findings come from the hippocampus and prefrontal cortex, measured with electrodes or driven electrically. Whether sound-driven coupling carries over is the open question this app's design should be honest about.

The brain also responds to sound with a delay, which shifts phase. An estimated 30 to 50 ms delay is 65 to 110 degrees at 6 Hz, so a trough in the file does not mean a trough in the brain. Coupling phase therefore stays adjustable and gets tested, not assumed.

&#91;embedded content: audio graph · 1 clock, 4 sources, 4 paths, 1 output\]

The highlighted path is the one that broke in the challenge track: HRTF decoding leaked each carrier into the other ear and produced a monaural beat.

| Layer | Provisional default (all variable) | Basis |
| --- | --- | --- |
| Binaural layer (optional) | 6 Hz from 200 Hz left and 206 Hz right, dichotic only. Locked range: carriers below 1000 Hz, beat below about 30 Hz | Jirakittayakorn and Wongsawat (2017) used a 6 Hz beat on a 250 Hz carrier; perception limits from Licklider et al. (1950), as cited by López-Caballero and Escera (2017) |
| Gamma PAC layer | Designer-selected carrier (frequency selector, 200 to 500 Hz; starter recipes 300 Hz), amplitude-modulated at a 60 Hz gamma rate | Reviewer guidance: carrier 200 to 500 Hz, never equal to the modulation rate. Lower carriers give larger gamma responses (Ross et al., 2003), so test 250 to 300 Hz too. Gamma rate is an open decision (40 vs 60 Hz) |
| Theta reference (required for PAC) | 450 Hz sine carrier, amplitude-modulated at a 6 Hz theta rate (isochronic or monaural-beat shape) | Exists in the file, so its phase is measurable. Monaural beats entrain the cortex more strongly than binaural beats (Orozco Perez et al., 2020) |
| Coupling | Gamma modulation depth peaks at a set theta phase, from one shared clock. Trough is a hypothesis, not a proven default | Trough: Lega et al. (2016), Kragel et al. (2020), both brain recordings. Peak: Alekseichuk et al. (2016), the only human coupled-stimulation study, electrical; verified by measuring envelope peaks against the in-file trough |

How each layer is built, spelled out per rule 7:

- **Theta reference:** a carrier (default 450 Hz) whose volume rises and falls at the theta rate (default 6 Hz). The trough is a point in the file, so the gamma layer can be aligned to it and the alignment can be measured.
- **Gamma PAC layer:** a separate carrier, picked with the designer's frequency selector (starter default 300 Hz), whose volume is modulated at the gamma rate (default 60 Hz). The depth of that 60 Hz modulation swells toward each theta trough and fades toward each theta peak.
- **Binaural layer:** two steady sines, one per ear, whose difference is the beat rate. It is optional, never routed through spatial or width processing, and makes no PAC claim. If its beat rate matches the theta rate, the designer can start it in phase with the clock, but the brain's response timing is unknown, so nothing is claimed about alignment.

Kept from v5 as starting defaults: a sine shape for the theta envelope (switchable in the designer), no motion on binaural carriers (PLOS One, 2024: moving carriers create panning beats), notch filters in the stem bed at every active carrier, and v5 mix levels (tones -36 LUFS-I, voice -18 LUFS-I, master -16 LUFS-I at -1 dBTP).

Carrier spacing rule: no two active carriers, including the side frequencies that modulation creates (300 Hz at 60 Hz adds 240 and 360 Hz), may sit close enough to beat against each other. If the theta reference and the binaural layer shared a carrier, the theta layer would put the right-ear frequency into the left ear and break dichotic isolation. The recipe validator enforces a minimum gap; the gap value is a Phase 0 research item.

The defaults above are provisional. Each is checked in Phase 0 with spectrum analysis and listening before it is locked, per rule 5.

The 120 Hz audibility harmonic is retired. It existed because a 60 Hz sine is hard to hear on small drivers; a 450 Hz carrier solves that directly.

Automated checks for this section: the binaural isolation test, a coupling test that measures gamma envelope peaks against the recipe's coupling phase on the in-file theta reference within a set tolerance, a carrier-to-modulation ratio check, and the carrier spacing check. A recipe that fails any of them cannot be exported.

## Spatial motion layer

Movement goes on the gamma PAC layer only, never on the binaural carriers or the theta reference, which matches the v5 rule for carriers. The ambient bed gets stereo width without motion, so it supports the session without pulling attention.

Research support: Sudre et al. (2024) found that moving binaural beats, panning sounds, and alternating beeps at 6 and 40 Hz all changed EEG and improved relaxation versus a control, and attributed the effects to spatial movement rather than beating. That supports the Orbit layer and makes a rhythmic panning mode worth testing in Phase 2.

To stay clearly our own, the motion uses standard object panning rather than the abandoned SAM method:

|  | SAM application (not used) | Our motion layer |
| --- | --- | --- |
| How motion is made | One tone sent to both ears with opposite phase modulation, a Doppler-style shift | A sound object moved along a path with interaural level and time differences, or an HRTF spatializer |
| What moves | The entrainment tone itself | The gamma PAC layer; carriers stay fixed and dichotic |
| Name | Spatial Angle Modulation | Working name: Orbit layer |

Parameters the engine exposes, each tuned by listening tests, not borrowed values:

- Path shape: arc, full orbit, figure-eight, or drift
- Period: seconds per pass, slow enough to hold attention without becoming a panning effect
- Width, depth, and elevation of the path
- Anchor mix: how much of the layer moves versus stays centered
- Ramp curves for entering and leaving motion across the session

The test that justifies the feature is a blind A/B of static versus moving gamma at the same beat settings, measured by session completion and self-report, and by a consumer EEG headband if one is available.

## Parameter model and session designer

No signal choice is hard-coded: v5 values are the defaults, and an internal session designer lets us change any of them, audition the result live, and save it as a recipe the app plays. Recipes ship as data files, the same way stems do.

Two tiers of control:

- **Session designer (build side):** full access to every parameter below, for authoring and testing. A desktop tool for the designer and engineer role.
- **Listener controls (mobile app, end user):** a few safe knobs such as session length, intensity, and motion on or off, kept inside ranges the designer locks.

| Layer | Parameter | Options in the designer | Provisional default |
| --- | --- | --- | --- |
| Theta reference | Theta rate | any rate in Hz, inside a locked range set from the literature in Phase 0 | 6 Hz |
| Theta reference | Carrier | any frequency in Hz, spacing-checked | 450 Hz |
| Theta reference | Envelope shape | sine (monaural-beat shape), smoothed on-off (isochronic), sawtooth, reverse saw, custom curve | sine |
| Gamma PAC layer | Gamma rate | any rate in Hz, inside a locked range | 60 Hz (open decision: 40 or 60) |
| Gamma PAC layer | Carrier | Frequency selector, 200 to 500 Hz, at least 4 times the gamma rate, spacing-checked. Lower carriers give larger gamma responses (Ross et al., 2003) | Designer's choice; 300 Hz in starter recipes |
| Gamma PAC layer | Carrier waveform | sine, triangle, softened square | sine |
| Coupling | Phase | trough, peak, or any offset in degrees | per mode (see Session modes) |
| Coupling | Depth | 0 to 100 percent, as a smooth swell or short gamma bursts per theta cycle (Alekseichuk et al., 2016 used 50 ms bursts) | set by ear in Phase 1 |
| Binaural layer | On or off | on, off | open decision |
| Binaural layer | Carrier and beat rate | carriers below 1000 Hz, beat below about 30 Hz | 200 Hz, 6 Hz beat |
| Binaural layer | Waveform | sine; others flagged (see below) | sine |
| Orbit layer | Path, period, width, anchor mix | see Spatial motion layer | off until Phase 2 |
| Session | Ramps per layer, total length | drawn curves over time | fade order designed fresh |
| Levels | Gain per layer | dB or LUFS targets | tones -36, master -16 LUFS-I |

Waveform choice matters differently by layer. On the PAC envelope, a sawtooth is a real design option: v5 considered it to mirror the asymmetric shape of natural theta and chose sine for purity, so testing both is worthwhile. On the carriers, a sawtooth's harmonics form their own beats (400 and 412 Hz beat at 12 Hz, 600 and 618 Hz at 18 Hz), stacking extra rates on top of the 6 Hz target and sounding buzzy. The designer allows it but flags it, and recipes default to sine carriers.

Guardrails built into the designer:

- Locked ranges and level ceilings per parameter
- Automatic edge smoothing on hard-edged shapes, so sawtooth or square envelopes don't click
- The L/R isolation test runs on every recipe export
- Each recipe records author, date, and the reason for its values, which feeds the design log

A recipe is a small file the engine reads:

```json
{
  "name": "Theta Focus Default",
  "engine_version": "0.1.0",
  "seed": 1234,
  "clock": { "theta_hz": 6.0 },
  "theta_reference": { "carrier_hz": 450, "envelope": "sine" },
  "gamma_pac": {
    "carrier_hz": 300, "carrier_wave": "sine",
    "gamma_hz": 60, "phase": "trough", "depth": 1.0
  },
  "binaural": { "enabled": true, "carrier_hz": 200, "beat_hz": 6.0, "wave": "sine" },
  "levels_lufs": { "tones": -36, "master": -16 }
}
```

The engine version and random seed make every render reproducible: the same recipe always produces the same file, including any procedural choices in the stem sequencer.

### How the designer reaches the app

Decided: the designer is a separate desktop tool for the designer and engineer role, and the mobile app is for end users only. They connect in three ways:

1. **One engine.** The designer runs the same DSP core the app ships, compiled for desktop, so what you hear while authoring is what listeners hear. This makes the shared C++ core the strongest stack option.
2. **Push to device.** While authoring, the designer streams a recipe to a test phone on the same network, so you can check it on real earbuds before publishing.
3. **Publish without an app release.** Finished recipes and stem packs go to a content server with a versioned manifest. The app checks the manifest and downloads new content, so new sessions ship without an app store update. Code changes still go through the stores.

The publish step runs the guardrails first: range checks, level ceilings, and the L/R isolation test. A recipe that fails any of them can't be published.

|  | Desktop designer | Mobile app |
| --- | --- | --- |
| User | You, or future sound designers | Listeners |
| Controls | Every parameter, live audition, waveform and envelope drawing | Session length, intensity, motion on or off |
| Output | Recipes, stem packs, design log entries | Playback only |
| Updates | Installed on your PC | Engine via app stores; content via manifest |

## Session modes (provisional)

Four starter modes, each built from the closest published evidence. Every value is a recipe setting the designer can change, and every mode gets tested before its defaults lock. Evidence strength varies a lot by mode, so the last column says how much to trust it.

| Mode | When to use | Theta reference | Gamma layer and coupling | Binaural layer | Length and arc | Evidence and strength |
| --- | --- | --- | --- | --- | --- | --- |
| Focus | Start about 10 minutes before a task and keep it running | 6 Hz | 40 Hz rate (60 selectable), 50 ms bursts on the theta peak | Off | 30 to 45 minutes; layers reach full level in the first 5 minutes | Alekseichuk et al. (2016), peak bursts helped working memory, electrical; Garcia-Argibay et al. (2019), exposure before a task worked better. Moderate |
| Learn | Right after studying or practice | 5.5 Hz (4 to 5 Hz selectable) | 40 or 60 Hz, smooth swell peaking at the theta trough | Off | 15 to 20 minutes | Roberts et al. (2018), 5.5 Hz after study improved memory for context, audiovisual; Lega et al. (2016), trough coupling during encoding at 2.5 to 5 Hz. Moderate |
| Relax | Meditation, breaks, winding down | 6 Hz | Off by default, or low depth | Optional: 6 Hz beat on a 250 Hz carrier | 20 to 30 minutes; theta builds over the first 10 minutes; Orbit motion added in Phase 2 | Jirakittayakorn and Wongsawat (2017), theta rose within 10 minutes and tension fell; Sudre et al. (2024), moving sounds at 6 Hz improved relaxation. Moderate for relaxation, none for PAC |
| Sleep | Pre-sleep, in bed | Delta rate instead of theta: 3 Hz sweeping down to about 1 Hz, following the 0 to 3 Hz span Lee et al. used | Off | Optional: beat sweeping 3 Hz down to 0 on a 100 Hz carrier | 30 to 45 minutes, then a fade to silence. No stimulation after sleep onset | Lee et al. (2024), a beat sweeping 0 to 3 Hz cut time to fall asleep, 10 people. Ngo et al. (2013): sound during deep sleep only helped when timed to the brain's own slow waves, which needs EEG, so the app stops instead. Weak, preliminary |

Shared across modes: a pink or white noise option in the stem bed, since Melnichuk et al. (2025) found background noise changed results; the binaural layer is never required; and a stem-bed modulation option for Focus, pending a patent check on the method in Woods et al. (2024).

What these modes do not claim: each mode's description says what the sound is and how it was designed. It never promises focus, memory, or sleep outcomes.

## Content and stems

Stems are the musical and ambient bed only; every entrainment signal is synthesized live by the engine. AI stems are generated offline, curated by ear, and shipped as files, then human stems join the same library without code changes.

Every stem carries the same metadata:

| Field | Example | Why |
| --- | --- | --- |
| Layer role | pad, texture, nature, melodic | Sequencer picks one per slot |
| Key or scale | C major, pentatonic, unpitched | Keeps layers consonant with each other |
| Tempo | free time or BPM | Rhythmic stems stay aligned |
| Mode fit | Focus, Relax, Sleep | Mode rules filter the library |
| Energy | 1 to 5 | Shapes the arc of a session |
| Loudness | LUFS-normalized on import | Mix stays stable as stems swap |
| Loop points | sample-accurate start and end | Gapless playback |
| Source | AI or human | Provenance and marketing |
| Tool or artist, date, license | tool, plan, terms snapshot | AI output generally can't be copyrighted; human stems are the defensible asset |

Curation checklist for each stem: no artifacts or clicks at loop points, no key drift, nothing that masks any active carrier, and loudness within target. Use Ogg Vorbis or Opus (or carefully looped AAC); avoid MP3 because encoder padding breaks gapless loops. Ship a small built-in set and add downloadable packs later.

## Product requirements

Decided October 21; items marked TBD stay open.

- **Accounts:** sign-in with Google, plus Sign in with Apple on iOS. Apple's App Store rules have required Apple sign-in whenever an app offers third-party sign-in; confirm the current rule before building. Firebase Authentication covers both.
- **Analytics:** anonymous only. No names, emails, or audio-session content tied to a person; usage counted by random install ID; opt-out in settings.
- **Business model:** freemium. Free tier: core modes at standard settings. Premium: the full recipe library, longer sessions, the Orbit layer, artist and human-composed packs, and offline downloads.
- **Platforms:** reach the most people with the least support. Phase 0 picks the lowest Android and iOS versions the chosen stack supports well, using current device-share data, and avoids features that only work on recent phones.
- **Offline:** downloaded or queued sessions play without a connection. Because tones are synthesized live from tiny recipe files, the assets worth protecting are the stems. They are stored encrypted, with keys tied to the account and device, so files can't be lifted out of the app. Anything audible can still be recorded through the speaker or a cable, so the goal is to stop easy copying, not all copying.
- **TBD:** minimum OS versions, pricing, trial length, safety and wellness messaging, the first-run headphone check.

How the two reference apps package it:

| App | Free | Paid | Price |
| --- | --- | --- | --- |
| [Endel](https://apppricinglab.com/app/apple/1346247457) | A free edition with classic soundscapes | Premium: extra modes, spatial "Orbit", noise colors, focus timer, artist collaborations | Several monthly and yearly tiers on the App Store, plus $124.99 lifetime (as of June 2026) |
| [Expand](https://apps.apple.com/app/id1552705313) (Monroe Institute) | Free download | Subscription unlocks the full library of guided experiences; the app supports offline downloads | $11.99 a month or $69.99 a year |

Endel already uses "Spatial Orbit" as a premium feature name, so our Orbit layer needs a different public name. That is now part of the naming decision.

## Build and test workflow

Claude Code writes the code on top of an existing audio framework, and the engine is built so agents can test it without ears. Most mistakes should fail an automated check within seconds; your listening time goes only to what machines can't judge.

Tools:

| Tool | Role | Note |
| --- | --- | --- |
| JUCE (C++) | Engine, desktop designer UI, Android and iOS builds from one codebase | Leading candidate; verify current license terms before committing |
| miniaudio + Dear ImGui | Lighter alternative: engine plus designer UI, with a thin native or React Native phone UI | Less framework, more wiring |
| Python reference renderer (numpy) | Generates every signal the obviously correct way; engine output is compared against it | Catches subtle DSP bugs as numeric mismatches |
| Reaper, RX, Youlean | Your listening and visual inspection of rendered WAVs | Same tools as the v5 workflow |
| GitHub Actions | Runs the full test suite on every push | Failing code doesn't merge |

The agent loop:

1. **Headless render.** The engine has a command-line mode that renders any recipe to WAV. Agents can't listen, but they can analyze files, so this makes everything testable.
2. **Tests before code.** In BMAD, a QA agent with fresh context turns each story's acceptance criteria into tests before the dev agent writes code, so the dev agent never grades its own work.
3. **Signal assertions** on every render:
   - Binaural isolation: only the left binaural carrier in the left ear and only the right one in the right, with cross-leakage far below audibility
   - Gamma modulation depth peaks at the recipe's coupling phase on the in-file theta reference, and the envelope shape matches the recipe; carrier spacing and carrier-to-rate ratio pass
   - Loudness and true-peak targets met
   - No clicks at loop seams or envelope edges, no dropouts, no NaN values
   - Renders faster than real time on target hardware
4. **Golden files.** A render you approve by ear becomes a reference; any code change that alters it fails until you re-approve.
5. **Hooks and CI.** Claude Code hooks run the fast tests after every edit; GitHub Actions runs everything on push.
6. **Human gates.** Your ears on every new recipe, using a short listening checklist, and a real Android phone for background playback and battery behavior, which emulators can't verify.

## MVP scope (v0.1)

v0.1 proves the engine is correct before anything is built on it: a desktop command-line renderer that turns a recipe into a WAV file, checked by the full test suite. No app, no interface, no stems.

In scope:

- Engine core in plain C++ with no framework dependency, so it can sit under JUCE or miniaudio later: one engine clock, sine oscillators, amplitude modulation, the theta reference, the gamma PAC layer (smooth swell and burst shapes, any phase), the binaural layer, per-layer gain ramps, and a final limiter
- Recipe files in JSON, loaded and validated against every locked range and the carrier spacing rule
- A command-line renderer: recipe in, 48 kHz 24-bit WAV out, faster than real time
- The Python reference renderer for every layer
- The full automated test suite (below) running locally and in GitHub Actions
- Four starter recipes matching the Session modes table: Focus, Learn, Relax, Sleep
- The design log, with every default traced to a Research library source

Out of scope for v0.1: the desktop designer, mobile apps, the stem bed, the Orbit layer, accounts, analytics, payments, the content server, and encryption.

Done when: every test passes in CI, all four starter renders have golden files, and Aaron signs off on each render after listening in Reaper and checking it in RX.

## Test thresholds (provisional)

Starting numbers so the QA agent can write real tests now. Phase 0 confirms or adjusts each one, and every change is logged with its reason.

| Test | Pass condition | Why this number |
| --- | --- | --- |
| Binaural isolation, engine output | In each ear, the other ear's carrier is at least 90 dB below its own | Digital generation should give essentially zero leakage; anything measurable means a routing bug |
| Binaural isolation, after the master chain | At least 60 dB below | Leaves room for limiter artifacts while staying far below audibility |
| Coupling timing | Each gamma envelope peak lands within 2 ms of its target theta phase point (about 4 degrees at 6 Hz) | Tight enough to tell peak from trough with a wide margin |
| Carrier-to-rate ratio | Every amplitude-modulated carrier is at least 4 times its modulation rate | Avoids the 60 Hz on 60 Hz failure; 300 Hz at 60 Hz passes at 5 times |
| Carrier spacing | At least 50 Hz between any two active spectral components, counting modulation side frequencies | Placeholder until a critical-band source is checked; starter recipes pass because gamma and binaural never run together |
| Frequency accuracy | Every carrier and rate within 0.01 Hz of the recipe value | A 6 Hz beat is only meaningful if both carriers are exact |
| Long-session drift | Theta phase error under 1 ms after an 8-hour render | Sleep sessions and all-night tests |
| Reference match | Engine and Python reference differ by less than -100 dBFS, sample by sample | Catches DSP bugs as numbers instead of by ear |
| Determinism | Same recipe, engine version, and seed give a byte-identical file | Rule 1 |
| Clicks | No discontinuity above -60 dBFS in an 8 kHz high-pass of loop seams, ramp edges, and burst edges | Bursts and on-off envelopes are where clicks hide |
| Gain ramps | No gain change faster than 10 ms | Prevents clicks at fades |
| Loudness | Integrated loudness within 1 LU of the recipe target; true peak at or below -1 dBTP | v5 mastering targets |
| Speed | Renders at least 20 times faster than real time on the development PC | Fast tests, and headroom for phones later |

## Roadmap

Phase 0 is next: a short spike that proves background audio and the carrier isolation test before any feature work. Each later gate becomes a set of acceptance tests in BMAD.

&#91;embedded content: roadmap · 5 phases, 4 gates\]

No dates yet; they follow once the Phase 0 spike shows how much the stack choice costs.

## Gaps check

The biggest gap was in the evidence, not the engineering: two v5 citations don't support what v5 used them for, and the audio-specific evidence for binaural beats is weaker than the plan assumed. Checked October 21, 2026.

| Finding | Why it matters | Action |
| --- | --- | --- |
| [Alamalhoda et al. (2025)](https://research-explorer.ista.ac.at/record/21245) used 60 Hz flickering light, in 30-minute sessions, not audio in 20-minute sessions | v5 called it the most applicable human validation for 60 Hz audio; it isn't auditory evidence | Drop it as audio support; feeds the open 40 vs 60 Hz decision |
| [Manippa et al. (2024)](https://ricerca.uniba.it/handle/11586/451103): 60 Hz auditory stimulation reduced recall intrusions but did not improve recall or working memory | Real auditory evidence, but a narrow effect | Cite for what it found, nothing broader |
| [López-Caballero and Escera (2017)](https://www.frontiersin.org/articles/10.3389/fnhum.2017.00557/full) found no EEG power change from binaural beats at any rate tested | The binaural evidence base is mixed | Binaural default is an open decision; claims stay audio-descriptive |
| [Orozco Perez et al. (2020)](https://www.eneuro.org/content/eneuro/7/2/ENEURO.0232-19.2020.full-text.print): monaural beats entrain the cortex more strongly; binaural beats alone produced cross-frequency activity | Supports the in-file theta reference, and suggests keeping both layer types | Done: theta reference added; binaural kept as an optional layer |
| Binaural beats need carriers below 1000 Hz and a difference under about 35 Hz (Licklider et al., 1950, cited by López-Caballero and Escera) | A 60 Hz gamma rate can never be a binaural beat | Done: locked ranges in the designer |
| A theta reference sharing a carrier with the binaural layer would leak the other ear's tone | A second route to the challenge bug | Done: carrier spacing rule and validator |
| Phone and headphone spatial-audio features can re-mix the ears | The challenge bug can happen after our output | Added to risks; device testing in Phase 2 |
| [Jirakittayakorn and Wongsawat (2017)](https://public-pages-files-2025.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2017.00365/text): 6 Hz binaural beat on a 250 Hz carrier, 28 people, theta increase within 10 minutes | Confirms the v5 citation | Kept |
| [FDA general wellness guidance](https://www.fda.gov/media/90652/download), January 6, 2026: software playing audio to relax and manage stress is a general wellness product; disease claims are not | Gives us the exact wording boundary | Store and marketing copy follows it |
| [WHO-ITU safe listening standard](https://who.int/publications/i/item/9789241515276) (2019): 80 dB for 40 hours a week for adults | Sleep sessions can run all night | Level ceiling and listening guidance in the app |
| The trough-coupling rationale comes from recordings of the brain's own rhythms (Lega et al., 2014), not from studies of sound designed to produce PAC | Whether coupled sound induces PAC in listeners is untested | No PAC outcome claims; consider an EEG pilot with a sham control |

Not yet in the plan, worth adding when relevant:

- **Business model:** subscription, one-time purchase, or free with packs. It shapes the content server and account design.
- **Accessibility:** listeners with hearing in one ear can't use binaural beats; the in-file modes still work for them.
- **Usability test of the designer:** one session with someone who isn't an engineer, per rule 6.
- **Evidence register:** a table in the design log for every cited study, with modality (audio, light, electrical), sample size, and what it actually found. It would have caught the Alamalhoda mismatch.

## Open decisions, risks, and BMAD handoff

The stack is the one decision that blocks the BMAD architecture phase; everything else can be settled during Phase 1.

Open decisions:

- [ ] Stack: shared C++ DSP core (miniaudio or JUCE) with a thin UI, Unity, or React Native with a native audio module. The desktop designer favors the shared C++ core, since one engine can build for Windows, Android, and iOS. The core needs background playback with the screen off, low battery drain, and identical DSP on Android and iOS.
- [ ] Gamma rate default: 60 Hz (v5) or 40 Hz (the rate used in most of the auditory gamma studies in the Research library). v5's case for 60 Hz leaned on rodent band roles and a light-flicker study; the only auditory 60 Hz study found one narrow effect. Research before locking; the designer supports both either way.
- [ ] Coupling phase per mode: trough (brain recordings during memory encoding) or peak (Alekseichuk et al., 2016: peak-aligned gamma bursts improved working memory, trough-aligned cancelled it). How a sound's envelope phase maps onto the brain's theta phase is unknown, so test peak, trough, and uncoupled gamma head to head in Phase 1.
- [ ] Theta rate default: 6 Hz (Jirakittayakorn and Wongsawat, 2017) or slower. The trough-coupling finding behind the PAC design was for 2.5 to 5 Hz theta (Lega et al., 2016).
- [ ] Binaural layer on or off by default. Monaural beats entrain the cortex more strongly (Orozco Perez et al., 2020), and one controlled study found no EEG change from binaural beats (López-Caballero and Escera, 2017).
- [ ] Binaural carrier: keep 200/206 Hz or test higher carriers. v5's 450 to 500 Hz figure could not be verified, and perception and comfort vary by listener (Schütze et al., 2026), which argues for a listener-adjustable carrier. A 450 Hz binaural carrier would collide with the 450 Hz theta reference default, so the spacing rule applies.
- [ ] Locked ranges: the minimum carrier spacing and the safe range for every rate, set from the literature in Phase 0.
- [ ] Loudness: decide how the v5 file-master targets map to live rendering, where the engine controls gain on the fly.
- [ ] Names: the app, the Orbit layer, and the term "SAP" in the project description. If it means SAM-style spatial motion, this doc's Orbit layer is our clean-room version and the description should use that name.

Risks:

| Risk | Mitigation |
| --- | --- |
| Active third-party patents on modulated audio | Freedom-to-operate review before launch |
| Health or efficacy claims draw regulators or store rejection | Use general wellness wording only (relaxation, stress, sleep, focus); never disease, therapy, or "neurostimulation" language |
| Binaural beats fail on speakers, mono earbuds, or the phone's mono-audio setting | Detect headphones and mono output; fall back to modes without the binaural layer |
| Phone or headphone spatial-audio features re-mix the two ears, repeating the challenge bug outside our code | Test with those features on; tell users to turn them off; research whether the app can opt out |
| Spatial processing leaks into the binaural path in our own graph | CI isolation test on every build |
| Mobile OS stops background audio | Prove background playback in the Phase 0 spike |
| Long sleep sessions drift in phase or click | High-precision phase math; test renders up to 8 hours |
| Hearing exposure over long or nightly sessions | Level ceiling, no sudden loud events, and guidance aligned with the WHO-ITU safe listening standard |

BMAD handoff: this doc becomes the project brief. The PM agent turns it into a PRD with one epic per phase, the architect agent picks the stack and audio graph, and each phase's exit criteria become acceptance tests. When the app is solid, a short design-log summary is the natural thing to share with the Monroe Institute.
