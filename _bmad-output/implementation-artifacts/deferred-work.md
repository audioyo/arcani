# Deferred Work

- source_spec: none
  summary: Story 0.1 part 2, compile-flag check (`-ffp-contract=off` present, no fast-math, on every toolchain) and engine undefined-symbol denylist, each with its must-fail case.
  evidence: Split from Story 0.1 on 2026-11-02 at Audio's choice; independently shippable once the part 1 build exists.
- source_spec: none
  summary: Story 0.1 part 3, full four-platform CI matrix (Windows arm64, macOS arm64, Android NDK arm64 on the USB phone via the guarded self-hosted runner), hash compare tool with exact and tolerance modes, wall-time budget table with CI minutes estimate, and nightly skip when main is unchanged.
  evidence: Split from Story 0.1 on 2026-11-02 at Audio's choice; depends on part 1 but ships as its own reviewable change. Repo is public, so hosted runners cost nothing; the self-hosted PC runner must refuse fork pull requests.
