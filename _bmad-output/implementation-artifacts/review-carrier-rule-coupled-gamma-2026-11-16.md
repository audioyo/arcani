# Independent review: carrier rule for coupled gamma

Date: 2026-11-16. Scope: CLAUDE.md rule 4 review before Story 3.1. Reviewer had a fresh context and wrote only this file.

## Question

Threshold row `carrier-rule` says every modulated carrier is at least 4 times its modulation rate. For the gamma PAC layer with coupling `smooth_swell` or `bursts`, which rate does the validator use?

- **A (today):** the gamma rate alone, worst case `rate_hz + swing_hz`.
- **B (progress review 2026-11-16):** gamma rate plus theta rate for coupled gamma, each at its worst case.
- **C (considered here):** a rule on the layer's spectral components.

## Evidence checked

- `docs/signal-spec.md`: Gamma PAC layer (AM law, carrier rule text), Coupling (swell law, depth law), Bursts (gate, Spectrum table), Rate curve (range checks).
- `docs/project-plan.md` lines 49, 55, 149, 318; `docs/research-library.md` (all rows; Ross et al. 2003 at line 72).
- `docs/design-log.md` 2026-10-27 (a), (g), (m), 2026-10-28 (o), 2026-11-05 (hh), 2026-11-14 (ss), and the Current state table (line 25).
- `_bmad-output/specs/spec-arcani-v0-1/starter-recipes.md`, `thresholds-and-ranges.md`, `SPEC.md` CAP-9; `_bmad-output/planning-artifacts/epics.md` (FR-9, Story 2.4 criteria at lines 669 to 671, Story 3.1).
- `_bmad-output/implementation-artifacts/deferred-work.md` line 92; `epic-3-context.md` line 23.
- All 42 fixtures with a `gamma_pac` field in `recipes/fixtures/valid/`, scripted against both limits; references to the failing ones across `tests/`, `tools/`, `ci/`, `docs/`.
- A small NumPy line-spectrum calculation of the swell and burst gamma taps (1 s at 48 kHz, ideal formulas from the signal spec). It reproduces the spec's -51.3 dB figure for the 60 Hz burst fixture (-51.29 dB), so the model matches.

## Findings

1. **The math in the brief is right for the swell.** `a = 1 - d*s*(1-e)` gives lines at the carrier, carrier +- theta rate, carrier +- gamma rate, and carrier +- gamma rate +- theta rate. With a 250 Hz carrier, gamma AM at 60 Hz, and theta 6 Hz, the outer lines are at 184 and 316 Hz, 21.6 dB under the carrier.
2. **Option B is not the highest modulation component for bursts.** The burst gate carries many theta-rate harmonics. Lines within 40 dB of the strongest (the Story 3.1 component definition) reach 76 Hz from the carrier for a 250 Hz carrier with gamma AM at 40 Hz and 6 Hz theta (174 and 326 Hz, -37.6 dB), and 102 Hz from the carrier with gamma AM at 60 Hz (148 and 352 Hz, -40.0 dB). B would check 46 Hz and 66 Hz. So B is exact for the swell and arbitrary for bursts.
3. **No source decides the matter.** The research library has no carrier-to-rate ratio and no study of a carrier with nested AM. The rule's only stated reason is the earlier project's failure of a 60 Hz carrier amplitude-modulated at 60 Hz (plan lines 49 and 55: "the carrier must be several times the rate"). The value 4 is provisional and sourced to the plan, not to a study (design log line 25; entry (hh) implements it without adding a source). Either reading is an engineering default.
4. **The failure the rule guards is far from both readings.** It needs the carrier near the modulation rate. Under A the tightest accepted coupled case (240 Hz carrier, gamma AM at 60 Hz, 6 Hz theta, swell) has its lowest line at 174 Hz, 0.725 of the carrier, against 0.75 for plain AM at the limit. No degenerate condition is near.
5. **Recorded intent matches A.** Design log (a): "a 60 Hz rate needs a carrier of at least 240 Hz". Design log (m) and `starter-recipes.md`: the 250 Hz carrier, chosen for coupled starters, "passes the carrier rule at 40 and 60 Hz". Epics Story 2.4 requires burst renders "at gamma rates of 40, 45, and 60 Hz on a 250 Hz carrier". Design log (o) set the 10 ms burst edge from the 60 Hz worst case on that carrier. Under B each of these statements describes a rejected recipe.
6. **Consistency.** The theta reference carrier rule checks the theta rate only, although the sawtooth, reverse saw, and smoothed on-off shapes carry harmonics well above it. The rule already means "the layer's named rate", not "its spectral extent". B would make coupled gamma the one exception.
7. **Option C, done honestly, rejects a starter.** "Every component within 40 dB lies within carrier/4 of the carrier" would reject Focus (250 Hz carrier, gamma AM at 40 Hz, bursts, 6 Hz theta: 76 Hz against 62.5 Hz; it needs a 304 Hz carrier). That moves the gamma carrier up against Ross et al. 2003 and back toward the 300 Hz value the spacing risk note moved away from, with no source asking for it.
8. **What already covers the real risk.** Collisions between layers are the spacing rule's job (Story 3.2), and it reads the full component table, burst harmonics included, under any option. Audible artifacts within the layer are the click test's and listening sign-off's job.

## Fixtures that would newly fail under B (confirmed by script)

Exactly two of the 42; both get limit 264 Hz against a 250 Hz carrier.

| Fixture | Depends on it |
| --- | --- |
| `bursts-60hz.json` (250 Hz carrier, gamma AM at 60 Hz, bursts, theta 6 Hz) | `tests/cpp/test_bursts.cpp`, `test_recipe.cpp`, `test_validate.cpp`; `tests/python/test_bursts_reference.py` (holds the 60 Hz line to the research figure -51.3 dB and bounds the 40 and 45 Hz lines by it), `test_probe_bursts.py`; `tests/hashprobe/main.cpp` and `ci/hash_expected.json` components `gamma-bursts-44100` and `gamma-bursts-48000`; `tools/signal_spec_vectors.py` and 56 entries in `tests/data/signal_spec_vectors.json`; `tests/data/recipe_hash_vectors.json`; the signal spec's burst vector tables and Spectrum table; epics Story 2.4; design log (o) |
| `gamma-cycle-swell-theta-cycle.json` (250 Hz carrier, gamma AM at 45 +- 15 Hz, swell, theta 4 +- 2 Hz) | `tests/cpp/test_rate_curves.cpp`, `test_seek.cpp`, `test_loop.cpp`, `test_recipe.cpp`, `test_validate.cpp`; `tests/python/test_rate_curve_reference.py`, `test_probe_rate_curves.py`, `test_loop_render.py`, `test_recipe_hash.py` (it is the base of the rate cycle hash cases); hash probe components `rate-curves-44100` and `rate-curves-48000`; `tools/signal_spec_vectors.py` and 57 entries in the vectors file; the signal spec's rate cycle tables |

Rework if they moved to a higher carrier: regenerate both vector sets and the spec tables, re-pin four probe hashes from a full four-platform CI run, edit about ten test files, and rerun the research script for a new burst figure, because -51.3 dB belongs to the 250 Hz carrier (a 264 Hz carrier shifts every line and the 394 Hz boundary case). The one externally anchored spectrum number would be replaced by a new one. Estimate: one to two working days plus at least one full CI run, for no change in any starter recipe.

## Recommendation

**Keep Option A, and make it explicit.** Reasons: no source supports B or C; B is not a consistent principle (right for the swell, wrong for bursts, unlike the theta rule); the recorded design intent and a merged acceptance criterion assume A; and B costs real rework and a research anchor while protecting against nothing the spacing rule, click test, and listening do not already cover. A is the status quo, so no threshold is weakened.

## Conditions

1. Close the ambiguity in words. In the signal spec, glossary, and a design log entry, define the rule's modulation rate as the layer's own named rate (theta rate for the theta reference, gamma rate for the gamma PAC layer, worst case along a rate cycle), and state that coupling does not change it. Mark it an engineering default with this review as its record.
2. Story 3.1's component table must list the swell lines at carrier +- gamma rate +- theta rate and the burst gate harmonics, so the spacing rule sees the full spread.
3. Add one listening item to the starter checklist: a 250 Hz carrier with gamma AM at 60 Hz, coupled, beside a 450 Hz theta reference at 6 Hz, judged for roughness or artifacts. If Audio hears a problem, reopen this with that evidence.
4. Revisit if Phase 0 or the EEG pilot produces a source for a ratio.

## Corrections to the brief

- Sleep has no gamma PAC layer (`starter-recipes.md`; its theta reference runs at a steady 2 Hz). Three starters use the 250 Hz gamma carrier, not four. Under B the Learn limit is 182 Hz (5.5 Hz theta); Focus and Relax 184 Hz. All pass either way.
- `docs/project-plan.md` lines 149 and 318 still name a 300 Hz starter gamma carrier; design log (m) and the starter spec say 250 Hz. Stale plan text, worth a cleanup.
- For bursts, "gamma rate plus theta rate" is not the highest modulation component (finding 2).
