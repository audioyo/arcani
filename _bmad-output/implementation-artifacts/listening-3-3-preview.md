# Listening checklist: Story 3.3 early preview

Six short renders of the starter layer configurations and two gamma checks, heard on earbuds and on headphones, so a harsh carrier or a rough gamma pulse is caught now instead of at sign-off. Describe what you hear in plain words. Write down the sound, not how it makes you feel or what it might do.

These previews are not the starter recipes: they have no level ramps or fades (Epic 4), and they are never goldens. Story spec: `spec-3-3-early-listening-preview.md`. Signal spec: `docs/signal-spec.md`, Preview. Design log 2026-11-17 (xx).

## How to render

Build first (`powershell -File tools/dev.ps1 cmake --workflow --preset windows-clang-cl`), then run one command from the repository root:

```
uv run --locked python tools/render_previews.py
```

It writes six WAVs at 48 kHz into `build/previews/`, each with its report: `starter-focus-layers.preview.wav`, `starter-learn-layers.preview.wav`, `starter-relax-layers.preview.wav`, `starter-sleep-layers.preview.wav`, `preview-gamma-250-am-60-swell.preview.wav`, and `preview-gamma-250-am-60-bursts.preview.wav`. Nothing is committed: `build/` is ignored by git.

## Level

The previews are quiet on purpose: the summed layers peak at -30 dBFS at most (row `preview-peak-level`). Start with the playback level low in Reaper and raise it to a comfortable level, then leave it there for the whole pass. Keep it the same for every render in a pass so they can be compared.

Protect your hearing: the previews peak at -30 dBFS, so the playback level you set for them is far above normal. Turn the playback level back down after each pass, and never play a normal (non-preview) render at the raised setting: normal renders peak near full scale.

Both edges of every preview are abrupt, as expected: there are no level ramps or fades until Epic 4. The sound starts at full level at 0 s and stops at the end of each file. Ignore a click at either edge, and note any click anywhere else.

## Budget

| Render | Length |
| --- | --- |
| Focus | 210 s |
| Learn | 210 s |
| Relax | 180 s |
| Sleep | 180 s |
| 250 Hz carrier with gamma AM at 60 Hz, smooth swell | 180 s |
| 250 Hz carrier with gamma AM at 60 Hz, 50 ms bursts | 180 s |
| One pass | 1,140 s (19 min) |

Two passes: first on earbuds, then on headphones, 38 min of audio in all. With notes and a few replays, plan about 50 minutes, and stop under about 1 hour. One pass per sitting is fine.

## Renders

Fill the Earbuds column in the first pass and the Headphones column in the second. A short phrase is enough ("clean", "a bit buzzy", "click at 60 s"). Leave a cell empty only if you did not get to it.

### Focus: `starter-focus-layers.preview.wav` (210 s)

A 450 Hz carrier amplitude-modulated by the sine envelope at 6 Hz, 75 percent depth (theta reference), and a 250 Hz sine carrier amplitude-modulated at 40 Hz in 50 ms bursts at the 0 degree coupling phase, 100 percent depth (gamma PAC layer). Loops: opening 60 s, then a 120 s body.

| # | Listen for | Time | Earbuds | Headphones |
| --- | --- | --- | --- | --- |
| F1 | The 450 Hz tone and its slow 6 Hz pulse: harsh or not? | whole render | | |
| F2 | The 250 Hz tone: harsh or not? | whole render | | |
| F3 | The 40 Hz flutter in the bursts: rough or not? | whole render | | |
| F4 | Inside each 50 ms burst the 40 Hz flutter runs on its own, so each burst opens at a different point of it. Do the bursts sound even, or does one burst differ from the next? (design log (qq)) | whole render | | |
| F5 | The seam at the opening end: any click, jump, or change in the sound? | 60 s | | |
| F6 | The first body seam: any click, jump, or change in the sound? | 180 s | | |

### Learn: `starter-learn-layers.preview.wav` (210 s)

A 450 Hz carrier amplitude-modulated by the sine envelope at 5.5 Hz, 75 percent depth, and a 250 Hz sine carrier amplitude-modulated at 40 Hz with a smooth swell peaking at the 0 degree coupling phase, 100 percent depth. Loops: opening 60 s, then a 120 s body.

| # | Listen for | Time | Earbuds | Headphones |
| --- | --- | --- | --- | --- |
| L1 | The 450 Hz tone and its slow 5.5 Hz pulse: harsh or not? | whole render | | |
| L2 | The 250 Hz tone: harsh or not? | whole render | | |
| L3 | The 40 Hz flutter as it swells in and out: rough or not? | whole render | | |
| L4 | The seam at the opening end: any click, jump, or change in the sound? | 60 s | | |
| L5 | The first body seam: any click, jump, or change in the sound? | 180 s | | |

### Relax: `starter-relax-layers.preview.wav` (180 s)

A 450 Hz carrier amplitude-modulated by the sine envelope at 6 Hz, 75 percent depth, and a 250 Hz sine carrier amplitude-modulated at 40 Hz with a smooth swell peaking at the 0 degree coupling phase, 25 percent depth. No loop.

| # | Listen for | Time | Earbuds | Headphones |
| --- | --- | --- | --- | --- |
| R1 | The 450 Hz tone and its slow 6 Hz pulse: harsh or not? | whole render | | |
| R2 | The 250 Hz tone: harsh or not? | whole render | | |
| R3 | The light 40 Hz flutter as it swells in and out: rough or not, and can you hear it at all? | whole render | | |

### Sleep: `starter-sleep-layers.preview.wav` (180 s)

A 450 Hz carrier amplitude-modulated by the sine envelope at 2 Hz, 75 percent depth, and a binaural layer: a 100 Hz pure sine in the left ear and a pure sine in the right ear 0 to 3 Hz above it. The binaural beat rate cycles over 0 to 3 Hz every 60 s: 0 Hz at 0, 60, 120, and 180 s, and 3 Hz at 30, 90, and 150 s. No gamma PAC layer. No loop.

| # | Listen for | Time | Earbuds | Headphones |
| --- | --- | --- | --- | --- |
| S1 | The 450 Hz tone and its slow 2 Hz pulse: harsh or not? | whole render | | |
| S2 | The low 100 Hz tones: harsh, boomy, or clean? | whole render | | |
| S3 | The binaural beat: does it slowly speed up and slow down once a minute, smoothly, with no jump? | 0 to 180 s, fastest at 30, 90, 150 s | | |

### 250 Hz carrier with gamma AM at 60 Hz, smooth swell: `preview-gamma-250-am-60-swell.preview.wav` (180 s)

A 450 Hz carrier amplitude-modulated by the sine envelope at 6 Hz, 75 percent depth, and a 250 Hz sine carrier amplitude-modulated at 60 Hz with a smooth swell peaking at the 0 degree coupling phase, 100 percent depth. The carrier rule review of 2026-11-16 asked for this check (condition 2): 250 Hz is close to the 240 Hz floor at 60 Hz.

| # | Listen for | Time | Earbuds | Headphones |
| --- | --- | --- | --- | --- |
| W1 | The 250 Hz tone with the 60 Hz flutter swelling in and out: harsh or not? | whole render | | |
| W2 | The 60 Hz flutter: rough or not? Does it sound like a separate low hum? | whole render | | |

### 250 Hz carrier with gamma AM at 60 Hz, 50 ms bursts: `preview-gamma-250-am-60-bursts.preview.wav` (180 s)

The same 450 Hz theta reference, and a 250 Hz sine carrier amplitude-modulated at 60 Hz in 50 ms bursts at the 0 degree coupling phase, 100 percent depth. The same review condition.

| # | Listen for | Time | Earbuds | Headphones |
| --- | --- | --- | --- | --- |
| B1 | The 250 Hz tone with the 60 Hz flutter in short bursts: harsh or not? | whole render | | |
| B2 | The 60 Hz flutter in the bursts: rough or not? Does it sound like a separate low hum? | whole render | | |
| B3 | The bursts: even, or does one burst differ from the next? | whole render | | |

## Proposed changes

List each change you would make to a default or a range, one per line. Each one gets its own design log entry and goes to the story that owns it before Epic 4 starts. Leave the table empty if nothing needs changing.

| # | What to change | From | To | Why (what you heard, by line number) | Owning story | Design log entry |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## Result

Write one of these, with the date, after both passes:

- "Nothing needs changing." This is a valid result, and the story closes on it.
- "Changes proposed." Then every row above has an owning story and a design log entry.

| Field | Entry |
| --- | --- |
| Date | |
| Listener | |
| Commit the previews were rendered from (`git rev-parse --short HEAD`) | |
| Engine version (`engine_version` in each report) | |
| Sample rate | 48 kHz |
| Playback gain in Reaper (dB) | |
| Earbuds (model) | |
| Headphones (model) | |
| Result | |
| Notes | |
