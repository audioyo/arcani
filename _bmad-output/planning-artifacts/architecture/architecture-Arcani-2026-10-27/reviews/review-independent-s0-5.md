---
review: independent architecture review (CLAUDE.md rule 4), Story 0.5
target: ARCHITECTURE-SPINE.md, AD-4, AD-5, AD-9, AD-19, AD-20 and the Stack table
date: 2026-11-04
method: two fresh-context reviewer agents with no part in writing the spine, run in parallel and blind to each other. Reviewer A took the signal decisions (AD-4, AD-5, AD-19, AD-20); reviewer B took AD-9 and the Stack table, with a web check of every pinned version. Both checked against the PRD, SPEC, CLAUDE.md, the research library, and the S0.2 result (design log 2026-11-03 (bb), full run 41648370470). Verdicts recorded in design log 2026-11-04 (ee).
---

# Independent Review: AD-4, AD-5, AD-9, AD-19, AD-20 and the Stack

## Verdict

All six decisions are sound and now locked. AD-4, AD-19, and AD-20 lock with wording edits that only record what the sources already say. AD-5, AD-9, and the Stack table change: Audio approved every change as the reviewers proposed (2026-11-04, below). Changed text, the design log entry, and every affected story are applied in the same change as this file.

| Decision | Verdict | Source | Notes |
| --- | --- | --- | --- |
| AD-4 | lock | CLAUDE.md Signal facts; PRD FR-4, FR-5, glossary; SPEC CAP-5, CAP-6; design log (k), (p); `thresholds.tsv` `limiter-idle`; epics S1.2, S4.5 | Wording: rule records the v0.1 zero bound from (p) and that a non-zero bound needs a design log entry with measured data. Limiter latency note becomes a S4.5 AC. |
| AD-5 | change | CLAUDE.md Signal facts and Never; PRD FR-3; SPEC CAP-4; design log (b), (s); adversary review H25 | Rejection now also covers a theta reference at zero level; uncoupled gamma stated as constant depth. No new value. Stories: epics FR-3 line, S2.3, S6.5; SPEC CAP-4. |
| AD-9 | change | PRD FR-6; design log (j), (z), (aa), (bb) and full run 41648370470; `ci/hash_tolerance.json`; `toolchain.json`; freshness review F8, F9 | Decision holds (S0.2 byte-identical on four platforms, no fallback). Rule now names IEEE denormal mode with restore, bans explicit fma, adds the float-to-integer clamp rule and x86-64 only, records the hosted static NDK method, requires a physical-phone run of the app-built library before the Phase 0 part 2 stack spike closes, and narrows the fallback to a cited (platform, component) entry outside the AD-9 rules with a rule-4 review. Stories: 0.1 (text only), 1.2, 1.4, 1.6. |
| AD-19 | lock | SPEC CAP-1; `docs/signal-spec.md` Core, Sine, Conventions; design log (o), (bb); AD-16 | Wording: records the ideal-plus-engine-algorithm form from (o), and adds seconds-to-samples, sine, per-layer AM and carrier laws, and PRNG to the list. |
| AD-20 | lock | CLAUDE.md Signal facts; PRD FR-9; plan Signal architecture, Test thresholds; design log (e), (i); memlog AD-20 decision; epics S3.1, S3.2 | Wording: the two binaural carriers are exempt from each other (not the whole binaural layer), spacing is per ear after the 3D renderer, both rules are checked along rate curves, notch schedule named. Phase 1 and 2 notes go to deferred-work. |
| Stack | change | `toolchain.json`; `pyproject.toml`, `uv.lock`; design log (y), (aa); web checks listed in reviewer B's Stack findings (2026-11-04) | Rows now record what the repo pins (LLVM 23.1.4, Apple clang 17.0.0, NDK r30, Ninja 1.13.2, pytest 9.2.0, PyYAML 6.0.3, exact CI labels). Requirement changes: miniaudio floor 0.11.26 (contains the CVE-2026-32837 fix), Flutter floor 3.47.8 (security fixes in 3.47.2 and 3.47.8). |

## Audio's decisions (2026-11-04)

The "change" verdicts that alter what a decision requires were shown to Audio in plain language before they were applied. All four were approved as the reviewers proposed:

1. **AD-5:** apply reviewer A's rule. Coupled gamma is rejected when the theta reference is absent, at zero level, or at zero AM depth wherever gamma level and depth are non-zero; uncoupled gamma has constant depth. Updates the epics FR-3 line, S2.3 (rejection AC plus a must-fail fixture), S6.5, and SPEC CAP-4.
2. **AD-9, phone:** the engine library from the real Android app build must match the hashes on a physical phone before the Phase 0 part 2 stack spike closes. The hosted static NDK run stays the v0.1 proof.
3. **AD-9, rules:** apply reviewer B's full proposed AD-9 text (IEEE denormal mode restored on return, no explicit fma, no `long double`, float-to-integer clamp rule, x86-64 only, narrowed fallback with rule-4 review). Updates Stories 1.2, 1.4, 1.6, and Story 0.1's AC text (records the chosen alternative).
4. **Stack:** apply reviewer B's replacement Stack table (miniaudio 0.11.26 floor, Flutter 3.47.8 floor, rows for what the repo already pins).

No finding was rejected. Low-severity notes that need later work and have no story are entries in `_bmad-output/implementation-artifacts/deferred-work.md` (source: this review).

## Reviewer A: signal decisions AD-4, AD-5, AD-19, AD-20


Reviewer: fresh-context agent, no part in writing the spine. Date: 2026-11-04. Read-only review of the repo at branch `story/0-5-independent-review-of-the-pending-architecture-decisions` (baseline 921b53f).

Sources checked: `ARCHITECTURE-SPINE.md` (whole file, including Signal flow and Open Questions), `.memlog.md`, `reviews/review-adversary.md` (H5, H7, H25, H26), `prd.md` (glossary, FR-3, FR-4, FR-5, FR-9, FR-25, FR-27), `addendum.md`, `SPEC.md`, `thresholds-and-ranges.md`, `starter-recipes.md`, `CLAUDE.md` (Signal facts, Never, Rules), `docs/research-library.md`, `docs/design-log.md` (entries 2026-10-21, (b), (e), (i), (k), (m), (n), (o), (p), (r), (s), (t), (bb), (cc)), `docs/signal-spec.md` (Core and Sine sections as they exist now), `docs/project-plan.md` (Signal architecture, Test thresholds), `tests/tables/thresholds.tsv`, `epics.md` (Requirements, S1.2, S2.2, S2.3, S2.4, S2.5, S2.6, S3.1, S3.2, S4.5, S6.5, S6.6).

### Verdicts

| AD | Reviewer verdict | Summary |
| --- | --- | --- |
| AD-4 | lock | Mix order, binaural join point, master chain contents, and the idle limiter agree with CLAUDE.md, FR-4, FR-5, SPEC CAP-5 and CAP-6, design log (k) and (p), and S1.2 and S4.5. Two wording edits record the zero bound from (p). One low note on limiter latency for S4.5. |
| AD-5 | change (small) | The rejection condition checks theta depth and presence, not theta level. A recipe with coupled gamma and a theta reference held at zero level compiles, yet the reference has no waveform in the file. Proposed rule adds "at zero level" and states the uncoupled case. No invented value. Affects S2.3, the FR-3 line in epics Requirements, SPEC CAP-4. |
| AD-19 | lock | Sound and already in practice (signal-spec.md Core and Sine sections, vectors generated independently). Wording edits record design log (o) and (bb): the spec holds both an ideal formula and a bit-exact engine algorithm with an error bound, and the list should name the seconds-to-samples rule and the sine, which the spec and SPEC CAP-1 already contain. |
| AD-20 | lock | Values trace to design log (e) and (i) as declared placeholders; "including both binaural carriers" traces to (e) and the plan's Signal architecture. Wording edit: "the binaural pair are exempt" can be read as exempting the whole binaural layer; replace with "the two binaural carriers are exempt from each other", which is what (e) says. Record "post-3D" from the memlog. Low notes for Phase 1 and 2. |

### AD-4: Fixed mix order, binaural joins last, limiter stays idle

**Verdict: lock**, with two wording edits that only record what the sources already say.

#### Consistency

- CLAUDE.md Signal facts: binaural "must reach the output on its own dichotic path. It never passes through spatial, HRTF, ambisonic, reverb, or stereo-width processing." AD-4 rule and the Signal flow diagram (spine Structural Seed, `SUM --> BJ --> MC`) put the binaural join after every spatial and effect stage. Consistent.
- PRD FR-4: "joins the mix after every spatial, reverb, and width stage; only the master chain follows it"; "never sums or downmixes its output channels". AD-4 says the same. PRD glossary "Master chain: master gain and the final limiter. It processes left and right without mixing them." AD-4 matches.
- PRD FR-5 says the "final limiter ... meets the recipe's loudness target". AD-4 and AD-13 replace that with a stored loudness gain and an idle limiter. This was logged (design log (k)) and SPEC CAP-6 carries the new form, so the PRD wording is superseded, not contradicted. No action.
- Design log (p) sets the v0.1 bound to zero gain reduction; `thresholds.tsv` row `limiter-idle` is 0 samples with gain reduction; S4.5 asserts the tap is unity and output equals input times master gain, bit for bit. The spine Open Questions row already says "resolved for v0.1 as zero gain reduction, design log 2026-10-28 (p)". Consistent.
- S1.2 structural test: "theta reference, gamma PAC layer, stereo bus, binaural join, master chain (per-channel gain, stereo-linked limiter)" and "no stage type exists that mixes, sums, or swaps channels". This makes the rule enforceable from the first stub. S2.5 and S6.6 run the muted-ear isolation test at 0 Hz beat and across the Sleep cycle.

#### Enforceable and testable

Yes. Structural stage-list test (S1.2), output isolation test at 90 dB and 60 dB (`binaural-isolation-engine`, `binaural-isolation-master`), and the limiter-idle bit-for-bit assertion (S4.5). The adversary finding H7 (a stereo-linked limiter that acts imposes gamma-rate gain modulation on the binaural pair, which the muted-ear test cannot see) is closed for v0.1 by the zero bound in (p), which is stricter than H7's proposal.

#### Findings

1. **Wording, low.** AD-4 rule says "its gain reduction stays under a bound set in the design log". Record the current value so the AD is self-contained: append "(v0.1: zero gain reduction; master chain output equals input times master gain, bit for bit; design log 2026-10-28 (p))". Source: design log (p); thresholds-and-ranges.md, Limiter idle row.
2. **Wording, low.** The "Prevents" clause names limiter gain modulation reaching the binaural pair, but the rule does not say what happens when (p) is loosened in Phase 1. Suggested addition, recording (p)'s Revisit line: "Any non-zero bound is a design log entry with measured gain-reduction data (design log (p), Revisit)." This adds no new requirement; (p) already requires its own entry for loosening.
3. **Note for S4.5, low (no AD change).** If the signal spec's limiter uses lookahead, it delays every sample by the lookahead length even when idle. The (p) assertion "master chain output equals input times master gain, bit for bit" then holds only against delayed input, and AD-24's matched-latency rule and the coupling timing test must account for the delay. S4.5's §limiter should state the limiter's latency (zero, or a fixed sample count per sample rate) and the assertion should compare against input delayed by that count. Cheap to state now; changing the latency after golden files exist would shift every sample and invalidate every golden file. Source: epics.md S4.5; design log (p); spine AD-24.
4. **Note, low (no change).** A stereo-linked limiter couples the two channels' gain (one ear's level sets both ears' reduction). This is not channel mixing, and it is the right choice (equal gain keeps the binaural pair balanced), but it is the reason the idle bound matters. Nothing to change while the bound is zero.

#### Staleness

Nothing since 2026-10-27 makes AD-4 stale. Design log (y) to (dd) touch toolchain, CI, tables, sine, and wording only. `signal-spec.md` has no limiter section yet; S4.5 adds it, as AD-19 expects.

### AD-5: Gamma couples only to the theta reference

**Verdict: change (small).**

#### Consistency

- CLAUDE.md Signal facts: theta reference "exists in the file, so its phase is measurable. It is the only thing PAC couples to." Never list: "Couple gamma to a binaural beat. It has no waveform in the file." PRD FR-3: depth "follows the theta reference phase"; "An uncoupled setting produces gamma AM at constant depth"; "The validator rejects a coupled gamma PAC layer when the recipe has no theta reference." SPEC CAP-4 and S2.3: rejected "when the theta reference is absent or at zero depth". AD-5 matches all of these.
- Design log (b): coupling phase defined on the in-file theta reference envelope, uncoupled option allowed. (s) gives theta depth a 0 to 100 percent range and names the AD-5 zero-depth rejection as the reason a range is needed. Consistent.
- S2.3 has a structural test that the depth function takes theta phase as its only input; S2.5 sweeps binaural beat rate and phase and requires gamma peak times unchanged to the sample (`coupling-independence`, 0 samples). Enforceable and testable.

#### Findings

1. **Gap, medium: theta at zero level is not covered.** The rejection checks "theta reference is absent or at zero depth". A recipe whose theta reference layer is present at 75 percent depth but at zero level (layer gain 0, or a per-layer fade that reaches silence while coupled gamma keeps playing) compiles. The gamma envelope then follows a theta phase with no waveform in the file, which is exactly the failure CLAUDE.md names ("It exists in the file, so its phase is measurable"; "It has no waveform in the file"). The adversary review raised this as H25; the spine amendment (memlog, "AD-5 rejects coupled gamma when theta reference is absent or zero depth") adopted only the depth reading. H25's fix used an invented 20 dB ratio and a -80 dBFS floor; neither traces to a source, so this review does not propose them. Zero level needs no value: it is the same physical test as zero depth.
   - Starters stay valid: Relax ramps theta from silence over 10 min and gamma from silence over 2 min (design log (r), (t)); both are zero only at the first sample, where gamma is silent too, so the rule passes. Sleep has no gamma. Focus and Learn ramp in from silence together. S6.5 already measures coupling timing on taps before layer gain, so the timing test is unaffected.
   - Cost: S2.3 has not started (Epic 1 waits on this story). Adding one must-fail case now is a few lines; changing the rule after recipes and golden files exist means re-checking every published recipe.
2. **Wording, low: the uncoupled case.** "Gamma modulation depth is a function of the theta reference phase only" read literally contradicts FR-3's uncoupled setting (constant depth) and SPEC CAP-4. It also leaves out the static recipe parameters the depth function needs (shape, coupling phase, coupling depth). The proposed text separates the two cases.
3. **Note, low (Phase 2, no v0.1 change).** Adversary H26: under Orbit, gamma can sit mostly in one ear while theta is in both. AD-8 keeps theta out of the 3D stage, and v0.1 has no Orbit, so nothing breaks now. Revisit when Orbit width ranges are set (FR-27).
4. **Optional test strengthening, low.** S2.5 checks peak times unchanged to the sample. A stricter and simpler check is that the gamma tap is byte-identical when the binaural layer is toggled or its beat rate and phase are changed, since gamma shares no state with the binaural oscillators. Offer to S2.5; not required.

#### Proposed new rule text (AD-5 Rule)

> **Rule:** Coupled gamma modulation depth is a function of the theta reference phase only, plus static recipe parameters (shape, coupling phase, coupling depth), as defined per envelope shape in the signal spec. Uncoupled gamma has constant AM depth (FR-3). The schema has no coupling-target field. The validator rejects coupled gamma wherever gamma level and depth are both non-zero while the theta reference is absent, at zero level, or at zero AM depth. Test: changing the binaural beat rate or phase leaves every gamma envelope peak time unchanged to the sample.

Reason: CLAUDE.md Signal facts (theta reference "exists in the file, so its phase is measurable") and Never ("It has no waveform in the file"); PRD FR-3 (uncoupled setting at constant depth); design log (s) (zero-depth rejection rationale); adversary H25 (gap raised, partly adopted).

Affected `epics.md` stories:
- Requirements inventory, FR-3 line (line 33): "Coupled gamma is rejected when the theta reference is absent, at zero level, or at zero depth."
- S2.3 (Gamma coupled, smooth swell): the rejection AC becomes "Given coupled gamma with no theta reference, with the theta reference at zero level, or with theta reference AM depth at zero, wherever gamma level and depth are non-zero ... rejected with a named rule"; add a must-fail fixture where a theta-only fade to silence ends before a coupled gamma fade.
- S6.5 (Relax): add "and passes the AD-5 zero-level check from the first sample" (it should already pass; the AC proves it).
- SPEC CAP-4 success line and the spine's AD-5 text change to match. Needs a design log entry (Audio decides, per Story 0.5 spec).

### AD-19: One signal spec is the only source of formulas

**Verdict: lock**, with wording edits that record design log (o) and (bb) and the current spec.

#### Consistency

- SPEC CAP-1, epics Additional Requirements (Signal spec bullet), AD-16, and the header of `docs/signal-spec.md` all state the rule the same way. The spec exists with Core (phase accumulator, increment rule, seconds-to-samples) and Sine sections, worked vectors generated by `tools/signal_spec_vectors.py` from exact and 60-digit arithmetic, never from the engine, checked by a test against `tests/data/signal_spec_vectors.json` (signal-spec.md, Conventions). This is a working enforcement mechanism, and the S0.2 result (design log (bb)) shows it produced byte-identical engine output on four platforms.
- Design log (o) states it "refines AD-19 ... while it is REVIEW PENDING; the independent reviewer should check it". The refinement: the reference renders the ideal sine; the spec states the ideal waveform plus the engine approximation's error bound (-120 dBFS). `signal-spec.md` Sine section follows this exactly ("The Python reference never implements this algorithm; it renders the ideal sine").

#### Check of the (o) refinement and its margin arithmetic

- The principle is sound: a reference that ports the engine polynomial cannot catch a wrong polynomial. The spec still pins the engine's exact bits (Vectors: engine sine bits), so cross-platform identity is guarded separately from accuracy.
- Margin: (o) counts three layers adding coherently (+9.5 dB, 20 log10 3). A single tap can also combine several sine evaluations (gamma: carrier, gamma-rate AM, and a theta-phase depth function), so the worst case per tap is also about 3 errors, about -110.5 dBFS at full scale, still about 10 dB under -100 dBFS. Measured error is -145.0 dBFS (design log (bb)), about 35 dB under the bound in practice. **Low note:** when S2.2 to S2.4 write their sections, the margin statement should count sine evaluations per tap, not layers. No change to the -120 dBFS bound.

#### Findings

1. **Wording, low: "exact formulas evaluated per sample".** The spec now holds two kinds of definition: bit-exact engine algorithms (integer phase, increment rounding, the engine sine with pinned bits) and ideal mathematical functions the reference evaluates to within a stated bound. Proposed edit records (o): "For each transcendental the spec gives the ideal function, which the reference renders, and the engine algorithm with its error bound against the ideal and its pinned output bits."
2. **Wording, low: the list.** AD-19's list omits the seconds-to-samples rule and the sine, both of which are in `signal-spec.md` today and the first in SPEC CAP-1; it also omits the per-layer AM laws that S2.2 (§gamma) and S2.5 (§binaural: right carrier = left carrier + beat(t)) will add. Add "seconds-to-samples rule, sine (ideal and engine), per-layer AM and carrier laws". The closing sentence ("A shape or stage not in the spec does not exist") already makes the list non-exhaustive in effect, so this only aligns the text with CAP-1.
3. **Note, low.** The resampler and (from Phase 1) the counter-based PRNG (AD-14) also determine output. The resampler is listed; the PRNG is not. Phase 1 item; adding "PRNG" to the list now costs nothing.

#### Proposed wording (lock with edit)

> **Rule:** `docs/signal-spec.md` defines every formula evaluated per sample: envelope shapes and their 0 degree point, coupling depth function, bursts, per-layer AM and carrier laws, ramp and rate-curve laws, phase increment quantization and accumulator width, the seconds-to-samples rule, the sine, loop seam behavior, limiter, resampler, PRNG, internal block size, loudness measurement window, and the spectral component model per shape. For each transcendental it gives the ideal function, which the reference renders, and the engine algorithm with its error bound and pinned output bits (design log 2026-10-28 (o)). Engine and reference implement it; neither defines a formula of its own. A shape or stage not in the spec does not exist.

No stories change: the epics' per-story §section pattern already matches.

### AD-20: Carrier and spacing rules come from one spectral component table

**Verdict: lock**, with wording edits.

#### Consistency and traceability

- Carrier rule: "at least 4 times" matches CLAUDE.md Signal facts, PRD FR-9, plan Test thresholds (provisional), design log Current state (`carrier-rule`, provisional). S1.3 and S2.6 (worst case over a rate curve, must-fail gamma curve) enforce it.
- Spacing value 50 Hz: design log (e), declared placeholder; `spacing-rule` row. Component threshold 40 dB: design log (i), declared placeholder; `spectral-component-level` row. The research library has no spacing or critical-band source; both values are declared placeholders with a Phase 0 owner (PRD §11 Q3), which CLAUDE.md rule 3 allows when declared. Not invented.
- "Computed analytically ... a shape with no component model is rejected": matches SPEC CAP-1 and CAP-9, epics FR-9, S3.1 (analytic table per ear and per layer, cross-checked against reference spectra, must-fail dropped side frequency), and S3.2 (closed-form worst case over curves, exactly 50 Hz passes).
- "including both binaural carriers": CLAUDE.md does not say this in so many words, but it traces to design log (e) ("to stop one layer from placing the other ear's binaural carrier in this ear"), the 2026-10-21 baseline entry, and plan Signal architecture ("If the theta reference and the binaural layer shared a carrier, the theta layer would put the right-ear frequency into the left ear"). For diotic layers (every v0.1 layer except the binaural pair) the per-ear check already implies it: a component present in both ears must clear the left carrier in the left ear and the right carrier in the right ear. It also keeps the muted-ear isolation measurement (FR-4) free of other layers at the muted carrier's frequency. Consistent, stricter only for a future non-diotic layer.

#### Findings

1. **Wording, medium (lock with edit): exemption clause.** AD-20 copies CLAUDE.md's "a layer's own components and the binaural pair are exempt" right after "including both binaural carriers". Read quickly, "the binaural pair are exempt" sounds like the binaural layer is exempt from the spacing rule altogether, which contradicts the preceding clause and the Sleep checks (S6.6 "spacing rule between the binaural pair and the theta reference"). Design log (e) gives the intended meaning: the binaural pair is exempt because "its carriers never share an ear", that is, the two binaural carriers are exempt from each other. Proposed text uses that meaning. It changes nothing a validator does; S3.2 and the must-fail 250/256 Hz fixture are unaffected. CLAUDE.md is the user's rules file and is not edited here; the reviewer suggests Audio consider the same clarification there.
2. **Wording, low: post-3D.** The memlog AD-20 decision says "Spacing checked per ear on post-3D output". The rule text drops it. From Phase 2 the 3D renderer changes each ear's levels and adds slow motion side frequencies to gamma, so the per-ear table must model what each ear receives after it. Record it: "per ear, on the signal each ear receives after the 3D renderer". No v0.1 effect (no 3D stage).
3. **Wording, low: carrier rule over curves.** AD-20 says "the validator checks them across the whole session, including along rate curves", where "them" grammatically means spectral components. S2.6 already checks the carrier rule at a curve's worst case. Make it explicit: "both rules are checked across the whole session, including along rate curves".
4. **Note, low (Phase 1): stems.** Tone zone stems are broadband and have no analytic component model. Read literally ("any spectral component of one layer ... any of another layer"; "A shape with no component model is rejected"), every stem recipe would be rejected. The intended design is that FR-25's carrier guard protects carriers from stems. Before Phase 1, state that the spacing rule applies between Core layers (and any Tone source with a component model), and that stems are handled by the carrier guard. Deferred-work candidate.
5. **Note, low (Phase 1): "static data".** Binaural carriers may follow a rate curve (Sleep right ear moves over 100 to 103 Hz), so a single static notch frequency cannot follow them. "Static data" should mean a precompiled notch schedule (frequency per time segment, from the component table), as adversary H10 proposed and the memlog calls "the compiled carrier-guard notch schedule". Wording only; Phase 1.
6. **Note, low (Phase 2).** "Within 40 dB of a layer's strongest line" needs a per-ear reading once Orbit makes gamma louder in one ear: the strongest line in that ear, or overall. S3.1 or the Phase 2 component model should say which. No v0.1 effect.
7. **Note, low (stale value, harmless).** `starter-recipes.md` says the Sleep theta reference carrier "must be at least 156 Hz to clear the 100/103 Hz binaural pair". That figure comes from entry (m)'s 3 Hz theta rate; with the steady 2 Hz rate from (n), the bound is 155 Hz (103 + 50 + 2). The 450 Hz carrier passes either way and the stricter figure is safe. Fix when that file is next touched.

#### Proposed wording (lock with edit)

> **Rule:** Every modulated carrier is at least 4 times its modulation rate. In each ear, on the signal that ear receives after the 3D renderer, at least the spacing value (50 Hz placeholder, design log (e)) separates any spectral component of one layer from any of another layer, including both binaural carriers; a layer's own components are exempt, and the two binaural carriers are exempt from each other, since they never share an ear (design log (e)). Spectral components (within 40 dB of a layer's strongest line, placeholder, design log (i)) are computed analytically from the spec's component model; the validator checks both rules across the whole session, including along rate curves. A shape with no component model is rejected. The compiler writes the carrier guard's notch schedule into the plan as static data.

No v0.1 stories change. Suggested S3.2 wording edit (optional, matches the above): "exempting a layer's own components and the two binaural carriers from each other".

### Cross-cutting notes

- No banned names or em dashes were found in the four AD texts.
- Nothing in design log (y) to (dd) or the current `signal-spec.md` makes any of the four decisions stale; (bb) is direct evidence that the AD-19 method works.
- Only AD-5 changes what a story must test. Its cost now is one AC and one must-fail fixture in S2.3; its cost later is re-validating every recipe compiled under the looser rule.

## Reviewer B: AD-9 and the Stack table

Reviewer: fresh-context agent, no part in writing the spine. Date: 2026-11-04.

Sources checked: spine (whole), PRD FR-6, FR-15, FR-30, FR-35, NFRs, phase table; SPEC v0.1; CLAUDE.md; docs/research-library.md; docs/signal-spec.md; design log (i), (j), (y), (z), (aa), (bb), Current state; toolchain.json; ci/hash_tolerance.json; ci/hash_expected.json; .github/workflows/full.yml, fast.yml; cmake/Pins.cmake; CMakeLists.txt; CMakePresets.json; pyproject.toml; uv.lock; .python-version; docs/ci-setup.md; tools/engine_symbol_denylist.json; tools/check_compile_flags.py; tools/check_fp_pragmas.py; deferred-work.md; epics.md; reviews/*.md; web checks listed under each finding.

### Verdicts

| AD | Reviewer verdict | Summary |
| --- | --- | --- |
| AD-9 (bit-exact across platforms) | change (narrow) | The decision itself holds and S0.2 confirms it: the sine is byte-identical on all four platforms with no fallback (design log (bb), run 41648370470). The rule text must change in four places: record the actual Android method and runner layout (design log (aa)), name the denormal mode (IEEE, no flush, restored on exit), narrow the fallback to a cited (platform, component) entry that also proves the cause lies outside the AD-9 code rules, and close three enforcement gaps (`long double`, explicit `fma`, constant-folded libm calls) plus one rule gap (float-to-integer conversion of out-of-range values) in named stories. |
| Stack table | change | Most rows only need to record what `toolchain.json` and `uv.lock` already pin (design log (y), (aa)). Two rows change what is required for security reasons: miniaudio moves to the tagged 0.11.26 release (it contains the CVE-2026-32837 fix commit), and the Flutter floor moves from 3.47.1 to 3.47.8 (3.47.2 and 3.47.8 are security hotfixes). Ninja, LLVM, Apple clang and Xcode, pytest, PyYAML are missing rows; "pinned in the first build story" is stale; the CI row does not match the runners. |

Severity labels: high (the rule is wrong or unenforced where it matters for v0.1), medium (a real gap that a later story must close), low (wording, staleness, or a future-phase note).

### AD-9: the engine is bit-exact across platforms

#### What the repo shows

- Compile flags: `-ffp-contract=off` project-wide via `add_compile_options` (`CMakeLists.txt` lines 23 to 42), checked on every engine source by `tools/check_compile_flags.py`, including fast-math, value-changing fp options, and denormal flags other than `ieee` (design log (z)). Runs in both fast jobs and in all four full-tier platform jobs (`full.yml` "Compile-flag and symbol checks"). Must-fail cases exist.
- Pragmas: `tools/check_fp_pragmas.py` bans fp pragmas in `engine/`, including `FENV_ACCESS` and `fenv_access` (design log (bb)).
- libm: `tools/engine_symbol_denylist.json`, family "libm transcendental", checked with `llvm-nm` on the built engine library on every platform (design log (z)). `sqrt` allowed (correctly rounded, IEEE 754).
- 64-bit phase: `docs/signal-spec.md` Core, Phase accumulator and increment rule, with test vectors that the engine test and the Python test each pass (design log (bb)).
- arm64-v8a: `CMakePresets.json` android preset sets `ANDROID_ABI=arm64-v8a`; `tests/python/test_ci_workflows.py` line 399 asserts it in the CMake cache.
- Hash compare: `tools/hash_compare.py` compares each platform exactly with `windows-x64` and with `ci/hash_expected.json`; tolerance only per (platform, component) entry in `ci/hash_tolerance.json` citing a design log entry; bound -100 dBFS strictly below (design log (aa)). `ci/hash_tolerance.json` `entries` is empty.
- S0.2 result: `probe-arith`, `sine-44100`, `sine-48000` byte-identical on Windows x64 (clang-cl), Windows arm64 (clang-cl), macOS arm64 (Apple clang), Android NDK arm64 (static binary on hosted `ubuntu-24.04-arm`), full run 41648370470 (design log (bb)).

#### Question 1: should the -100 dBFS fallback and its scope stay, narrow, or change?

**Answer: keep the fallback, narrow its scope, and fix its stale timing words.** (medium)

Reasons:

1. **Keep it.** FR-6 (PRD 4.1, second bullet) and design log (j) make the fallback part of the decision, and later components (stem decoder, resampler, effects, 3D renderer; AD-9 Binds) have not been tried yet. The fallback costs nothing while `entries` is empty, and Story 6.1 (epics.md, "Given a platform the hash compare config runs in -100 dBFS tolerance mode") and AD-15 already handle a fallback golden. Removing it would force a PRD change for no benefit.
2. **Narrow the scope to what the repo already enforces.** The spine says "a component"; the repo enforces a (platform, component) pair with a cited design log entry (design log (aa); `ci/hash_tolerance.json`). The spine should say so, so nobody reads it as "a component may go tolerant on every platform".
3. **Narrow eligibility.** S0.2 shows the method works for pure binary64 arithmetic on all four toolchains. Every v0.1 Core component (envelopes, AM, coupling depth, rate curves, limiter, 24-bit rounding) is the same kind of arithmetic under the same flags. A Core mismatch therefore means an AD-9 rule was broken (a contraction, a libm call, an out-of-range conversion), not a platform limit. Letting such a mismatch fall back would hide a bug behind a log entry. The fallback entry should have to show that the cause lies outside the AD-9 code rules (for example in vendored third-party code under AD-7, or a hardware behavior), and that no AD-9 check missed a violation.
4. **A fallback entry changes a threshold, so it needs review.** Design log (aa) already treats the tolerance entry as a cited change; under CLAUDE.md rule 4 and rule 6 a new entry is a big decision (it relaxes `cross-platform` from 0 differing hashes to `cross-platform-fallback`, design log (cc)). Say so in the rule.
5. **"The Phase 0 spike" is stale.** S0.2 was the spike for the sine. The decoder and resampler arrive with stems in Phase 1 (PRD phase table; spine Stack "Stem codec"). The proof happens in the story that adds each component.

Low note: hash_expected.json still holds only `probe-arith`; the sine hashes are compared only against `windows-x64` in the same run (deferred-work.md, Story 0.2 finding B6). A toolchain bump that moves all four platforms alike would pass the cross-platform check. The signal spec's "Vectors: engine sine bits" catch this for the sine today, and golden files catch it from Epic 6, so this is low; the deferred entry should be closed in Story 1.6 at the latest, when the first non-sine fixture joins the check (epics.md, Rules for Every Story, definition of done).

#### Question 2: does the hosted static NDK binary satisfy "an Android NDK arm64 build on emulator or device"?

**Answer: it satisfies the purpose of the rule for v0.1, not its letter; change the text to match the repo, and keep a device run owed by the Phase 0 part 2 stack spike.** (medium)

Why it satisfies the purpose. The engine is pure arithmetic with no OS calls (AD-1; symbol denylist). For such code the result is fixed by four things, and the hosted run covers each:

- **The compiler and flags.** Same NDK r30 clang 21.0.0, same CMake preset, API level 21, arm64-v8a, checked by `cmake/Pins.cmake` and the flag check on that very build (`full.yml` android-build job).
- **The instruction set.** Real AArch64 hardware. IEEE 754 binary32 and binary64 add, subtract, multiply, divide, sqrt, and conversions are fully specified for Armv8-A, so a Neoverse server core and a phone's Cortex core give the same bits. The Armv8.7 alternate behaviors (FEAT_AFP) apply only when FPCR.AH or FPCR.FIZ is set, which nothing sets by default. Reciprocal estimate instructions appear only with `-mrecip`, which the flag check bans.
- **The FP control state at thread start.** Android uses the Linux kernel, which starts threads with FPCR zero (round to nearest, no flush) on both. 
- **libc.** The static binary links bionic. The engine calls no libm transcendental, so bionic's libm does not touch output; `sqrt` is one instruction.

An emulator would be worse, not better: an arm64 Android emulator on an x86 host runs AArch64 FP through QEMU's software floating point, an extra layer that real hardware does not have; on an arm64 host it is the same hardware the hosted run already uses.

Residual risks the hosted run does not cover:

1. **The host thread's FP state.** In the app, the engine runs on an AAudio callback thread through miniaudio, and audio frameworks may set flush-to-zero on that thread. The static probe runs on a fresh process thread. Covered by the AD-9 clause "sets its own denormal mode on entry" and Story 1.2's test ("renders identically after the host sets a different mode"), provided the mode is named (see Q3).
2. **The shipping build is not the probe build.** The app builds the engine as a shared library through Gradle; Flutter's Android Gradle plugin defaults its own `ndkVersion` and may add flags. If that build uses another NDK or drops `-ffp-contract=off`, the CI hash proves nothing about the APK. This is the larger risk and the reason a device run still matters: it should run the library from the real app build, not only the CI probe.
3. **Dynamic bionic.** Dynamic linking changes no arithmetic, but a libm function that slips past the denylist (for example a non-transcendental with an implementation-specific result) would come from the device's libm, not from the NDK's static copy. Low, since the denylist and the IEEE-exact nature of the remaining libm functions cover it.

Evidence: design log (aa), "Android, chosen alternative"; deferred-work.md, "Run the NDK arm64 hash probe on a physical Android phone"; PRD phase table, "Phase 0 part 2: stack spike ... isolation test passes on device"; PRD FR-30 (real phone needed for background playback anyway).

Story 0.1's ACs in epics.md still say "with the NDK hash binary run on a physical Android device" and describe a self-hosted PC runner with a USB phone. Its own later AC ("or the chosen alternative ... is recorded in the design log and running") is what the repo met. Low: epics.md Story 0.1 text should record the alternative so a later reader does not see a done story with an unmet AC.

#### Question 3: is every other clause enforced or owed by a named story?

| AD-9 clause | Status | Evidence | Gap and owner |
| --- | --- | --- | --- |
| No libm for sine and transcendentals | enforced | denylist, `check_engine_symbols.py`, all four platforms (design log (z)) | **Medium gap:** the check sees only undefined symbols. Clang folds a libm call with constant arguments at compile time using the build host's own math library, leaving no symbol; the NDK build folds on an x86-64 Linux host, the others on Windows or macOS hosts, so folded values can differ while every check passes. Fix: a source scan of `engine/` for `<cmath>` transcendental names (same style as `check_fp_pragmas.py`), owed by Story 1.6, which already extends the denylist. |
| Engine sine engine-owned | enforced | signal spec Sine, engine sine bit vectors, -145.0 dBFS measured (design log (bb)) | none |
| 64-bit integer phase accumulators | enforced | signal spec Core, test vectors (design log (bb)) | none |
| No `long double` | **not enforced** | only a comment in `engine/src/core/phase.hpp` line 5 | **Medium gap.** `long double` is 64-bit on Windows and Apple, 128-bit quad on Android arm64 and Linux arm64, so it is exactly the case where Android alone would differ. Fix: (a) source scan for `long double` and `L`-suffixed float literals in `engine/`; (b) add the compiler-rt quad helpers (`__addtf3`, `__subtf3`, `__multf3`, `__divtf3`, `__extenddftf2`, `__extendsftf2`, `__trunctfdf2`, `__trunctfsf2`, `__fix*tf*`, `__float*tf*`, `__(eq|ne|lt|le|gt|ge|unord)tf2`) to the denylist; they show up only on the Android and Linux arm64 builds, which is where it matters. Owner: Story 1.6 (or Story 1.2, the next engine code). |
| `-ffp-contract=off`, no fast-math, CI fails if missing | enforced | design log (z); must-fail cases; arm64 contraction must-fail job (design log (aa)) | **Low gap:** an explicit `std::fma` or `fma` call is not a contraction, so neither check sees it. The signal spec forbids fused multiply-add (`docs/signal-spec.md` line 9). Add `fma[fl]?` to the denylist, Story 1.6. |
| Engine sets its own denormal mode on entry | owed | Story 1.2 AC: "the engine sets its own denormal mode on entry, verified by a test that renders identically after the host sets a different mode" | **Medium:** the rule names no mode. It must be IEEE (no flush-to-zero, no denormals-are-zero): the flag check already forces the compiler's assumption to `-fdenormal-fp-math=ieee` (design log (z)), the Python reference computes with IEEE denormals (AD-16), and a flush mode at run time would disagree with compile-time folding. The engine should restore the host's mode on return, so the host's own code is unchanged (AD-1 purity). Setting the mode uses the x86 MXCSR and the AArch64 FPCR, so the denylist must allow those intrinsics, while `fesetenv` and similar stay out of `engine/` (the pragma check bans `FENV_ACCESS`). Performance note (low): IEEE denormals can be slow on x86 in decaying filter or reverb tails; the Tone zone must avoid producing them arithmetically, not by flushing. Owner: Story 1.2. |
| Android ships arm64-v8a only | enforced for CI builds; owed for the app | `CMakePresets.json`; `test_ci_workflows.py` line 399 | The APK's `abiFilters` belong to the Phase 3 app build; no story exists yet (epics.md covers v0.1 only). Low. |
| Stems decode through an engine-owned decoder | owed | AD-7 defines "engine-owned"; Stack "Stem codec" | Phase 1 stems; no story yet. Acceptable, since v0.1 has no stems (SPEC v0.1 scope). Low. |
| CI renders on four platforms and compares hashes | enforced | full.yml; design log (aa), (bb) | Text mismatch (Q2) and "Linux or Windows arm64 (Clang)": the repo uses Windows arm64 clang-cl for the hash; Linux arm64 runs only the NDK probe and the contraction must-fail. Low, wording. |
| Fallback per component, cited | enforced (per platform and component) | `ci/hash_tolerance.json`, design log (aa) | wording (Q1) |

Gaps not in the rule text at all:

- **Float-to-integer conversion of out-of-range values or NaN** (medium). C++ makes it undefined behavior, and the hardware differs: x86-64 `cvttsd2si` returns the "integer indefinite" value, AArch64 `fcvtzs` saturates. The 24-bit WAV writer (Story 1.4, "rounding to 24 bits with no dither per the signal spec") converts floats to integers; any sample above full scale would give different bytes on x64 and arm64. The phase increment rule already handles its own domain (`docs/signal-spec.md`, Phase increment rule, Domain). Fix: the rule says every float-to-integer conversion is preceded by a clamp to the target range and a NaN check, defined in the signal spec; Story 1.4 writes that section. Deferred-work.md already asks to extend the flag check to `cli/` when the WAV writer lands (Story 1.4 or 1.6).
- **x86 means x86-64 only** (low). The freshness review (F9 item 4) asked for "no 32-bit x86" because x87 extended precision breaks the method. Every current target is x86-64 or arm64, so this is a one-word clarification.
- **NaN payloads** (low). Freshness review F9 item 5. Already covered by NFR12 and Story 5.2 (NaN or infinite values, zero tolerance), so hashes only ever compare valid output. No change.

Earlier review findings: freshness F8 (CI did not test phone toolchains) and F9 items 1 to 3 and 6 are addressed in the spine and repo (Android NDK and Apple clang jobs, `-ffp-contract=off` with check, `long double` and denormal clauses, arm64-v8a, engine-owned decoder defined in AD-7). F9 item 2 (`long double`) is in the text but not enforced. F9 item 3 asked to "name a mode"; still open. reconcile-rules finding on AD-15 versus the fallback is addressed (AD-15 now names the tolerance for fallback components). Rubric finding 13 (Android and iOS stand-in builds) is addressed.

Low, PRD drift: PRD §5 NFR "Determinism" still reads "bit-exact synthesis core across platforms (target)" and "within -100 dBFS across platforms (provisional floor)", while FR-6 records the whole-engine decision. Once AD-9 locks, the NFR row should match FR-6.

#### Proposed new AD-9 text

> ### AD-9: The engine is bit-exact across platforms
>
> - **Binds:** all engine code: Core, stem decoder, resampler, built-in effects, 3D renderer (FR-6, FR-35)
> - **Prevents:** PC, Android, and iOS producing different samples for the same plan.
> - **Rule:** Engine code uses engine-owned math for sine and every transcendental (no libm), 64-bit integer phase accumulators, no `long double`, and no explicit fused multiply-add. Every float-to-integer conversion clamps to the target range first and never receives NaN, by a rule in the signal spec. Every toolchain compiles the engine with `-ffp-contract=off` and no fast-math (clang-cl through `/clang:`), and CI fails if the flags are missing. On entry to each render call the engine sets IEEE denormal handling (no flush to zero, no denormals-are-zero) and restores the host's mode on return. x86 targets are x86-64 only; Android ships arm64-v8a only. Stems decode through an engine-owned decoder (AD-7), never the OS. CI renders on Windows x64 (clang-cl), Windows arm64 (clang-cl), macOS arm64 (Apple clang), and Android NDK arm64 (the NDK build, linked statically, run on hosted arm64 Linux; design log 2026-11-02 (aa)), and compares hashes exactly against Windows x64 and against the expected hashes in the repo. Before the Phase 0 stack spike closes, the engine library from the real Android app build matches the same hashes on a physical phone. A component that cannot be exact on a platform falls back to the -100 dBFS tolerance for that platform and component only, through a `ci/hash_tolerance.json` entry that cites a design log entry; the entry shows the cause lies outside these rules (a Core zone mismatch is a bug, not a fallback) and gets the independent review CLAUDE.md rule 4 requires.

Design log entry needed: a new entry superseding the AD-9 wording points of (j) and stating the S0.2 result, the narrowed fallback, the named denormal mode, and the Android method; cite (aa), (bb), (z), this review.

Stories affected (epics.md):

- **Story 1.2:** the denormal AC names the mode: "the engine sets IEEE denormal handling on entry and restores the host's mode on return, verified by a test that renders identically after the host sets flush-to-zero, and by a test that the host's mode is unchanged after the call".
- **Story 1.4:** the signal spec section for 24-bit rounding defines clamp, NaN handling, and the tie rule before conversion; add a must-fail fixture with a sample above full scale.
- **Story 1.6:** extend the denylist with the quad-precision helpers and `fma[fl]?`, and add a source scan of `engine/` for `long double`, `L`-suffixed float literals, and `<cmath>` transcendental names, each with a must-fail fixture; close the deferred `ci/hash_expected.json` sine entry.
- **Story 0.1 (done):** AC text records the hosted static NDK run as the chosen alternative (no work).
- **Story 6.1:** no change (fallback goldens already handled).
- **Phase 0 part 2 stack spike (no story yet):** owns the physical-phone hash run of the app-built engine library (deferred-work.md entry).

### Stack table

#### Findings

Web checks made 2026-11-04.

| Row | Spine says | Repo pins | Current reality | Severity, finding |
| --- | --- | --- | --- | --- |
| C++ | C++20 | `CMAKE_CXX_STANDARD 20`, required (CMakeLists.txt lines 9 to 10) | fine | none |
| Clang | "NDK r30; others pinned in the first build story" | LLVM 23.1.4 (clang-cl Windows x64 and arm64, clang Linux), Apple clang 17.0.0.17000013 with Xcode 16.4, NDK r30 with clang 21.0.0 and API 21 (`toolchain.json`; design log (y), (aa)); checked by `cmake/Pins.cmake` | LLVM 23.1.5 released 2026-11-03, release page lists no security fix (https://github.com/llvm/llvm-project/releases). NDK r30 is the latest stable (https://github.com/android/ndk/releases). App Store uploads need Xcode 26 or later since 2026-04-28 (https://developer.apple.com/news/upcoming-requirements/) | low: stale text; split into three rows with exact pins. Keep LLVM 23.1.4: any compiler bump must pass the full-tier hash check and get a design log line, and 23.1.5 has no security reason. Xcode 16.4 is fine for the macOS hash job, but must be re-pinned to an App Store accepted Xcode before any iOS build (Phase 4), and that re-pin reruns the hash check. |
| CMake | 4.4.5 | 4.4.5 with SHA-256 per platform | 4.4.5 is the latest stable; 4.5.0-rc2 in testing (https://cmake.org/download/) | none |
| Ninja | missing | 1.13.2 with SHA-256 per platform | latest (https://github.com/ninja-build/ninja/releases) | low: missing row |
| Catch2 | 3.16.1 | 3.16.1, source archive SHA-256 | latest (https://github.com/catchorg/Catch2/releases) | none |
| miniaudio | "0.11.25 at commit 1df46ae or later" | not vendored yet (hosts only, Phase 1) | 0.11.26 released 2026-10-31 (https://github.com/mackron/miniaudio/releases). GitHub compare `1df46ae...0.11.26` is "ahead by 72, behind by 0", so 0.11.26 contains the CVE-2026-32837 fix (https://osv.dev/vulnerability/CVE-2026-32837 lists 1df46ae as the fix and 0.11.25 and earlier as affected) | medium: pin the tagged release 0.11.26 or later instead of a bare commit on top of a vulnerable tag; keep `MA_NO_DECODING` and `MA_NO_ENCODING` (AD-23). |
| Python | 3.14 | `.python-version` 3.14; `requires-python ==3.14.*` | 3.14.10 (2026-10-25) is current, an expedited security release (eMudhra CA keys); 3.14.9 updated bundled pip for the same incident (https://www.python.org/downloads/) | low: the patch level floats under uv. It cannot change engine bytes (the reference is compared at -100 dBFS and NumPy is pinned), but the dev PC may sit on an older 3.14.x. Record "3.14 (uv-managed, latest patch)" and refresh with `uv python upgrade` occasionally. |
| uv | 0.13.6 | 0.13.6 (`toolchain.json`; `setup-uv` reads it) | 0.13.7 (2026-11-03) has no security fix; 0.13.4 and 0.13.5 carried the certificate fixes, so 0.13.6 includes them (https://github.com/astral-sh/uv/releases) | none |
| NumPy | 2.5.4 | 2.5.4 in `pyproject.toml` and `uv.lock` | latest (https://pypi.org/project/numpy/) | none |
| pytest | "pinned in the first build story" | 9.2.0 (`pyproject.toml` dev group, `uv.lock`, `toolchain.json`; design log (y)) | 9.2.0 (2026-10-27) is the latest (https://pypi.org/project/pytest/) | low: stale text |
| PyYAML | missing | 6.0.3 (dev group) | used by tests | low: missing row |
| Flutter | "3.47.1 or later 3.47.x; re-pin at the Phase 0 spike" | not used yet | 3.47.9 is the newest 3.47.x; 3.47.2 fixed a libpng vulnerability and 3.47.8 is security advisory GHSA-frr6-h895-5pxp (eMudhra CA keys); no 3.50 yet (https://github.com/flutter/flutter/blob/stable/CHANGELOG.md, https://docs.flutter.dev/release/release-notes) | medium: the floor 3.47.1 allows two releases with known security fixes missing. Floor becomes 3.47.8; the spike pins an exact version, and the Android build pins the NDK to the `toolchain.json` NDK rather than Flutter's default (see AD-9 Q2 risk 2). |
| Stem codec | "Opus (fixed-point libopus build, vendored) or FLAC; proven bit-exact in Phase 0" | not used yet | libopus 1.6.1 (2026-01-14) is current (https://opus-codec.org/downloads/) | low: "Phase 0" is wrong for stems (Phase 1); name the proof point as the story that adds stem decoding, pin the libopus version then. |
| CI | "windows x64, ubuntu-24.04-arm or windows-11-arm, macOS arm64, Android NDK arm64" | fast: `windows-2025`, `ubuntu-24.04`; full adds `windows-11-arm`, `macos-15`, NDK build on `ubuntu-24.04`, NDK probe and contraction must-fail on `ubuntu-24.04-arm`; all hosted, public repo, $0 spending cap (design log (aa); docs/ci-setup.md) | runner labels exist and are free for public repos | low: record exact labels and the no-self-hosted decision. |

Missing concept (low): the Stack table has no line saying `toolchain.json` is the single source of versions (design log (y)). Adding it stops the spine and the file from drifting again, which is exactly what happened to the pytest and Clang rows.

#### Proposed replacement Stack table

| Name | Version |
| --- | --- |
| Version source | `toolchain.json` (tools, with download SHA-256), `pyproject.toml` and `uv.lock` (Python packages); CMake configure fails on a CMake or compiler mismatch (design log 2026-11-02 (y), (aa)). A change needs a design log line and a passing full-tier hash check. |
| C++ (engine, CLI) | C++20 |
| LLVM: clang-cl (Windows x64 and arm64), clang (Linux) | 23.1.4 |
| Apple clang (macOS arm64) | 17.0.0.17000013, Xcode 16.4 on `macos-15`; re-pin to an App Store accepted Xcode (26 or later) before any iOS build |
| Android NDK (arm64-v8a) | r30 (30.0.16248370), clang 21.0.0, API level 21; the app build uses the same NDK |
| CMake | 4.4.5 |
| Ninja | 1.13.2 |
| Catch2 (C++ tests) | 3.16.1 |
| Python (reference renderer, signal tests) | 3.14, latest patch managed by uv |
| uv | 0.13.6 |
| NumPy | 2.5.4 |
| pytest | 9.2.0 |
| PyYAML (tests) | 6.0.3 |
| miniaudio (host audio I/O only) | 0.11.26 or later 0.11.x (contains the CVE-2026-32837 fix), `MA_NO_DECODING`, `MA_NO_ENCODING`; pinned exactly in the first host story |
| Flutter (designer and apps, via dart:ffi) | 3.47.8 or later 3.47.x (security fixes in 3.47.2 and 3.47.8); exact pin at the Phase 0 stack spike |
| Stem codec | Opus (fixed-point libopus build, vendored, current 1.6.1) or FLAC; proven bit-exact under AD-9 in the story that adds stem decoding (Phase 1) |
| CI | GitHub Actions, hosted runners only, public repo, $0 spending cap. Fast: `windows-2025`, `ubuntu-24.04`. Full adds `windows-11-arm`, `macos-15`, NDK build on `ubuntu-24.04`, NDK probe and contraction must-fail on `ubuntu-24.04-arm` (design log 2026-11-02 (aa)) |

Stories affected (epics.md): none in v0.1 need new work. Additional Requirements ("pytest pinned", "Clang toolchains pinned (clang-cl, Apple clang, NDK r30)") can cite the table. The first host story (Phase 1 designer) pins miniaudio; the Phase 0 part 2 stack spike pins Flutter and its NDK. Design log: one entry recording the miniaudio and Flutter floor changes with the advisory links above, and the Current state "Toolchain pins" row gains Apple clang and NDK (already in the "Full-tier toolchain pins" row).

### Other spine edits that follow (low)

- Deployment diagram: "CI: x64 and arm64 matrix" is fine; "PHONE: Real Android phone: Phase 0 spike" matches the proposed AD-9 device run. No change.
- Open Questions row "Independent review of AD-4, AD-5, AD-9, AD-19, AD-20 and the Stack": update when Story 0.5 closes.
- Header `updated: '2026-10-27'` should change with the edits.
