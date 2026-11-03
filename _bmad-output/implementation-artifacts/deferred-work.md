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
  summary: Extend the AD-9 flag check (and the symbol denylist where it applies) from `engine/` sources to `cli/` once the WAV writer or any sample conversion lands there.
  evidence: Review pass 1 finding 21 (part 2); flags are already project-wide and a test asserts `cli/main.cpp` has them, but the checker enforces engine sources only. Story 1.4 or 1.6 is the trigger.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-3-four-platform-ci-and-hash-compare.md`
  summary: Run the NDK arm64 hash probe on a physical Android phone, in addition to the static binary on the hosted arm64 Linux runner.
  evidence: No phone is available yet (Audio, 2026-11-02); the hosted run uses real arm64 hardware and the real NDK compiler but not the Android OS. Design log 2026-11-02 (aa).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-2-engine-sine-oscillator-spike-that-ships.md`
  summary: (closed by Story 0.3: `tests/tables/*.tsv`, loaders and assertion call in `tests/assertions/`, design log 2026-11-03 (cc)) Story 0.3 absorbs `tests/tables/thresholds.json` and `tests/tables/ranges.json` (C++ and Python loaders, uncited-row failure, two-way coverage, design log gate) and replaces the configure-time header in `tests/cpp/SpecTables.cmake`.
  evidence: Story 0.2 needed cited values before Story 0.3 builds the tables; its tests read the two interim files, never literals (design log 2026-11-03 (bb)).
- source_spec: `_bmad-output/implementation-artifacts/spec-0-2-engine-sine-oscillator-spike-that-ships.md`
  summary: (closed by Story 0.2: all four platforms byte-identical, full run 41648370470, design log 2026-11-03 (bb)) Record the four-platform `sine-44100` and `sine-48000` hash result from the pull request's `full` run in design log 2026-11-03 (bb), or apply the defined fallback if a platform cannot match.
  evidence: Pushing waits for Audio's go-ahead; local windows-x64 hashes are in the entry.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-2-engine-sine-oscillator-spike-that-ships.md`
  summary: Add `sine-44100` and `sine-48000` entries to `ci/hash_expected.json` once the first four-platform `full` run confirms their hashes, so a toolchain change that shifts every platform alike fails CI.
  evidence: Review pass 1 finding B6 (Story 0.2); today the sine components are compared only against `windows-x64` in the same run, and `ci/hash_expected.json` was on this story's do-not-change list.
