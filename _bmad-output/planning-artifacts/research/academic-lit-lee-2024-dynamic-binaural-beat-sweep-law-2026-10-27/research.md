---
title: 'academic-lit research: Lee et al. 2024 dynamic binaural beat sweep law and timing'
type: 'academic-lit'
topic: 'Lee et al. 2024 dynamic binaural beat sweep law and timing'
decision: 'Arcani v0.1 Sleep starter rate-curve law and timing'
source: 'native run'
status: complete
preset: 'standard (scaled: 8 sources, 2 rounds, inline)'
validation: 'normal'
created: '2026-10-27'
updated: '2026-10-27'
claims: 'per digests: 13 verified, 1 disputed, 2 unverified'
---

# academic-lit research: Lee et al. 2024 dynamic binaural beat sweep law and timing

**Decision this research serves:** the law and timing of the Sleep starter's rate curves (theta reference delta 3 Hz to 1 Hz, binaural beat rate 3 Hz to 0 Hz, 45 min, 5 min fade).

## Executive summary

**The Sleep starter's sweep is not what Lee et al. did.** The paper never sweeps the beat rate once from 3 Hz to 0 Hz across a session. The right-ear carrier "continuously fluctuated between 100 and 103 Hz over a duration of one minute", with the left ear fixed at 100 Hz. The beat rate cycles across 0 to 3 Hz every 60 s, repeating for as long as the sound plays [1]. The sound played in three windows: pre-sleep until sleep onset, 20 min after a 3 min delay at sleep onset, and 20 min after each REM to non-REM transition [1].

**The waveform of the change (linear, sinusoidal, other) is not stated in the text.** Figure 1's caption only says "Scheme of dynamic binaural beat", and the authors say the pattern and form "were not optimized" and the one-minute cycle was "set to one minute without optimization" [1].

**Nothing in Lee et al. supports a theta reference delta sweep from 3 Hz to 1 Hz.** The study had no in-file rhythm. Its rationale for cycling was to cover "the entire range of the delta frequency band" on a 60 s cycle aligned with very low frequency rhythms [1], which is the authors' hypothesis, not a tested finding.

**Biggest caveat:** n = 10 healthy adults, silent sham, and 7 of 10 participants noticed the sound, so blinding was incomplete [2]. No replication, retraction, or correction was found.

## Sweep law and timing

**Carriers and range.** Left ear 100 Hz fixed; right ear 100 to 103 Hz; beat rate 0 to 3 Hz [1]. The editorial on the paper gives "between 1 and 3 Hz" while quoting the same carriers [2]. Those carriers imply 0 to 3 Hz, so the primary paper wins; the editorial figure is treated as an error (disputed).

**Cycle.** One cycle every 60 s, continuous; "the cycler duration of DBB was 60 s" [1]. Direction within a cycle and the number of cycles are not reported; about 20 cycles per 20 min window is an inference.

**Law.** Not stated in the text or captions [1]. The Figure 1 image and supplementary Figure S1 (docx) may show it; neither was read in this run.

**Timing.** Three windows [1]:
1. Pre-sleep: from lying comfortably in bed until sleep onset (variable length).
2. Sleep onset: once a technician judged non-REM from PSG, a 3 min delay, then 20 min.
3. Each REM to non-REM transition: 3 min delay, then 20 min (3.80 +/- 0.79 transitions per night in the stimulus condition).

Nothing outside these windows is described [1] (medium confidence, implied).

**Level.** Adjusted to comfort, measured 50.50 +/- 5.93 dB on night one, kept for later nights [1]. Generated in MATLAB R2020b, delivered over earphones, no background sound [1].

**Reported result.** Sleep latency 6.1 +/- 4.3 min with the stimulus vs 12.5 +/- 7.9 min sham, p = 0.027 [1] (unverified: from an abstract summary, not checked against the results text).

## Cross-dimension insights

Single-dimension run; none.

## Recommendations

1. **Correct the record (high confidence).** `docs/listening-modes.md`, design log entries 2026-10-27 (i) and (m), PRD FR-16, and the spec's `starter-recipes.md` describe Lee et al. as a 3 Hz to 0 Hz sweep. Rewrite them to say: a beat rate cycling over 0 to 3 Hz every 60 s, played before sleep onset and in 20 min windows after it. Feeds: design log, listening-modes.md, PRD FR-16, spec starter-recipes.md.
2. **Pick the Sleep binaural design consciously (decision for Audio).** Two honest options:
   - **Follow Lee's structure:** binaural beat rate cycling 0 to 3 Hz on a 60 s cycle for the whole session before the fade. The 60 s cycle and range are sourced [1]; the waveform within the cycle is an engineering default (for example, a triangle linear in Hz, so the beat rate covers the range evenly).
   - **Keep a monotone 3 Hz to 0 Hz sweep:** declared an engineering default with no study behind its shape, citing Lee et al. only for carriers and range.
   The first keeps Sleep's evidence claim intact; the second keeps the current arc but weakens it further. Arcani's sound stops at session end, never after sleep onset detection, so Lee's post-onset windows have no counterpart either way (PRD non-goals).
3. **The theta reference delta sweep needs its own basis (high confidence on the gap).** Lee et al. has no in-file rhythm. Either declare the 3 Hz to 1 Hz sweep an engineering default, or mirror the binaural design (cycling 1 to 3 Hz, the locked-range floor being 1 Hz). Both are engineering defaults; neither is sourced.
4. **Optional deepen:** read Figure 1 and supplementary Figure S1 to recover the waveform, if Audio wants the within-cycle shape sourced rather than declared.

## Open questions

- Waveform of the frequency change within each 60 s cycle: answer by reading Figure 1 or supplementary Figure S1, or by asking the corresponding author (Han-Jeong Hwang, Korea University).
- Whether stimulation was strictly off outside the three windows: implied, not stated.

## Source appendix

| # | Claim or finding it supports | Publisher | Pub date | Accessed | Confidence |
| --- | --- | --- | --- | --- | --- |
| 1 | Carriers, 60 s cycle, three windows, level, rationale, unoptimized parameters, latency result | [Lee H-A-N et al., Sleep 47(10) zsae097, Oxford University Press](https://academic.oup.com/sleep/article/47/10/zsae097/7647043) | 2024-04-17 (online) | 2026-10-27 | high (peer-reviewed primary; latency figure unverified) |
| 2 | Disputed 1 to 3 Hz range; incomplete blinding; open design questions | [Thomas RJ, Sleep 47(10) zsae190, editorial, Oxford University Press](https://academic.oup.com/sleep/article/7733451) | 2024-08-14 | 2026-10-27 | high for quotes; range figure disputed |

## Staleness map

From `recon_kit.py staleness` with windows method 120 mo, finding 24 mo, status 12 mo:

| Claim | Class | Re-check |
| --- | --- | --- |
| Stimulus structure: 0 to 3 Hz, 60 s cycle, three windows | method | 2034-04 |
| Waveform not stated | method | 2034-04 |
| Editorial 1 to 3 Hz range, disputed | method | 2034-08 |
| Sleep latency result, n = 10 | finding | 2026-04 (due now) |
| No replication, retraction, or correction found | status | 2027-10 |

Earliest: the latency finding is past its 24-month window. This run's replication search covers it for now; re-check for follow-up studies by 2027-10.
