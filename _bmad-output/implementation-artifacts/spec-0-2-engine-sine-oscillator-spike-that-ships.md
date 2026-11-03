---
title: 'Story 0.2: engine sine oscillator (spike that ships)'
type: 'feature'
created: '2026-11-03'
status: 'in-progress'
baseline_commit: '28196581af6342d1855c9121f81c3c873a8427c1'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** AD-9 (bit-exact engine on four platforms) is the project's riskiest assumption and is still unproven: the engine has no signal code, `docs/signal-spec.md` does not exist, and the hash probe carries only an arithmetic test pattern.

**Approach:** Write the §core and §sine sections of `docs/signal-spec.md` with worked test vectors, then implement them in `engine/` (64-bit phase accumulator, increment and seconds-to-samples rules, engine-owned sine) and independently in a Python ideal-sine module. Add two engine sine renders (44.1 and 48 kHz) to the hash probe so the existing full tier proves the four-platform hashes, and prove the -120 dBFS, 0.01 Hz, and 1 ms bounds in tests.

Decisions (2026-11-03, build agent, under Audio's standing "settle tech forks yourselves" preference; spec approved by Audio 2026-11-03, kept as one story at about 2,600 tokens): the spec section lands as the first commit on the story branch, before any test or engine commit, and is reviewed in the same pull request (no separate PR). Story 0.3 has not built the tables yet, so the values this story asserts live in two small cited data files under `tests/tables/` that Story 0.3 absorbs; tests read them, never literals.

## Boundaries & Constraints

**Always:**
- Signal spec rules (the only formula source, AD-19):
  - Phase: `uint64` accumulator, one cycle = 2^64, `phase[n+1] = phase[n] + inc` mod 2^64.
  - Increment: `q = (f_hz * 2^64) / fs` in IEEE binary64 (the multiply is exact, one rounded division); `inc` = `q` rounded to the nearest integer, ties to even. Valid for `0 <= f_hz < fs/2`; anything else (NaN included) gives `inc = 0`.
  - Seconds to samples: `n` = `t_s * fs` in binary64, rounded to nearest, ties to even; valid for `t_s >= 0`.
  - Ideal sine: `y = sin(2*pi*phase/2^64)`.
  - Engine sine: fold the phase to `[-pi/2, pi/2]` with exact integer steps, convert once to binary64, then an odd Taylor polynomial to x^11 (coefficients the binary64 nearest to `±1/k!`, written as hex float literals) in a fixed Horner order. Bound: `20*log10(max|engine - ideal|) <= -120 dBFS` (design log 2026-10-28 (o)). Test resolution: 2^24 evenly spaced phases over one cycle plus each quadrant edge and its neighbours ±1.
  - Every rule has worked vectors: exact phases (0, 2^61, 2^62, 2^63, 3*2^62), increments for theta, gamma, and binaural carriers and rates at both rates, sample values of a 450 Hz carrier at 44.1 kHz, and ties-to-even cases for both rounding rules.
- Vectors live once in `tests/data/signal_spec_vectors.json`, written by `tools/signal_spec_vectors.py` from high-precision arithmetic (`fractions`, `decimal`), never from the engine. A test checks the spec's tables equal the JSON. The C++ test and the Python test each pass them on their own.
- Bounds and ranges (`tests/tables/thresholds.json`, `tests/tables/ranges.json`): every row has id, value, unit, source. Rows: sine error -120 dBFS; frequency accuracy 0.01 Hz; drift 1 ms over 8 h; theta rate 1 to 6 Hz; theta carrier 100 to 500 Hz; gamma rate 30 to 60 Hz; gamma carrier 200 to 500 Hz; binaural carrier up to 1000 Hz plus the beat rate (right ear up to 1030 Hz); beat rate 0 to 30 Hz; session up to 8 h; sample rates 44100 and 48000. Values match `thresholds-and-ranges.md`. C++ gets them through CMake `string(JSON)` at configure time.
- Quantization error under 0.01 Hz and 8-hour drift under 1 ms for every carrier and rate: from the engine's own increments on a 0.001 Hz grid over each range at both rates (C++), and exactly with `fractions` at every range endpoint plus an analytic worst-case bound (Python).
- Hash probe components `sine-44100` and `sine-48000`: engine sine, unmodulated, 1 s each at 1 Hz, 450 Hz, and 1000 Hz carriers, phase 0 at each segment start, float32. A Python test checks the host-built probe output against the ideal sine within -120 dBFS. Cross-platform: exact against `windows-x64` through the existing `full` workflow.
- Engine code stays pure: no libm, no `long double`; the symbol and flag checks cover the new sources. New `tools/check_fp_pragmas.py` fails on floating-point pragmas in `engine/` (deferred-work entry from part 2), with passing and must-fail fixtures, run in both workflows.
- Tests first by a fresh-context QA agent, committed tests-only (after the spec commit) before implementation. No em dashes; CLAUDE.md "Never" terms stay out. Signals named by carrier, modulation type, rate.

**Never:**
- Render, recipe, C API, denormal-mode, or validator work (Epic 1). Loaders, coverage, or design-log gating for the tables (Story 0.3).
- A Python reference that implements the engine polynomial. Weakening any bound. Changing `tools/hash_compare.py` or the workflows beyond adding the pragma check.
- Pushing or opening the pull request without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Exact phases | phase 0, 2^62, 2^63, 3*2^62 | engine sine 0, 1, 0, -1 within the bound | N/A |
| Increment tie | `q` exactly k + 0.5 | even neighbour | N/A |
| Out of range | f < 0, f >= fs/2, NaN | `inc = 0` | no throw |
| Samples tie | t_s = 2^-8 at 48 kHz (187.5) | 188 | N/A |
| Wraparound | phase near 2^64 plus inc | wraps mod 2^64, sine continuous | N/A |
| Pragma | `#pragma clang fp contract(fast)` in an `engine/` file | check exits 1 | names file, line |
| All platforms match | four manifests with `sine-*` | compare passes exact | N/A |
| Platform differs | a `sine-*` hash cannot be made identical | design log entry (platform, component, reason), `ci/hash_tolerance.json` entry citing it, AD-9 flagged in the spine's Open Questions; story closes | defined outcome |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` -- new: §core and §sine only, with vector tables.
- `engine/src/core/phase.hpp|.cpp` (`phase_increment`, `seconds_to_samples`), `engine/src/core/sine.hpp|.cpp` (`sine(uint64)`, a small `SineOscillator`), namespace `arcani::core`. Add to `_arcani_engine_sources` in `engine/CMakeLists.txt` and expose `engine/src` to tests and probe through a separate INTERFACE target (`arcani::engine_internal`); `arcani.h` unchanged (C API is Story 1.2).
- `tests/hashprobe/main.cpp`, `CMakeLists.txt` -- link the engine, add the two components; keep `probe-arith` and its comment block; update "Story 0.2 adds..." line. `ARCANI_HASHPROBE_EXTRA_FLAGS` still targets the probe only, so the contraction job's `probe-arith` must-differ is unaffected.
- `tests/cpp/test_sine.cpp`, `tests/cpp/test_phase.cpp`, `tests/cpp/CMakeLists.txt` (generate an include from the JSON files with `string(JSON)`).
- `reference/ideal.py` -- new, numpy and stdlib: increment rule, seconds-to-samples, ideal sine, probe segment render. Load by path with `importlib` like `tests/python/test_probe_reference.py:66`.
- `tests/python/test_signal_spec_core.py` (vectors, doc vs JSON, exact quantization and drift), `tests/python/test_probe_sine.py` (host probe vs ideal, reusing the probe-build pattern at `test_probe_reference.py:166-197`), `tests/python/test_fp_pragmas.py`.
- `tools/check_fp_pragmas.py` -- stdlib, pattern of `tools/check_compile_flags.py`; one step in each job of `fast.yml` and `full.yml` that already runs the flag check.
- `docs/design-log.md` -- entry (bb): the two rounding rules, the Taylor degree with its computed error, probe components, interim tables, and the S0.2 hash result; Current state rows. `reference/README.md` one line.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- close the pragma entry; add "Story 0.3 absorbs `tests/tables/`".
- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- `0-1-build-skeleton-and-ci-matrix: done` (PR #1 merged as 2819658).
- Do not change: `tools/hash_compare.py`, `tools/hash_manifest.py`, `ci/hash_expected.json`, the denylist, `tools/check_compile_flags.py`.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, `tests/data/signal_spec_vectors.json`, `tests/tables/*.json` -- spec and data, first commit.
- [ ] `tests/cpp/*`, `tests/python/test_signal_spec_core.py`, `test_probe_sine.py`, `test_fp_pragmas.py`, pragma fixtures -- QA agent, failing tests-only commit.
- [ ] `engine/src/core/*`, `engine/CMakeLists.txt` -- engine.
- [ ] `reference/ideal.py` -- Python ideal.
- [ ] `tests/hashprobe/*` -- sine components.
- [ ] `tools/check_fp_pragmas.py`, `.github/workflows/*.yml` -- pragma check.
- [ ] `docs/design-log.md`, `reference/README.md`, `deferred-work.md`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given a clean checkout, when `uv run pytest` and the `windows-clang-cl` workflow preset run, then all tests pass, the engine meets -120 dBFS over the test resolution, and every grid and endpoint stays under 0.01 Hz and 1 ms at both rates.
- Given Audio's go-ahead to push, when the `full` workflow runs on the pull request, then `sine-44100` and `sine-48000` match `windows-x64` byte for byte on all four platforms, or the defined fallback in the matrix is applied and recorded.

## Spec Change Log

## Design Notes

Taylor to x^11 on `[-pi/2, pi/2]`: truncation at most `(pi/2)^13/13!`, about 5.7e-8 (-145 dBFS), 25 dB inside the bound; coefficients are exact-derivable, so no fitted constants need a source. Folding before conversion keeps every step but the int64-to-binary64 conversion exact. With a 2^64 cycle, increment error is at most about `fs/2^64` plus the division rounding (under 1e-12 Hz), so the 0.01 Hz and 1 ms bounds pass by many orders; the tests still measure them.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass.
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: build and ctest pass.
- `uv run python tools/signal_spec_vectors.py --check` -- expected: exit 0.

**Manual checks:**
- After Audio's go-ahead: the `full` run on the pull request passes, or the fallback is recorded.
