# PRD Quality Review: Arcani

## Overall verdict

This is a strong internal-tool PRD: it has a real thesis (transparent, reproducible, honestly described audio), a glossary that downstream work can use, gate-based phases with counter-checkpoints, and numeric pass conditions on most v0.1 FRs. The risk is in the details that v0.1 stories will lean on hardest. FR-13 lists several assertions with no threshold anywhere. "Byte-identical" and "renders identically" are not scoped to one machine or across platforms. A few terms ("gain change", "gamma envelope peak", "flagged") can be read in ways that make the tests contradict the signal design. None of this needs a rethink. It needs about a dozen targeted edits before the architecture and story steps.

## Decision-readiness: adequate

Decisions are stated as decisions, not as considerations. The mono and speaker trade-off in §7 says what is given up ("Listeners with hearing in one ear and speaker playback are a small group") and the §10 risk table accepts it openly. The §4.1 "Honesty note" names the biggest scientific tension head-on ("Whether coupled sound produces coupling in a listener's brain is untested"). The nine items in §11 are genuinely open, not rhetorical.

The gap is linkage. The Open Questions do not say which gate each one blocks or who closes it, and several of them sit directly under v0.1 FRs. OQ1 (theta default) feeds FR-16, OQ3 (spacing value) feeds FR-9, OQ4 (gamma default and coupling phase) feeds FR-8, and OQ5 (loudness mapping) feeds FR-5. The v0.1 gate in §8 says only "Phase 0 research confirms thresholds and locked ranges", so a reader cannot tell whether v0.1 can pass with these still open (as provisional values) or must wait for them. The PRD has no `[NOTE FOR PM]` callouts. Given a sole designer and producer that is acceptable, but the tensions listed below would have been the right places for them.

### Findings

- **[medium]** Open Questions not tied to gates (§11, §8 Phase 0 row): OQ1, OQ3, OQ4 and OQ5 constrain v0.1 FRs, but nothing says whether v0.1 ships on provisional values or waits for them. *Fix:* Add a "Blocks" column to §11 (for example "v0.1: provisional OK, must close before Phase 1 gate"), and add a clause to the v0.1 gate saying which questions may stay open.
- **[low]** No PM callouts at real tensions (whole document): the free tier versus offline (see Strategic coherence) and non-sine binaural (see Done-ness) are unresolved tensions with no callout. *Fix:* Either resolve them inline or tag them `[NOTE FOR PM]`.

## Substance over theater: strong

There is very little furniture. The Vision (§1) could not be swapped into another entrainment-app PRD: it names the in-file theta reference, the isolated dichotic path, and test-enforced rules. The NFRs (§5) are product-specific numbers, not "scalable and secure" boilerplate. There are two personas. Audio drives nearly every FR. Dana (UJ-3) drives the offline, screen-off and interruption requirements (FR-30, FR-32). The differentiation in §1 traces to `research-comparables.md` and is reflected in constraints (§6 Claims, Naming), not just asserted.

### Findings

- **[low]** Battery and Reach rows are placeholders (§5): "uses no more than a set battery share" and "Lowest Android and iOS versions the stack supports well" have no bounds. That is acceptable because they are tagged or deferred to Phase 0, but they currently read as NFR shells. *Fix:* Name the Phase 0 gate that must fill them, as the hearing-safety row does by assumption tag.

## Strategic coherence: strong

The thesis is explicit in §1: the signal design is the spine, and every rule is enforced by a test "rather than by memory." The features follow it. Engine, validator, reference renderer and test suite come first (Phase 0). Listener-facing work comes only after the signal is proven. Spatial motion is gated on a blind A/B (FR-28). The success checkpoints (§9) validate the thesis rather than activity. The counter-checkpoints SC-C1 ("do not chase subjective 'it works on me' impressions") and SC-C2 ("do not trade test thresholds for render speed or battery") are well chosen for this product. The MVP is clearly a problem-solving and platform MVP, and the scope logic matches it.

### Findings

- **[medium]** Free tier versus offline listening (FR-37, FR-32, UJ-3): FR-37 makes "offline downloads" a premium feature, but UJ-3's protagonist plays Sleep "with no signal," and the addendum ("Ship a small built-in set") implies bundled content. It is unclear whether a free listener can play anything offline. That matters for Dana's journey and for FR-30's Phase 0 gate. *Fix:* State that built-in starter recipes play offline on the free tier and that premium covers downloaded packs, or make UJ-3 a premium listener.
- **[low]** Sign-in versus two taps (FR-36, FR-29): FR-36 says "Listeners sign in", while FR-29 promises a playing session in "no more than two taps from launch." If sign-in is required, the two-tap promise holds only after the first run. *Fix:* Say whether sign-in is optional for the free tier, or scope FR-29 to "after first run."

## Done-ness clarity: adequate (v0.1 FRs), thin (Phase 1 onward)

For v0.1 (FR-1 to FR-17) most FRs carry a numeric consequence that traces to the plan's thresholds table: 0.01 Hz, 1 ms over 8 hours, 2 ms coupling, 90 dB and 60 dB isolation, -100 dBFS reference match, 1 LU, -1 dBTP, 20 times real time. That is better than most PRDs. The problems are a handful of ambiguous terms and assertions without thresholds. Story writers and the QA agent will hit both on day one. Phase 1 to 4 FRs are thinner, which is acceptable under gate-based phasing, but several of them have no testable consequence at all.

### Findings

- **[high]** FR-13 assertions with no threshold (§4.4 FR-13, §5): FR-13 adds "envelope shape matching the recipe", "dropouts", "NaN or infinite values" and "hearing-safety level ceiling" to the suite, but neither §5 nor the plan's Test thresholds table gives a pass condition for envelope shape or dropouts, and the ceiling is an `[ASSUMPTION]` set in Phase 0. The v0.1 gate is "Every test passes in CI," so these tests cannot be written red-first per CLAUDE.md Rule 6. *Fix:* Add §5 rows: envelope shape (for example maximum RMS error against the reference renderer's envelope), dropouts (for example no run of more than N zero samples where the recipe level is above silence), NaN or Inf (zero tolerance), and a provisional numeric hearing ceiling marked for Phase 0 review.
- **[high]** Determinism and cross-platform identity scope (FR-6, FR-35, §5 Determinism): "byte-identical" does not say whether it holds on the same build and machine, or across compilers, CPUs and operating systems. FR-35 says iOS "renders the same recipe identically to the Android engine" with no tolerance. Floating-point DSP on ARM and x86 will not be bit-identical without deliberate design (strict FP modes, no fused multiply-add, or fixed-point), and that is a load-bearing architecture decision. *Fix:* State the scope: byte-identical on the same platform and build, and across platforms either byte-identical (forcing strict FP as an architecture constraint) or within a stated tolerance (for example matching the -100 dBFS reference-match bound).
- **[medium]** "Gain change" collides with the modulation itself (FR-5, §5 Ramps): "No gain change faster than 10 ms" read literally fails every render. 40 Hz gamma AM has a 25 ms period, the 50 ms Focus bursts have edges, and FR-2 offers sawtooth envelopes. The plan's intent is layer gain ramps and fades. *Fix:* Reword to "No layer gain or master gain ramp (recipe ramps, fades, intensity changes, limiter gain) changes faster than 10 ms; AM envelopes are governed by the Clicks threshold."
- **[medium]** "Gamma envelope peak" is ambiguous (FR-3, §5 Coupling): it can mean the per-theta-cycle depth envelope peak or each 40 Hz AM cycle peak. The 2 ms test differs completely between the two. The coupling-phase anchor "0 degrees at its maximum" (§3 Coupling phase) is also undefined for a custom curve with more than one maximum or for flat-topped smoothed on-off shapes. *Fix:* Define it as "the peak of the gamma depth envelope within each theta reference cycle", and define the 0-degree anchor per envelope shape (for example the start of the plateau for on-off, the maximum sample for sawtooth, and author-declared for custom curves).
- **[medium]** Non-sine binaural contradicts the glossary (FR-4, §3 Binaural layer): FR-4 allows "Non-sine binaural waveforms ... only with a validator warning," while the glossary and CLAUDE.md define the layer as "two steady sines." A non-sine waveform also adds harmonics that the spacing rule must then cover. *Fix:* Either drop the allowance, or amend the glossary and say the spacing rule counts the harmonics.
- **[medium]** Spacing rule versus starter modes (FR-9, FR-16, addendum Starter mode parameters): the plan's spacing row says starter recipes pass "because gamma and binaural never run together", but the PRD's Relax mode has gamma "Off or low depth" and an optional 250 Hz binaural layer. With a gamma carrier anywhere in 200 to 500 Hz and a 40 Hz rate, the side frequencies sweep 160 to 540 Hz, so Relax can fail FR-9 depending on settings. The PRD dropped the constraint that made it pass. *Fix:* State in FR-16 or the Relax recipe notes either that gamma and binaural are mutually exclusive in starter recipes, or which carriers keep them 50 Hz apart.
- **[medium]** Looping max run time is not a recipe field (FR-7, FR-16, FR-29): Focus and Learn loop in v0.1, and FR-29 says "Every looping session has a maximum run time set in the recipe", but FR-7's field list omits it and the validator (FR-8) does not check it. *Fix:* Add maximum run time to FR-7's required fields, and make the validator reject a looping recipe without one.
- **[medium]** "Every render" is impractical for 8-hour drift (FR-13, FR-15): FR-13 runs every check, including 8-hour drift, on "every render", while FR-15 has fast tests after every change. The split between fast and full is undefined, so stories will guess. *Fix:* Mark which FR-13 checks belong to the fast tier and which run full-suite only in CI.
- **[medium]** Phase 1 and 2 FRs without consequences (FR-19, FR-22, FR-25, FR-28): FR-19 has no update latency, FR-22 has no criterion for "stream a recipe" (rendered audio or recipe file, latency, identical output), FR-25 gives no notch depth or width and does not say whether modulation side frequencies are notched, and FR-28 gives no decision rule for "supports keeping motion." These are deferred phases, so this is not blocking. *Fix:* Add one measurable consequence each before Phase 1 stories are drafted.
- **[low]** Rate-curve accuracy method (FR-1): "within 0.01 Hz of the scheduled curve at every point" is not directly measurable for a sweeping rate. *Fix:* Specify the measurement, for example comparing instantaneous phase against the integrated scheduled curve, which also catches the "phase stays continuous" clause.
- **[low]** "Flagged" settings undefined (FR-21): the example "a sawtooth carrier" does not exist. Sawtooth is a theta envelope shape (FR-2), and the carrier waveforms are sine, triangle and softened square (FR-3). *Fix:* List the flagged settings, or reference a validator warning list.

## Scope honesty: strong

Omissions are explicit. §7 Non-Goals does real work: no closed-loop, no voice, no speaker or mono variants (with reasoning), "No coupling to a binaural beat, ever." §8 has an "Out of scope for v0.1" line and a "Later" line. Inferences carry `[ASSUMPTION]` tags. Deferrals of pricing, OS versions and listener metrics are declared, not silent. Open-items density (9 open questions and 11 inline assumptions) is appropriate for an internal, gate-based PRD whose first gate is research-driven.

### Findings

- **[low]** Content server and encryption appear without scope (FR-23, FR-32, FR-33): the content server, manifest and per-device key scheme are introduced inside FRs with no requirement of their own, and appear only in the v0.1 out-of-scope list. *Fix:* Add a one-line `[NON-GOAL for Phase 1]` or a stub FR stating what the content server must do for FR-23 to be testable.

## Downstream usability: strong

The glossary (§3) is thorough and is used consistently: "theta reference", "gamma PAC layer", "binaural layer" and "engine clock" do not drift. FR-1 to FR-38 are contiguous and unique. Every feature block says which UJs it realizes. Each UJ has a protagonist and an edge case. The addendum separates implementation detail cleanly. A few terms that stories will need are missing from the glossary.

### Findings

- **[low]** Undefined working terms (FR-4, FR-7, FR-23, FR-31): "master chain", "session body", "ramp-in", "stem pack", "intensity" and "level ceiling" are used as defined terms but are not in §3. "Master chain" matters most, because FR-4's 60 dB bound is measured after it. *Fix:* Add glossary entries, with "master chain" listing its stages (for example limiter only).
- **[low]** NFRs lack IDs (§5): stories and test design will cite NFRs by row name. *Fix:* Number them NFR-1 to NFR-12.

## Shape fit: strong

The PRD is correctly shaped as a capability spec for a single-operator tool that later grows a consumer surface. It has three UJs, which is light but enough: two for the operator and one listener journey placed in Phase 3 where it becomes load-bearing. Success is operational and gate-based, which suits a sole designer and producer. Launch-grade detail is rightly deferred. It is neither over- nor under-formalized.

### Findings

- **[low]** Designer usability test audience (FR-18): "One usability session with someone who is not an engineer" sits oddly next to §2.2 ("The designer is built for Audio first"). *Fix:* State the purpose (for example readiness for future outside designers), or drop it.

## Mechanical notes

- **Assumptions Index roundtrip:** there are 11 inline tags and 10 index entries. The UJ-3 and FR-30 resume assumption is merged into one entry, which is acceptable. Every index entry appears inline, and no inline tag is missing from the index.
- **ID continuity:** FR-1 to FR-38, UJ-1 to UJ-3, and SC-1 to SC-3 plus SC-C1 and SC-C2 are contiguous with no duplicates. Cross-references resolve: FR-24 is cited from FR-6, FR-17 from FR-23, FR-4 from FR-27, and §5, §7, §8 and §11 references all land.
- **Carrier inconsistency:** §11 OQ2 frames the binaural carrier as "200/206 Hz or higher," but the addendum's Sleep row uses a 100 Hz carrier. Reconcile, or note that Sleep is the exception.
- **Locked range versus carrier rule:** the gamma PAC carrier range starts at 200 Hz (FR-8), but at the selectable 60 Hz gamma rate the carrier rule requires at least 240 Hz. The validator catches it, but the designer UI (FR-18) will offer values it then rejects. Consider stating a rate-dependent lower bound.
- **Rate naming in Sleep:** the glossary explains that the theta reference runs at a delta rate in Sleep, but FR-2 and FR-8 still say "theta rate." That is acceptable given the glossary note, so keep it consistent.
- **Required sections:** all are present for the agreed stakes. Pricing, store copy and listener metrics are absent by design.
- **Style:** no em dashes found. Signals are named by carrier, modulation type and rate throughout.
