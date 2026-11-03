# Design Log

Every changed default, range, or test threshold gets an entry here, with its source or test result (CLAUDE.md, Workflow). Newest entries go at the top of the log.

**Status values:**
- **proposed:** recommended, not yet in force
- **locked:** independently reviewed and in force
- **superseded:** replaced by a later entry, which it names

Sources point to `docs/research-library.md`, a research run under `_bmad-output/planning-artifacts/research/`, or a test result.

## Current state

| Parameter | Value | Status | Entry |
| --- | --- | --- | --- |
| Gamma AM rate, default | 40 Hz | proposed | 2026-10-27 (a) |
| Gamma AM rate, locked range | 30 to 60 Hz | proposed | 2026-10-27 (a) |
| Coupling phase, definition | 0 to 360 degrees on the in-file theta reference envelope, 0 degrees at its maximum | proposed | 2026-10-27 (b) |
| Coupling phase, default | 0 degrees (peak), with an uncoupled option | proposed | 2026-10-27 (b) |
| Learn mode coupling phase | 0 degrees (peak), was trough | proposed | 2026-10-27 (d) |
| Theta rate, default | open (6 Hz or slower) | open | project plan, Open decisions |
| Binaural layer in v0.1 starter recipes | off in Focus, Learn, Relax; on in Sleep (100 Hz, beat rate cycling sinusoidally over 0 to 3 Hz every 60 s) | proposed | 2026-10-27 (i), (n) |
| Binaural carrier | open (200/206 Hz or higher), set per recipe; not listener-adjustable | open | project plan, Open decisions; 2026-10-27 (g) |
| Binaural locked ranges | carriers below 1000 Hz; beat rate below 30 Hz (perception limit about 35 Hz) | proposed | 2026-10-21; 2026-10-27 (f) |
| Carrier-to-rate ratio | at least 4 times | provisional | project plan, Test thresholds |
| Carrier spacing | at least 50 Hz per ear between components of different layers, including side frequencies | provisional (value is a placeholder) | project plan, Test thresholds; 2026-10-27 (e) |
| Gamma carrier range, theta carrier, levels | 200 to 500 Hz; 450 Hz; tones -36, master -16 LUFS-I | engineering defaults | 2026-10-27 (g) |
| v0.1 provisional ranges | theta rate 1 to 6 Hz; theta carrier 100 to 500 Hz; depth 0 to 100 percent; burst 50 ms fixed | provisional | 2026-10-27 (h) |
| Spectral component threshold (spacing rule) | within 40 dB of the layer's strongest line | provisional (placeholder) | 2026-10-27 (i) |
| Dropout threshold | more than 1 ms of all-zero samples where signal is expected | provisional | 2026-10-27 (i) |
| Determinism scope | bit-exact across PC, Android, and iOS for the whole engine; a component proven unable falls back to -100 dBFS | proposed | 2026-10-27 (j), supersedes (i) on this point |
| Sample rates | Core renders natively at 44.1 and 48 kHz, never resampled; stems use an engine-owned deterministic resampler | proposed | 2026-10-27 (j) |
| WAV output dither | none in v0.1 (24-bit rounding) | engineering default | 2026-10-27 (j) |
| Loudness gain | measured at export, stored in the recipe, same live and offline | proposed | 2026-10-27 (k) |
| Limiter at stored gain | stays idle; v0.1 bound is zero gain reduction (any render where it acts fails) | proposed | 2026-10-27 (k), 2026-10-28 (p) |
| Visualizer | no more than 3 flashes per second; never pulses at theta, gamma, or beat rates; smoothing rate open | proposed | 2026-10-27 (k) |
| Tone zone time-varying rates (stem motion, effect LFOs, gates) | locked ranges required; values open | open | 2026-10-27 (k) |
| Seed policy | recipe seed for tooling and tests; fresh seed per play in consumer app, stored on device | proposed | 2026-10-27 (l) |
| v0.1 starter values | gamma PAC 250 Hz carrier, AM at 40 Hz; theta reference 450 Hz carrier; Learn 5.5 Hz; Relax 30 min, depth 25 percent; Sleep 45 min with 5 min fade, steady 2 Hz delta | provisional | 2026-10-27 (m), (n) |
| Looping max run time (v0.1) | Focus 45 min, Learn 20 min | engineering default | 2026-10-27 (m) |
| v0.1 starter loudness target | -36 LUFS-I | engineering default | 2026-10-27 (m) |
| Reference renderer sine | ideal sine; engine approximation error at most -120 dBFS against it | engineering default | 2026-10-28 (o) |
| Gamma bursts and swells | depth-gated: the gamma PAC carrier plays continuously, only AM depth is gated | proposed | 2026-10-28 (o) |
| Gamma burst edges | raised cosine, 10 ms each, inside the 50 ms full width (30 ms plateau) | engineering default | 2026-10-28 (o) |
| Non-sine binaural waveform (v0.1) | rejected with a named rule; a warning applies once the signal spec models it | proposed | 2026-10-28 (o) |
| Theta reference AM depth | locked range 0 to 100 percent; 75 percent in every v0.1 starter | engineering default | 2026-10-29 (s) |
| Relax theta reference build | level ramp from silence to full over the first 10 min; AM depth and rate unchanged | engineering default | 2026-10-29 (r) |
| Loudness window | the steady part, ramps and fades excluded: looping body only (looping); longest stretch with no gain ramp (non-looping); whole render never above target + 1 LU | proposed | 2026-11-01 (w), (x) |
| Session length, locked range | up to 8 h | engineering default | 2026-11-01 (u) |
| Golden listening coverage | each starter in full at 48 kHz; 44.1 kHz copy spot-checked (opening, every loop seam and transition, ending); record lists what was heard | proposed | 2026-11-01 (v), amends (q) |
| Relax gamma PAC fade-in | level ramp from silence to full over the first 2 min; AM depth, rate, and coupling unchanged | engineering default | 2026-11-01 (t), amends (r) |
| Golden sign-off | two stages: provisional (Audio), full (second listener); bound to file hash; v0.1 closes on provisional | proposed | 2026-10-29 (q) |
| Toolchain pins | `toolchain.json`: CMake 4.4.5, LLVM 23.1.4, Ninja 1.13.2, Catch2 3.16.1, Python 3.14, uv 0.13.6, NumPy 2.5.4, pytest 9.2.0 | proposed | 2026-11-02 (y) |
| Engine compile flags and symbol denylist | `-ffp-contract=off` for the whole project, no fast-math; warnings as errors on engine and CLI; engine library denies libm transcendentals, file, thread, clock, console symbols; `sqrt` allowed | proposed | 2026-11-02 (z) |
| CI runner layout | all GitHub-hosted: fast tier `windows-2025`, `ubuntu-24.04`; full tier adds `windows-11-arm`, `macos-15`, and the NDK probe on `ubuntu-24.04-arm`; no self-hosted runner | proposed | 2026-11-02 (aa), supersedes (y) runner paragraph |
| Full-tier toolchain pins | Apple clang 17.0.0.17000013 (Xcode 16.4); Android NDK r30 (clang 21.0.0, API level 21); arm64 LLVM, CMake, Ninja assets | proposed | 2026-11-02 (aa) |
| Cross-platform hash compare | exact against `windows-x64` and `ci/hash_expected.json`; tolerance only per cited entry in `ci/hash_tolerance.json`, bound -100 dBFS (strictly below) | proposed | 2026-11-02 (aa); 2026-10-27 (j) |
| CI wall-time budgets and schedule | `ci/wall_time_budget.json`; timeout twice the budget; nightly 03:00 UTC, skipped when main is unchanged | proposed | 2026-11-02 (aa) |
| Phase increment and seconds-to-samples rules | 64-bit accumulator; `inc` = round-half-even of binary64 `f*2^64/fs`; `n` = round-half-even of binary64 `t*fs`; out of domain gives 0 | proposed | 2026-11-03 (bb) |
| Engine sine | integer fold, odd Taylor to x^11, fixed Horner order; measured -145.0 dBFS against the ideal (bound -120) | proposed | 2026-11-03 (bb); 2026-10-28 (o) |
| Probe sine components | `sine-44100`, `sine-48000`: 1, 450, 1000 Hz carriers, unmodulated, 1 s each; byte-identical on all four AD-9 platforms (full run 41648370470) | proposed | 2026-11-03 (bb) |
| All other test thresholds | see project plan, Test thresholds (provisional) | provisional | project plan |

## Entries

### 2026-11-03 (bb): Signal spec core and sine rules, engine sine, probe sine components (S0.2)

- **Rounding rules (docs/signal-spec.md, Core):** phase increment `inc` = `q` rounded to the nearest integer, ties to even, where `q = (f_hz * 2^64) / fs` in binary64 (exact multiply, one rounded division); out of domain (`f_hz < 0`, `f_hz >= fs/2`, NaN, infinities) gives 0. Seconds to samples: `n` = `t_s * fs` in binary64, rounded to the nearest integer, ties to even; negative, NaN, infinite, or a product at or above 2^64 gives 0 (the spec's own choice for the uint64 limit, mirroring the increment rule). Ties to even matches IEEE 754 default rounding and Python's `round`, so the engine and the reference need no special case.
- **Engine sine:** exact integer fold of the 64-bit phase to `[-2^62, 2^62]`, one int64-to-binary64 conversion, a multiply by the binary64 nearest to `2*pi/2^64`, then an odd Taylor polynomial to x^11 in a fixed Horner order, coefficients the binary64 nearest to `+-1/k!` as hex floats. Computed truncation bound `(pi/2)^13/13!`, about 5.7e-8 (-145 dBFS). Measured: max error 5.63e-8 (-145.0 dBFS) over the spec test resolution (2^24 phases plus each quadrant edge and its neighbours), clang-cl 23.1.4, against the -120 dBFS bound (entry 2026-10-28 (o)).
- **Quantization and drift:** worst-case increment error `|inc - f*2^64/fs|` is at most 32.5 phase units for carriers and rates up to 1030 Hz, so frequency error is at most about 8.5e-14 Hz at 48 kHz, against the 0.01 Hz threshold; 8-hour drift is at most about 2.4e-8 s (worst at the 0.001 Hz grid floor of the 0 Hz ranges; about 3e-11 s or less at the endpoints of the ranges with a floor of 1 Hz or more) for every range row in `tests/tables/ranges.json` measured on the C++ 0.001 Hz grid and exactly at every range endpoint in Python, against 1 ms. Ranges with a 0 Hz floor use the 0.001 Hz grid step as their lowest nonzero frequency for the analytic drift bound (relative drift has no bound as f goes to 0; at exactly 0 Hz, `inc = 0` and there is no drift).
- **Probe components:** `sine-44100` and `sine-48000`, the engine sine, unmodulated, 1 s each of a 1 Hz, a 450 Hz, and a 1000 Hz carrier, phase 0 at each segment start, float32. They are compared exactly against `windows-x64` by the existing full tier; they have no `ci/hash_expected.json` entry (that file is unchanged), and the Python test checks the host-built probe against the ideal sine within -120 dBFS. Local `windows-x64` hashes (clang-cl 23.1.4): `sine-44100` `82dc6461...`, `sine-48000` `3ebea007...`; `probe-arith` unchanged at `933f0602...`.
- **Interim tables:** `tests/tables/thresholds.json` (sine-error, frequency-accuracy, drift-8h) and `tests/tables/ranges.json` (theta and gamma rates and carriers, binaural carrier and right ear, beat rate, session length, sample rates) hold every value these tests assert, each row with id, value, unit, and source, matching `thresholds-and-ranges.md`. `binaural-carrier-right` (up to 1030 Hz) is derived: binaural carrier max plus beat rate max. Story 0.3 absorbs both files with its loaders, coverage, and design log gate.
- **Pragma check:** `tools/check_fp_pragmas.py` fails on floating-point pragmas in `engine/`, run in every fast job and every full job that runs the flag check (deferred-work entry from Story 0.1 part 2).
- **S0.2 hash result (four platforms):** byte-identical. Full run 41648370470 on pull request #2 (2026-11-03): `tools/hash_compare.py` reported "4 platforms match windows-x64 for 3 component(s): probe-arith, sine-44100, sine-48000" across Windows x64 (clang-cl), Windows arm64 (clang-cl), macOS arm64 (Apple clang), and Android NDK arm64 (static binary on hosted arm64 Linux). Hashes: `sine-44100` (132300 samples) `82dc64616ec3e179f3d1a4d86c595b40044a5682160565ceaf53dbdb52b82922`, `sine-48000` (144000 samples) `3ebea0075617a73b49483b9c569637441bd2e9a55a82fbdfbedd7f504638e524`, equal to the local dev PC build. No fallback needed; no `ci/hash_tolerance.json` entry. This is the S0.2 result Story 0.5's AD-9 review uses.
- **Source:** Story 0.2 spec; AD-9, AD-10, AD-19; entry 2026-10-28 (o); test result: `uv run pytest` and the `windows-clang-cl` workflow preset pass on the dev PC.
- **Decided by:** build agent under Audio's standing preference to settle technical forks; spec approved by Audio 2026-11-03.
- **Status:** proposed.

### 2026-11-02 (aa): Full-tier runner layout, Android on hosted arm64 Linux, hash compare, wall-time budget, nightly skip

- **Runner layout:** every CI job runs on a GitHub-hosted runner; none is self-hosted. Full tier: Windows x64 on `windows-2025`, Windows arm64 on `windows-11-arm`, macOS arm64 on `macos-15` (exact labels, no "latest", so the Apple clang and Xcode pins hold), the Android NDK build on `ubuntu-24.04`, and the NDK probe run plus the contraction must-fail job on `ubuntu-24.04-arm`. Supersedes the runner paragraph of entry (y) and the epic's self-hosted PC runner: Smart App Control on the dev PC blocks test binaries, and hosted runners cost nothing for this public repo.
- **Android, chosen alternative:** no Android phone is available yet. The NDK r30 arm64 build of the hash probe is linked statically (bionic) and run on the hosted arm64 Linux runner: real arm64 hardware and the real NDK compiler, without the Android OS, which the engine never touches. Running it on a physical phone is a `deferred-work.md` entry for when one is available. The Android jobs build without the Catch2 tests (the CLI test needs the build machine's path) and run the compile-flag and symbol checks directly on the NDK build.
- **Pins added to `toolchain.json`:** Windows arm64 LLVM 23.1.4 (`LLVM-23.1.4-woa64.msi`: LLVM publishes an arm64 `.msi`, so it is unpacked with `msiexec /a` like the x64 one, not the `tar.xz` fallback), CMake and Ninja Windows arm64 assets; Linux arm64 LLVM, CMake, and Ninja for the contraction job (the `linux-clang` preset's pin check needs LLVM 23.1.4 there too); CMake and Ninja macOS assets; Apple clang `17.0.0.17000013` (CMake's AppleClang version string) with Xcode at `/Applications/Xcode_16.4.app`, the default Xcode on the `macos-15` image (image 20261028); NDK r30 (30.0.16248370, the current LTS) with its SHA-256 computed locally, clang 21.0.0, and API level 21 (`ANDROID_PLATFORM=android-21`, the lowest level NDK r30 supports, chosen so the engine assumes nothing newer; a later story may raise it). Every download hash comes from the GitHub release asset digest, or for the NDK, from the downloaded zip. `cmake/Pins.cmake` checks AppleClang on Apple, the NDK clang and API level on Android, and LLVM elsewhere, naming expected and found.
- **Hash compare rule:** a test-only probe (`tests/hashprobe/`, never in `engine/`) writes one raw little-endian float32 file per component; Python hashes them on the host (`tools/hash_manifest.py`). Part 3 has one component, `probe-arith`: a float32 logistic map and output scaling whose two multiply-add expressions change bits when contraction is on. Its expected SHA-256 comes from the NumPy float32 reference (`tools/probe_reference.py`, each operation rounded separately) and lives in `ci/hash_expected.json`. `tools/hash_compare.py` compares every platform against `windows-x64` (the reference platform) in exact mode, and every platform against `ci/hash_expected.json`, so four identically wrong results fail. Tolerance mode applies only to a (platform, component) entry in `ci/hash_tolerance.json` that cites a design log entry; the bound (-100 dBFS, measured as `20*log10(max|a-b|)` in float64, strictly below) lives in that file with its source, AD-9 and entry (j). The must-fail job builds the probe with `-ffp-contract=fast` on arm64 and passes only if its hash differs from the expected one.
- **Verdict and nightly skip:** a final `verdict` job (`if: always()`) fails unless every build, test, probe, and compare job succeeded; a skipped, cancelled, or never-scheduled Android job fails it. The nightly run (03:00 UTC) skips every job when the last successful scheduled or manual full run on `main` has the current `main` commit; the summary then says "skipped: main unchanged since run <id> (<sha>)", and that is the only skip that passes. Pull request and manual runs never skip.
- **Wall-time budget:** `ci/wall_time_budget.json` holds, per tier and job, the budget minutes, runner label, billing multiplier, and runs per month. Fast budgets: Linux 15 min, Windows 20 min (fast run 41578714584 took about 3 min per job). Full budgets, first estimates to correct after the first full run: gate 5, Windows x64 25, Windows arm64 30, macOS 20, Android build 20, Android probe run 10, contraction must-fail 25, hash compare 5, verdict 5. Every job's `timeout-minutes` is twice its budget, and its last step fails the job when it ran over budget.
- **Estimate (`tools/check_wall_time.py --estimate`):** at 120 fast runs and 45 full runs a month (30 nightly, about 10 pull requests, 5 manual), at full budget: 10,725 runner minutes a month, 23,700 billed-equivalent minutes with the multipliers (Linux 1, Windows 2, macOS 10; arm64 runners counted at their x64 multiplier). Billed minutes are 0: the repo is public and GitHub-hosted runners are free for public repos. Shortfall if the repo were private: 21,700 minutes over the Free plan's 2,000. Remedy, only if the repo goes private: drop the nightly to pull request and manual runs, and run macOS weekly.
- **First full run (41588933334, 2026-11-03):** failed on two test issues, fixed after it. The Android pin must-fail tests ran on hosted runners that carry their own NDK; they now run only in the android-build job. The macOS symbol check passed vacuously: on Mach-O, `llvm-nm --undefined-only` prints names with no type column, so `tools/check_engine_symbols.py` now lists all symbols and keeps the undefined types. Every other check passed, including the pinned Apple clang 17.0.0 (Xcode 16.4), the NDK r30 build and API level, and the static NDK probe starting on `ubuntu-24.04-arm`. Measured wall times: gate 0.1, Windows x64 3.0, Windows arm64 4.3, macOS 1.2 (stopped at the Python tests), Android build 0.6, Android probe run 0.1, contraction must-fail 1.8, verdict 0.1 min, all far inside budget.
- **Passing full run (41609300056, 2026-11-03):** every job passed on commit fde4365. Hash compare: all 4 platforms (windows-x64, windows-arm64, macos-arm64, android-arm64) give the same `probe-arith` hash as windows-x64, which matches the reference `933f0602...`. Measured wall times: gate 0.2, Windows x64 2.9, Windows arm64 4.6, macOS 1.6, Android build 0.6, Android probe run 0.2, contraction must-fail 2.0, hash compare 0.2, verdict 0.1 min. Full budgets in `ci/wall_time_budget.json` now sit at about 3x the measured time, rounded up to 5 min (Windows x64 25 to 10, Windows arm64 30 to 15, macOS 20 to 10, Android build 20 to 5, Android probe 10 to 5, contraction must-fail 25 to 10); job timeouts stay at twice the budget. Tighter budgets catch a slow regression sooner; macOS matters most at a 10x minute multiplier.
- **Spending cap:** Audio sets the GitHub Actions spending limit to $0 (docs/ci-setup.md), so no run can ever bill.
- **Source:** AD-9; Story 0.1 part 3 spec; runner image READMEs (`macos-15-arm64` 20261028, `ubuntu-24.04` 20261026, `windows-2025` 20261021); test result: `uv run pytest` passes on the dev PC (546 passed, 0 skipped, clang-cl 23.1.4); the host-built probe matches the reference hash `933f0602...`; a local `-ffp-contract=fast -mfma` build of the probe gives a different hash, as the arm64 must-fail job expects. First full run 41588933334 failed on two test issues (above); full run 41609300056 passed every job.
- **Decided by:** Audio (no phone for now, all hosted runners, nightly at 03:00 UTC, 2026-11-02).
- **Status:** proposed.

### 2026-11-02 (z): Engine compile flags, warning flags, and undefined-symbol denylist (AD-9)

- **Decision:** the top-level CMake adds `-ffp-contract=off` (clang-cl `/clang:-ffp-contract=off`) for the whole project with `add_compile_options`, so it lands after `CMAKE_CXX_FLAGS` and the build-type flags on every command line and restores contraction off after any earlier fp option. Other fast-math effects of an earlier flag are not undone; the flag check catches them. No fast-math flag is set anywhere. `arcani_engine` and `arcani-render` build with warnings as errors: clang `-Wall -Wextra -Werror`, clang-cl `/W4 /WX`. C++20 module scanning is off (`CMAKE_CXX_SCAN_FOR_MODULES OFF`): no modules are used, and the scan adds an `@` modmap response file to every compile command, which would hide flags from the check.
- **Checks:** `tools/check_compile_flags.py` reads the build's `compile_commands.json` and fails, naming toolchain, source file, and flag, when an `engine/` source's effective contraction is not off, a fast-math flag appears, a value-changing fp option appears, a command uses an `@` response file, or there are no engine sources. Flags count bare, behind `/clang:` or `-clang:`, or after `-Xclang`. Effective contraction: clang-cl moves every `/clang:` argument after all other arguments, so those are evaluated last; the value is then set by the last of `-ffp-contract=X` or an fp model that implies contraction on (`-ffp-model=precise|fast|aggressive`, `/fp:precise|fast`). The strict and except models never turn contraction on (verified with `clang-cl -###`). Value-changing fp options: `-fdenormal-fp-math=` and `-fdenormal-fp-math-f32=` other than `ieee`, `-mdaz-ftz`, `-fcomplex-arithmetic=basic`, `-mrecip` and `-mrecip=*`, `-fveclib=*` other than `none`, `-mfpmath=387`, and cc1 `-mreassociate`, `-menable-no-nans`, `-menable-no-infs`, `-menable-unsafe-fp-math`. `tools/check_engine_symbols.py` runs the `llvm-nm` found next to the pinned compiler (configure fails if it is missing there) on the engine library and fails on any undefined symbol in `tools/engine_symbol_denylist.json`. Both run from pytest on every fast-tier job and locally, each with a passing case and a must-fail case on a real configure or build.
- **Denylist families:** libm transcendentals with `f` and `l` variants (trig, inverse and hyperbolic trig, exp, exp2, exp10, expm1, log, log2, log10, log1p, pow, cbrt, hypot, erf, erfc, tgamma, lgamma, `lgamma_r`, sincos, their `_finite` and `sincos_stret` forms, the pi forms such as `sinpi` and Apple `__sinpi`, `exp2m1`, `exp10m1`, `log2p1`, `log10p1`, `rootn`, `pown`, `powr`, `compoundn`, Bessel `j0`/`j1`/`jn`/`y0`/`y1`/`yn`, complex `cexp` through `cabs` and `carg`, MSVC `__std_smf_*`, and vector `_ZGV*` forms); file (C stdio and POSIX file calls, glibc `__isoc99_`/`__isoc23_` fscanf and fortify `__fprintf_chk` forms, Win32 file calls, MSVC `__std_fs_*`, C++ file streams and `std::filesystem`); thread (pthreads, C11 threads, MSVC `_Thrd_*`/`_Mtx_*`/`_Cnd_*`/`_Smtx_*`, `__std_atomic_wait`/`notify`, `WaitOnAddress`, `WakeByAddress*`, `__libcpp_atomic_wait`, `sched_yield`, sleeps, `std::thread`, `std::jthread`, mutexes, condition variables); clock (C and POSIX clocks, `localtime`, `gmtime`, `mktime`, `ctime`, `asctime`, `strftime`, `tzset` with `_r`, `_s`, and 32/64 variants, Windows and Mach clocks, `std::chrono::*::now`); console (stdio console calls, glibc `__isoc99_`/`__isoc23_` scanf and `__printf_chk` forms, `stdin`/`stdout`/`stderr`, Win32 console calls, `std::cout` and the other standard streams, `std::print`). Raw C names match after stripping `__imp_` and one leading underscore; demangled C++ names and the Windows UCRT internals (`__stdio_common_*`, `__acrt_iob_func`, `_Thrd_*`, `_Mtx_*`, `_Xtime_get_ticks`, `_Query_perf_*`) count. Unseeded-randomness entries arrive with Story 1.6.
- **`sqrt` allowed:** IEEE 754 requires correctly rounded square root, so it gives the same bits on every target (spine review-freshness).
- **Deferred:** reproducible-binary flags (`/Brepro`, `-ffile-prefix-map`). No requirement asks for identical binaries, only identical output; logged in `deferred-work.md`.
- **Source:** AD-9; Story 0.1 part 2 spec; test result: `uv run pytest` passes on the dev PC (clang-cl 23.1.4), both must-fail cases fail as required; fast run 41578714584 (f9159fd) passed on windows-x64 and linux-x64.
- **Decided by:** Audio (part 2 scope and deferral, 2026-11-02).
- **Status:** proposed.

### 2026-11-02 (y): Toolchain pins for Story 0.1 and the fast-tier runner layout

- **Decision:** the toolchain pins chosen in Story 0.1 are LLVM 23.1.4 (clang-cl on Windows, clang on Linux), Ninja 1.13.2, and pytest 9.2.0, alongside the already decided CMake 4.4.5, Catch2 3.16.1, Python 3.14, uv 0.13.6, and NumPy 2.5.4. `toolchain.json` at the repo root is the single source for every version and for the SHA-256 of each third-party download (LLVM, CMake, Ninja, Catch2). CMake configure fails, naming expected and found, when the CMake or C++ compiler version differs from the pin.
- **Runner layout until part 3 (superseded by 2026-11-02 (aa): all runners hosted, no self-hosted PC runner):** the Windows x64 fast tier runs on a GitHub-hosted `windows-2025` runner, and Linux on `ubuntu-24.04`. The repo is public, so both are free (no billed minutes). Part 3 of Story 0.1 adds the guarded self-hosted runner on the dev PC with the Android work; the epic's runner layout is met when part 3 closes.
- **Manual step for Audio (branch rule):** in GitHub, Settings, Branches (or Rules, Rulesets), add a rule for `main`: require a pull request before merging, and require the status checks `windows-x64` and `linux-x64` from the `fast` workflow to pass, with "require branches to be up to date" on. After this, a failing fast-tier job blocks merge. The checks appear in the picker only after the workflow has run once on GitHub.
- **Source:** Story 0.1 part 1 spec; versions verified installed on the dev PC; download hashes taken from the GitHub release asset digests and, for the Catch2 source archive, computed locally.
- **Decided by:** Audio (split and hosted runner, 2026-11-02); pins chosen in Story 0.1.
- **Status:** proposed.

### 2026-11-01 (x): Non-looping recipes also measure loudness over the steady part

- **Decision:** for a non-looping recipe, the loudness gain is measured over the longest stretch where no layer or master gain ramp is active. Ramps and fades are excluded, as in entry (w) for looping recipes. A recipe whose steady part is shorter than the signal spec's minimum is rejected in `measure` mode. Over the whole render, integrated loudness must never exceed the target by more than 1 LU.
- **Reason:** in Relax the theta reference ramps in over the first 10 minutes of 30, so measuring the whole session would leave the steady part about 1 dB above target. One rule for every recipe: the steady part sits at the target, ramps and fades are quieter.
- **Effect on starters:** Relax measures from minute 10 to 30; Sleep measures from 0 to 40 min (before its fade).
- **Amends:** entry (w); AD-13 measurement window; S4.1 and S4.2.
- **Source:** epics and stories assumption audit, 2026-11-01.
- **Decided by:** Audio.
- **Status:** proposed.

### 2026-11-01 (w): Looping recipes measure loudness over the body only

- **Decision:** for a looping recipe, the loudness gain is measured over the looping body only, repeated seamlessly to the length the signal spec sets. The ramp-in is excluded. The steady part of Focus and Learn sits at the -36 LUFS-I target; the ramp-in is quieter by design. Over a whole render to the max run time, integrated loudness is reported and must never exceed the target by more than 1 LU.
- **Reason:** the earlier window (ramp-in plus one body, AD-13) is dominated by the ramp-in when the body is short. At 48 kHz the shortest seamless Focus body is 0.5 s (the least common period of 6 Hz, 40 Hz, 450 Hz, and 250 Hz), so the gain came mostly from a 5 min ramp from silence and the steady part would play roughly 3 to 5 dB above target while every test passed. Found in the assumption audit.
- **Amends:** AD-13 measurement window in the architecture spine; S4.1 and S4.2.
- **Source:** epics and stories assumption audit, 2026-11-01.
- **Decided by:** Audio (option a).
- **Status:** proposed.

### 2026-11-01 (v): Golden sign-off listening coverage

- **Decision:** for the v0.1 provisional sign-off, Audio hears each starter in full at 48 kHz. The 44.1 kHz copy is spot-checked: the opening, every loop seam, every transition (each gain ramp or fade start and end), and the ending. Each sign-off record lists exactly what was heard, as `full` coverage or as the time ranges of the spot check. The stage stays `provisional` either way. A tool lists every seam and transition time from the recipe so none is missed.
- **Reason:** listening all eight renders in full takes about 4 h 40 min, much of it repeating a sound just heard, and attention fades. The two sample rates carry the same recipe, and the automated checks already compare them in full. Audio: listening is subjective to a large extent, and every loop and transition must be heard.
- **Amends:** entry (q). The record gains a coverage field; the two stages are unchanged.
- **Source:** epics and stories party review, 2026-11-01.
- **Decided by:** Audio (option b from the room).
- **Status:** proposed.

### 2026-11-01 (u): Session length locked range up to 8 hours

- **Decision:** a recipe's session length has a locked range of up to 8 hours. A longer recipe is rejected with parameter, value, rule, and limit.
- **Reason:** no range capped session length, so a recipe of any length would compile. 8 hours is the longest length the drift test (S5.1) proves.
- **Engineering default:** no study sets it. Phase 0 sets the hearing-safety value alongside the looping max run time (WHO-ITU based).
- **Source:** epics and stories party review, 2026-11-01.
- **Decided by:** Audio.
- **Status:** engineering default.

### 2026-11-01 (t): Relax gamma PAC layer fades in over 2 min

- **Decision:** in the Relax starter, the gamma PAC layer's level ramps from silence to full over the first 2 minutes, following the signal spec's gain ramp law. Its AM depth (25 percent), rate, and coupling to the theta reference do not change. This amends entry (r), which left the gamma level unchanged.
- **Reason:** with (r) alone, the gamma PAC layer played at full level from the start, pulsing in step with a theta reference that was still nearly silent. Audio asked for a slow gamma fade-in of 1 to 2 minutes. 2 minutes is the slow end of that span.
- **Engineering default:** both the fade from silence and the 2 minute length. No study sets either for the sound. Revisit by ear at the Epic 6 sign-off.
- **Source:** epics and stories session, 2026-11-01.
- **Decided by:** Audio (fade-in, 1 to 2 min); 2 min picked within that span by the agent.
- **Status:** engineering default.

### 2026-10-29 (s): Theta reference AM depth range and starter value

- **Decision:** the theta reference AM depth has a locked range of 0 to 100 percent. Every v0.1 starter uses 75 percent: each theta cycle dips the theta reference carrier to a quarter of its peak amplitude, never to silence.
- **Reason:** no doc set a theta depth range or value, yet the validator needs a range (S2.1) and coupled gamma is rejected at zero theta depth (AD-5). 0 to 100 percent is the full physical span, matching the coupling depth range. Audio chose 75 percent over 100 percent for a gentler pulse that keeps the tone present, while leaving a deep, measurable theta phase.
- **Engineering default:** both the range and the 75 percent value. No study sets either for the sound. Revisit by ear at the Epic 6 sign-off.
- **Source:** epics and stories session, 2026-10-29.
- **Decided by:** Audio.
- **Status:** engineering default.

### 2026-10-29 (r): Relax theta reference "builds" means a level ramp

- **Decision:** in the Relax starter, "building over the first 10 min" means the theta reference layer's level ramps from silence to full level over the first 10 minutes. Its AM depth and rate do not change. The ramp follows the signal spec's gain ramp law. The gamma PAC layer's level is unchanged by this ramp.
- **Reason:** the phrase came from `docs/listening-modes.md`, where it described the study's finding (EEG theta rose within 10 minutes, Jirakittayakorn and Wongsawat 2017), not a property of the sound. The starter tables carried it over without saying what changes in the sound. A level ramp matches the ramp-ins in Focus and Learn.
- **Engineering default:** starting from silence; 10 minutes kept from the study's time frame. No study sets either for the sound.
- **Source:** epics and stories session, 2026-10-29.
- **Decided by:** Audio.
- **Status:** engineering default.

### 2026-10-29 (q): Two-stage golden sign-off; v0.1 closes on provisional sign-off

- **Decision:** a golden file's listening sign-off has two stages. Provisional: Audio has listened. Full: a second listener (alpha testers Audio will recruit) has also listened. Each golden carries a record of stage, signer, date, and the SHA-256 of the file heard. CI accepts both stages. A golden whose hash changes reverts to unsigned, whatever its stage was. v0.1 closes on Audio's provisional sign-off; full sign-off may land during Phase 1, and anything the testers catch is fixed there.
- **Reason:** a second listener catches what Audio no longer hears after weeks with these tones, but recruiting testers should not block Phase 1. Binding the sign-off to the file hash stops a re-render from inheriting a sign-off for audio nobody heard.
- **Refines:** CLAUDE.md "Golden files change only after a human listening sign-off" and the v0.1 sign-off in the project plan.
- **Source:** v0.1 story breakdown session, 2026-10-29.
- **Decided by:** Audio.
- **Status:** proposed.

### 2026-10-28 (p): Limiter idle bound for v0.1 is zero

- **Decision:** in v0.1 the stereo-linked limiter never acts. Any render where it applies gain reduction fails. The assertion checks that the limiter's gain-reduction tap is exactly unity on every sample, and that master chain output equals input times master gain, bit for bit.
- **Reason:** every v0.1 starter is tones only at -36 LUFS-I (entry (m)). Pure tones at that level peak far below the limiter's -1 dBTP ceiling, so the limiter has nothing to do. Zero is the strictest bound and is testable now; loosening it later needs its own entry.
- **Revisit:** when the Phase 1 master level (-16 LUFS-I) and stems arrive, with measured gain-reduction data.
- **Closes:** the SPEC and spine open questions on the limiter idle bound (AD-4). The spine's v0.1 loudness target question is closed by entry (m).
- **Source:** v0.1 story breakdown session arithmetic; entries (k), (m).
- **Decided by:** Audio, during the v0.1 story breakdown session.
- **Status:** proposed.

### 2026-10-28 (o): Reference sine, depth-gated bursts, burst edges, non-sine binaural

- **Decision:** the Python reference renders the ideal sine. The signal spec states the ideal waveform plus the engine approximation's error bound: at most -120 dBFS against the ideal. Reason: a reference that implements the engine's own polynomial cannot catch a bad sine. Margin arithmetic: three layers' errors adding coherently gain about 9.5 dB, leaving about 10 dB under the -100 dBFS reference match. This refines AD-19 (one formula source) while it is REVIEW PENDING; the independent reviewer should check it.
- **Decision:** gamma bursts and swells are depth-gated. The gamma PAC carrier plays continuously; bursts and swells gate only its AM depth, matching the CAP-4 wording. Audio: it "would sound better and be less abrupt." Carrier-gated rectangular bursts at 40 Hz fail spacing against the 450 Hz theta reference (worst line -21 dB).
- **Decision:** the 50 ms burst width (Alekseichuk et al. 2016) is the full width. Each edge is a 10 ms raised cosine inside it, leaving a 30 ms plateau. Computed spectra: worst line at or above 394 Hz is -51.3 dB at 60 Hz gamma, the worst case checked across 40, 45, and 60 Hz. 10 ms is the top of the 5 to 10 ms rise-time convention in auditory physiology. No acoustic study sets burst edges.
- **Decision:** a non-sine binaural waveform is rejected in v0.1 with a named rule (parameter `binaural.waveform`, rule "non-sine binaural not modeled", limit sine). The CAP-5 compile warning applies once the signal spec models non-sine binaural. Resolves a contradiction between SPEC CAP-5 and the SPEC Assumptions.
- **Confidence:** weak for the burst edges (engineering default from computed spectra and a physiology convention); the -120 dBFS bound is an engineering default.
- **Source:** research run `burst-edge-taper-2026-10-28` (literature notes and `burst_spectra.py`); Alekseichuk et al. 2016 methods.
- **Decided by:** Audio, during the v0.1 story breakdown session (sine reference and margin, depth-gated, burst width and edges). The non-sine binaural rule was delegated by Audio to the build agents.
- **Status:** engineering defaults and proposed, as listed in Current state. Phase 0 may replace any value; S2.4 must reproduce the burst figures through the signal spec, reference, and validator.

### 2026-10-27 (n): Sleep beat rate cycles, correcting the Lee et al. reading

- **Correction:** Lee et al. (2024) did not sweep the beat rate once from 3 Hz to 0 Hz. The right-ear carrier "continuously fluctuated between 100 and 103 Hz over a duration of one minute", so the beat rate cycled over 0 to 3 Hz every 60 s, played before sleep onset and in 20 minute windows after it. The waveform of the change is not stated, and the authors say pattern and form were not optimized. Entries (i) and (m), `docs/listening-modes.md`, the project plan, PRD FR-16, and the addendum carried the misreading; all are corrected.
- **Decision:** Sleep's binaural beat rate cycles over 0 to 3 Hz every 60 s for the session body, as a sinusoid. The range and cycle come from Lee et al.; the sinusoid shape and its start phase are engineering defaults. Supersedes the Sleep binaural sweep in entries (i) and (m).
- **Decision:** Sleep's theta reference holds a steady 2 Hz delta rate (450 Hz carrier, sine AM). Engineering default; no study sets it. Supersedes the 3 Hz to 1 Hz sweep in entry (m).
- **Unchanged:** 100 Hz left carrier; 45 min with a 5 min fade; no sound after the session ends. Arcani has no counterpart to Lee's post-onset windows (PRD non-goals).
- **Source:** research run `academic-lit-lee-2024-dynamic-binaural-beat-sweep-law-2026-10-27` (Lee et al. 2024, Sleep 47(10) zsae097; Thomas 2024 editorial, zsae190).
- **Decided by:** Audio, during the v0.1 spec session.
- **Status:** provisional.

### 2026-10-27 (m): v0.1 starter recipe values and loudness target

- **Decision:** the four v0.1 starters use these values. All are provisional; Phase 0 may change them, and affected golden files are re-approved by ear.
  - Gamma PAC layer (Focus, Learn, Relax): 250 Hz carrier, AM at 40 Hz. 40 Hz per entry (a). 250 Hz because the gamma response falls about 30% per octave of carrier (Ross et al., 2003); it passes the carrier rule at 40 and 60 Hz, and its 210 to 290 Hz side frequencies sit far from the 450 Hz theta reference.
  - Focus: 450 Hz carrier, sine AM at 6 Hz; gamma as 50 ms bursts at 0 degrees, depth 100 percent; 5 min ramp-in, then looping.
  - Learn: 450 Hz carrier, sine AM at 5.5 Hz (Roberts et al., 2018); gamma as a smooth swell at 0 degrees (entry (d)), depth 100 percent; 5 min ramp-in, then looping.
  - Relax: 450 Hz carrier, sine AM at 6 Hz, building over the first 10 min; gamma as a smooth swell at 0 degrees, depth 25 percent; 30 min (Jirakittayakorn and Wongsawat, 2017, ran 30 min sessions).
  - Sleep: 450 Hz carrier, sine AM on a delta rate curve from 3 Hz to 1 Hz; binaural 100 Hz left, 100 Hz plus beat rate right, beat rate 3 Hz to 0 Hz (Lee et al., 2024); 45 min, the last 5 min a fade to silence. The theta reference carrier must be at least 156 Hz to clear the binaural pair by 50 Hz.
  - Looping max run time: Focus 45 min, Learn 20 min, the top of each mode's length range in `docs/listening-modes.md`. Phase 0 sets the value from the WHO-ITU safe listening standard.
  - Loudness target: -36 LUFS-I for every v0.1 starter (tones level, entry (g)), so sign-off judges the tones at the level they will have in the product.
- **Engineering defaults (no study sets them):** Relax depth 25 percent, Sleep length and fade, Learn ramp-in, loop max run times, the 450 Hz theta reference carrier, -36 LUFS-I.
- **Assumed:** a sine theta reference envelope in every starter, and 100 percent gamma depth in Focus and Learn; `docs/listening-modes.md` names neither.
- **Open:** the law and timing of Sleep's two rate curves.
- **Source:** v0.1 spec session (`_bmad-output/specs/spec-arcani-v0-1/`); research library entries named above.
- **Decided by:** Audio, during the v0.1 spec session.
- **Status:** provisional.

### 2026-10-27 (l): Seed policy

- **Decision:** the CLI, tests, golden files, and designer audition and export use the recipe seed, so every check is reproducible. Consumer app builds draw a fresh seed for each play, so stem choices vary between listens. The play's seed stays on the device with the play record, so any play can be re-rendered exactly. It is never sent in analytics (FR-38). Internal app builds may pin a seed.
- **Note:** the Core zone draws no random values, so the entrainment signals are identical on every play; only Tone zone choices vary.
- **Source:** architecture step, spine AD-25.
- **Decided by:** Audio, during the architecture session.
- **Status:** proposed.

### 2026-10-27 (k): Loudness gain, limiter, visualizer, and Tone zone rates

- **Loudness gain:** the exporting tool (the CLI in v0.1, the designer from Phase 1) measures integrated loudness and stores the gain in the recipe with a hash of the loudness-relevant fields. Live and offline playback use the same gain. Resolves PRD Q6. Targets stay at the engineering defaults in entry (g).
- **Limiter:** at the stored gain, the master limiter must stay idle, so it never adds gain changes to the binaural pair. The allowed gain-reduction bound is open and is set from the v0.1 starter renders.
- **Visualizer (new scope, Phase 3):** no more than 3 flashes in any one second (WCAG 2.2, 2.3.1, research library Standards), and no flashing or pulsing at theta, gamma, or beat rates, so it never adds a visual flicker stimulus. Its smoothing rate is open.
- **Tone zone rates:** every time-varying Tone parameter (stem motion, effect LFOs, gates) needs a locked range so ambience cannot carry rhythm at entrainment rates. Values are open; set from research in Phase 1 or 2.
- **Source:** architecture step, spine AD-4, AD-6, AD-13, AD-18; reviewer gate.
- **Decided by:** Audio, during the architecture session.
- **Status:** proposed for the rules; open for the values.

### 2026-10-27 (j): Determinism scope, sample rates, and dither

- **Determinism:** the whole engine (Core, stem decoder, resampler, built-in effects, 3D renderer) targets identical samples on PC, Android, and iOS. Method: engine-owned math, 64-bit integer phase, strict compiler flags, and CI hash checks on x64 and ARM. A component the Phase 0 spike proves cannot be exact falls back to the -100 dBFS tolerance, logged here with the reason. Supersedes the determinism scope in entry (i). Resolves PRD Q5.
- **Sample rates:** the Core renders natively at 44.1 and 48 kHz and is never resampled. Stems whose rate differs from the output pass through an engine-owned deterministic resampler, since Opus decodes only at 48 kHz-family rates. Tests and golden files cover both rates. The plan's 48 kHz CLI default stays.
- **Dither:** v0.1 WAV output rounds to 24 bits with no dither. Engineering default, chosen so renders stay byte-identical; any later dither draws from a named seeded stream.
- **Source:** architecture step, spine AD-9, AD-10, AD-14; freshness review (Opus decode rates).
- **Decided by:** Audio, during the architecture session.
- **Status:** proposed. The bit-exact target needs the independent review in CLAUDE.md rule 4 before it locks.

### 2026-10-27 (i): Starter binaural choice, spacing component threshold, dropouts, determinism scope

- **Binaural in v0.1 starters:** off in Focus, Learn, and Relax; on in Sleep with a 100 Hz carrier and a beat sweeping 3 Hz to 0 (Lee et al., 2024). Relax keeps low-depth gamma, and gamma plus a 250/256 Hz binaural pair would break the spacing rule (256 Hz sits 4 Hz from gamma's 260 Hz side frequency). No starter runs gamma and binaural together.
- **Spectral component:** for the spacing rule, any spectral line within 40 dB of the layer's strongest line, including harmonics from bursts, envelope shapes, and non-sine carriers. Placeholder, confirmed in Phase 0 with the 50 Hz value.
- **Dropout:** more than 1 ms of all-zero samples in a channel where the recipe sets a non-zero level. Placeholder.
- **Determinism scope:** byte-identical on one platform and build; within -100 dBFS (the reference-match tolerance) across platforms as the provisional floor; a bit-exact synthesis core across platforms as the target, confirmed or dropped in the architecture step and Phase 0 spike.
- **Source:** PRD reviewer pass, 2026-10-27 (`review-architecture-readiness.md`, `review-rubric.md`).
- **Decided by:** Audio, during the PRD session.
- **Status:** provisional.

### 2026-10-27 (h): Provisional v0.1 ranges

- **Decision:** v0.1's validator uses these provisional ranges, spanning the values the starter recipes and their cited studies use. Phase 0 widens or locks each one.
  - Theta reference rate, including delta and rate curves: 1 to 6 Hz. Lee et al. (2024) 0 to 3 Hz sweep; Lega et al. (2016) 2.5 to 5 Hz; Roberts et al. (2018) 5.5 Hz; Jirakittayakorn and Wongsawat (2017) 6 Hz.
  - Theta reference carrier: 100 to 500 Hz. Chaieb et al. (2017) about 107 to 220 Hz; Orozco Perez et al. (2020) about 400 Hz; 450 Hz engineering default (entry (g)).
  - Coupling depth: 0 to 100 percent. Ross et al. (2003): the response scales with depth.
  - Burst width: 50 ms, fixed in v0.1. Alekseichuk et al. (2016).
- **Why:** v0.1 is Phase 0 part 1, so the validator and starter recipes need testable ranges before Phase 0 research finishes.
- **Decided by:** Audio, during the PRD session.
- **Status:** provisional.

### 2026-10-27 (g): Engineering defaults, and no listener binaural control

- **Decision:** the 200 to 500 Hz gamma PAC carrier range, the 450 Hz theta reference carrier, and the -36 (tones) and -16 (master) LUFS-I levels are engineering defaults, not science claims. They came from an earlier internal reference and private review feedback, which the clean-room rules do not accept as sources.
  - Supporting public context: lower carriers give larger gamma responses (Ross et al., 2003), and -16 LUFS is a common streaming convention (research library, Standards).
  - They stay until Phase 0 replaces or confirms them.
- **Decision:** listeners cannot change the binaural layer on or off or its carrier. The designer sets both per recipe. This closes the "listener-adjustable carrier" option in the plan's open decisions.
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed.

### 2026-10-27 (f): Binaural beat-rate limit is 30 Hz

- **Decision:** the binaural beat rate's locked range is below 30 Hz.
- **Why:** binaural beats are perceived with differences under about 35 Hz (Licklider et al., 1950, cited by López-Caballero and Escera, 2017). 30 Hz keeps a margin inside that limit.
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed.

### 2026-10-27 (e): Spacing rule applies between layers, per ear

- **Change:** the spacing rule compares spectral components of different layers in the same ear. A layer's own components (carrier and its modulation side frequencies) are exempt, and so is the binaural pair, whose carriers never share an ear.
- **Why:** read literally, the old wording rejected every recipe: a 300 Hz carrier modulated at 40 Hz has side frequencies at 260 and 340 Hz, and the binaural carriers sit a beat rate apart. The rule exists to stop unintended beating and roughness between layers, and to stop one layer from placing the other ear's binaural carrier in this ear.
- **Value:** 50 Hz is still a placeholder. A critical-band source, checked in Phase 0, may replace it with a frequency-dependent minimum.
- **Source:** PRD reconciliation, 2026-10-27; project plan, Signal architecture (carrier spacing rule).
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed. CLAUDE.md spacing rule wording updated to match, 2026-10-27.

### 2026-10-27 (d): Learn mode coupling phase changed from trough to peak

- **Change:** the Learn starter recipe's gamma PAC layer peaks at 0 degrees (theta reference peak) instead of the theta trough. `docs/listening-modes.md` is updated to match.
- **Why:** the Learn table predates the research run. Its trough rationale was Lega et al. (2016), brain recordings that are region-specific and biphasic in the hippocampus. The only coupled-stimulation evidence (tACS) favors peak, and sound phase does not map onto brain phase. Learn now follows the general default in entry (b) rather than being an exception.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, refs [13], [14], [17], [21], [23]; entry (b).
- **Decided by:** Audio, during the PRD session.
- **Status:** proposed. Locks with entry (b) after independent review. The Phase 1 peak vs trough vs uncoupled comparison can revisit it.

### 2026-10-27 (c): Plan doc wording for the coupling assertion

- **Change:** `docs/project-plan.md`, Build and test workflow, signal assertion 3 says gamma depth "peaks at the in-file theta trough". It should say "peaks at the recipe's coupling phase", matching CLAUDE.md.
- **Why:** trough coupling in the brain is region- and task-specific. Stimulation evidence leans away from trough, and the sound phase does not map onto the brain phase.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, recommendation 4.
- **Status:** applied 2026-10-27 during the PRD session, in signal assertion 3, the Lessons table guard, and the Signal architecture automated-checks line.

### 2026-10-27 (b): Coupling phase definition and default

- **Decision:** the coupling phase is a recipe parameter from 0 to 360 degrees, defined on the in-file theta reference envelope, with 0 degrees at the envelope maximum.
  - Default: 0 degrees (peak).
  - Recipes can choose uncoupled gamma as a control.
  - The coupling timing test checks this phase in the sound, which is the only phase that is measurable and reproducible.
- **Evidence:**
  - **tACS studies:** peak-coupled gamma helped in some of them, and trough-coupled gamma was ineffective or impaired performance. But the direct peak vs trough contrast was not significant, and one peak-coupled study reduced accuracy.
  - **Brain recordings:** they show no single preferred phase.
  - **Sound:** no study has tested theta-gamma coupled sound.
  - **Delay:** cortical tracking of theta AM lags the sound by roughly 80 to 160 ms, and the lag varies by listener. So the sound phase is a design convention, not a brain target.
- **Confidence:** low to medium.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, refs [13] to [23].
- **Status:** proposed. Needs an independent review before it locks (CLAUDE.md rule 4). The Phase 1 EEG pilot (peak vs trough vs uncoupled sound, with each listener's delay measured) would make it evidence-based.
- **No claims:** no source supports an outcome claim for any coupling phase delivered by sound.

### 2026-10-27 (a): Gamma AM rate default and range

- **Decision:** default 40 Hz, locked range 30 to 60 Hz. Any rate in the range is valid.
  - Treat 60 to 80 Hz as a possible extended band later, only if auditory behavioral evidence appears.
  - With the 4 times carrier rule, a 60 Hz rate needs a carrier of at least 240 Hz.
- **Evidence:**
  - The human auditory steady-state response peaks in the 30 to 40 Hz region.
  - Individual peak rates measured 36 to 53 Hz, with a mean of about 42 to 46 Hz.
  - About 58 of 62 auditory gamma studies used 40 Hz. Data outside 40 Hz is sparse: 60 Hz mainly from one lab, and one study at 80 Hz.
  - Behavioral effects in healthy adults are inconsistent even at 40 Hz.
- **Confidence:** high for the response peak, low for behavioral relevance.
- **Listening check:** on carriers of a few hundred Hz, roughness peaks broadly at 20 to 50 Hz, so 40 Hz may sound rough. Add this to the starter recipe listening checklist.
- **Future feature:** a per-listener gamma rate within the range is supported (refs [5][6]). It is not a v0.1 default.
- **Source:** research run `academic-lit-gamma-rate-and-coupling-phase-2026-10-27`, refs [1] to [12].
- **Status:** proposed. Needs an independent review before it locks.

### 2026-10-21: Gaps check outcomes (baseline)

These are recorded from `docs/project-plan.md`, Gaps check. The design log started on 2026-10-27, so this is the earliest baseline entry.

- **Theta reference:** added as an in-file AM carrier, the only thing PAC couples to (Orozco Perez et al., 2020).
- **Binaural layer:** kept as an optional layer, with its default still open (Orozco Perez et al., 2020; López-Caballero and Escera, 2017).
- **Binaural locked ranges:** carriers below 1000 Hz and a difference under about 35 Hz (Licklider et al., 1950, as cited by López-Caballero and Escera). So a gamma-rate beat can never be binaural.
- **Carrier spacing rule and validator:** added, so that a theta reference sharing a carrier with the binaural layer cannot leak the other ear's tone.
- **Alamalhoda et al. (2025):** dropped as support for audio, because it used light flicker.
