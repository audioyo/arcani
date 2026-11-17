# Epic 3 Context: The validator catches collisions

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Any recipe whose layers collide in either ear, at any point in the session including along rate curves, is rejected at compile time with parameter, value, rule, and limit, and produces no plan. The epic first builds one analytic spectral component table per layer shape, cross-checked against measured reference spectra, so the validator and the tests agree on exactly what each layer puts in each ear. It then adds the per-ear spacing rule on top of that table, proves that the four starters' layer configurations pass here (not in Epic 6), and ends with a short listening preview so a harsh carrier or rough gamma AM is caught well before sign-off.

## Stories

- Story 3.1: Spectral component table per shape
- Story 3.2: Spacing rule per ear, whole session
- Story 3.3: Early listening preview

## Requirements & Constraints

- **Spectral component:** any spectral line of a layer within 40 dB of that layer's strongest line, counting modulation side frequencies and lines from bursts and envelope shapes. 40 dB is a placeholder and lives in a threshold table row.
- **Component model coverage:** every v0.1 shape has a model: each theta reference envelope (sine, smoothed on-off, sawtooth, reverse saw), uncoupled gamma, smooth swell, 50 ms bursts, and the binaural pair. A shape with no component model is rejected with a named rule.
- **Compiled component table:** per ear and per layer, every component's frequency, or frequency interval where a rate curve moves it, and its level relative to the layer's strongest line.
- **Cross-check:** on reference renders of every Epic 2 fixture shape, every measured line within 40 dB of its layer's strongest appears in the analytic table within the frequency and level tolerances in the threshold table, and no analytic component is missing from the measurement. A model doctored in the harness to drop one side frequency must be caught.
- **Spacing rule:** in each ear, at least 50 Hz (placeholder, threshold table row) between every component of one layer and every component of another. A layer's own components are exempt, and the two binaural carriers are exempt from each other because they never share an ear. Each binaural carrier still counts against other layers in its own ear. Exactly 50 Hz passes; anything less fails.
- **Whole session:** a rate curve on any layer is checked by the closed-form worst case over the curve's whole range, never by sampling the session.
- **Carrier rule:** every modulated carrier is at least 4 times its worst-case modulation rate. It already runs from Epic 1 and shares the same component table.
- **Rejection:** a spacing failure returns no plan and an error naming parameter, value, rule, and limit, plus both colliding components, their layers, the ear, and where in the session or rate range the minimum distance occurs. A rejected recipe writes no WAV.
- **Required fixtures:** a must-fail recipe with a binaural pair (two pure sines, 250 Hz left and 256 Hz right) beside a gamma PAC layer whose side frequency sits at 260 Hz is rejected for spacing in the right ear. The four starter configurations (Focus, Learn, Relax, Sleep) and Epic 2's coupled gamma plus binaural fixture must all pass.
- **Never weaken the rule:** if Focus fails spacing, the story stays open until the cause is logged in the design log and resolved through the signal spec.
- **Preview renders:** about 3 minutes each at 48 kHz at a steady level, with loop seams for Focus and Learn, marked unsigned and preview in the report, never stored as goldens. With no loudness gain yet, level is set so the analytic sample peak of the summed layers is -30 dBFS, a preview-only engineering default logged in the design log in that story.
- **Preview listening:** on earbuds and on headphones; every observation recorded in plain words. Any proposed change to a default or range is logged in the design log and routed to the story that owns it before Epic 4 starts. Closing on "nothing needs changing" is a valid recorded result.
- **Process:** tests first as a failing tests-only commit; every assertion has a passing and a must-fail fixture, doctored in the harness and never in `engine/`; reference matches compare real waveforms, not silence; engine story fixtures join the four-platform hash check at 44.1 and 48 kHz.

## Technical Decisions

- **One component table feeds both rules:** the carrier rule and the spacing rule both read the analytic table built by the compiler from the signal spec's component model. The validator and the test suite must not compute collisions two different ways.
- **Signal spec is the only formula source:** the component model per shape is written as the components section of `docs/signal-spec.md`, with worked test vectors, and merges before the engine or the reference implements it. A shape not in the spec does not exist.
- **Analytic, not measured:** the validator computes components in closed form at compile time. Measurement (the spectrum tool calibrated in Epic 2) only cross-checks the model.
- **Per-ear signal:** spacing is judged on the signal each ear receives. Topology is fixed (theta reference, gamma PAC layer, stereo bus, binaural join, master chain) with no channel mixing, so the left binaural carrier appears only in the left ear and the right only in the right.
- **Tables as data:** the 50 Hz spacing value, the 40 dB component threshold, and the cross-check frequency and level tolerances are rows in the threshold table, read by the C++ and Python loaders. No literals in code or tests; a table change needs a design log entry.
- **Error format:** compile returns a status code plus a structured error (parameter, value, rule, limit) through the `arc_` C API; the spacing detail extends that structure. The render call never throws or logs.
- **Coupling is unchanged:** coupled gamma depth depends only on theta reference phase plus static recipe parameters. The spacing rule adds no dependency between the gamma PAC layer and the binaural beat.
- **Starters:** every starter uses a sine theta envelope; only Sleep has a binaural layer; Focus and Learn loop.

## Cross-Story Dependencies

- Builds on Epic 1's validator framework, locked-range rows, carrier rule, and structured rejection, and on Epic 2's layers, rate-curve law, loops, fixtures, and spectrum tool.
- 3.1's component table is the input to 3.2. 3.3 previews only the starter configurations that passed 3.2.
- Changes proposed in 3.3 are routed to their owning stories before Epic 4 starts. Level ramps, fades, and stored loudness gain arrive in Epic 4; goldens and sign-off stay in Epic 6.
