# Epic 4 Context: Safe, steady loudness

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Every render hits its loudness target under the true-peak ceiling, gain ramps are smooth and click-free, the stereo-linked limiter provably never acts, and the CLI measures the loudness gain once and stores it in the recipe. This is v0.1 hearing safety: loudness and true-peak targets met on every render. It also gives the four starters (Epic 6) real levels, ramp-ins, and fades for the first time; until now every layer runs at unit amplitude and fixtures with two layers peak near 2.0 and clip in their 24-bit WAVs.

## Stories

- Story 4.1: Loudness meter
- Story 4.2: Stored loudness gain
- Story 4.3: True peak
- Story 4.4: Gain ramps
- Story 4.5: Limiter idle

## Requirements & Constraints

- **Loudness target:** every v0.1 starter targets -36 LUFS-I (tones level, an engineering default). The recipe field `loudness_target_lufs` already maps to the fixed range row `loudness-tones`; any other value is rejected. Pass band: integrated loudness within 1 LU of target (row `loudness-tolerance`).
- **Integrated loudness:** ITU-R BS.1770 with K-weighting, 400 ms blocks, absolute gate at -70 LUFS, relative gate at -10 LU.
- **Measurement window (the steady part):** every ramp and fade excluded. Looping recipe: the looping body only, repeated seamlessly a whole number of times to at least the minimum length the signal spec sets. Non-looping recipe: the longest stretch with no layer or master gain ramp active. A steady part shorter than the spec minimum is rejected in `measure` mode with a named rule. Until ramps exist, the steady part is the whole session or the body. Expected effect: Relax measures minutes 10 to 30, Sleep 0 to 40 (before its fade).
- **Whole-render ceiling:** over a whole render (to the max run time for looping recipes), integrated loudness is reported and never more than 1 LU above target. Ramps and fades are quieter by design.
- **Meter proof:** two meters, one in the Python assertion library and one in the CLI tooling (outside `engine/`), each read every EBU Tech 3341 compliance signal within its stated tolerance, and agree with each other on any render within the Tech 3341 integrated tolerance (a threshold table row). A must-fail meter with gating off fails the gating cases. A render doctored to 1.5 LU above target fails the loudness assertion.
- **Compliance signals:** Tech 3341 v4.0 Table 1 cases 1 to 5, synthesized in the harness from the printed levels and durations; the EBU files are never downloaded or committed (EBU terms of use, July 2019; Story 4.1 decision 1, 2026-11-20). Cases 6 to 8 are out of scope.
- **Stored gain:** the CLI measure command compiles in `measure` mode, renders, measures over the window, and writes `loudness_gain_db` and `loudness_hash` (over loudness-relevant schema fields) into the recipe. Measuring twice writes identical bytes. `final` compile rejects a missing gain or a stale hash with parameter, value, rule, limit; editing a non-loudness, non-audio field keeps it compilable. CI never writes a gain: no recipe file changes during a CI run, and a must-fail CI step that writes one is caught.
- **True peak:** at or below -1 dBTP (row `true-peak`) on the final 24-bit output, measured with BS.1770 Annex 2 oversampling. Calibrated on Tech 3341 v4.0 Table 1 true-peak cases 15 to 19 (synthesized in the harness; cases 20 to 23 out of scope, Story 4.3 decision 5) and Python signals with known inter-sample peaks; a must-fail signal with sample peak below -1 dBFS but true peak above -1 dBTP must fail. If the needed gain would breach the ceiling, the measure command writes no gain and reports target, gain needed, and resulting true peak.
- **Gain ramps:** per-layer and master ramps from the recipe; none completes in under 10 ms (row `gain-ramp-min`; exactly 10 ms passes). Modulation envelopes and limiter gain reduction are exempt. No discontinuity above -60 dBFS (8 kHz high-pass) at any ramp start or end. A fade to silence ends in exact zeros.
- **Limiter idle:** gain-reduction tap exactly unity on every sample and master chain output equals input times master gain, bit for bit (row `limiter-idle`, zero). Latency is zero in v0.1.
- **Reference match:** ramp renders, master chain, and the must-fail limiter render all match the Python reference below -100 dBFS, comparing real waveforms.
- **Process:** tests first as a failing tests-only commit by a fresh-context QA agent; every assertion has a passing and a must-fail fixture, doctored in the harness, never in `engine/`; every measurement tool is calibrated on Python-synthesized closed-form signals before it judges an engine render; engine fixtures join the four-platform hash check at 44.1 and 48 kHz. Any new or changed threshold row needs a design log entry; never weaken one.

## Technical Decisions

- **Loudness gain lives in the recipe (AD-13):** measured once at export by the CLI (later the designer), stored with a loudness hash, used identically live and offline. `loudness_gain_db` and `loudness_hash` are hash-excluded from the recipe hash, so writing them does not change the determinism key. `loudness_gain_db` is currently exempt from range checks; Story 4.2 checks it.
- **Signal spec is the only formula source:** each story writes only its section of `docs/signal-spec.md` (loudness window in 4.1, ramps in 4.4, limiter in 4.5), with worked test vectors, merged before engine or reference implement it.
- **Meters are tooling, not engine:** loudness and true-peak measurement sit outside `engine/`, which stays pure C++ standard library with no I/O, threads, or clocks.
- **Fixed topology (AD-4):** theta reference, gamma PAC layer, stereo bus, binaural join, master chain. The master chain is only per-channel gain plus a stereo-linked limiter; no channel mixing. The limiter applies the same gain reduction to both channels, and binaural isolation after the master chain stays at least 60 dB even when it acts.
- **Taps:** 4.4 splits each layer into a tap before gain and a tap after gain (bit-identical at unity). Coupling timing, frequency, and phase read before gain; loudness reads after gain.
- **Bit-exact rules (AD-9) apply:** engine-owned transcendentals, `-ffp-contract=off`, no fast-math, clamped float-to-int conversions. Ramp alignment goes through the seconds-to-samples rule.
- **Tables as data:** every threshold read from `tests/tables/thresholds.tsv` or `ranges.tsv` through the C++ and Python loaders. Rows `loudness-tolerance`, `true-peak`, `gain-ramp-min`, `limiter-idle` exist and are marked pending on their stories.

## Cross-Story Dependencies

- Order is fixed: 4.1 first (4.2, 4.3, 4.5 depend on the meter); 4.4 before 4.5 so a ramp cannot trip the limiter.
- 4.4 proves the ramp exclusion of the 4.1 window, including a must-fail looping fixture measured over ramp-in plus one body (the superseded window).
- 4.2 must replace the shared placeholder `loudness_hash` in the Story 1.1 and 1.2 valid fixtures, or those fixtures and the final-mode API tests fail once the hash match is enforced.
- 4.4 also carries deferred work: reject coupled gamma wherever the theta reference gain (including its ramp) is exactly zero per sample while gamma level and depth are non-zero, with a must-fail fixture; an end fade at the max run time cap for Focus and Learn; the ramp-in inside the opening.
- Builds on the Epic 1 CLI, report, and validator; the Epic 2 loop and click tool; the Epic 3 preview gain, which Epic 4's loudness gain replaces for real renders. Epic 5 (clicks, long renders) and Epic 6 (starters, goldens) consume the gains and ramps set here.
