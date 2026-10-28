---
review: freshness and reality check
target: ARCHITECTURE-SPINE.md (with .memlog.md)
date: 2026-10-27
lens: Was each committed decision web-checked rather than asserted from training data? Are versions current, does each technology exist and fit its role? Are AD-9 and AD-10 technically feasible as written?
---

# Freshness Review: Arcani Architecture Spine

## Verdict

The stack choices all still exist and fit their roles, but three pinned "confirmed" versions are stale (Flutter, CMake, Catch2 implied), miniaudio 0.11.25 carries an open CVE, and AD-9 and AD-10 each hide one concrete gap (Clang fuses FMA by default; Opus cannot decode at 44.1 kHz) that should be written into the spine before it locks.

## Summary table

| Item | Spine says | Found (2026-10-27) | Status |
| --- | --- | --- | --- |
| Flutter | pin at spike; "3.44 confirmed May 2026" | 3.47 stable, released 2026-08-12; hotfixes in the 3.47.x line (3.47.1 on 2026-08-19 with Dart 3.13.1; docs banner mentions 3.47.8); 3.50 scheduled November 2026 | Outdated note |
| dart:ffi role | UI calls engine via dart:ffi; audio on native thread | Fits. Build hooks (native assets) stable since Flutter 3.38. Audio callback must stay in C (miniaudio thread calls engine directly), never Dart | Confirmed fit |
| Background playback | Deferred to Phase 0 spike | Android needs a `mediaPlayback` foreground service (type mandatory from API 34); iOS needs `UIBackgroundModes: audio` plus an AVAudioSession playback category. `audio_service` 0.18.19 wraps a custom engine | Correctly deferred; add notes |
| miniaudio | 0.11.25; 0.12 moves to .c/.h | 0.11.25 (2026-03-04) is still latest; no 0.12 release yet. CVE-2026-32837 (heap OOB read in WAV BEXT parser) affects 0.11.25 and earlier | Version right; add CVE mitigation |
| miniaudio Android/iOS | Host audio I/O on desktop, Android, iOS | AAudio (Android 8+) with OpenSL ES fallback; Core Audio on iOS (compile as Objective-C) | Confirmed fit; one caveat on API 26 |
| CMake | 4.3 or later (4.3.4 confirmed June 2026) | 4.4.5 latest stable; 4.5.0-rc1 in testing | Floor OK; note stale |
| Catch2 | v3, pin in first build story | v3.16.1 latest (08 Oct, year inferred 2026) | Confirmed; give the pin |
| Clang everywhere | clang-cl, NDK clang, Apple clang; pin in first build story | NDK r30 latest stable (clang-r574158c); VS 2026 bundled Clang reported bumped to 22 in the June 2026 update (secondary source) | Exists; three different LLVM builds, so "pin" means pin each |
| Python | 3.12 via uv | 3.12 is security-only (EOL 2028-10). 3.15 is the newest feature line (3.15.0 on 2026-10-09; downloads page shows 3.15.2). NumPy 2.5.4 (2026-10-10) requires Python >=3.12 | Works; at the floor of NumPy support |
| uv | manages Python | 0.13.6 (2026-10-26) | Confirmed; pin it. Note: uv is not installed on the dev PC (per project memory) |
| GitHub Actions ARM | x86 and ARM runners | `ubuntu-24.04-arm`, `ubuntu-22.04-arm`, `windows-11-arm` GA for public repos (2025-08-07); standard arm64 runners in private repos since 2026-01-29 (2 vCPU private, 4 vCPU public) | Confirmed; but see coverage gap below |

## Findings in detail

### F1. Flutter "3.44 confirmed May 2026" is stale (low, but labeled as confirmed)

Flutter 3.47 shipped 2026-08-12 and is the current stable line; the docs site states it reflects 3.47. A 3.47.1 hotfix (2026-08-19, Dart 3.13.1) closed a plugin-registrant code injection issue in the build tooling, and the archive page banner names a 3.47.8 hotfix (eMudhra CA key block), which I could not date. 3.50 is on the published schedule for November 2026, so it may land before the Phase 0 spike. The memlog note "3.47 scheduled Aug 2026, unconfirmed" is now confirmed.

Fix: change the Stack row to "pin at the Phase 0 spike (3.47.x current stable at 2026-10-27; 3.50 due November 2026)". Pin to the latest 3.47 hotfix or 3.50, never 3.47.0 (security fix in 3.47.1).

Fit for role: confirmed. Flutter on Windows, macOS, Linux desktop plus Android and iOS remains supported. dart:ffi with build hooks (native assets, stable since Flutter 3.38) is the supported way to ship a C library. The architecture already keeps synthesis and the audio callback out of Dart, which is the only safe way: Dart isolates cannot run real-time audio callbacks. Plans and snapshots cross FFI from the UI isolate, which is fine. Flutter's own cookbook shows the same pattern (flutter_soloud, a C++ engine over FFI), and `audio_io` uses miniaudio over FFI, so the pattern has precedent.

Sources:
- https://docs.flutter.dev/release/release-notes
- https://docs.flutter.dev/install/archive
- https://docs.flutter.dev/release/whats-new.html
- https://startdebugging.net/2026/08/flutter-3-47-1-blocks-plugin-registrant-code-injection/
- https://codewithandrea.com/newsletter/august-2026
- https://docs.flutter.dev/cookbook/audio/soloud
- https://pub.dev/packages/audio_io/versions/0.5.0
- https://dart.dev/interop/c-interop

### F2. Background playback: correctly deferred, but the spike needs these facts (medium)

Neither Flutter nor miniaudio provides background playback by itself. What the spike must prove:

- Android: a foreground service of type `mediaPlayback` with `FOREGROUND_SERVICE_MEDIA_PLAYBACK` permission. Declaring the type is mandatory from Android 14 (API 34). Apps targeting Android 15+ cannot start it from `BOOT_COMPLETED`.
- iOS: `UIBackgroundModes` includes `audio`, and the AVAudioSession category is playback. miniaudio's Core Audio backend exposes a session category setting; confirm it in the spike rather than assume.
- `audio_service` 0.18.19 supports background audio on both and explicitly allows wrapping a custom engine in an `AudioHandler`, with `audio_session` for session setup. It is a candidate for the media session, notification, and lock screen work.

Fix: add these three items to the Deferred row for FR-30 as the spike's acceptance checklist.

Sources:
- https://developer.android.com/develop/background-work/services/fgs/service-types
- https://pub.dev/packages/audio_service

### F3. miniaudio 0.11.25 is the latest, but has an open CVE (medium)

0.11.25 (released 2026-03-04) is still the latest release; 0.12 has not shipped. The .c/.h split note is correct (announced in 0.11.22; `miniaudio.c` already exists, and the single translation unit build stays supported).

CVE-2026-32837: heap out-of-bounds read in the WAV BEXT metadata parser, affecting 0.11.25 and earlier, CVSS 3.1 5.5. Fixed upstream in commit 1df46ae, not yet in a tagged release. The spine uses miniaudio for device I/O only, so the exposure is small, but the CLI will write WAV and someone will be tempted to read WAV through miniaudio in a test or tool.

Fix: in the Stack row, add "build with `MA_NO_DECODING` and `MA_NO_ENCODING` (device I/O only), or pin a commit at or after 1df46ae". Also prefer the `miniaudio.c` integration now so the 0.12 move is a no-op.

Android detail: miniaudio prefers AAudio (Android 8+) and falls back to OpenSL ES. Google's Oboe history documents an AAudio crash bug on 8.0 (API 26) fixed in 8.1 (API 27); Oboe only uses AAudio on API 27+. If the minimum Android version (Deferred) ends up at 26, the spike should check miniaudio's behavior on 8.0 or force OpenSL ES there. iOS: Core Audio backend; must be compiled as Objective-C; for App Store builds use `MA_NO_RUNTIME_LINKING` and link the frameworks.

Sources:
- https://github.com/mackron/miniaudio/releases
- https://nvd.nist.gov/vuln/detail/CVE-2026-32837
- https://osv.dev/vulnerability/CVE-2026-32837
- https://security-tracker.debian.org/tracker/CVE-2026-32837
- https://miniaud.io/docs/manual/index.html
- https://android.googlesource.com/platform/external/oboe/+show/10cd299e/docs/AndroidAudioHistory.md

### F4. CMake "4.3.4 confirmed June 2026" is stale (low)

Latest stable is 4.4.5; 4.5.0-rc1 is in testing. "4.3 or later" as a floor is fine.

Fix: "4.3 or later (4.4.5 latest stable at 2026-10-27)". Pin the exact version in the first build story and in CI.

Sources:
- https://cmake.org/download/
- https://www.kitware.com/cmake-4-3-4-available-for-download/
- https://bugzilla.redhat.com/show_bug.cgi?id=2452239

### F5. Catch2 v3: confirmed, here is the pin (low)

Latest is v3.16.1 (08 Oct; the page omits the year, v3.16.0 was 25 Aug and v3.15.3 26 Jul, consistent with 2026). Note 3.16.1 restored MSVC-driver optimizations lost in 3.16.0, which matters for clang-cl.

Fix: "Catch2 v3.16.1 (or newer 3.x at the first build story)".

Source: https://github.com/catchorg/Catch2/releases

### F6. Clang on every platform: exists, but it is three different compilers (medium)

- Windows: clang-cl ships with Visual Studio. A secondary source reports the VS 2026 June update bumped the bundled Clang to 22 and moved binaries to per-architecture folders (unconfirmed against Microsoft release notes). LLVM's own Windows installer also provides clang-cl.
- Android: NDK r30 is the latest stable (released 08 Sep), shipping clang-r574158c (exact LLVM major is in `clang_source_info.md`; not confirmed from public pages). r29 shipped clang-r563880c.
- Apple: Apple clang from Xcode, its own versioning.

"Pin in the first build story" cannot mean one Clang version: Apple clang and NDK clang are fixed by their SDKs. Bit-exactness must come from flags and code rules (AD-9), not from a shared compiler version. Fix: say "pin each toolchain: clang-cl version, NDK release, Xcode version".

Sources:
- https://github.com/android/ndk/releases
- https://newreleases.io/project/github/android/ndk/release/r29
- https://app.semanticdiff.com/gh/nvaccess/nvda/commit/4059aecc644ad3b93f42455663f9758e60a6790a
- https://learn.microsoft.com/en-us/cpp/build/clang-support-msbuild

### F7. Python 3.12 and uv: valid, but at the edge (low)

- Python 3.12 is in security-only maintenance until 2028-10. Bugfix lines are 3.14 and 3.15 (3.15.0 released 2026-10-09; the downloads page lists 3.15.2 as latest).
- NumPy 2.5.4 (2026-10-10) requires Python >=3.12, so 3.12 is the oldest supported version. Under the scientific Python support policy (SPEC 0), 3.12 is likely dropped by NumPy within the next year.
- uv is current: 0.13.6 (2026-10-26). Note uv is not installed on the dev PC per project memory; the first build story must install it.

Fix: either keep 3.12 with a note that it is the NumPy floor, or move to 3.14 (bugfix line, 3+ years of support, full NumPy support). Recommend 3.14 with `requires-python = ">=3.12"`. The reference renderer is double precision NumPy; nothing ties it to 3.12.

Sources:
- https://www.python.org/downloads/
- https://peps.python.org/pep-0790/
- https://pypi.org/project/numpy/
- https://github.com/astral-sh/uv/releases

### F8. GitHub Actions ARM runners: available, but the CI matrix does not test what ships (high)

Runner availability is confirmed:
- Linux and Windows arm64 standard runners (`ubuntu-24.04-arm`, `ubuntu-22.04-arm`, `windows-11-arm`) are GA for public repos (2025-08-07).
- Since 2026-01-29 they also work in private repos, billed against plan minutes, with 2 vCPU (4 vCPU in public repos). The repo has no remote yet, so visibility is undecided; both cases are now covered.

The gap: AD-9 promises identical samples on PC, Android, and iOS. "x86 and ARM runners" as written tests a Linux or Windows ARM build, which uses a different compiler and C library than either phone. NDK-built binaries do not run on a glibc Linux runner, and Apple clang only exists on macOS.

Fix: make the CI matrix explicit:
1. `windows-latest` x64, clang-cl (dev PC parity).
2. `ubuntu-24.04-arm` or `windows-11-arm`, Clang (ARM64 baseline).
3. `macos` arm64 runner with Apple clang (stands in for iOS; same arch and compiler family). Note macOS minutes cost 10x in private repos.
4. NDK-built engine test binary run on an arm64 Android target: an emulator on a runner that supports it, a device farm, or the dev phone in the Phase 0 spike, until an automated path exists.

Sources:
- https://github.blog/changelog/2025-08-07-arm64-hosted-runners-for-public-repositories-are-now-generally-available/
- https://github.blog/changelog/2026-01-29-arm64-standard-runners-are-now-available-in-private-repositories
- https://blogs.windows.com/windowsdeveloper/2025/04/14/github-actions-now-supports-windows-on-arm-runners-for-all-public-repos/

### F9. AD-9 feasibility: achievable, with precedent, but the rule misses specifics (high)

The approach is sound. IEEE 754 requires +, -, *, / and sqrt to be correctly rounded, so with the same operation order, x86-64 (SSE2) and AArch64 give identical results. Box2D v3 achieves cross-platform determinism on x64 and ARM across MSVC, GCC, and Clang by the same means: no fast-math, `-ffp-contract=off`, own sin, cos, and atan2 (it found `atan2f` differs across platforms), and hardware sqrt.

Gaps to write into AD-9:

1. **Clang contracts FMA by default.** Clang's documented default is `-ffp-contract=on` (fusion within a statement), and `-ffp-model=precise` (the default model) keeps contraction enabled. "No FMA contraction" is not the default; it needs `-ffp-contract=off` on every target (for clang-cl, pass `-ffp-contract=off` or `/clang:-ffp-contract=off`), plus a CI check that the flag is present. On AArch64 the fused path is a real instruction, so this would break hashes immediately.
2. **No `long double`.** It is 80-bit on x86 Linux, 128-bit on Android arm64 and Linux arm64, 64-bit on Windows and Apple. Ban it in `engine/`.
3. **Denormals: set it, do not inherit it.** "Same denormal handling" should name a mode. The host thread's FTZ/DAZ state (MXCSR on x86, FPCR on ARM) is inherited by the render call, and some host frameworks set FTZ on audio threads. Either the engine sets and restores the FP control register on entry to render, or (simpler and portable) the code avoids producing denormals and a test asserts none occur. Also restrict Android to `arm64-v8a`: 32-bit ARM NEON always flushes denormals while VFP does not.
4. **x86-64 only.** No 32-bit x86 (x87 extended precision).
5. **NaN sign and payload differ** between x86 and ARM default NaNs. Hash-compare only valid output; the validator and a test should guarantee no NaN is produced.
6. **Stem decoder.** "Engine-owned decoder" plus AD-7 "links no third-party DSP" means writing an Opus or Vorbis decoder from scratch, which is large. libopus float decoding is not guaranteed bit-exact across platforms; its fixed-point build and Tremor (integer Vorbis) are the realistic bit-exact options. Decide at Phase 1 whether a vendored, fixed-point third-party decoder counts as "engine-owned" (compiled from source in `engine/`, same flags). Flag now so AD-7 and AD-9 do not contradict each other.
7. **Rounding to 24 bits.** Use an explicit, engine-owned rounding (for example add 0.5 and floor, with defined tie rule) rather than relying on the current rounding mode.

Sources:
- https://clang.llvm.org/docs/UsersManual.html (`-ffp-contract`, `-ffp-model`)
- https://box2d.org/posts/2024/08/determinism/
- https://docs.rs/box2d-rust (hand-rolled `b2Atan2` and `b2ComputeCosSin` kept bit for bit)
- https://code.dlang.org/packages/box3d (in-tree polynomial transcendentals; only + - * / sqrt remain)

### F10. AD-10 feasibility: fine for synthesis, breaks for Opus stems (high)

Native 44.1 and 48 kHz synthesis is straightforward: oscillators, AM, and envelopes are computed from the rate, and integer phase increments are derived per rate. Byte identity per rate is consistent. Points to fix:

1. **Opus decodes only at 8, 12, 16, 24, and 48 kHz.** A 44.1 kHz render of an Opus stem needs a resampler. That contradicts "no resampling" and AD-7 unless the engine owns a deterministic resampler, or stems are shipped per rate, or Vorbis (which supports 44.1 natively) is chosen. Fix: add this to the Phase 1 codec decision and AD-10 now.
2. **Device rate is not the engine rate.** Most Android devices run their output at 48 kHz; some devices and DACs run at 96 kHz. AD-10 should say: the host renders at the device rate when it is 44.1 or 48 kHz, otherwise renders at 48 kHz and lets the OS or host resample outside the engine (outside the byte-identity guarantee).
3. **Time-based parameters convert per rate.** The 10 ms minimum ramp, gamma peak timing tolerance, and fixed internal block (a fixed sample count is a different duration at each rate) must be specified in seconds and converted to samples per rate, with a defined rounding. Coupling-timing tests should take the rate as a parameter.

Sources:
- https://lists.xiph.org/pipermail/opus/2015-April/002959.html (Opus supported rates; other rates require resampling)
- https://lists.xiph.org/pipermail/opus/2016-March/003382.html

## Decisions that were web-checked versus asserted

| Decision | Evidence in memlog | Assessment |
| --- | --- | --- |
| miniaudio version and 0.12 change | "0.11.25 latest seen" | Checked; still correct. CVE not noted |
| Flutter version | "3.44 confirmed May 2026; 3.47 scheduled, unconfirmed" | Checked at the time; now stale |
| CMake | "4.3.4 confirmed June 2026" | Checked at the time; now stale |
| JUCE licensing (rejected option) | "Starter tier capped at 20k USD" | Not re-verified here; does not affect the chosen stack |
| Atmos on mobile | Apple ignores Dolby binaural-render-mode Off | Not re-verified here; supports a rejection, not a dependency |
| Catch2, Clang, NDK, uv, Python | "pin in the first build story" | Not checked; versions above give the pins |
| GitHub ARM runners | Asserted | Exists; matrix does not cover phone toolchains (F8) |
| Bit-exact method (AD-9) | Asserted method, Phase 0 fallback | Feasible with precedent; missing the FMA default and other specifics (F9) |
| Native 44.1 and 48 kHz (AD-10) | "Audio took lean" | Feasible for synthesis; Opus conflict (F10) |
