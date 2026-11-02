# Starter Recipes (v0.1)

Values from `docs/listening-modes.md`, picked by Audio on 2026-10-27 and logged in design log 2026-10-27 (m). All provisional; Phase 0 may change them. Every recipe targets -36 LUFS-I.

| Mode | Theta reference | Gamma PAC layer | Binaural layer | Length and arc | Looping |
| --- | --- | --- | --- | --- | --- |
| Focus | 450 Hz carrier, sine AM at 6 Hz | 250 Hz carrier, AM at 40 Hz, 50 ms bursts at coupling phase 0 degrees, depth 100 percent | Off | Ramp-in 5 min to full level, then looping body | Yes, max run time 45 min |
| Learn | 450 Hz carrier, sine AM at 5.5 Hz | 250 Hz carrier, AM at 40 Hz, smooth swell peaking at coupling phase 0 degrees (design log (d)), depth 100 percent | Off | Ramp-in 5 min to full level, then looping body | Yes, max run time 20 min |
| Relax | 450 Hz carrier, sine AM at 6 Hz; layer level ramps from silence to full over the first 10 min (design log 2026-10-29 (r)) | 250 Hz carrier, AM at 40 Hz, smooth swell at coupling phase 0 degrees, depth 25 percent; layer level ramps from silence to full over the first 2 min (design log 2026-11-01 (t)) | Off | 30 min | No |
| Sleep | 450 Hz carrier, sine AM at a steady 2 Hz delta rate | Off | 100 Hz left, 100 Hz plus beat rate right; beat rate cycles sinusoidally over 0 to 3 Hz every 60 s (Lee et al. 2024 range and cycle) | 45 min, last 5 min a fade to silence; no rhythmic signal after the end | No |

Sources and status per value:
- 40 Hz gamma rate: design log (a). 250 Hz gamma PAC carrier: Ross et al. 2003 (lower carriers drive larger responses); passes the carrier rule at 40 and 60 Hz.
- 5.5 Hz Learn theta rate: Roberts et al. 2018. 6 Hz Focus and Relax: listening-modes.md.
- 450 Hz theta reference carrier: engineering default (design log (g)). In Sleep it must be at least 156 Hz to clear the 100/103 Hz binaural pair.
- Relax 30 min: Jirakittayakorn and Wongsawat 2017 (30 min sessions).
- Engineering defaults, checked by ear: Relax depth 25 percent, Sleep 45 min with a 5 min fade, Learn 5 min ramp-in, loop max run times, -36 LUFS-I target.
- Theta reference AM depth: 75 percent in every starter (engineering default, design log 2026-10-29 (s)).
- Assumed, since listening-modes.md names neither: sine theta envelope in every starter; 100 percent gamma depth in Focus and Learn (addendum illustrative value).
- Sleep (design log (n)): Lee et al. 2024 cycled the beat rate over 0 to 3 Hz every 60 s; it never swept once from 3 Hz to 0 Hz. The 60 s cycle and range are sourced; the sinusoid shape, its start phase (set in the signal spec), and the steady 2 Hz theta reference rate are engineering defaults.
- Loop body length is set by the signal spec's seam rule.

No starter runs gamma and binaural together: a 250/256 Hz binaural pair in Relax would sit 4 Hz from gamma's 260 Hz side frequency and fail the spacing rule (design log (i)).

## Describe-the-sound notes

Each recipe carries these, matching `docs/listening-modes.md`. Describe the sound, never an outcome.

| Mode | When to use | Evidence strength |
| --- | --- | --- |
| Focus | Start about 10 minutes before a task and keep it running | Moderate |
| Learn | Right after studying or practice | Moderate for the theta rate, low to medium for the phase |
| Relax | Meditation, breaks, winding down | Moderate for relaxation, none for PAC |
| Sleep | Pre-sleep, in bed | Weak, preliminary |

## Known risks

- **Focus spacing.** Bursts on the 250 Hz gamma PAC carrier spread energy around 210 to 290 Hz and beyond. Any burst component within 40 dB of the layer's strongest line that reaches 394 Hz or above collides with the 450 Hz theta reference (444 to 456 Hz). The move from 300 Hz to 250 Hz widened the margin; smoothing burst edges fixes any remaining collision. The validator must pass, so this is resolved in the Focus story.
- **Focus citation.** The 40 Hz default rests on the auditory response literature (design log (a)), not on Alekseichuk et al. 2016, which used 80 Hz electrical gamma and found 40 Hz did nothing.
