# Arcani v0.1 Story Breakdown (working draft)

From the v0.1 story breakdown session (party mode, Winston, Amelia, Murat, with Audio), 2026-10-27 to 2026-10-28. Contract: `_bmad-output/specs/spec-arcani-v0-1/`. E0 to E3 are drafted; E4 to E6 are still in discussion. Story files and full acceptance criteria come after the epic list is locked.

## Rules for every story

- Tests are written first, from the acceptance criteria, by a fresh-context QA agent.
- Every assertion ships with a passing fixture and a must-fail fixture: a deliberately broken render the assertion has to catch.
- Each story writes only the `docs/signal-spec.md` section it needs; that section merges before either the engine or the reference implements it.
- Silence is not evidence: a reference match must compare a real waveform.

## E0 Foundations

- **S0.1 Build skeleton.** CMake 4.4.5, Clang toolchains pinned, Catch2, uv and pytest, CI matrix (the NDK arm64 job runs a hash binary only; full Catch2 on NDK waits for the full tier), check for `-ffp-contract=off` and no fast-math.
- **S0.2 Sine spike (run early, decided by Audio).** Not throwaway: this oscillator ships.
  - AC1 spec §core (accumulator, increment quantization, seconds-to-samples) and §sine: ideal waveform defined, engine approximation bound stated.
  - AC2 engine sine max error against the ideal sine at most -120 dBFS over a full accumulator cycle.
  - AC3 SHA-256 of a fixed sine render identical on Windows x64, arm64, macOS arm64, Android NDK arm64.
  - AC4 8-hour drift: analytic phase error under 1 ms from integer increments.
  - AC5 frequency accuracy: increment quantization error under 0.01 Hz across the locked carrier ranges.
  - AC6 design log entry (done: 2026-10-28 (o)).
- **S0.3 Threshold and range tables as data,** with loaders in C++ and Python.

## E1 Walking skeleton

- **S1.1** Minimal recipe schema, RFC 8785 canonical JSON, SHA-256 recipe hash.
- **S1.2** C API compile and render; the full fixed stage list as stubs (theta, gamma, stereo bus, binaural join, master chain); structural stage-order test; binaural isolation assertion with a must-fail leaky stub (0.1 percent crosstalk).
- **S1.3** CLI: 24-bit WAV at 48 kHz and 44.1 kHz, JSON report (name, threshold, measured, pass or fail, determinism key, seed).
- **S1.4** Python reference for the stub chain, with the S0.2 sine routed through the theta stub as an unmodulated carrier; reference-match assertion.
- **S1.5** Determinism and block-size invariance (1, 64, 512, 4096 frames per call).

## E2 Core layers (order fixed)

- **S2.1 Theta reference envelopes** (sine, smoothed on-off, sawtooth, reverse saw), filling the theta stub.
- **S2.2 Gamma uncoupled:** AM at the gamma rate, constant depth.
- **S2.3 Gamma coupled, smooth swell:** depth-gated (carrier plays continuously); depth follows theta phase and peaks at the coupling phase; rejects coupled gamma when theta is absent or at zero depth. Coupling timing measured from audio taps (demodulated gamma envelope against theta phase recovered from the theta tap), never from the engine's internal depth value. Must-fail: a swell shifted 3 ms fails, 1 ms passes, at 25 and 100 percent depth. AD-5 checked structurally here: the gamma depth function takes theta phase as its only input.
- **S2.5 Binaural layer** (runs before S2.4):
  - AC1 isolation, muted-ear method: at least 90 dB at engine output, 60 dB after the master chain, including 0 Hz beat.
  - AC2 rate curve: right = left + beat(t), continuous phase.
  - AC3 frequency accuracy along the curve, measured as unwrapped tap phase against the closed-form integral of the schedule (spec defines the rate-curve law and its integral).
  - AC4 AD-5 behavioral: sweeping beat rate and phase leaves every gamma peak time unchanged to the sample.
  - AC5 non-sine `binaural.waveform` rejected with a named rule (must-fail: `triangle`).
- **S2.4 Gamma coupled, 50 ms bursts** (last in E2): full width, 10 ms raised-cosine edges inside, depth-gated. Must reproduce the research run figures (depth-gated 60 Hz near -51 dB passes). Must-fail: carrier-gated rectangular 40 Hz bursts fail spacing (near -21 dB) and the click test.

## E3 Validator

- **S3.1** Locked-range checks from the range table; every rejection names parameter, value, rule, limit.
- **S3.2** Carrier rule (at least 4 times the modulation rate), analytic, whole session including rate curves.
- **S3.3** Spectral component table per shape (AD-20) and the spacing rule, per ear, whole session. Rate curves become interval checks (worst case over the curve's range), closed form. Analytic model cross-checked against the reference render's spectrum. Must-fail: a 250/256 Hz binaural pair beside gamma's 260 Hz side frequency is rejected.

## E4 to E6 (to discuss)

- **E4 Master:** gain ramps, loudness measure and store, true peak, limiter. Limiter is measure-first: render starters at stored gain and report gain reduction as MEASURED, never PASS; the data proposes the open idle bound; nothing goes golden until it is logged.
- **E5 Long runs and robustness:** 8-hour drift, clicks, dropouts, NaN, render speed. Loop seams move into E2 (Focus and Learn loop).
- **E6 Ship:** four starters, listening checklist, golden files in Git LFS with sign-off.

## Doc changes made in this session

- Design log 2026-10-28 (o): reference ideal sine and -120 dBFS bound; depth-gated bursts; 10 ms burst edges; non-sine binaural rejected in v0.1.
- SPEC CAP-4 and CAP-5 and the range table's burst row updated to match.
- Research run `burst-edge-taper-2026-10-28`.
