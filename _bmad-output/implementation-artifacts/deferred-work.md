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
  summary: `tests/cmake/test_pin_check.py` needs a macOS preset or a skip on hosts other than Windows and Linux before part 3 runs pytest on macOS.
  evidence: Review finding 18; the test picks `linux-clang` on any non-Windows host, and that preset's condition rejects macOS.
- source_spec: `_bmad-output/implementation-artifacts/spec-0-1-part-1-build-skeleton-and-fast-ci.md`
  summary: Local ctest on the dev PC is blocked by Windows Smart App Control; C++ tests are verified on GitHub Actions until Audio turns it off (Win+R, `windowsdefender:`, App and browser control).
  evidence: Review finding 20; CodeIntegrity event 3077/3118 blocked `arcani_tests.exe` on 2026-11-02, while pytest passes locally and fast run 1 passed on both CI jobs.