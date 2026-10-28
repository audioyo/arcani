---
title: 'Adversarial review: Arcani architecture spine'
reviewed: ARCHITECTURE-SPINE.md (draft, 2026-10-27)
companions_read: .memlog.md, prd.md, CLAUDE.md, docs/project-plan.md (Test thresholds)
date: '2026-10-27'
method: 'Pairs of units one level below the spine, each built to obey every AD to the letter, checked for incompatibility, plus attacks on binaural isolation and theta-only coupling.'
---

# Adversarial review: Arcani architecture spine

## Verdict

The spine fixes the right boundaries (pure core, fixed Core topology, binaural joins last, one C API), but it leaves the shared data between units undefined: recipe hash and canonical form, loudness hash scope, phase quantization, PRNG draw semantics, seek and plan-swap semantics, the spectral component model, the snapshot shape, and host channel handling. Two teams can each obey all 18 ADs and still produce engines that disagree on bytes, validators that disagree on spacing, a designer that cannot audition an edit, and a phone that sums the binaural pair to mono. 24 holes found; 8 are blocking for v0.1.

Severity key: **B** blocks v0.1 (determinism, isolation, coupling, or test integrity at risk now). **P** must close before the phase that builds the unit. **M** minor or clarifying.

## Summary table

| # | Pair | Hole class | Sev |
| --- | --- | --- | --- |
| H1 | CLI loudness writer and validator / plan compiler | Circular dependency, undefined hash scope | B |
| H2 | Golden file store and CLI report / Python reference | Undefined recipe hash and canonical form | B |
| H3 | Engine integer phase accumulator and Python reference | Frequency quantization not in the spec | B |
| H4 | Engine rate-curve integration and Python reference | Ambiguous integration grid (per sample vs per block) | B |
| H5 | Validator spacing check and Python spacing test | Two spectral component models | B |
| H6 | Gamma PAC layer and coupling-timing test | Coupling phase undefined for non-sine theta envelopes | B |
| H7 | Master limiter and binaural layer | Stereo-linked limiter imposes gamma-rate AM and cross-ear gain on the binaural pair | B |
| H8 | Fixed internal block size and every host | Block size unpinned, yet it shapes output | B |
| H9 | 3D renderer (Orbit) and gamma coupling test | Renderer latency and HRTF group delay shift gamma against theta | P |
| H10 | Carrier guard (Tone zone) and Core zone | Guard must read Core carriers, AD-3 and AD-6 forbid it | P |
| H11 | Carrier guard and binaural isolation test | Stem energy at the opposite ear's carrier; notch depth unset | P |
| H12 | Host audio adapter (miniaudio) and AD-4 | Host may downmix, resample, or channel-map; AD-4 binds only the engine | P |
| H13 | Stem sequencer and PRNG streams | Stateful streams vs plan swap, loop, and seek | P |
| H14 | Seek / resume (FR-30) and AD-1 "function of sample index" | Stateful stages contradict closed-form sample index | P |
| H15 | Plan swap (AD-11) and Core phase continuity | Crossfade vs parameter ramp; who owns the running phase | P |
| H16 | Designer live audition and AD-13 loudness gate | Every edit invalidates the gain hash, so no plan compiles | P |
| H17 | Designer warnings (FR-21) and engine validator | Second validator in Dart | P |
| H18 | Listener controls (FR-31) and determinism / loudness | No owner and no API path for intensity, length, Orbit toggle | P |
| H19 | C API plan handles and dart:ffi | Plan lifetime and free on the audio thread | P |
| H20 | Engine snapshot and visualizer (AD-18) | Snapshot exposes entrainment-rate data; torn reads | P |
| H21 | Stem decoder and AD-10 native 44.1 / 48 kHz | Stems at one rate require a resampler the AD forbids | P |
| H22 | Tone zone built-in effects and AD-6 | LFO, tremolo, auto-pan rates unlocked: untracked rhythm in the file | P |
| H23 | Seed owner: recipe vs host | Hosts can override the seed; golden key omits it | M |
| H24 | Engine version, threshold tables, golden lookup | Table data changes output without a version bump; missing golden passes | M |

Additional theta-only and isolation attacks are folded into H6, H7, H9, H11, H12, H22, and H25 to H27 below.

---

## Blocking holes (v0.1)

### H1. CLI loudness writer vs validator and plan compiler

- **Both obey:** AD-13 says the CLI measures loudness and writes gain plus a hash into the recipe; the validator rejects a recipe whose gain is missing or stale. AD-2 says only a validated plan can be rendered.
- **Clash:**
  1. Chicken and egg. To measure loudness the CLI must render. To render it needs a plan. The compiler refuses a recipe with no gain. A literal implementation can never produce the first gain. Each team invents a bypass (a `--no-gain` flag, a fake gain of 0 dB, a second compiler path), and AD-2's "one compiler path" is gone.
  2. "Loudness-relevant parameters" is undefined. The CLI team hashes every Core and level field; the validator team excludes `author`, `date`, `reason` but includes `seed`; neither includes stem file contents, the sample rate, or the engine version, all of which change loudness. Recipes then pass in one build and fail in another.
  3. The written gain changes the recipe bytes, so the recipe hash that keys golden files (AD-15) changes on every export, and the loudness hash itself lives inside the hashed object unless explicitly excluded.
  4. Loudness of a looping recipe (FR-7) is unbounded in length; the measurement window is undefined.
  5. Order against the limiter is ambiguous: the gain sits before the limiter, so measured loudness depends on limiter action, and the gain to hit target is not linear in gain.
- **Proposed rule (tighten AD-13):** "The compiler has exactly one entry point, `arc_compile(recipe, mode)`, where mode is `final` or `measure`. `measure` ignores the stored gain, applies unity loudness gain, and produces a plan flagged non-exportable that only `arc_render_offline` accepts. The loudness-relevant set is defined in the JSON Schema by an `x-loudness: true` annotation on each field; the loudness hash is SHA-256 over the JCS-canonical (RFC 8785) projection of those fields plus the content hashes of every referenced stem, the sample rate, and the engine DSP revision. The gain and hash fields are excluded from both the loudness hash and the recipe hash. The measurement window is: the whole session for fixed-length recipes; ramp-in plus two body iterations for looping recipes. The gain is solved iteratively against the post-limiter output until within 0.2 LU, and the number of iterations is recorded in the report."

### H2. Golden file store vs CLI report vs Python reference: what is the "recipe hash"?

- **Both obey:** AD-15 keys golden files by recipe hash; AD-17 puts the recipe hash in the report. Neither defines it.
- **Clash:** The CLI hashes raw file bytes; the golden tooling hashes parsed-and-reserialized JSON; Python hashes `json.dumps(sort_keys=True)`. A whitespace edit or a key reorder silently orphans a golden file, or a number written as `6` vs `6.0` vs `6.00` yields two hashes for the same recipe. Worse, number parsing: the engine parses `0.1` with its own parser into a double and the Python reference with `float()`; if the engine parser is not correctly rounded, the two renderers start from different parameters.
- **Proposed rule (new AD-19, Recipe canonical form):** "The recipe hash is SHA-256 of the RFC 8785 (JCS) canonical serialization of the recipe after removing the fields `loudness_gain_db`, `loudness_hash`, and `signoff`. All numeric parsing in the engine uses a correctly rounded decimal-to-binary64 conversion (`std::from_chars`), never locale-dependent functions. A conformance test parses a fixed corpus of edge-case numbers in C++ and Python and compares bit patterns. Both hashes appear in every report and golden file name."

### H3. Engine integer phase accumulator vs Python reference

- **Both obey:** AD-9 mandates integer phase accumulators; AD-16 says the reference is written from the spec in double precision and never ported from engine code; FR-12 demands less than -100 dBFS sample by sample.
- **Clash:** An integer accumulator quantizes every frequency to a multiple of `fs / 2^N`. With a 32-bit accumulator at 48 kHz the step is about 1.1e-5 Hz. Over an 8-hour render that is up to 0.32 cycles of phase difference against a reference that computes the exact frequency, so the sample-by-sample comparison fails by tens of dB, while every AD is satisfied. The reference team cannot fix it without porting engine code (forbidden) because the spec does not state the quantization. Rounding mode (truncate vs round-to-nearest) for the increment is also unspecified, so two engine implementers diverge from each other too.
- **Proposed rule (tighten AD-9):** "The signal spec, not the engine code, defines phase: each oscillator's phase increment is `round_half_even(f * 2^64 / fs)` as an unsigned 64-bit integer, phase wraps modulo 2^64, and the oscillator reads the top bits. The Python reference implements the same quantized increment from this sentence. The sine approximation's maximum absolute error is below -130 dBFS and is part of the spec. The frequency-accuracy test checks the quantized increment against the recipe value."

### H4. Rate-curve integration grid: engine vs reference

- **Both obey:** AD-10 fixes an internal block; FR-1 requires the instantaneous rate within 0.01 Hz along a curve with continuous phase.
- **Clash:** One engine developer updates the theta rate once per internal block (cheap, legal, within 0.01 Hz for slow curves); the reference integrates the curve per sample or analytically. The phase difference accumulates over a sweep and the reference match fails. Or the developer updates per block and changes the block size later, changing output (see H8). Interpolation shape between curve points (linear in Hz, linear in log Hz, spline) is also undefined, and the Sleep starter (3 Hz to 0 Hz sweep) depends on it.
- **Proposed rule (new clause in AD-9 or the recipe spec):** "Rate curves are piecewise linear in Hz between breakpoints, evaluated per sample, and the phase increment is recomputed every sample using the quantization rule of H3. The integration rule is: `phase[n+1] = phase[n] + inc(f(n))`, where `f(n)` is the curve value at sample n. No block-rate parameter updates in the Core zone. The reference implements the same recurrence from this text."

### H5. Validator spacing check vs Python spacing test

- **Both obey:** CLAUDE.md spacing rule; FR-9 says the validator rejects; FR-13 says every render is tested for spacing. AD-2 makes the validator the gate. "Non-sine carriers' spacing model" is Deferred to Phase 1.
- **Clash:**
  1. FR-2 and FR-3 already allow sawtooth, smoothed on-off, reverse saw, and custom theta envelopes, and triangle and softened square gamma carriers. Those have infinite harmonic series. The validator team counts only first-order sidebands (carrier plus or minus rate); the test team counts every spectral peak above -60 dBFS in an FFT. A recipe passes compile and fails the test, or vice versa. The spine defers the model while v0.1 ships the shapes.
  2. "At any point in the session, including during rate curves": the validator team samples curves at 1 s intervals; the test team checks each STFT frame. Interior crossings are missed by one and caught by the other.
  3. "In each ear": with Orbit (Phase 2) or per-channel gains, one team assumes all layers in both ears, the other uses the per-ear gain. Results differ.
- **Proposed rule (new AD-20, One spectral component model):** "A single data table in `tests/` (read by codegen into the engine and directly by Python) lists, for each carrier waveform and envelope shape, the spectral components to count: offset from carrier as a multiple of the modulation rate, up to the harmonic where the component falls below -60 dBc. The validator evaluates spacing analytically over each curve segment by interval arithmetic on component frequencies, not by sampling. Spacing is checked assuming every layer is present in both ears. A shape absent from the table is rejected by the validator; until Phase 1 extends the table, v0.1 accepts only the shapes in it."

### H6. Gamma PAC layer vs coupling-timing test: what is "theta phase"?

- **Both obey:** AD-5 says gamma depth is a function of theta reference phase only.
- **Clash:** The engine team uses the theta oscillator's raw phase accumulator (0 deg at accumulator zero). The test team derives phase from the rendered theta envelope by Hilbert transform, with 0 deg at envelope maximum. For a sine envelope these may differ by 90 deg depending on whether the envelope is built from sin or cos; for sawtooth, reverse saw, and custom curves the envelope maximum is not at a fixed oscillator phase at all. Every gamma peak lands at the "right" phase by one definition and fails the 2 ms test by the other. Also: after an edge-smoothing filter (FR-2) the envelope maximum moves.
- **Theta-only attack inside this hole:** a custom theta envelope with two maxima per cycle (legal under "custom curve") makes the in-file theta reference's measured dominant rate twice the theta rate; gamma still couples to the oscillator's single cycle. The in-file rhythm and the coupling no longer agree, which is exactly the "coupled to something without a waveform" failure in a new form.
- **Proposed rule (tighten AD-5):** "Coupling phase is defined on the theta reference's envelope as rendered: 0 deg is the envelope's global maximum within each cycle, measured after edge smoothing; the spec tabulates the oscillator-phase offset of that maximum for each built-in shape. Custom theta envelope curves must have a single global maximum per cycle and are validated for it. The coupling test and the engine both use this definition, and the test also checks the dominant envelope rate of the theta reference equals the recipe theta rate."

### H7. Stereo-linked master limiter vs binaural layer

- **Both obey:** AD-4 allows exactly per-channel gain and a stereo-linked limiter after the binaural join, and forbids channel mixing. The FR-4 isolation test mutes one binaural oscillator and measures its carrier in the other channel.
- **Clash:** A stereo-linked limiter applies one gain to both ears, computed from the louder ear. When it acts on gamma PAC peaks (40 Hz AM) the binaural carriers in both ears get 40 Hz gain modulation, and the left ear's level drives the right ear's gain. Nothing is summed, so AD-4 is obeyed; the isolation test (one-oscillator mute) does not see it because no carrier leaks. Yet the binaural pair now carries in-file gamma-rate and theta-rate AM, i.e., the limiter has coupled the binaural layer to the gamma envelope, contrary to FR-4 "nothing couples to the binaural layer", and side frequencies appear at carrier plus or minus 40 Hz that the spacing check never modeled. The limiter's attack and release are also unspecified, so the reference (H3) cannot match it at -100 dBFS.
- **Proposed rule (tighten AD-4):** "The limiter is a safety stage, not a loudness stage: the loudness gain (AD-13) is set so that in a normal render the limiter applies no gain reduction. A render assertion fails if gain reduction exceeds 0.1 dB on more than 0.1 percent of samples, or if the limiter's gain-reduction signal has any spectral component above -80 dB at the theta, gamma, or beat rate. The limiter algorithm (lookahead length, attack, release, detector) is written in the signal spec so the reference implements it."

### H8. Fixed internal block size: unpinned constant that shapes output

- **Both obey:** AD-10 says output is identical for any host call size; AD-11 swaps plans at a block boundary; AD-9 says bit-exact across platforms.
- **Clash:** The internal block size is never given. The mobile team raises it to 512 to save battery; the desktop team keeps 64. Any block-rate quantity (plan swap time, stem sequencer event times, snapshot cadence, any per-block smoothing) now lands on different samples. Unedited renders may still match if nothing is block-rate, but nothing in the ADs forbids block-rate DSP, and H4 shows the temptation.
- **Proposed rule (tighten AD-10):** "The internal block size is a single compile-time engine constant, identical on every platform, and part of the engine DSP revision. No Core or Tone DSP value depends on the block size except plan swap timing; a test renders with the constant set to two different values in a test build and asserts identical output for an unedited plan."

---

## Phase holes

### H9. Orbit 3D renderer vs gamma-to-theta coupling timing

- **Both obey:** AD-8 sends the gamma PAC layer through the 3D renderer and keeps theta out; AD-5 makes gamma depth a function of theta phase.
- **Clash:** The 3D renderer adds latency (FIR HRTF of 128 to 512 taps is 1.3 to 5.3 ms of group delay at 48 kHz, plus interaural delay up to about 0.7 ms that changes as the object moves). Theta goes straight to the bus. Gamma envelope peaks now arrive late against the in-file theta reference by more than the 2 ms tolerance, and the lag differs per ear and over time. Coupling is exact inside the engine's math and wrong in the file. Also, if the 3D renderer offers room or reverb for Orbit, reverb smears the 40 Hz envelope and reduces measured modulation depth.
- **Proposed rule (new clause in AD-8):** "Every Core path reaches the stereo bus with the same latency: the engine delays the theta reference and binaural paths by the 3D renderer's fixed latency. The Orbit renderer applies only direct-path gain, filtering, and interaural delay, no reverb or reflections. The coupling test runs per ear on the final output with Orbit active, and the interaural delay is included in the 2 ms budget."

### H10. Carrier guard (Tone zone) vs Core zone boundary

- **Both obey:** AD-3 says no Tone graph node takes Core signal or state as input; AD-6 says the Tone zone reads no Core clock, phase, or envelope state; the signal flow puts the carrier guard in the Tone zone; FR-25 says the stem bed is notched at every active carrier.
- **Clash:** The guard must know every active Core carrier, and carriers can follow curves over time. Team A reads the live Core oscillator frequencies each block (breaks AD-3 and AD-6). Team B notches only the static recipe values (misses curves and sidebands). Team C has no guard. All three can claim compliance.
- **Proposed rule (tighten AD-3):** "The plan compiler computes a notch schedule (frequency, width, depth per time segment) from the spectral component table of H5 and stores it in the plan. The carrier guard reads only that compiled schedule, which is plan data, not Core state. The guard notches every counted Core component, including AM side frequencies, with width at least the spacing rule (50 Hz) and depth set in the threshold table."

### H11. Carrier guard vs binaural isolation test

- **Both obey:** FR-4 test: mute one oscillator, measure its carrier in the other channel, require 90 dB. Stems are stereo files.
- **Clash:** A stem with energy at 256 Hz in the left channel looks, to the isolation test, like right-ear binaural leakage into the left ear. Team A runs the isolation test with the Tone zone off (passes, real output untested). Team B runs it with stems on and the test fails at 30 dB because guard notch depth is unspecified. Nothing tells either team which is correct.
- **Proposed rule (tighten AD-4 test clause):** "The isolation test runs on the full render with every Tone and Orbit stage active. Guard notches at binaural carriers apply to both channels with depth at least 100 dB at the carrier frequency (threshold table row). A second structural test asserts the binaural oscillators' samples reach the bus through no stage other than per-channel gain."

### H12. Host audio adapter (miniaudio) vs AD-4

- **Both obey:** AD-4 says "the engine never sums or downmixes its output channels". AD-1 forbids hosts from synthesis or mixing, but channel conversion and resampling in miniaudio are not "mixing" in the obvious reading.
- **Clash:** The Android host opens a device that reports 1 channel (Bluetooth hands-free profile, some USB devices) and miniaudio's default channel converter downmixes stereo to mono. The binaural pair is summed, which is exactly the original project's bug, one layer outside the engine. Equally, the host opens a 96 kHz or 44.1 kHz device while rendering at 48 kHz and miniaudio resamples, so the phone output no longer matches the render. Or a Phase 3 developer uses `ma_engine` (which has its own spatializer) instead of `ma_device`.
- **Proposed rule (new AD-21, Host output contract):** "Hosts open the device with `ma_device` only (never `ma_engine` or `ma_sound`), exactly 2 output channels, `ma_channel_mix_mode_simple` disabled for downmix, and request the engine's sample rate. If the device cannot provide 2 independent channels, the host refuses to start any recipe with a binaural layer and shows the reason. If the device rate differs, the host restarts the engine at 44.1 or 48 kHz, whichever the device accepts, and only otherwise allows miniaudio resampling, flagged in the session log. An adapter test opens a mono virtual device and asserts the binaural recipe is refused."

### H13. Stem sequencer vs PRNG streams under loop, swap, and seek

- **Both obey:** AD-14: one seed, independent stream per consumer by fixed name.
- **Clash:** Streams are stateful. After a live plan swap, team A carries stream state over; team B reseeds from the new plan. After the ramp-in, the loop body repeats: team A keeps drawing (loops pick new stems each pass), team B rewinds (each pass identical). Seeking to minute 30 requires replaying all prior draws or gives different picks. Names are also unspecified: `slot_3` vs the slot's id; inserting a slot shifts index-named streams so every later pick changes.
- **Proposed rule (tighten AD-14):** "The PRNG is counter-based: each draw is `H(seed, stream_name, event_index)` with H a fixed keyed hash (for example SipHash-2-4 or Philox) defined in the spec. `stream_name` is the stable id string of the consumer in the recipe, never an array index. `event_index` is derived from session time and loop iteration, so any draw is computable without replaying earlier draws. A plan swap keeps seed and names; loop iterations draw new events by default unless the recipe sets `repeat_picks`."

### H14. Seek and resume (FR-30) vs AD-1 "output is a function of sample index"

- **Both obey:** AD-1 states output is a function of (plan, seed, sample rate, sample index). FR-30 resumes from the same point after a call.
- **Clash:** Limiters, filters, notches, the stem decoder, and edge-smoothing are stateful. Rendering sample N cold differs from rendering it after N-1 samples. Team A implements resume by keeping the engine instance paused (identical); team B by recreating the engine and starting at index N (different, with a limiter and filter transient that can click). Designer scrub (FR-20) has the same split. AD-1 as written is false for any stateful stage, so implementers will interpret it two ways.
- **Proposed rule (tighten AD-1):** "Output is a function of (plan, seed, sample rate) and the sample index reached by continuous rendering from 0. The C API offers `arc_seek(index)`, which renders a fixed pre-roll defined in the spec (silent, discarded) before the target so stateful stages settle; seeked output must match continuous output within -100 dBFS after the pre-roll, tested. Hosts resume by keeping state when possible and by `arc_seek` otherwise; a ramp of at least 10 ms is applied on resume."

### H15. Plan swap vs Core phase continuity

- **Both obey:** AD-11: new plan swapped at a block boundary with ramps of at least 10 ms.
- **Clash:** Team A crossfades old plan output into new plan output over 10 ms. During the crossfade, two theta references with different phases coexist; gamma in the new plan couples to the new theta while the old gamma still sounds; the binaural layer has four carriers. Team B keeps the running oscillators and ramps parameters. With closed-form phase (H14 reading of AD-1), a rate change recomputes phase as `index * new_inc` and jumps. All legal.
- **Proposed rule (tighten AD-11):** "A plan swap never crossfades Core layers. The engine carries every Core phase accumulator across the swap and ramps each changed Core parameter (rate, carrier, depth, gain) over at least 10 ms from its current value. Topology changes in the Tone zone may crossfade. A test swaps a theta rate mid-render and asserts phase continuity and the coupling test across the swap."

### H16. Designer live audition vs AD-13 loudness gate

- **Both obey:** AD-11 says every edit produces a new plan; AD-13 says the validator rejects a recipe whose loudness hash no longer matches.
- **Clash:** Every edit to a loudness-relevant parameter makes the stored hash stale, so the compiler rejects the edited recipe and the designer cannot audition it. Team A adds a "skip loudness" flag to the designer path (a second compile path, against AD-2); team B re-measures on every slider move (an offline render per edit, not real time).
- **Proposed rule (extend H1 mode set):** "`arc_compile` accepts mode `audition`, which uses the last stored gain (or unity if none) and marks the plan non-exportable. Export, publish, push-to-device, and CLI final renders require mode `final`. The plan carries its mode and `arc_render_offline` in CI rejects non-final plans for golden comparison."

### H17. Designer warnings (FR-21) vs engine validator

- **Both obey:** AD-12 lists compile but no "validate with warnings" call; FR-21 needs warnings before a failing setting and flags for non-failing ones (for example non-sine binaural).
- **Clash:** The Flutter team reimplements range and spacing logic in Dart to show warnings while dragging. Two validators drift.
- **Proposed rule (tighten AD-12):** "The C API returns all diagnostics from `arc_compile`, each with severity (error, warning, info), parameter path (JSON Pointer), value, rule id, and limit. No rule logic, range, or threshold exists in Dart or any host; hosts render the diagnostics list. A CI grep forbids range constants in `app/`."

### H18. Listener controls (FR-31) vs determinism, loudness, and the API

- **Both obey:** AD-12's API has no control input; AD-11 says hosts change sound only by submitting a plan.
- **Clash:** The app team implements intensity by editing recipe JSON and recompiling: the recipe hash changes, the loudness hash goes stale (H16), and the render cannot be traced to a golden. Another team scales output in Dart-side native code (a host doing mixing, against AD-1). Session length on a looping recipe and Orbit on/off (which changes gamma latency, see H9) have no defined path at all.
- **Proposed rule (new clause in AD-2):** "Listener controls are a typed control vector, `{intensity_db, session_length_s, orbit_enabled}`, passed to `arc_compile` with the recipe. Each control's range comes from the recipe. The control vector is part of the plan identity, appears in every report, and is excluded from the loudness hash; intensity is applied as tone-layer gain after the loudness gain and can only reduce level. Golden files use the default control vector."

### H19. C API plan handles vs dart:ffi

- **Both obey:** AD-11: the render call never allocates or frees; hosts submit plans. AD-12: stable ABI.
- **Clash:** Dart attaches a `NativeFinalizer` to the plan handle; when the Dart object is collected, the plan is freed while the audio thread still renders it (use after free). Team B frees the retired plan inside the render call (a free on the audio thread). Error structs with `char*` fields have no defined owner.
- **Proposed rule (tighten AD-12):** "`arc_submit_plan` transfers ownership of the plan to the engine; the host must not touch the handle afterwards. Retired plans are returned through a lock-free single-producer single-consumer queue that a non-audio host thread drains with `arc_collect_retired()` and frees. Error and diagnostic structs use fixed-size inline char buffers and are owned by the caller. Every API struct starts with a `size` field for ABI versioning."

### H20. Engine snapshot vs visualizer and designer views

- **Both obey:** AD-11: hosts read state only from a lock-free snapshot. AD-18: visualizer never pulses at entrainment rates. FR-19: designer shows waveform and spectrum.
- **Clash:** The snapshot shape is undefined. The engine team publishes per-block theta phase and gamma envelope (the designer needs them). The app's visualizer reads the same snapshot and maps gamma envelope to brightness, violating AD-18 while "reading the snapshot only". Dart reads a multi-field struct without a sequence counter and gets torn values.
- **Proposed rule (tighten AD-18 and AD-11):** "The snapshot has two profiles. `arc_snapshot_calm` contains only session time, arc position, and per-layer levels smoothed with a low-pass below 0.5 Hz; it is the only profile the mobile build exposes. `arc_snapshot_scope` (waveforms, spectrum, phases) exists only in designer builds behind a compile flag. Snapshots are published by seqlock or triple buffer with a sequence number, and the reader retries on mismatch."

### H21. Stem decoder vs AD-10 native 44.1 and 48 kHz with no resampling

- **Both obey:** AD-10 renders natively at both rates with no resampling; AD-9 has an engine-owned decoder.
- **Clash:** A stem file has one sample rate. At the other rate, either the engine resamples (forbidden) or stems play at the wrong pitch and tempo, or the stem team ships 48 kHz only and the 44.1 kHz golden files silently omit stems. Opus decodes natively at 48 kHz only, which forces the issue.
- **Proposed rule (tighten AD-10 before the codec choice):** "Either stem packs ship one encoded file per supported rate and the manifest lists both, or the engine includes one engine-owned, bit-exact resampler used only for stems, specified in the signal spec and covered by the reference. The codec decision (Deferred) must state which. Core synthesis is never resampled."

### H22. Tone zone built-in effects vs AD-6

- **Both obey:** AD-6 locks only stem object motion rates and bars reading Core timing; AD-7 allows engine-owned live effects.
- **Clash:** A designer adds a built-in tremolo at 40 Hz or an auto-pan at 6 Hz to the ambience. No Core timing is read, so AD-6 holds, but the file now contains an uncoupled gamma-rate AM signal and a theta-rate rhythm that the spacing, coupling, and honesty rules never see. Measured PAC (gamma strength vs theta phase) on the whole mix now includes an uncoupled 40 Hz component. Stem sequencer slot changes at a fixed sub-second period do the same. A stem file whose content is a 40 Hz AM tone passes curation if the checklist does not check rhythm.
- **Proposed rule (extend AD-6):** "Every time-varying Tone parameter (LFO, tremolo, auto-pan, filter sweep, delay modulation, motion, sequencer event rate) has a locked rate range in the range table, traced to the design log, that excludes 1 to 60 Hz until research sets it. Stem curation (FR-26) includes an automated envelope-spectrum check that rejects stems with an AM peak above a threshold in that band. A render assertion measures the Tone zone tap's envelope spectrum against the same threshold."

---

## Minor holes

### H23. Who owns the seed

- **Clash:** AD-14 says the PRNG is seeded "from the recipe seed"; nothing forbids `--seed` on the CLI or a per-session random seed in the app for variety. Golden keys (AD-15) do not include the seed.
- **Proposed rule:** "The seed lives only in the recipe. Hosts cannot override it; variety across sessions is expressed as a recipe field `seed_policy: fixed | per_session`, where `per_session` derives the session seed by the counter-based hash from the recipe seed and a session counter supplied in the control vector (H18). The seed used is in every report and in the golden key."

### H24. Engine version, table data, and golden lookup

- **Clash:** The threshold and range tables are "read by code"; the engine does no file I/O, so they must be compiled in, yet a table edit does not bump the engine version. AD-15 keys golden files by engine version: on a version bump, lookups miss and a naive test passes with "no golden found". Build flags or compiler versions can also change bytes without a version change.
- **Proposed rule:** "Tables are code-generated into the engine at build; their content hash, the compiler id, and the build flags hash form the engine DSP revision, which is part of the engine version string. A missing golden for any starter or test recipe at the current version and rate is a CI failure. A version bump first checks byte identity against the previous version's golden; identical files are carried forward automatically, changed files require re-approval by ear."

---

## Further attacks on binaural isolation and theta-only coupling

### H25. Theta "absent, muted, or zero depth" vs level fades

- **Clash:** AD-5 rejects coupled gamma when the theta reference is muted at any point. One validator reads "muted" as the theta layer gain equals 0; another reads it as theta depth equals 0. A Relax or Sleep-style fade-out that brings theta level to -inf before the gamma fade completes passes the depth reading and leaves seconds of gamma coupled to an inaudible reference. Conversely, a strict reading rejects every recipe whose end fade is simultaneous.
- **Proposed rule (tighten AD-5):** "At every sample where coupled gamma's level is above -80 dBFS, the theta reference's level must be within the coupling-reference ratio in the range table (provisional: no more than 20 dB below gamma) and its depth above zero, checked analytically over the gain curves. Fade-outs end gamma before or with theta, never after."

### H26. Theta reference and gamma in different ears

- **Clash:** Per-channel gain, or Orbit (H9) placing gamma hard left while a per-channel gain puts theta right, leaves gamma coupled to a reference the same ear does not hear. All ADs hold.
- **Proposed rule:** "The theta reference is always present in both ears with equal gain (no per-channel gain on the theta path). Orbit width is limited so the gamma layer never falls more than a locked number of dB below its anchor level in either ear."

### H27. Binaural pair and non-Core paths that look like Core

- **Clash:** AD-3 bars Tone nodes from taking the binaural path as input, but nothing bars a Tone stem or a built-in Tone oscillator (for example a drone generator or a noise generator with a resonant filter) from producing a steady tone at one ear's binaural carrier, which then goes through Tone width and reverb. The listener hears a "binaural-like" component processed by spatial stages, the exact failure the rule exists to prevent, under a different owner.
- **Proposed rule (tighten AD-3):** "Only the Core zone may contain engine-generated tonal oscillators. The Tone zone's sources are stem files and noise only. The carrier guard notch schedule (H10) covers the binaural carriers in the Tone path in both channels, so no Tone content at a binaural carrier survives into the bus."

---

## Suggested new or changed ADs, consolidated

| Change | Closes |
| --- | --- |
| AD-1: define output as continuous render from 0; add `arc_seek` with spec pre-roll | H14 |
| AD-2: control vector as compile input; compile modes `final`, `measure`, `audition` | H1, H16, H18 |
| AD-3: compiled notch schedule; Tone sources are stems and noise only | H10, H27 |
| AD-4: limiter must be idle in normal renders, algorithm in spec; isolation test on full mix | H7, H11 |
| AD-5: coupling phase defined on rendered envelope maximum; theta level relation over time; theta equal in both ears | H6, H25, H26 |
| AD-6: locked rate ranges for every time-varying Tone parameter; stem AM screening | H22 |
| AD-8: matched Core latency; Orbit direct-path only | H9 |
| AD-9: 64-bit phase increment rule and sine error bound in the spec; per-sample curve integration | H3, H4 |
| AD-10: block size a pinned constant; stem rate strategy fixed with the codec | H8, H21 |
| AD-11: no Core crossfade on swap; two snapshot profiles; seqlock | H15, H20 |
| AD-12: diagnostics list with severities; plan ownership transfer and retired-plan queue; size-prefixed structs | H17, H19 |
| AD-13: x-loudness annotations, JCS hashing, stem content hashes, looping window, iterative solve | H1 |
| AD-14: counter-based PRNG keyed by stable names; seed owned by recipe | H13, H23 |
| AD-15: DSP revision includes table, compiler, and flag hashes; missing golden fails | H24 |
| New AD-19: recipe canonical form and number parsing | H2 |
| New AD-20: one spectral component model shared by validator, guard, and tests | H5, H10 |
| New AD-21: host output contract (2 channels, no downmix, no `ma_engine`, rate handling) | H12 |

Each proposed number (100 dB notch depth, 0.1 dB limiter activity, -130 dBFS sine error, 20 dB theta-to-gamma ratio, 0.5 Hz calm snapshot cutoff, 1 to 60 Hz excluded Tone band) is a placeholder for the design log, per CLAUDE.md rule 3; each needs a source or a logged engineering reason before it locks.
