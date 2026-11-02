# Thresholds and Locked Ranges (v0.1)

The repo's threshold table and locked-range table (spine Conventions) are built from these two tables. All values are provisional: Phase 0 confirms or changes each one, with a design log entry. Never weaken a value to make a test pass.

## Test thresholds

| Assertion | Pass condition | Source |
| --- | --- | --- |
| Binaural isolation, engine output | In each ear, the other ear's binaural carrier at least 90 dB below its own. Measured with one ear's oscillator muted, so it works at any beat rate incl. 0 Hz | Plan Test thresholds; FR-4 |
| Binaural isolation, after master chain | At least 60 dB below | Plan Test thresholds; FR-4 |
| Coupling timing | Each gamma envelope peak within 2 ms of its target coupling phase on the in-file theta reference | Plan Test thresholds; FR-3 |
| Coupling independence | Changing binaural beat rate or phase leaves every gamma peak time unchanged to the sample | AD-5 |
| Envelope shape | Passes through the reference match | FR-13 |
| Carrier rule | Every modulated carrier at least 4 times its modulation rate | Plan Test thresholds; FR-9 |
| Spacing rule | Per ear, at least 50 Hz between any spectral component of one layer and any of another, incl. side frequencies; own-layer components and the binaural pair exempt. Component = line within 40 dB of the layer's strongest line. Checked across the whole session incl. rate curves | Design log 2026-10-27 (e), (i); AD-20 |
| Frequency accuracy | Every carrier and rate within 0.01 Hz of the recipe value; along rate curves, instantaneous rate within 0.01 Hz of the schedule with continuous phase | Plan Test thresholds; FR-1 |
| Long-session drift | Theta reference phase error under 1 ms after an 8-hour render | Plan Test thresholds; FR-1 |
| Reference match | Engine pre-quantization float output and per-layer taps vs Python reference: less than -100 dBFS, sample by sample | Plan Test thresholds; AD-16 |
| Determinism | Same recipe, engine version, seed, sample rate: byte-identical file | CLAUDE.md rule 1; FR-6 |
| Cross-platform | Identical hashes across the AD-9 CI matrix; a component proven unable falls back to -100 dBFS, logged | AD-9; design log (j) |
| Block-size invariance | Identical bytes at 1, 64, 512, 4096 frames per call | AD-10 |
| Clicks | No discontinuity above -60 dBFS in an 8 kHz high-pass at loop seams, ramp edges, burst edges | Plan Test thresholds |
| Dropouts | No run of all-zero samples longer than 1 ms in a channel where the recipe sets a non-zero level | Design log (i) |
| NaN or infinite values | Zero tolerance | FR-13 |
| Gain ramps | No layer or master gain ramp completes in under 10 ms. Modulation envelopes and limiter gain reduction exempt | Plan Test thresholds; FR-5 |
| Limiter idle | Zero gain reduction on every v0.1 render: master chain output equals input times master gain, bit for bit | AD-4; design log (k), (p) |
| Loudness | Integrated loudness within 1 LU of the recipe target | Plan Test thresholds; FR-5 |
| True peak | At or below -1 dBTP | Plan Test thresholds; FR-5 |
| Render speed | At least 20 times real time, on the dev PC only | Plan Test thresholds; FR-11 |

## Locked ranges

| Parameter | v0.1 range | Basis |
| --- | --- | --- |
| Theta reference rate (incl. delta and along rate curves) | 1 to 6 Hz | Lee et al. 2024 (0 to 3 Hz beat range), Lega et al. 2016 (2.5 to 5 Hz), Roberts et al. 2018 (5.5 Hz), Jirakittayakorn and Wongsawat 2017 (6 Hz); design log (h) |
| Theta reference carrier | 100 to 500 Hz | Chaieb et al. 2017 (about 107 to 220 Hz), Orozco Perez et al. 2020 (about 400 Hz); 450 Hz engineering default; design log (h), (g) |
| Theta reference AM depth | 0 to 100 percent; every v0.1 starter uses 75 percent | Engineering default; design log 2026-10-29 (s) |
| Gamma rate | 30 to 60 Hz (default 40 Hz, proposed) | Design log (a) |
| Gamma PAC carrier | 200 to 500 Hz; carrier rule raises the floor to 4 times the gamma rate | Engineering default; design log (g) |
| Coupling phase | 0 to 360 degrees, or uncoupled (default 0 degrees, proposed) | Design log (b) |
| Coupling depth | 0 to 100 percent | Ross et al. 2003; design log (h) |
| Burst width | 50 ms full width, fixed; 10 ms raised-cosine edges inside it, depth-gated | Alekseichuk et al. 2016; design log (h), (o) |
| Binaural carriers | Below 1000 Hz | Licklider et al. 1950, cited by Lopez-Caballero and Escera 2017 |
| Binaural beat rate | 0 to below 30 Hz | Design log (f) |
| Session length | Up to 8 h | Engineering default, the longest length the drift test proves; Phase 0 sets the hearing-safety value; design log 2026-11-01 (u) |
| Looping max run time | Required on every looping recipe; v0.1 starters: Focus 45 min, Learn 20 min | Engineering default, top of each mode's length range (listening-modes.md); design log (m); Phase 0 sets the WHO-ITU-based value |
| Loudness levels | Tones -36 LUFS-I, master -16 LUFS-I; every tones-only v0.1 starter targets -36 LUFS-I | Engineering defaults; design log (g), (m) |
