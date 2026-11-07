# Epic 2 Context: Every Core layer, exact and on time

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Audio can render every Core zone layer for real: the theta reference (carrier AM at the theta rate with one of four envelope shapes), the gamma PAC layer (uncoupled, smooth swell, 50 ms bursts), and the binaural layer (two pure sines, one per ear). Each layer replaces an Epic 1 stage stub and is proven on frequency accuracy, coupling timing, isolation, clicks, and a -100 dBFS sample-by-sample match against the Python reference, then gains rate curves and seamless loops. The theta reference comes first because it is the only signal gamma may couple to; its phase must exist in the file and be measurable.

## Stories

Order is fixed and not numeric: 2.1, 2.2, 2.3, 2.5, 2.4, 2.6, 2.7.

- Story 2.1: Theta reference envelopes
- Story 2.2: Gamma PAC layer, uncoupled
- Story 2.3: Gamma coupled, smooth swell
- Story 2.5: Binaural layer
- Story 2.4: Gamma coupled, 50 ms bursts
- Story 2.6: Rate curves on theta and gamma rates
- Story 2.7: Looping body and seams

## Requirements & Constraints

- **Engine clock:** one clock drives every rate and phase. Every carrier and rate within 0.01 Hz of the recipe; along a rate curve, instantaneous rate within 0.01 Hz of the schedule with continuous phase. Theta phase error under 1 ms after 8 hours (whole-session check lands in Epic 5).
- **Theta reference:** a carrier AM at the theta rate with a sine, smoothed on-off, sawtooth, or reverse saw envelope, set by the recipe. Locked ranges: carrier 100 to 500 Hz, rate 1 to 6 Hz, AM depth 0 to 100 percent. Custom envelope curves are rejected with a named rule until the signal spec models them. Hard-edged shapes must pass the click test.
- **Gamma PAC layer:** a separate sine carrier AM at the gamma rate (carrier 200 to 500 Hz, rate 30 to 60 Hz, depth 0 to 100 percent). Depth follows theta reference phase and peaks at the coupling phase (smooth swell or 50 ms bursts with 10 ms raised-cosine edges inside, depth-gated), or is constant when uncoupled. The carrier always plays continuously. Every envelope peak within 2 ms of its coupling phase. Non-sine gamma carriers are rejected.
- **Coupling input:** coupled gamma depth takes theta reference phase as its only signal input, plus static recipe parameters. Coupled gamma is rejected wherever gamma level and depth are non-zero while the theta reference is absent, at zero level (its own gain including ramp, per sample, exactly zero; master gain does not count), or at zero AM depth. Changing binaural beat rate or phase leaves every gamma peak time unchanged to the sample.
- **Binaural layer:** right carrier = left carrier + beat(t); carriers below 1000 Hz, beat 0 to below 30 Hz (worst case over any rate curve). Non-sine binaural is rejected (`binaural.waveform`, "non-sine binaural not modeled", limit sine). Isolation at least 90 dB at engine output and 60 dB after the master chain, any beat rate including 0 Hz.
- **Carrier rule:** every modulated carrier is at least 4 times its worst-case modulation rate, including along rate curves.
- **Reference match:** engine theta, gamma, and binaural taps and output within -100 dBFS of the Python reference sample by sample, at 44.1 and 48 kHz. The margin is stated per tap by counting sine evaluations, not layers.
- **Looping:** looping recipes need a max run time; the opening plays once, the body repeats with no click and no theta or gamma phase jump; seek into a later iteration is byte-identical to a continuous render.
- **Process:** each story writes only the `docs/signal-spec.md` section it needs, with worked test vectors from the closed form, and that section merges before engine or reference implement it. Each new measurement tool (frequency accuracy, click, coupling timing, spectrum) is first calibrated on Python-synthesized signals with known answers. Every assertion has a passing and a must-fail fixture; must-fail fixtures are doctored in the harness, never in `engine/`. Tests first, as a failing tests-only commit. Thresholds and ranges come from the tables only. Every engine story's fixture joins the four-platform hash check at both sample rates.

## Technical Decisions

- **Signal spec is the only formula source:** envelope shapes and their 0 degree points, coupling depth function, bursts, AM and carrier laws, rate-curve law and phase integral, loop seams, component model per shape. For each transcendental it gives the ideal function (reference) and the engine algorithm with error bound. A shape not in the spec does not exist.
- **Fixed topology:** theta reference, gamma PAC layer, stereo bus, binaural join, master chain. The binaural pair joins after every other stage; no channel-mixing stage. No routing fields and no coupling-target field in the schema.
- **Bit-exact math:** engine-owned sine, 64-bit integer phase accumulators, no libm transcendentals, no FMA, `-ffp-contract=off`, no fast-math, clamped float-to-integer conversions. Seek is a pure function of (plan, seed, sample rate, sample index); output independent of block size.
- **Spectral components:** carrier and spacing rules read one analytic component table per shape (spacing rule itself lands in Epic 3); a shape with no component model is rejected.
- **Starters:** every starter uses a sine theta envelope; only Sleep has a binaural layer.

## Cross-Story Dependencies

- Builds on Epic 1: schema and hash (1.1), C API, stage stubs, taps, seek, isolation assertion (1.2), validator and range rows (1.3), CLI and report (1.4), Python reference (1.5), determinism and block-size checks (1.6).
- 2.1 theta phase feeds the coupling stories (2.3, 2.4). 2.3 introduces the coupling timing tool; 2.4 introduces the spectrum tool. 2.5 runs before 2.4 so the AD-5 behavioral test exists first.
- 2.5 defines the rate-curve law; 2.6 reuses it unchanged for theta and gamma rates. 2.7 builds loops on 2.6 curves.
- Epic 3 spacing rule and Epic 4 gain ramps build on these layers.
