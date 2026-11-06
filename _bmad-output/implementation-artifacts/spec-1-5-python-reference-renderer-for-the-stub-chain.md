---
title: 'Story 1.5: Python reference renderer for the stub chain'
type: 'feature'
created: '2026-11-05'
status: 'in-review'
baseline_commit: '03a39de8b30ea8ff2e69b44bc05c036d9f487e61'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** `reference/` holds only the ideal sine and the Core rules. Nothing renders a recipe independently of the engine, so an engine DSP bug can only be caught by ear, and the theta reference stub outputs zeros, so the stub chain carries no layer signal to compare.

**Approach:** Route the S0.2 sine through the theta reference stub as an unmodulated carrier (signal spec first), write an independent double-precision Python renderer of the stub chain in `reference/`, and add a reference match assertion that compares engine pre-quantization output and every tap with it sample by sample, failing as silent when either side is below a table-set minimum level.

Decisions (2026-11-05, build agent, under Audio's standing "settle tech forks yourselves" preference):
- **Theta stub (§Stub chain rewrite):** with `theta_reference` present, `inc_T = phase increment rule(carrier_hz, fs)`, `phase_T[n] = n * inc_T mod 2^64`, `a_T = 1.0`, and `theta[c][n] = a_T * sine(phase_T[n])`, the same value in both channels; absent, `inc_T = 0`, `a_T = 0.0`. Seek sets `phase_T` like the binaural phases. `bus = theta + gamma` stays exact; `join = bus + bin` is now one rounding. Mute affects only the binaural oscillator, so a muted channel equals its theta tap bit for bit. Unit amplitude matches the binaural stub; `stub-chain-1s-beat-6.json` (300 Hz theta, 400 and 406 Hz binaural) then peaks near 2.0 and clips in a 24-bit WAV by §24-bit rounding. It is a test fixture, not for listening; real levels arrive in Epic 2 and 4. Its rationale text (hash-excluded) is updated; the vectors gain theta columns.
- **Reference (`reference/stub_chain.py`):** `render(recipe_path, fs)` reads the JSON with the standard library, returns the five taps and the output as interleaved stereo float64 arrays, using `ideal.py` rules and the ideal sine; `join = bus + bin` in binary64. Imports only the standard library, NumPy, and `reference/`.
- **Engine dump:** test-only executable `arcani-tapdump RECIPE RATE OUT_DIR` in `tests/tapdump/`, public header only, writes `out.f64` and one `<tap>.f64` per tap (raw little-endian binary64, interleaved). The pytest builds it with the platform preset's own build directory (`cmake --build --preset <p> --target arcani-tapdump`, Windows through `tools/dev.ps1`), so CI adds no configure.
- **Reference match assertion (`tests/assertions/reference_match.py`):** per signal and per channel, `measured = 20 log10(max |engine - reference|)` (exact match gives `-inf`, reported as `null` with note `exact`); pass when `measured < row reference-match` (strictly). Before that, if `20 log10(max |x|)` of either side is below row `reference-match-min-level`, the result is `fail`, note `silent`. Returns the Story 1.4 report assertion shape. Signals compared: output, theta, bus, join, master. The gamma tap, and the theta tap of a recipe without `theta_reference`, are zeros by the spec: they get an exact-zero check on both sides, not a reference match.
- **New table row** `reference-match-min-level`, value `-60`, unit `dBFS` (peak over the whole render, per signal and channel), source "engineering default: 40 dB above row reference-match; design log 2026-11-05 (jj)". Decided by Audio (2026-11-05). Clear `pending` on `reference-match`.
- **Hash probe:** its stub chain recipe gains `"theta_reference": {"carrier_hz": 300}`, so the new engine path joins the per-run four-platform compare (no expected entry until Story 1.6).

## Boundaries & Constraints

**Always:**
- Signal spec section and vectors merge before engine or reference code. Tests first by a fresh-context QA agent, committed failing.
- Every check has a passing and a must-fail case: an engine output doctored in the harness with a -90 dBFS error fails; a scaled-down signal fails as silent. The match measure is calibrated first on synthesized pairs with known errors (-110, -100.5, -99.5, -90 dBFS) read within 0.1 dB.
- A test proves `reference/` imports no engine code and loads no engine binary: an import scan (no `ctypes`, `cffi`, `subprocess`, `os.add_dll_directory`, no `engine/`, `cli/`, or `build/` path) and an isolated run (`python -I`) after which no such module is loaded.
- Both rates, both 1 s stub chain fixtures, every compared signal and channel. All existing checks keep passing; tests that assumed a zero theta tap follow the new spec.

**Never:**
- The reference reading engine code, the generator's engine-sine polynomial, or engine output.
- Gamma, envelopes, AM depth, coupling (Epic 2), loudness or gain (Epic 4), block-size tests (1.6), a reference match in the CLI report.
- Weakening any threshold, or pushing or opening the PR without Audio's go-ahead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Match | beat-6 and beat-0, 44.1 and 48 kHz | every compared signal and channel `pass` | N/A |
| Doctored | engine out plus a -90 dBFS error at one sample | `fail`, measured about -90 | must-fail |
| Silent | both sides scaled below the minimum level | `fail`, note `silent` | must-fail |
| One side silent | engine zeros, reference real | `fail`, note `silent` | must-fail |
| Spec zero tap | gamma tap; theta tap of beat-0 | exact zeros both sides | a nonzero sample fails |
| Muted ear | beat-6, each ear muted | muted channel equals theta tap bit for bit; isolation rows still pass | N/A |
| Past end | samples at and after N | `+0.0` both sides | N/A |

</frozen-after-approval>

## Code Map

- `docs/signal-spec.md` §Stub chain -- theta oscillator lines, per-sample `theta`, seek, mute note, vectors with theta columns; `tools/signal_spec_vectors.py` `stub_chain_sample`, `STUB_CHAIN_FIXTURES` (add theta carrier or none), `stub_chain_rows`; regenerate `tests/data/signal_spec_vectors.json`; `tests/cpp/SpecTables.cmake` `kStubChain` gains theta bits.
- `engine/src/plan/plan.{hpp,cpp}` -- `Plan` gains theta increment and amplitude from `recipe::ThetaReference` (`recipe.hpp:52`). `engine/src/render/renderer.{hpp,cpp}` -- `phase_` gains a theta phase, `seek` sets it, `render_block` line `theta = ...`.
- `tests/cpp/test_stages.cpp` (`row_matches`, zero-theta checks at 210, 236), `test_isolation.cpp`, `test_seek.cpp`, `isolation.hpp` -- follow the spec.
- `tests/hashprobe/main.cpp` `kStubChainRecipe` and comment; `tests/python/test_probe_sine.py` docstring.
- `reference/stub_chain.py` (new), `reference/README.md`; reuse `reference/ideal.py` (`phase_increment`, `seconds_to_samples`, `ideal_sine`).
- `tests/tapdump/{CMakeLists.txt,main.cpp}` (new, pattern `tests/hashprobe/`, links `arcani::engine` only, `_CRT_SECURE_NO_WARNINGS` on Windows); add to the root `CMakeLists.txt` under `ARCANI_BUILD_TESTS`; `tools/check_cli_includes.py` stays about `cli/`.
- `tests/assertions/reference_match.py` (new, reads rows via `assertions.row`), `tests/python/test_reference_match.py`, `tests/python/test_reference_independent.py` (new).
- `tests/tables/thresholds.tsv`, `docs/design-log.md` (jj), `recipes/fixtures/valid/stub-chain-1s-beat-6.json` rationale, `docs/timeline-guidebook.html`, `sprint-status.yaml`.

## Tasks & Acceptance

**Execution:**
- [x] `docs/signal-spec.md`, `tools/signal_spec_vectors.py`, vectors JSON, `SpecTables.cmake` -- theta stub and vectors -- spec first.
- [x] `tests/cpp/*`, `tests/python/test_reference_*.py`, `tests/assertions/reference_match.py` contract, `tests/tapdump/` -- QA agent writes failing tests -- tests first.
- [x] `engine/` plan and renderer, `reference/stub_chain.py`, `reference_match.py` -- implementation.
- [x] `thresholds.tsv`, design log (jj), fixture rationale, hash probe recipe -- table and records.
- [x] `docs/timeline-guidebook.html`, `sprint-status.yaml` -- records.

**Acceptance Criteria:**
- Given `reference/`, when it renders a recipe, then it reads recipe JSON, works in binary64, uses the increment rule and ideal sine, and its output at every stub chain vector row is within 1e-15 of the vector's ideal value (past-end rows exact `+0.0`).
- Given the independence test, then it passes on `reference/` and fails on a must-fail module that imports `ctypes`.
- Given the engine and the reference on both fixtures at 44.1 and 48 kHz, then output, theta, bus, join, and master differ by less than row `reference-match` in every channel, and gamma (and beat-0 theta) are exact zeros on both sides.
- Given the engine render after the theta change, then the C++ stub chain vector test passes bit for bit and both isolation rows still pass with each ear muted.

## Design Notes

Error budget: `join` sums two sines each within -120 dBFS of ideal (S0.2 measured -145 dBFS), plus one binary64 rounding on each side, so the expected match is near -140 dBFS against a -100 dBFS line.

## Verification

**Commands:**
- `powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl` -- expected: every ctest passes.
- `uv run pytest` -- expected: all pass, including the reference match at both rates.
- `uv run --no-project python tools/check_wording.py`, `tools/check_fp_pragmas.py`, `tools/signal_spec_vectors.py --check`; `uv run --locked python tools/check_row_coverage.py`; `tools/check_table_log.py --base main` -- expected: exit 0.

## Implementation Notes

QA agent, tests-first pass (2026-11-05). Execution tasks 1 and 2 only; nothing under `engine/`, `reference/stub_chain.py`, or `tests/assertions/reference_match.py` is written, and `thresholds.tsv`, the hash probe, and the design log are untouched. Settled test-side choices the implementation must follow:

- **Spec (§Stub chain):** new "Theta reference oscillator" block (`f_T`, `inc_T`, `phase_T`, `a_T = 1.0`; absent field gives `a_T = 0.0`, `inc_T = 0`), per-sample line `theta[c][n] = a_T * sine(phase_T[n])`, mute note (muted channel equals its theta tap bit for bit), exactness paragraph (`bus = theta` exact, `join = bus + bin` one rounding, exact when either is `+0.0`), Level note (peaks near 2.0, beat-6 WAV clips, fixture not for listening), Seek line. The two 24-bit rounding vectors keep their values; their labels now read "stub chain sample (beat 0, ...)" and "406 Hz binaural sine sample (48 kHz, n = 63)", since beat-6 output now includes theta.
- **Vectors:** `STUB_CHAIN_FIXTURES` rows are `(fixture, theta_hz or None, left, beat, length)`; each `stub_chain` row gains `theta_carrier_hex` (`none` when absent), `inc_theta`, `phase_theta`, `theta_bits`, `ideal_theta`. `left_bits`/`right_bits` stay the output; `ideal_left`/`ideal_right` are now the ideal output (exact decimal sum of the ideal theta and binaural sines, rounded once to 25 digits). beat-0 rows are byte-identical to before. `kStubChain` appends `has_theta, theta_carrier_hz (0.0 when none), inc_theta, phase_theta, theta_bits`. The spec still has 11 vector tables.
- **Contracts:** full text in the docstring of `tests/python/test_reference_match.py`. In short: `reference.stub_chain.render(recipe_path, fs, frames=None) -> dict` with keys `output, theta, gamma, bus, join, master`, each 1-D C-contiguous float64 interleaved stereo of `2 * T` (T = `frames` or N), `+0.0` at n >= N; built from `ideal.phase_increment` and `ideal.ideal_sine` exactly as the spec lines (the test checks theta, bus, join bit for bit against that composition). It is imported as `reference.stub_chain` with the repo root on `sys.path`. `assertions.reference_match`: `level_dbfs`, `difference_dbfs` (ValueError on shape mismatch), `match(name, engine, reference)` (check order: not finite, then silent, then exact, then strict `<`; report shape `name,row,threshold,unit,measured,result,note`; notes `not finite`, `silent`, `exact`, ""), `match_stereo(signal, ...)` (names `reference match <signal> left|right`), `all_positive_zero`.
- **Tap dump:** `arcani-tapdump RECIPE RATE OUT_DIR [EXTRA_FRAMES]` (optional 4th argument added so the past-end row is testable), writes `out, theta, gamma, bus, join, master .f64`, prints `arcani-tapdump: frames N total T`. Not EXCLUDE_FROM_ALL, so the workflow builds it; the pytest still runs `cmake --build --preset <p> --target arcani-tapdump`.
- **Spec-zero signals:** gamma always, and theta and bus for beat-0, get the exact-zero check on both sides (bus of beat-0 is `theta + gamma = +0.0`, so it would fail as silent).
- **Independence:** the scan forbids `ctypes, _ctypes, cffi, subprocess, _posixsubprocess, multiprocessing, importlib`, `__import__`, `os.add_dll_directory/system/popen/startfile/exec*/spawn*`, `numpy.ctypeslib`, `CDLL`/`LoadLibrary`, non-docstring strings naming `engine/`, `cli/`, `build/` or a binary, and any import outside stdlib, numpy, reference. Docstrings may mention the engine. NumPy itself loads `ctypes`, so the `python -I` run judges modules loaded after an `import numpy` baseline; the ctypes must-fail is caught by the scan (the AC). Must-fail stand-ins live in `tests/fixtures/reference_independence/`.
- **Throwaway proof:** a copy outside the repo with a minimal engine change (plan `theta_increment`/`theta_amplitude`, renderer theta phase set in seek), a reference, the match module, and the new row passed every ctest and the new pytest modules. Measured match: about -140 to -146 dBFS on every signal and channel. Planted bugs all caught: reference join in float32, reference ignoring the theta carrier, wrong right carrier, a 15 dB loose line, no silent check, `-0.0` accepted as zero, reference importing subprocess, seek leaving the theta phase, theta in one channel only, and a 1e-9 engine scaling (below the match line, caught by the C++ bit vectors and the dump vector test).
- **Open points for task 4:** (1) Add row `reference-match-min-level` and clear `pending` on `reference-match`; the md mapping test (`test_tables_loader.py::test_md_mapping_holds_for_real_tables`) then also needs `-60` in the "Reference match" row of `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md` (it failed in the throwaway copy until then). (2) Update the beat-6 fixture rationale ("the theta reference stub outputs zeros" is now false) and the hash probe recipe. (3) The new files are untracked, so `check_wording.py` without paths does not see them until committed; run with explicit paths they pass.

**Red state at hand-off:** `signal_spec_vectors.py --check` and `check_wording.py` (also on all new and changed files) pass; `test_signal_spec_core.py` passes (99). ctest: `arcani_tests` fails in `test_stages.cpp` (vector rows, theta tap, theta-only fixture, muted ear equals theta, past end, doctored-sample case), `test_seek.cpp` (theta after seek), `test_isolation.cpp` (muted channel of beat-6 not silent), all because the engine theta stub still outputs zeros. pytest: 18 failed and 14 errors, all in `test_reference_match.py` and `test_reference_independent.py` (missing `reference/stub_chain.py`, `tests/assertions/reference_match.py`, row `reference-match-min-level`, and the dump's theta bits). Environment note: on the dev PC, Device Guard currently blocks the freshly relinked `build/windows-clang-cl/cli/arcani-render.exe`, so the 16 `[cli]` cases also fail there (exit 4551); the same tests pass in the out-of-repo copy, so this is not caused by the test change.

## Spec Change Log

## Review Triage Log

Pass 1 (2026-11-06): blind hunter (BH), edge case hunter (EC), verification gap (VG), all fresh context, on diff 03a39de..4970c30 (generated vectors, guidebook, and `_bmad-output` left out).

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | BH: isolation not re-proven with theta present; crosstalk must-fails not run on beat-6 | false | `tests/cpp/test_isolation.cpp` pass case (160) and both crosstalk must-fails (193, 215) loop over kBeat0 and kBeat6 | reject |
| 2 | BH: muted-ear render never compared with the reference | low | mute is an offline measurement control, not a recipe field; the C++ tests prove a muted channel equals its theta tap bit for bit; a fix adds a reference parameter | reject |
| 3 | BH, VG: theta carrier only checked at 300 Hz; no-binaural branch never matched against the engine | medium | every engine theta value check uses beat-6 (300 Hz); the 200 Hz C++ test is carrier-independent; a hard-coded 300 Hz increment would pass | patch |
| 4 | BH, EC, VG: engine-vs-reference tests skip when `shutil.which("cmake")` fails on Windows | low | repo-wide pattern (`test_probe_sine.py`, `test_tables_crosscheck.py`); CI puts cmake on PATH; on the dev PC the cases ran (only NDK skips reported) | reject |
| 5 | BH: pytest builds C++ and asserts on an unconfigured checkout | low | the workflow and CI build before pytest; the build is incremental | reject |
| 6 | BH: isolated run checks modules, not behavior (audit hook) | low | the import scan covers the AC; an audit hook adds a mechanism | reject |
| 7 | BH, EC: scan misses exec, eval, compile | low | direct addition to the name set | patch |
| 8 | EC: `from numpy.ctypeslib import load_library` then bare `load_library` passes the scan | medium | ImportFrom flags names only when the module is exactly os, ctypes, or numpy; the Name list is shorter than FORBIDDEN_NAMES | patch (with 7) |
| 9 | EC: os aliased (`import os as o; o.execv`) bypasses the prefix check | low | unlikely in the project's own reference; fix tracks aliases | reject |
| 10 | BH: `isolated_run` parameter `extra_forbidden_roots` unused | low | the body never reads it | patch (delete) |
| 11 | BH: calibration levels test checks only ordering | low | offsets 1, 2, 3, 4 dB would pass; direct correction | patch |
| 12 | BH, EC: at-threshold branch of the strictness test may never run | low | runs only if a candidate's log10 lands exactly on the threshold | patch |
| 13 | BH: beat-6 fixture clips in every CLI render, no test pins the clamp | low | the CLI tests compare whole files with the harness rounding, clamp included; later assertions are later stories | reject |
| 14 | BH, EC: reference accepts any `fs` | low | only test code calls it, always at 44.1 or 48 kHz; a fix adds a guard | reject |
| 15 | BH: dump cross-check skips bus, join, master bits | false | a miswired bus or join differs from the reference by a whole sine and fails the match; master, join, and output are identical by the spec | reject |
| 16 | BH, EC: `arcani-tapdump` aborts on bad_alloc for huge inputs; never creates OUT_DIR | low | test tool fed 1 s fixtures by its own test, which creates the directory | reject |
| 17 | EC: reference treats `theta_reference: null` as absent | low | the engine rejects that recipe (`invalid/theta-reference-null.json`); the reference is fed valid fixtures only | reject |
| 18 | EC: non-integer `frames` truncated | low | only test code passes integers | reject |
| 19 | VG: nothing checks the hash probe stub chain carries the theta reference | medium | the shape test asserts only finite, even, non-silent; dropping theta still passes | patch |

- Review pass 1 patches in 1d101bd (triage rows 3, 7, 8, 10, 11, 12, 19). Orchestrator check: `windows-clang-cl` workflow 4/4 ctest entries pass; `uv run pytest` 1,205 passed, 2 NDK-only skips; wording, pragma, vector, row coverage, and table log checks exit 0. Nothing deferred.
