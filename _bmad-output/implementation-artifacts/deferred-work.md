# Deferred Work

- source_spec: none
  summary: Story 0.1 part 2, compile-flag check (`-ffp-contract=off` present, no fast-math, on every toolchain) and engine undefined-symbol denylist, each with its must-fail case.
  evidence: Split from Story 0.1 on 2026-11-02 at Audio's choice; independently shippable once the part 1 build exists.
- source_spec: none
  summary: Story 0.1 part 3, full four-platform CI matrix (Windows arm64, macOS arm64, Android NDK arm64 on the USB phone via the guarded self-hosted runner), hash compare tool with exact and tolerance modes, wall-time budget table with CI minutes estimate, and nightly skip when main is unchanged.
  evidence: Split from Story 0.1 on 2026-11-02 at Audio's choice; depends on part 1 but ships as its own reviewable change. Repo is public, so hosted runners cost nothing; the self-hosted PC runner must refuse fork pull requests.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-1-build-skeleton-and-fast-ci.md`
  summary: Part 2 must set the engine compile flags (`-ffp-contract=off`, no fast-math, warnings as errors, reproducible-binary flags such as `/Brepro` and `-ffile-prefix-map`) in CMake, not only check for them.
  evidence: Review finding 8; part 1 CMake sets only C++20 and Release, and AD-9 bit-exactness depends on these flags before any DSP code lands.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-1-build-skeleton-and-fast-ci.md`
  summary: Check that the CLAUDE.md Build, C++ tests, and Render commands name an existing preset and the real built binary path, not only that they are non-empty.
  evidence: Review finding 13; `test_repo_layout.py` checks text only, so the documented `build/windows-clang-cl/cli/arcani-render` path can go stale silently. Revisit when the real render command replaces the stub.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-1-build-skeleton-and-fast-ci.md`
  summary: (closed by Story 0.1 part 3) `tests/cmake/test_pin_check.py` needs a macOS preset or a skip on hosts other than Windows and Linux before part 3 runs pytest on macOS.
  evidence: Review finding 18. Closed: part 3 adds the `macos-appleclang` preset and the tests pick it on Darwin.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-1-build-skeleton-and-fast-ci.md`
  summary: Local ctest on the dev PC is blocked by Windows Smart App Control; C++ tests are verified on GitHub Actions until Audio turns it off (Win+R, `windowsdefender:`, App and browser control).
  evidence: Review finding 20; CodeIntegrity event 3077/3118 blocked `arcani_tests.exe` on 2026-11-02, while pytest passes locally and fast run 1 passed on both CI jobs.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-2-compile-flags-and-symbol-denylist.md`
  summary: Reproducible-binary flags (`/Brepro` on clang-cl, `-ffile-prefix-map` on clang) are not set; part 2 sets only the AD-9 output flags and warnings.
  evidence: Decided 2026-11-02 (Audio): no requirement asks for identical binaries, only identical output; design log 2026-11-02 (z). Revisit if a later story needs binary-level reproducibility.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-2-compile-flags-and-symbol-denylist.md`
  summary: (closed by Story 0.2) Scan `engine/` sources for floating-point pragmas (`#pragma clang fp`, `#pragma STDC FP_CONTRACT`, `#pragma float_control`, `#pragma fenv_access`) and fail, since they can re-enable contraction or reassociation while every compile flag looks clean.
  evidence: Review pass 1 finding 7 (part 2); the flag check reads only command lines. No engine source has such a pragma yet; add before or with Story 0.2's first DSP code. Closed: `tools/check_fp_pragmas.py` runs in both workflows, with clean and must-fail fixtures.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-2-compile-flags-and-symbol-denylist.md`
  summary: Add an environment and locale family to the engine symbol denylist (`getenv`, `setlocale`, `localeconv`, `std::locale` constructors, locale-dependent `strtod`), so host settings cannot change engine results.
  evidence: Review pass 1 finding 20 (part 2); not one of the five families in the part 2 intent. Natural home is Story 1.6, which extends the denylist with unseeded randomness.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-2-compile-flags-and-symbol-denylist.md`
  summary: (closed: flag check part by Story 1.4, `tools/check_compile_flags.py` applies every rule to `cli/` sources, design log 2026-11-05 (ii); symbol denylist part by Story 1.6, `tools/check_engine_symbols.py` checks the WAV writer library `arcani_cli_core` against the randomness and clock families, design log 2026-11-06 (kk)) Extend the AD-9 flag check (and the symbol denylist where it applies) from `engine/` sources to `cli/` once the WAV writer or any sample conversion lands there. The symbol denylist part stays open for Story 1.6.
  evidence: Review pass 1 finding 21 (part 2); flags are already project-wide and a test asserts `cli/main.cpp` has them, but the checker enforced engine sources only. Story 1.4 or 1.6 is the trigger.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-3-four-platform-ci-and-hash-compare.md`
  summary: Run the NDK arm64 hash probe on a physical Android phone, in addition to the static binary on the hosted arm64 Linux runner. Owner since 2026-11-04: the Phase 0 part 2 stack spike, which must run the engine library from the real Android app build (same NDK as `toolchain.json`) on a physical phone and match the hashes before it closes (AD-9, design log 2026-11-04 (ee)).
  evidence: No phone is available yet (Audio, 2026-11-02); the hosted run uses real arm64 hardware and the real NDK compiler but not the Android OS. Design log 2026-11-02 (aa).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-2-engine-sine-oscillator-spike-that-ships.md`
  summary: (closed by Story 0.3: `tests/tables/*.tsv`, loaders and assertion call in `tests/assertions/`, design log 2026-11-03 (cc)) Story 0.3 absorbs `tests/tables/thresholds.json` and `tests/tables/ranges.json` (C++ and Python loaders, uncited-row failure, two-way coverage, design log gate) and replaces the configure-time header in `tests/cpp/SpecTables.cmake`.
  evidence: Story 0.2 needed cited values before Story 0.3 builds the tables; its tests read the two interim files, never literals (design log 2026-11-03 (bb)).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-2-engine-sine-oscillator-spike-that-ships.md`
  summary: (closed by Story 0.2: all four platforms byte-identical, full run 41648370470, design log 2026-11-03 (bb)) Record the four-platform `sine-44100` and `sine-48000` hash result from the pull request's `full` run in design log 2026-11-03 (bb), or apply the defined fallback if a platform cannot match.
  evidence: Pushing waits for Audio's go-ahead; local windows-x64 hashes are in the entry.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-2-engine-sine-oscillator-spike-that-ships.md`
  summary: (closed by Story 1.6: `ci/hash_expected.json` has the `sine-*` and `stub-chain-*` entries, scope `engine`, from full run 42236304155, design log 2026-11-06 (kk)) Add `sine-44100` and `sine-48000` entries to `ci/hash_expected.json` once the first four-platform `full` run confirms their hashes, so a toolchain change that shifts every platform alike fails CI. Now an AC of Story 1.6 (design log 2026-11-04 (ee)).
  evidence: Review pass 1 finding B6 (Story 0.2); today the sine components are compared only against `windows-x64` in the same run, and `ci/hash_expected.json` was on this story's do-not-change list.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-4-ci-wording-check.md`
  summary: Add the wording check (`uv run python tools/check_wording.py`) to the CLAUDE.md "Tests" commands so it runs locally after every change, not only in CI.
  evidence: Review pass 1 finding B12 (Story 0.4); the fix edits an agent-context file, which Audio owns, and Audio has an uncommitted CLAUDE.md edit in progress.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Phase 1 (stems): state that the AD-20 spacing rule applies between Core layers and any Tone source with a component model, and that broadband stems are handled by the FR-25 carrier guard; read literally, AD-20 would reject every stem recipe.
  evidence: Review A, AD-20 finding 4.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Phase 2 (Orbit): decide whether the AD-20 "within 40 dB of a layer's strongest line" reading is per ear or overall once Orbit makes gamma louder in one ear; and revisit adversary H26 (gamma mostly in one ear while theta is in both) when Orbit width ranges are set (FR-27).
  evidence: Review A, AD-20 finding 6 and AD-5 finding 3. No v0.1 effect.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Fix the Sleep theta reference carrier bound in `starter-recipes.md`: "at least 156 Hz" comes from entry (m)'s 3 Hz theta rate; with the steady 2 Hz rate of entry (n) the bound is 155 Hz (103 + 50 + 2). The 450 Hz carrier passes either way.
  evidence: Review A, AD-20 finding 7. Fix when that file is next touched.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Audio to consider clarifying CLAUDE.md Signal facts, spacing rule: "the binaural pair are exempt" can be read as exempting the whole binaural layer; AD-20 now says the two binaural carriers are exempt from each other, since they never share an ear (design log 2026-10-27 (e)).
  evidence: Review A, AD-20 finding 1. CLAUDE.md is Audio's rules file and was not edited in Story 0.5.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Phase 3 app build: set the APK `abiFilters` to arm64-v8a only (AD-9), and pin the Android Gradle build's `ndkVersion` to the `toolchain.json` NDK with the AD-9 flags checked on that build.
  evidence: Review B, AD-9 Q2 risk 2 and Q3 table; no story exists yet (epics.md covers v0.1).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Tone zone effects (Phase 1): IEEE denormals can be slow on x86 in decaying filter or reverb tails; avoid producing them arithmetically, never by flushing, since AD-9 now requires IEEE denormal handling.
  evidence: Review B, AD-9 Q3 table, denormal row.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Refresh the dev PC's uv-managed Python 3.14 patch occasionally (`uv python upgrade`); 3.14.10 is a security release. Cannot change engine bytes.
  evidence: Review B, Stack findings, Python row.

- source_spec: `_bmad-output/implementation-artifacts/spec-0-5-independent-review-of-the-pending-architecture-decisions.md`
  summary: Make CI enforce the narrowed AD-9 fallback, so a `ci/hash_tolerance.json` entry must name its rule-4 review and why the cause lies outside the AD-9 code rules, not only cite a design log entry.
  evidence: `tools/hash_compare.py` accepts any entry that cites a design log entry (design log 2026-11-02 (aa)); the narrowed condition from design log 2026-11-04 (ee) is prose only. Natural owner: Story 1.6 or Story 6.1.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-minimal-recipe-schema-and-recipe-hash.md`
  summary: Find the cause of the one-off `arcani_tests` ctest failure seen on the first clean `windows-clang-cl` workflow run of Story 1.1 (11 s, output not captured), if it recurs.
  evidence: Unverified (would be medium). Six reruns and a second clean build passed; settle it by capturing `ctest --output-on-failure` on any recurrence locally or in CI.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-c-api-fixed-stage-list-seek-and-isolation-assertion.md`
  summary: Add an isolation calibration case with a second component in the muted channel at the spacing-rule distance from the measured carrier, once a layer other than the binaural pair shares a channel (Story 2.5).
  evidence: Unverified (would be medium). Calibration today holds only the leaked carrier in the muted channel; Hann sidelobe leakage from a 50 Hz neighbour into the single-bin DFT is unmeasured. Settle it with a Python calibration signal carrying a known interferer and a check that the C++ measurement still reads the known leakage within 0.5 dB.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-c-api-fixed-stage-list-seek-and-isolation-assertion.md`
  summary: Replace the shared placeholder `loudness_hash` in the valid recipe fixtures (Story 1.1 and Story 1.2 stub-chain ones) when Story 4.2 makes `final` mode check the hash match, or those fixtures and the final-mode API tests will fail.
  evidence: Every valid fixture carries the same placeholder hash; `tests/cpp/test_api.cpp` compiles stub-chain fixtures in `final` mode.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-c-api-fixed-stage-list-seek-and-isolation-assertion.md`
  summary: Prove the denormal guard at the C API call sites with a fixture whose output contains subnormals, rendered with host FTZ and DAZ set and compared byte for byte with an IEEE-mode render, once a layer (Epic 2 envelopes or ramps) can produce one.
  evidence: Review finding VG (Story 1.2 triage row 21): the stub chain never produces a subnormal, so deleting a call-site guard keeps the flush-mode tests green; the host-rounding test added in review observes the call sites for rounding only.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-determinism-and-block-size-invariance.md`
  summary: Make the hash probe report how many `arc_render` calls (and of which sizes) produced each `stub-chain-blocks-*` component, and assert it against row `block-sizes`, so a loop bug that renders in one call cannot pass the block-size proof on Android.
  evidence: Review pass 1 finding 20 (Story 1.6, verification gap); today only byte equality with the one-call component and a source-text check of `kBlockSizes` are tested.
