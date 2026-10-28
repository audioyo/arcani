---
title: Rubric review of ARCHITECTURE-SPINE.md (Arcani)
reviewed: _bmad-output/planning-artifacts/architecture/architecture-Arcani-2026-10-27/ARCHITECTURE-SPINE.md
inputs: .memlog.md (beside the spine), prds/prd-Arcani-2026-10-27/prd.md
date: 2026-10-27
---

# Rubric review: Arcani architecture spine

## Verdict

Strong, decision-dense spine whose Core-zone invariants (isolated binaural path, gamma coupled only to the theta reference, pure deterministic engine, one C API) are well chosen and mostly enforceable. It is not yet a complete consistency contract: the engine-versus-reference contract has no named signal specification, several cross-unit identities (recipe hash, stem assets, seed policy, assertion code) are undefined, a few Deferred items leave real divergence open, and there is no Open Questions section to hold the PRD conflicts the decision log already flags. Fix the High items before epics are cut.

Severity scale: **High** (two units will diverge or a gate cannot be met as written), **Medium** (likely divergence or unenforceable rule), **Low** (clarity, staleness, hygiene).

## Summary table

| # | Sev | Checklist | Finding | Suggested fix |
| --- | --- | --- | --- | --- |
| 1 | High | 1, 2 | No named signal specification; AD-16 says the reference is "written from the spec" but no spec artifact exists or is bound | Add an AD naming one signal spec document (exact formulas) as the sole source for engine and reference |
| 2 | High | 1, 5 | C API (AD-12) has no way to hand stem or asset bytes to a file-free engine | Add an asset-provision call keyed by content hash; engine decodes |
| 3 | High | 3, 4 | Deferred says Opus or Vorbis "both satisfy AD-9"; unverified, and "engine-owned decoder" conflicts with "no third-party DSP" | Define "engine-owned" for vendored code; restrict to integer-exact decoders (libopus fixed-point or FLAC); prove in Phase 0 |
| 4 | High | 1, 2 | "Recipe hash" is used by AD-13, AD-15, AD-17 and golden keys but never defined (canonical form, which fields, whether stored gain is included) | Add a convention: canonical JSON form, hash algorithm, excluded fields |
| 5 | High | 6 | No Open Questions section; PRD conflicts logged in the memlog (FR-27 stem motion, free-form Tone routing, visualizer, FR-15 CI cadence) are not carried | Add Open Questions with owner and blocking gate for each |
| 6 | Medium | 3, 5 | FR-23 publish is Phase 1 but content server, manifest, and stem identity are deferred to Phase 3 | Fix the manifest and stem identity format at Phase 1, or scope Phase 1 publish to a local staging target |
| 7 | Medium | 1 | Assertions run in Python and C++ tests; designer publish (FR-23) must run the same isolation and level checks with no Python | Rule: assertions implemented once in a C++ library behind the CLI; designer publish calls it; Python tests cross-check |
| 8 | Medium | 1, 2 | Validator warnings (FR-4 non-sine binaural, FR-21) have no channel in the C API; designer may reimplement them | Compile returns errors and warnings; no host computes its own |
| 9 | Medium | 1 | Seed policy for the app undecided (fixed recipe seed vs per-play seed); affects AD-13 loudness, goldens, FR-35 | Decide: recipe seed fixed, or name the allowed per-play seed source and how loudness is guaranteed |
| 10 | Medium | 1, 2 | Ramp, rate-curve, and loop-seam semantics (interpolation law, per-sample vs control-rate, phase at loop) are not fixed; engine and reference will diverge past -100 dBFS | Put these in the signal spec (finding 1); rule that every parameter is evaluated per sample |
| 11 | Medium | 2 | AD-5 "muted ... at any point" rejects any coupled-gamma recipe whose theta reference fades to silence (Sleep or Relax end fade) | Reword: theta reference level must be non-zero wherever coupled gamma depth is non-zero |
| 12 | Medium | 2 | AD-4 master chain uses a stereo-linked limiter; linked gain couples channels and can impose gamma or theta envelopes on the binaural pair | Rule that the limiter is a safety net that does not engage at the stored gain (test it), or make it unlinked; state that the FR-4 60 dB figure is tested with the limiter engaged |
| 13 | Medium | 2, 4 | AD-9 CI on GitHub x86 and ARM runners proves Linux or Windows ARM, not Android NDK or Apple clang targets | Add hash compare from an Android arm64 build (emulator or device) and an iOS simulator arm64 build on a macOS runner |
| 14 | Medium | 6 | Operational envelope thin: no secrets and signing strategy, no staging vs production content environment, no rollback for content pushes, no storage plan for large golden WAVs and lossless stem masters | Add rows: secrets store, content staging and rollback, Git LFS or hash-only goldens with WAVs in external storage |
| 15 | Medium | 5 | AD-17 runs the full suite nightly; PRD FR-15 says the full suite runs on every push and failing code does not merge | Record as a PRD deviation (Open Question) and state the merge gate: fast tier blocks merge; nightly failure blocks phase gate and opens an issue |
| 16 | Medium | 1 | Device sample rate handling unstated: devices at 96 kHz or other rates; who resamples, and is host resampling "host mixing" under AD-1? | Rule: hosts open the device at 44.1 or 48 kHz; if the OS forces another rate, OS resampling is accepted and designer audition reports it |
| 17 | Low | 4 | Stack staleness: CMake 4.4.1 is current (July 2026), not 4.3.4; Flutter 3.47 is stable (Aug 2026); miniaudio 0.11.25 has CVE-2026-32837 (WAV BEXT parser) | Update rows; build miniaudio with decoding disabled (MA_NO_DECODING) since hosts use it for device I/O only |
| 18 | Low | 2 | AD-6 and AD-18 rules depend on values not yet set (stem motion range; how "3 flashes per second" is tested) | Fail closed: validator rejects stem motion until the range exists; app snapshot channel exposes only arc-rate values, no per-cycle phase |
| 19 | Low | 7 | Deployment diagram draws CDN to STORE; content goes to installed apps, not the store | Add an APP node; CDN to APP, STORE to APP |
| 20 | Low | 7 | [ADOPTED] tag on 6 of 18 ADs with no legend; all 18 were confirmed by Audio per the memlog | Tag all or define the tag |

## Detail by checklist item

### (1) Divergence points for the level below

Covered well: binaural routing (AD-4), coupling target (AD-5), Core vs Tone (AD-3), plan-only rendering (AD-2), the single C API (AD-12), randomness streams (AD-14), block-size independence (AD-10), thresholds table (Conventions).

Missed or under-specified:

- **Signal specification (finding 1).** The engine and the Python reference are built independently by design (AD-16) and must agree to -100 dBFS sample by sample. That only works if both are written from one exact document: envelope shapes and their edge smoothing, burst shape, the coupling depth function and its mapping per envelope shape (PRD glossary "Coupling phase"), rate-curve phase integration, ramp law, loop seam rule, and the limiter algorithm (lookahead, attack, release, true-peak oversampling filter). A nonlinear limiter in particular cannot match to -100 dBFS unless its algorithm is spelled out. The spine never names this document, so the two units have nothing shared to diverge from.
- **Recipe hash (finding 4).** Used as a golden-file key, the loudness-gain freshness check, and in the report. CLI, designer, Python tests, and CI each compute it. Without a canonical form (key order, number formatting, whitespace) and a field list, they will disagree. Also undefined: whether the stored loudness gain and its own hash are inside the recipe hash (circular if so), and which fields are "loudness-relevant".
- **Asset path into the engine (finding 2).** AD-1 forbids file I/O in the engine and AD-9 requires an engine-owned decoder, so hosts must pass encoded stem bytes in. AD-12 lists no such call. The designer (desktop files) and app (encrypted store, FR-32) would each invent a way. AD-1's "output is a function of (plan, seed, sample rate, sample index)" also omits asset bytes.
- **Assertion code ownership (finding 7).** FR-23 requires publish to run the validator, level ceilings, and isolation test. The spine places assertions in `tests/` (C++ and Python) and the CLI report. The designer cannot run Python. Without a rule, the designer reimplements checks.
- **Warnings channel (finding 8).** The structured error covers rejection only.
- **Seed policy (finding 9).** Stem picks are seeded (FR-24); whether the app replays the recipe seed or draws a new one per play changes loudness (AD-13 measured at one seed), golden comparability, and FR-35 identity checks.
- **Sample rate at the device (finding 16).**
- **Plan lifetime.** Who frees a swapped-out plan without the audio thread deallocating is engine-internal; acceptable to leave to stories, but worth one clause in AD-11 ("retired plans are freed off the audio thread").

### (2) Rules enforceable and actually preventing the divergence

- AD-1, AD-2, AD-3, AD-12, AD-14, AD-15: enforceable (structure, API surface, CI).
- AD-4: the structural stage-list test plus FR-4 output test is good. Gap: "stereo-linked limiter" is a channel-coupling operation by gain, which the PRD's "processes left and right without mixing them" tolerates only loosely. When the limiter acts, the binaural pair's level is modulated by content in both ears, including the 40 Hz gamma AM, which puts an in-file rhythm on the binaural carriers. Either guarantee the limiter does not engage at the stored gain (AD-13 makes this checkable) or specify its behavior and test isolation with it engaged (finding 12).
- AD-5: the "muted or zero depth at any point" clause is over-broad (finding 11). It also needs the opposite direction: gamma depth must be zero wherever the theta reference is inaudible.
- AD-6: "locked range traced to the design log" has no range yet; until it exists the rule cannot be checked. Make it fail closed (finding 18).
- AD-8: "The app never hands audio to an OS or Dolby spatializer" is not fully within the app's control; recast as "the app sets every available platform opt-out flag and shows FR-34 guidance", which is testable.
- AD-9: the compile flags (no fast-math, `-ffp-contract=off`, no auto-vectorized reductions) are enforceable in CMake; the CI target set is not the shipping target set (finding 13). Specify the internal float type (float32 vs double) since it changes every hash.
- AD-10: "fixed internal block" is fine only if no parameter updates at control rate; otherwise the block size is part of the signal spec (finding 10).
- AD-11: good. Add the plan-retirement clause above.
- AD-13: enforceable, but depends on the undefined hash (finding 4); listener length and intensity (FR-31) change integrated loudness, so state that the target applies at recipe length and nominal intensity.
- AD-17: two tiers fine; merge gate unstated (finding 15).
- AD-18: "never exceeds 3 flashes per second" has no test; enforce through the data the app may read (finding 18).

### (3) Deferred items that could let units diverge

- **Content server, publish protocol, manifest (Phase 3)** vs FR-23 publish in Phase 1 and the deployment diagram's "publish (Phase 1 onward)". The designer would be built against an undefined target, and stem identity in recipes (how a recipe names a stem) is a recipe-schema field needed in Phase 1 (finding 6).
- **Stem codec.** "Both satisfy AD-9 with an engine-owned decoder" is an unverified claim. Vorbis decoders such as stb_vorbis use float math and libm calls (cos, exp, log), which AD-9 forbids. libopus has a fixed-point build that is integer-exact; FLAC is integer and lossless by design. Writing a decoder from scratch is not realistic for a one-person team, so "engine-owned" must be defined to cover vendored source compiled under engine rules, and AD-7 and the memlog's "no third-party DSP libraries inside the engine" must carve out that exception (finding 3).
- **Custom envelope curve format** (Phase 1): fine, but rate curves and ramps are already in v0.1 (Sleep sweep), so their format and law are not deferrable (finding 10).
- Push to device, background mechanism, head tracking, plugin hosting, Atmos export, multiple designers, minimum OS, crash reporting: safe to defer.

### (4) Named tech verified-current (checked 2026-10-27)

| Item | Spine says | Current | Note |
| --- | --- | --- | --- |
| CMake | 4.3 or later (4.3.4, June 2026) | 4.4.0 released 14 July 2026; 4.4.1 on 30 July 2026 | Floor still fine; update the confirmed version |
| Flutter | pin at spike (3.44, May 2026) | 3.47 stable 12 August 2026; next stable expected November | 3.47 moves Material and Cupertino into separate packages; pin after that lands |
| miniaudio | 0.11.25 | 0.11.25 (3 March 2026) still latest seen | CVE-2026-32837, heap out-of-bounds read in the WAV BEXT parser, affects 0.11.25 and earlier; hosts should compile with decoding disabled and track a fix |
| GitHub arm64 runners | x86 and ARM runners | arm64 Linux and Windows standard runners usable in private repos since January 2026 (2 vCPU there) | Fine; does not cover Android or iOS targets (finding 13) |
| C++20, Catch2 v3, Python 3.12 + uv | as listed | current or supported | Note: the project memory says uv is missing on this machine; the first build story must install it |

Sources: [miniaudio release tracker](https://releasealert.dev/github/mackron/miniaudio), [Debian miniaudio tracker](https://tracker.debian.org/pkg/miniaudio), [CMake 4.4.0 announcement](https://mail.kde.org/pipermail/kde-devel/2026-July/004349.html), [CMake 4.4.1](https://www.kitware.com/cmake-4-4-1-available-for-download/), [Flutter 3.47 release notes](https://docs.flutter.dev/release/release-notes/release-notes-3.47.0), [What's new in Flutter 3.47](https://flutter.dev/blog/whats-new-in-flutter-3-47), [arm64 runners in private repositories](https://github.blog/changelog/2026-01-29-arm64-standard-runners-are-now-available-in-private-repositories).

### (5) Coverage of PRD capabilities

The capability map covers FR-1 to FR-38. Gaps:

- FR-13 sub-assertions (dropouts, NaN or infinite, envelope shape) are covered only through AD-17's generic report; acceptable.
- FR-15 vs AD-17 cadence conflict (finding 15).
- FR-23 publish ordering and checks (findings 6, 7).
- FR-27 conflict: PRD says the stem bed gets width without motion; AD-8 allows moving stems. The memlog flags "PRD update needed" but the spine does not record it.
- FR-31 listener intensity and length interact with AD-13 (see (2)).
- FR-34 opt-out is only partly expressed by AD-8.
- FR-7 looping: seam rule (no phase jump in theta or gamma) is a cross-unit signal rule with no AD or spec home (finding 10).
- PRD Q5 and Q6 are resolved (AD-9, AD-13); good. Readiness review M9 resolved by AD-10.

### (6) Altitude dimensions: decided, deferred, or open

Decided: paradigm, zones, stack, repo layout, CI provider, deployment for v0.1, sample rates, determinism, loudness route, visualizer.

Missing or thin:

- **Open Questions section** is absent entirely (finding 5). Items that belong there: PRD updates for free-form Tone routing, moving stems, visualizer, Atmos-not-used; FR-15 cadence; codec exactness; seed policy; stereo-linked limiter behavior.
- **Operational envelope** (finding 14): environments (no staging vs production content split; a recipe pushed by FR-33 is a production change with no rollback path), secrets and signing (store signing keys, stem encryption keys, CI secrets), large-file storage (byte-exact golden WAVs at two sample rates for full-length starters run to hundreds of MB each; lossless stem masters), backups of masters and the design log evidence, CI cost (nightly 8-hour render, ARM minutes on a private plan). Crash reporting is deferred, which is fine.
- **Provider strategy:** cloud storage provider is deferred without a selection criterion; add one line (static hosting with signed URLs, no custom backend) so the Phase 1 publish story can target it.

### (7) Decisions not rationale; diagrams and mermaid

- Mostly decisions. Minor rationale leaks are acceptable ("the bug that broke an earlier project", "0.12 moves to a .c/.h pair").
- All three mermaid blocks parse: subgraph ids with quoted labels, quoted edge labels (`-- "..." -->`, `-. "..." .->`), no reserved words used as node ids.
- Deployment diagram semantics: CDN to STORE is wrong; content flows to installed apps (finding 19).
- Signal flow diagram does not show where the stored loudness gain (AD-13) and listener intensity apply; add them to the master chain node label or the tone-layer gains so stories place them consistently.
- Status tag inconsistency (finding 20).
- No em dashes found in the spine.
