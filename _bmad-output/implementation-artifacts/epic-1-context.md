# Epic 1 Context: Render a recipe end to end

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Audio, or a build agent, can take a minimal JSON recipe, compile it through the engine into an immutable plan, and render it from the command line to a 24-bit WAV plus a machine-readable report. The render is byte-identical at any block size, matches the independent Python reference sample by sample, fails a test if anything leaks between ears, and every recipe field is range-checked from the start. Real signal layers arrive in Epic 2; this epic builds the pipe they flow through (schema, hash, C API, stage stubs, validator, CLI, reference, determinism) so each later layer lands already guarded and measured.

## Stories

- Story 1.1: Minimal recipe schema and recipe hash
- Story 1.2: C API, fixed stage list, seek, and isolation assertion
- Story 1.3: Validator framework, locked ranges, and carrier rule
- Story 1.4: Command-line renderer, report, and render speed
- Story 1.5: Python reference renderer for the stub chain
- Story 1.6: Determinism and block-size invariance

## Requirements & Constraints

- **Recipe file:** one JSON recipe fully defines a session (layer parameters, gain ramps, rate curves, levels, length, looping flag and max run time, schema and engine version, seed, author, date, rationale, loudness target, stored gain and loudness hash, describe-the-sound notes). Later epics add fields; Epic 1 defines the minimal set plus the stub chain's fields.
- **Schema:** a JSON Schema in `recipes/` validates every starter and fixture. Fields are `snake_case` with units in the name (`_hz`, `_deg`, `_db`, `_lufs`, `_s`), times in seconds. The schema tags each field loudness-relevant, hash-excluded, or neither. No routing fields and no coupling-target field exist; unknown properties are rejected.
- **Versioning:** every recipe declares schema version and engine version; an unsupported schema major version is rejected.
- **Recipe hash:** SHA-256 over RFC 8785 canonical JSON, excluding the stored loudness gain, the loudness hash, and schema-marked hash-excluded (non-audio) fields. Computed identically in the engine and in Python. Determinism key = recipe hash + pinned asset hashes (none in v0.1) + engine version + sample rate.
- **Rejection:** every blocking error names parameter, value, rule, and limit, and produces no plan and no output. The renderer accepts only compiled plans (`measure` or `final` mode).
- **Locked ranges and carrier rule:** compiler rejects any value outside the locked-range table and any modulated carrier under 4 times its worst-case modulation rate. Inclusive bounds pass at the bound; exclusive bounds reject it.
- **Isolation:** muted-ear method, at least 90 dB at engine output and 60 dB after the master chain, at any beat rate including 0 Hz.
- **CLI:** 2-channel 24-bit WAV, 48 kHz default, 44.1 kHz selectable, any other rate refused; rounding to 24 bits with no dither; report JSON per assertion (name, threshold row ID, threshold, measured, pass or fail) plus determinism key, seed, engine version. At least 20 times real time on the dev PC only; elsewhere marked not applicable. Rejected recipe writes no WAV and exits non-zero.
- **Reference:** independent double-precision Python, from the signal spec only, ideal sine; engine pre-quantization output and per-layer taps within -100 dBFS sample by sample at 44.1 and 48 kHz; fails as silent below a table-set minimum level. Imports no engine code.
- **Determinism:** byte-identical across repeat renders (same and separate processes) and at 1, 64, 512, 4096, and odd block sizes. No unseeded randomness anywhere in `engine/` or the WAV writer.
- **Process:** tests first from acceptance criteria by a fresh-context QA agent, as a failing tests-only commit before implementation. Every check ships with a passing and a must-fail fixture; no fault-injection code in `engine/`. Thresholds and ranges are read from `tests/tables/`, never hard-coded or weakened. Every engine story's fixture joins the cross-platform hash check at both sample rates.

## Technical Decisions

- **Pure core:** `engine/` depends only on the C++20 standard library. No threads, clocks, devices, files, network, or third-party libraries (so JSON parsing and SHA-256 are engine-owned). Output is a pure function of (plan, seed, sample rate, sample index); seek is pure.
- **Bit-exact math:** no libm transcendentals (engine-owned sine), 64-bit integer phase accumulators, no `long double`, no explicit FMA, `-ffp-contract=off`, no fast-math. Every float-to-integer conversion is clamped first and never given NaN. Denormal mode set on entry to each floating-point C API call and restored on every return, using MXCSR / FPCR intrinsics (no `fesetenv`, no `FENV_ACCESS`).
- **Plans only:** the compiler turns a recipe into an immutable plan; blocking errors and non-blocking structured warnings. Modes in v0.1: `measure` (loudness gain may be absent) and `final` (everything enforced). No host validates on its own.
- **C API:** one `arc_`-prefixed API, plain C types, status code plus structured error (parameter, value, rule, limit): compile, render frames, seek, per-layer taps, warnings, engine version, plan release. CLI and C++ tests include only the public header.
- **Real-time contract:** render never allocates, locks, blocks, does I/O, throws, or logs.
- **Fixed topology:** stage order theta reference, gamma PAC layer, stereo bus, binaural join, master chain (per-channel gain plus stereo-linked limiter). No stage type mixes, sums, or swaps channels. Fixed internal block size from the signal spec, buffered to the host request.
- **Signal spec:** `docs/signal-spec.md` is the only formula source. Each story writes only the section it needs, with worked test vectors, and that section merges before engine or reference implement it.
- **Tables as data:** `tests/tables/thresholds.tsv` and `tests/tables/ranges.tsv`, with C++ and Python loaders; every assertion reports its row ID; unused rows must be marked pending with their story.
- **Seed:** tooling always uses the recipe seed; v0.1 has no random consumer, but the report carries the seed.
- **Wording:** no em dashes, banned terms, or outcome claims in docs, code comments, strings, or recipe descriptions (CI wording check).

## Cross-Story Dependencies

- 1.1 (schema, parser, hash) feeds every later story: 1.2 compiles recipes, 1.3 registers fields against range rows, 1.4 puts the hash in the determinism key, 1.5 reads recipe JSON, 1.6 checks the key.
- 1.2 (C API and stage stubs) precedes 1.4 (CLI uses only the public header) and 1.5/1.6 (they render through it).
- Builds on Epic 0: the S0.2 engine sine and phase accumulator, S0.3 tables and loaders, S0.1 symbol denylist and hash compare, S0.4 wording check. 1.6 extends the S0.1 denylist and adds the deferred `sine-44100` and `sine-48000` hash entries.
- Epic 2 layers replace the stubs; Epic 3 adds the spacing rule into the 1.3 validator; Epic 4 adds loudness gain writing into the 1.4 CLI.
