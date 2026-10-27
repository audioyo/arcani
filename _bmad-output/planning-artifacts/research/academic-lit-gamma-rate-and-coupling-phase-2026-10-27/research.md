---
title: 'academic-lit research: gamma AM rate range and theta coupling phase for the gamma PAC layer'
type: 'academic-lit'
topic: 'Gamma PAC layer: gamma AM rate range and default, and gamma-to-theta coupling phase'
decision: 'Set defaults and locked ranges for the gamma AM rate and the gamma-to-theta coupling phase'
source: 'native run (3 researchers + 1 verifier, web search)'
status: complete
preset: 'standard'
validation: 'normal'
created: '2026-10-27'
updated: '2026-10-27'
claims_verified: 6
claims_unverified: 12
claims_disputed: 0
claims_overturned: 0
---

# academic-lit research: gamma AM rate range and theta coupling phase

**Decision this research serves:** set the default and the locked safe range for (1) the gamma layer's amplitude-modulation rate and (2) the coupling phase, meaning where on the in-file theta reference envelope the gamma layer's modulation depth peaks.

## Executive summary

**Gamma AM rate.** Use a default of **40 Hz** and a locked range of **30 to 60 Hz**.

- The human auditory steady-state response (ASSR) is largest near 40 Hz in awake adults. It is maximal at 30 or 40 Hz and falls quickly by 50 Hz [1][2][4].
- People's individual peak rates cluster around 42 to 46 Hz. Measured individual values run from about 36 to 53 Hz [5][6].
- About 58 of 62 auditory gamma studies used 40 Hz. Outside 40 Hz, auditory behavioral data is sparse: 60 Hz (mainly one lab), one 80 Hz study, and work at each person's own peak rate [5][7][8].
- The cortex still follows AM at 98 Hz, the highest rate tested [3]. Above 60 Hz, though, there is no auditory behavioral evidence, so that band stays outside the locked range for now.
- Any rate in the range is valid. The default is a starting point, not a target.

**Coupling phase.** Make it a free recipe parameter (0 to 360 degrees). Define it on the **sound's** theta reference envelope, with 0 degrees at the envelope maximum. Default to **0 degrees (peak)**, and offer **uncoupled** as a control option.

The case for peak is weak:

- **Mixed results.** In electrical stimulation (tACS) studies, peak-coupled gamma helped in some studies [15][17]. Trough-coupled gamma either did nothing or impaired performance [15][16]. The direct peak-vs-trough test was not significant [17], and peak coupling was neutral in another study [16].
- **Brain recordings.** These show no single preferred phase. Hippocampal results are trough or biphasic [13], and frontal results sit near peak [28].

**Biggest caveat.** No study has ever delivered theta-gamma coupled *sound* and compared phases. That was confirmed by a dedicated absence search [verify C5].

Every phase result above comes from electrical stimulation or intracranial recording, and almost all of it used high gamma (75 to 100 Hz), not 40 Hz. The brain also follows a theta AM envelope with a delay of roughly 80 to 160 ms that differs between listeners [21][22][23]. So "peak in the sound" is not "peak in the brain". The coupling phase is a reproducible sound-design convention, and the recipe and test suite should treat it that way. No outcome claims should attach to it.

## Dimension A: gamma AM rate

**Where the auditory response peaks.**

- Galambos et al. first described a scalp response that builds up when sounds repeat at about 40 per second [1]. Picton's review describes ASSRs as recordable from about 1 to 200 Hz and "most prominent" near 40 Hz in awake listeners [2].
- An independent 1993 study used AM tones on 500 Hz carriers. It found the response maximal at 30 or 40 Hz, falling rapidly at 50 Hz [4]. This was verified, but only at snippet level.
- Ross et al. measured 30 rates from 10 to 98 Hz with MEG [3]:
  - Amplitude falls above the 40 Hz region but stays detectable up to 98 Hz.
  - Delay is about 48 ms at 40 Hz and about 26 ms at 80 Hz.
  - Their amplitude-versus-rate curve could not be read (scanned PDF), so this run found no peer-reviewed amplitude ratios for 60 or 80 Hz relative to 40 Hz.
- Responses near 80 Hz depend less on arousal [2]. That could matter for sleep recipes, but no study here tested it.

**Individual peak frequency.** People differ.

- Yokota et al. found a mean individual gamma frequency of 45.6 ± 5.3 Hz (SD, n = 29, ages 20 to 49). They measured it with 30 to 60 Hz click chirps embedded in music [5].
- Parciauskaite et al. found 41.9 ± 2.3 Hz (n = 37, 35 to 55 Hz chirps), with individual peaks from 36 to 53 Hz [6].
- A systematic review reports optimal rates of about 37 to 48 Hz across adult studies [7]. That is a range of study-level estimates, not of individuals.
- One study reported individual values from 30 to 90 Hz. It was not checked against the original (low confidence) and is excluded from the range.

**Behavioral and cognitive evidence by rate.** A systematic review covered 62 auditory gamma studies with 2,179 participants [7]:

- About 58 of the 62 studies used 40 Hz. Other rates were rare: 60 Hz (mainly Manippa's lab, plus Tada et al.) and 80 Hz in one study.
- Single sessions in healthy adults gave inconsistent cognitive effects.
- Animal amyloid findings did not replicate in humans.
- Mild side effects (headache, dizziness, tinnitus) were common in long-term studies.

At 60 Hz, sound-only stimulation reduced immediate-recall intrusions but did not improve recall or working memory [8]. A follow-up from the same lab mixed auditory and tACS arms. It found 40 Hz improved working memory against control, and 60 Hz again reduced intrusions [9] (low confidence; the auditory-only effect could not be separated). Yokota's gamma tuned to each person's own peak frequency improved one recall trial and one efficiency measure. That study had a single lab, low power and industry authors [5] (low confidence for the behavioral effect).

**Perception and comfort.**

- Roughness of AM tones peaks near 70 Hz for carriers above about 1 kHz, and the peak moves lower for lower carriers [10].
- For a 125 Hz carrier and for voices, roughness shows a broad maximum from about 20 to 50 Hz [11].
- So with carriers of a few hundred Hz, a 40 Hz gamma rate may sound close to maximally rough. This is a design cost to check by ear, not a safety finding.
- No annoyance or tolerance data by rate exists for hour-long listening.

**Carrier.** One snippet-level result says 40 Hz ASSR amplitude falls as the carrier rises, with a 250 Hz carrier about three times larger than a higher carrier [12] (low confidence). No direct 500 vs 1000 Hz comparison at gamma rates was found.

## Dimension B1: which theta phase gamma should peak on

**Brain recordings (endogenous).**

- In 56 neurosurgical patients, slow-theta (2.5 to 5 Hz) to gamma PAC was greater during successful memory encoding. Gamma at those sites "coupled to the trough of the slow-theta oscillation". In the hippocampus itself, though, phase preference was "biphasic" [13] (verified against the abstract).
- Hippocampal gamma couples to opposite theta phases at encoding and at retrieval. The degree of that opposition tracked memory performance [14].
- In anterior cingulate and dorsolateral prefrontal cortex during cognitive control, high gamma peaked near 0 to 60 degrees of theta phase [28] (secondary source, low confidence).
- The preferred phase therefore depends on region and task. The recorded "peak" and "trough" also depend on electrode site and reference.

**Stimulation that compares phases (all tACS, all human).**

- **Alekseichuk 2016** [15]. Prefrontal 6 Hz theta tACS improved spatial working memory when "bursts of high gamma oscillations (80–100 Hz) coincided with the peaks of the theta waves". Trough coupling and low-gamma protocols were "ineffective" (verified against the abstract; n not confirmed). One lab, with no direct replication [18].
- **Turi 2020** [16]. Same lab, 4 Hz + 80 Hz tACS, n = 24, double-blind. Trough-coupled bursts reduced accuracy (b = -0.70). Peak-coupled bursts had "no effects on the behavioral performance". An uncoupled control and a continuous-AM condition were included.
- **Akkad 2021** [17]. Motor cortex, 6 Hz + 75 Hz tACS.
  - Peak-coupled beat sham (p = 0.04), and trough-coupled did not (p = 0.766).
  - The direct peak-vs-trough contrast was not significant (p = 0.162).
  - A pre-registered replication of peak vs sham (n of about 44 to 46) held: d = 1.24 during stimulation and d = 1.01 at 75 minutes.
  - Note that Akkad's "peak" placed gamma across the whole positive half-cycle (0 to 180 degrees), not at a single point.
- **Other peak-coupled studies.**
  - One reduced Sternberg accuracy by 2.7% while shortening reaction times [19].
  - An independent motor study in young adults and stroke survivors reportedly found peak-coupled benefits, but the direction by group was not verified [20] (both low confidence, summaries only).
- Reinhart and Nguyen's working-memory tACS did not manipulate gamma phase [29]. It does not inform this choice.

**Summary.** The stimulation evidence leans toward peak and away from trough. Trough coupling has the clearest reported impairment [16]. One peak-coupled study also reduced accuracy [19] (low confidence). The lean rests on electrical stimulation, mostly high gamma, and a non-significant direct contrast.

## Dimension B2: how a phase in the sound maps to a phase in the brain

**Cortical tracking of theta-rate AM behaves like a fixed delay.**

- Phase lag grows linearly with frequency over about 4 to 8 Hz. The group delay is 156 ± 50 ms in EEG (n = 15; the paper does not say whether ± is SD or SEM) [21].
- An independent MEG study of slow AM sound found response latencies "between 100 and 150 ms" [22] (partially verified).
- Intracranial recordings show shorter, widely spread lags: theta 78 ± 64 ms, low gamma 59 ± 9 ms [23] (reviewed preprint).
- Because the lag is a delay, the phase offset between sound and brain grows with the theta rate. Our arithmetic, not a measured value: at 6 Hz, a 150 ms delay is about 324 degrees, and a 78 ms delay is about 168 degrees.

**The delay differs between listeners.**

- The spread is ± 50 ms in EEG (SD or SEM not stated; if SEM, the spread between listeners is larger) and ± 64 ms across intracranial contacts and patients [21][23].
- With a 3 Hz FM sound, the best stimulus phase for detection differed across listeners. The entrained neural phase predicted behavior better than the stimulus phase did [26].

**Entrainment or evoked responses is still open.**

- Some evidence favors repeated evoked responses [21], some favors a true oscillator [24], and a review treats the question as unresolved [25].
- For a steady AM tone, both views predict that neural theta lags the sound.

**Coupled sound and gamma ASSR versus theta phase.**

- No study was found that built gamma AM whose depth follows a theta envelope at a chosen phase and then measured brain PAC or behavior [verify C5].
- The closest evidence:
  - Natural speech already carries theta-gamma coupling, with gamma strongest near the theta envelope peak. Listening produces stimulus-driven theta-to-gamma PAC in auditory cortex [23] (preprint).
  - Electrical 6 Hz theta tACS reduced the 40 Hz ASSR and raised theta-gamma PAC for some frequency pairs [27] (low to medium confidence; electrical theta, not acoustic).

## Cross-dimension insights

- **The phase evidence and the rate evidence come from different gamma bands.**
  - The rate evidence: the auditory response peaks near 40 Hz (Dimension A).
  - The phase evidence: almost every phase-comparison study coupled 75 to 100 Hz gamma by tACS, and Alekseichuk found low gamma "ineffective" [15][16][17].
  - Neither result transfers cleanly to a 40 Hz auditory gamma layer coupled to an auditory theta reference.
- **The theta reference and the gamma layer reach cortex with different delays, so the coupling phase the brain receives is not the phase written into the file.**
  - Gamma ASSR delay is about 48 ms at 40 Hz [3], while theta tracking lags 100 to 160 ms at the scalp [21][22]. Our arithmetic: that difference could shift the effective coupling at 6 Hz by roughly 110 to 240 degrees.
  - Intracranial lags (78 vs 59 ms [23]) imply only about 40 degrees.
  - The true shift is unknown and listener-specific. This is the strongest reason not to lock a "brain phase" default and not to claim one.
- **Rate and comfort pull in opposite directions near 40 Hz.** The response peaks near 40 Hz [1][4], but on low carriers roughness also peaks around 20 to 50 Hz [11]. Low carriers may give larger 40 Hz responses [12] while sounding rougher. This is a listening-check item for the four starter recipes.

## Recommendations

1. **Gamma AM rate (PRD input, recipe schema):**
   - Default 40 Hz. Confidence is high that the response peaks in the 30 to 40 Hz region [1][4], and 40 Hz is by far the most-studied rate [7]. Confidence in behavioral relevance for healthy adults is low: effects are inconsistent even at 40 Hz [7].
   - Locked range 30 to 60 Hz. This covers the measured individual peaks of 36 to 53 Hz [6] and the most-studied non-40 Hz auditory behavioral rate, 60 Hz [8], which is mainly single-lab and low to medium confidence.
   - Treat 60 to 80 Hz as an "extended" band the designer can unlock later, only if new auditory evidence appears.
   - The carrier rule (at least 4 times the rate) then needs carriers of at least 240 Hz at 60 Hz.
2. **Individual peak frequency (PRD, later phase):** a per-listener gamma rate within the locked range is supported by [5][6]. Log it as a future feature, not a v0.1 default.
3. **Coupling phase (recipe schema, architecture):**
   - A parameter from 0 to 360 degrees, referenced to the in-file theta reference envelope, with 0 degrees at its maximum.
   - Default 0 degrees (peak), plus a recipe option for uncoupled gamma, following the control design in [16].
   - Confidence is low to medium: tACS evidence only, mostly high gamma, and a non-significant direct contrast [17].
   - The engine's "coupling timing" test should check the sound-domain phase exactly, because that is the only phase that is measurable and reproducible.
4. **Fix the plan doc (PRD input).** `docs/project-plan.md` currently asserts that gamma depth "peaks at the in-file theta trough" in its signal assertions. That should read "peaks at the recipe's coupling phase", matching CLAUDE.md. The trough default rests on brain-recording data that is region-specific [13][14] and does not map onto sound phase [21][23].
5. **No outcome claims (copy).** No source supports any claim that a given rate or phase of *sound* produces a cognitive effect.
6. **Phase 1 pilot (roadmap).** If an EEG pilot runs, compare sound-domain peak, trough and uncoupled conditions head to head, as the plan already proposes. Report the measured sound-to-cortex delay per listener. That measurement would turn the coupling phase from a convention into an evidence-based default.
7. **Design log entries.** Log the 40 Hz default, the 30 to 60 Hz range, the 0 degree phase convention and the plan doc correction, each with its source numbers from this report.

## Open questions

- **Amplitude ratios at 60 and 80 Hz.** What is the ASSR amplitude at 60 and 80 Hz relative to 40 Hz? Ross 2000 [3] has the curve; it needs a readable copy (library access or the authors).
- **Alekseichuk's sample size and trough effect.** What is the sample size in [15], and did trough coupling impair or just fail? This needs the full text.
- **Coupling in sound.** Does theta-gamma coupling delivered by sound produce phase-dependent brain or behavioral effects at all? No study exists. Answering it takes the Phase 1 pilot or a new literature search in a year.
- **Comfort over long sessions.** How comfortable are 30 to 60 Hz AM rates over long or overnight sessions? No data was found. Answering it takes listening checks, and later a user test.
- **Rate in sleep.** Does the arousal-insensitive response near 80 Hz [2] make a higher gamma rate better suited to sleep recipes? Not tested here; it needs a Deepen run.
- **Unverified leads.** Dickinson 2015's 30 to 90 Hz individual range, the 2025 Japanese 40 Hz safety study, and Tada (60 Hz) and Shahmiri (80 Hz), both cited in [7].

## Source appendix

| # | Claim / finding it supports | Publisher | Pub date | Accessed | Confidence |
|---|---|---|---|---|---|
| 1 | 40 Hz scalp response to repeated sounds | [PNAS, Galambos, Makeig & Talmachoff](https://doi.org/10.1073/pnas.78.4.2643) | 1981-04 | 2026-10-27 | medium (snippet) |
| 2 | ASSR recordable 1 to 200 Hz, most prominent near 40 Hz awake; 80 Hz less arousal-sensitive | [Int J Audiol, Picton et al.](https://doi.org/10.3109/14992020309101316) | 2003 | 2026-10-27 | medium (abstract) |
| 3 | ASSR across 10 to 98 Hz; amplitude falls above 40 Hz region; delay 48 ms at 40 Hz | [JASA, Ross et al.](https://doi.org/10.1121/1.429600) | 2000 | 2026-10-27 | medium (snippet) |
| 4 | Response maximal at 30 or 40 Hz, falling at 50 Hz (500 Hz carrier) | [PubMed 8377060](https://pubmed.ncbi.nlm.nih.gov/8377060/) | 1993 | 2026-10-27 | high (verified, snippet) |
| 5 | Individual gamma frequency 45.6 ± 5.3 Hz, n = 29; weak behavioral gains | [Sci Rep, Yokota et al.](https://doi.org/10.1038/s41598-025-22360-0) | 2025-11 | 2026-10-27 | high (IGF, verified); low (behavior) |
| 6 | Individual peaks 41.9 ± 2.3 Hz, range 36 to 53 Hz, n = 37 | [J Pers Med, Parciauskaite et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC8224604/) | 2021 | 2026-10-27 | high (verified) |
| 7 | Systematic review, 62 studies: 40 Hz dominant; inconsistent single-session effects; mild adverse events | [npj Aging, Bolland et al.](https://doi.org/10.1038/s41514-025-00305-1) | 2025 | 2026-10-27 | medium |
| 8 | 60 Hz sound reduced recall intrusions, no recall or WM gain | [Behav Brain Res, Manippa et al.](https://doi.org/10.1016/j.bbr.2023.114703) | 2024 | 2026-10-27 | low to medium (abstract) |
| 9 | Follow-up with mixed auditory and tACS arms | [Psychophysiology, Manippa et al.](https://doi.org/10.1111/psyp.14653) | 2024 | 2026-10-27 | low (snippet) |
| 10 | Roughness peaks near 70 Hz for high carriers, lower for low carriers | [Springer, Fastl & Zwicker ch. 11](https://link.springer.com/chapter/10.1007/978-3-540-68888-4_11) | 2007 | 2026-10-27 | medium (textbook) |
| 11 | Broad roughness maximum 20 to 50 Hz for 125 Hz carrier and voices | [JASA, Eddins, Kopf & Shrivastav](https://doi.org/10.1121/1.4937753) | 2015 | 2026-10-27 | medium |
| 12 | 40 Hz ASSR larger on low (250 Hz) carriers | [Hearing Research, Ross et al. (author PDF)](https://www.rotman-baycrest.on.ca/files/publicationmodule/@random45f5724eba2f8/pid707.pdf) | 2003 | 2026-10-27 | low (snippet; authors and year unverified) |
| 13 | Slow-theta to gamma PAC supports encoding; trough at memory sites; biphasic in hippocampus | [Cereb Cortex, Lega et al.](https://doi.org/10.1093/cercor/bhu232) | 2016-01 | 2026-10-27 | high (verified, abstract) |
| 14 | Opposite theta phases at encoding vs retrieval | [Curr Biol, Saint Amour di Chanaz et al.](https://www.cell.com/current-biology/fulltext/S0960-9822(23)00393-7) | 2023 | 2026-10-27 | medium (abstract) |
| 15 | Peak-coupled 80 to 100 Hz tACS improved spatial WM; trough and low gamma ineffective | [Curr Biol, Alekseichuk et al.](https://doi.org/10.1016/j.cub.2016.04.035) | 2016 | 2026-10-27 | medium (verified direction; single lab) |
| 16 | Trough-coupled tACS impaired cognitive control; peak no effect; uncoupled control design | [eNeuro, Turi et al.](https://doi.org/10.1523/ENEURO.0126-20.2020) | 2020-09 | 2026-10-27 | high (full text) |
| 17 | Peak-coupled tACS beat sham for motor learning, replicated; peak vs trough not significant | [eLife, Akkad et al.](https://doi.org/10.7554/eLife.67355) | 2021-11 | 2026-10-27 | high (full text) |
| 18 | Review: Alekseichuk the only peak-coupled WM study, unreplicated | [Front Psychol review](https://doi.org/10.3389/fpsyg.2022.822545) | 2022 | 2026-10-27 | medium |
| 19 | Peak-coupled tACS reduced Sternberg accuracy 2.7% | [GeroScience](https://link.springer.com/article/10.1007/s11357-024-01272-3) | 2024 | 2026-10-27 | low (summary) |
| 20 | Independent lab: peak-coupled tACS improves motor skill | [Brain Stimulation](https://www.brainstimjrnl.com/article/S1935-861X(24)00155-4/fulltext) | 2024 | 2026-10-27 | low (snippet) |
| 21 | Theta envelope tracking is a fixed delay, 156 ± 50 ms | [eNeuro, Zou et al.](https://doi.org/10.1523/ENEURO.0058-21.2021) | 2021 | 2026-10-27 | medium (full text, single study) |
| 22 | MEG latency to slow AM sound 100 to 150 ms | [J Neurophysiol, Wang et al.](https://doi.org/10.1152/jn.00310.2011) | 2012 | 2026-10-27 | medium (partially verified) |
| 23 | Intracranial lags theta 78 ms, low gamma 59 ms; speech carries and drives theta-gamma PAC | [eLife reviewed preprint, Lopez-Madrona et al.](https://doi.org/10.7554/eLife.110310.1) | 2026-04 | 2026-10-27 | medium (preprint) |
| 24 | Oscillator model fits MEG phase better than evoked model | [PNAS, Doelling et al.](https://doi.org/10.1073/pnas.1816414116) | 2019 | 2026-10-27 | medium (abstract) |
| 25 | Entrainment vs evoked responses unresolved | [Front Neurosci, Zoefel, ten Oever & Sack](https://doi.org/10.3389/fnins.2018.00095) | 2018 | 2026-10-27 | high (full text) |
| 26 | Best stimulus phase listener-specific; neural phase predicts better | [PNAS, Henry & Obleser](https://doi.org/10.1073/pnas.1213390109) | 2012 | 2026-10-27 | medium (abstract) |
| 27 | Theta tACS reduced 40 Hz ASSR, raised some theta-gamma PAC | [Clin EEG Neurosci, de la Salle et al.](https://doi.org/10.1177/15500594231179679) | 2023 | 2026-10-27 | low to medium |
| 28 | Frontal high gamma peaks near 0 to 60 degrees of theta (Smith et al. 2015, via Turi 2020) | [eNeuro, Turi et al. (citing Smith 2015)](https://doi.org/10.1523/ENEURO.0126-20.2020) | 2015 | 2026-10-27 | low (secondary) |
| 29 | WM tACS in older adults; no gamma phase manipulation | [Nat Neurosci, Reinhart & Nguyen](https://doi.org/10.1038/s41593-019-0371-x) | 2019 | 2026-10-27 | medium |

## Staleness map

The pack sets no freshness bar for seminal work or individual published findings. The state-of-the-art claims (what exists, what is replicated) age at 12 months, and preprints are checked at 6 months for a version of record. Computed with `recon_kit.py staleness`:

| Claim | Re-check by | Status |
|---|---|---|
| [23] intracranial sound-to-cortex lags (reviewed preprint) | 2026-10-01 | due now: check for a version of record |
| [5] individual gamma frequency distribution | 2026-11-01 | current |
| [C5] no study of theta-gamma coupled sound comparing phases | 2027-10-27 | current |
| [18] Alekseichuk 2016 working-memory benefit unreplicated | 2027-10-27 | current |
| [7] auditory gamma evidence concentrated at 40 Hz; 60 Hz single lab | 2027-10-27 | current |

Earliest re-check: 2026-10-01 (already due). Re-check [23] before the coupling-phase default is locked. A Refresh run handles this list.
