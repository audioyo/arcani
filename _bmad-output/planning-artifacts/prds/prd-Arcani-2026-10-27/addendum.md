# Arcani PRD: Addendum

This addendum holds detail that belongs downstream (architecture, stories) rather than in the PRD. Source: `docs/project-plan.md` unless noted.

## Stack candidates (for the architecture step)

| Option | Role | Note |
| --- | --- | --- |
| JUCE (C++) | Engine, designer UI, Android and iOS builds from one codebase | Leading candidate; verify current license terms |
| miniaudio + Dear ImGui | Engine plus designer UI, with a thin native or React Native phone UI | Less framework, more wiring |
| Unity, or React Native with a native audio module | Considered in the plan | Weaker fit for a shared desktop and mobile DSP core |

The engine core stays plain C++ with no framework dependency until the architecture step decides. The stack must support background playback with the screen off, low battery drain, and identical DSP on Android and iOS.

Supporting tools: Python reference renderer (numpy), Reaper, RX and Youlean for listening and inspection, GitHub Actions for CI, and Claude Code hooks that run fast tests after each edit.

## Recipe file shape (illustrative)

```json
{
  "name": "Focus Starter",
  "engine_version": "0.1.0",
  "seed": 1234,
  "theta_reference": { "rate_hz": 6.0, "carrier_hz": 450, "envelope": "sine" },
  "gamma_pac": {
    "carrier_hz": 300, "carrier_wave": "sine",
    "gamma_hz": 40, "coupling_phase_deg": 0, "shape": "burst", "depth": 1.0
  },
  "binaural": { "enabled": false },
  "levels_lufs": { "tones": -36, "master": -16 }
}
```

Values are illustrative, not locked defaults. Field names are for the architecture step to settle. Ramps, length, author, date, and rationale fields are also required (FR-7).

## Cross-platform bit-exactness (for the architecture step)

FR-6 targets a bit-exact synthesis core across PC, Android, and iOS. Basic IEEE 754 operations (add, subtract, multiply, divide, square root) are already deterministic across x86 and ARM. Cross-platform differences come from:

- **Math library calls:** `sin`, `exp`, `pow` differ between Windows, Android, and Apple libraries. Use engine-owned implementations (sine table with fixed interpolation, or fixed polynomials).
- **Phase accumulation:** use integer (fixed-point) phase counters. This also removes long-session drift.
- **Compiler behavior:** disable fused multiply-add contraction and fast-math; avoid reassociated or auto-vectorized reductions; set the same denormal handling on every platform.
- **Buffer size:** process per sample or in a fixed internal block, so host callback sizes never change the output.
- **CI:** render on x86 and ARM and compare file hashes.

Stem decoding and third-party Orbit spatialization are outside the synthesis core and use the -100 dBFS cross-platform tolerance instead.

## Stem metadata (Phase 1)

| Field | Example | Why |
| --- | --- | --- |
| Layer role | pad, texture, nature, melodic | Sequencer picks one per slot |
| Key or scale | C major, pentatonic, unpitched | Keeps layers consonant |
| Tempo | free time or BPM | Rhythmic stems stay aligned |
| Mode fit | Focus, Relax, Sleep | Mode rules filter the library |
| Energy | 1 to 5 | Shapes the session arc |
| Loudness | LUFS-normalized on import | Mix stays stable as stems swap |
| Loop points | sample-accurate start and end | Gapless playback |
| Source | AI or human | Provenance |
| Tool or artist, date, license | tool, plan, terms snapshot | AI output generally cannot be copyrighted; human stems are the defensible asset |

Codecs: Ogg Vorbis or Opus, or carefully looped AAC. Avoid MP3, whose encoder padding breaks gapless loops. Ship a small built-in set; add downloadable packs later.

## Starter mode parameters (provisional, from `docs/listening-modes.md`)

| Mode | Theta reference | Gamma PAC layer | Binaural layer | Length |
| --- | --- | --- | --- | --- |
| Focus | 6 Hz | 40 Hz rate (60 Hz selectable), 50 ms bursts at the theta reference peak | Off | 30 to 45 min, layers at full level within 5 min; looping |
| Learn | 5.5 Hz (4 to 5 Hz selectable) | 40 or 60 Hz rate, smooth swell peaking at coupling phase 0 degrees (theta reference peak) | Off | 15 to 20 min; looping |
| Relax | 6 Hz | Off or low depth | Off in v0.1 (gamma PAC layer is on); later option: 6 Hz beat rate on a 250 Hz carrier, spacing-checked | 20 to 30 min, theta reference builds over the first 10 min |
| Sleep | Delta rate: 3 Hz sweeping to about 1 Hz | Off | On in v0.1: beat rate sweeping from 3 Hz to 0 Hz on a 100 Hz carrier | 30 to 45 min, then silence |

Each value is checked against the design log before it goes into a starter recipe. Learn's coupling phase moved from trough to peak (0 degrees) after the coupling-phase research; see design log 2026-10-27 (d).

When to use each mode, and its evidence strength, per `docs/listening-modes.md`:

| Mode | When to use | Evidence strength |
| --- | --- | --- |
| Focus | Start about 10 minutes before a task and keep it running | Moderate |
| Learn | Right after studying or practice | Moderate for the theta rate, low to medium for the phase |
| Relax | Meditation, breaks, winding down | Moderate for relaxation, none for PAC |
| Sleep | Pre-sleep, in bed | Weak, preliminary |

**Spacing check to run early:** Focus gamma PAC layer bursts on a 300 Hz carrier spread energy around 260 to 340 Hz and beyond. If burst sidebands near 444 to 456 Hz come within 40 dB of the gamma PAC layer's strongest line, they collide with the 450 Hz theta reference carrier. Smoothing the burst edges, or moving one carrier, fixes the collision. FR-16 requires every starter to pass the validator, so this is a v0.1 story item.

**Focus citation note:** Focus cites Alekseichuk et al. (2016) for peak bursts, but that study used 80 Hz electrical gamma and found 40 Hz did nothing. The Focus 40 Hz default rests on the auditory response literature (design log 2026-10-27 (a)), not on that study.

## Comparables

See `research-comparables.md`. Table stakes: focus, relax, and sleep modes, offline play, timers, and a free taste before a subscription of roughly 70 to 120 USD a year. Angles no comparable covers: documented signal design, reproducible output, and describe-the-sound claims. A mode for listeners with hearing in one ear is also uncovered, but deferred (PRD §7).
