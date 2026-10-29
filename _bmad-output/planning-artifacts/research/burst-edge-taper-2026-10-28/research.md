# Research run: gamma burst edge taper (2026-10-28)

**Question:** v0.1 gamma PAC bursts are 50 ms wide (Alekseichuk et al. 2016). What edge shape and length keep them inside the spacing rule and click test across the 30 to 60 Hz gamma rate range?

**Asked by:** Audio, during the v0.1 story breakdown session ("research and use some data").

## Literature

- **Alekseichuk et al. 2016** (Current Biology, research library): methods say bursts "lasted for 50 ms during every trough ... or peak" of a 6 Hz wave. No taper is reported. Electrical stimulation, not sound. Supports 50 ms as the full width; says nothing about edges.
- **Tone-pulse rise time in auditory physiology:** a 1988 cat auditory cortex study calls 5 to 10 ms rise times conventional and found shorter rises changed neuron responses through onset splatter ([PubMed 3385471](https://pubmed.ncbi.nlm.nih.gov/3385471)).
- **Splatter onset:** a 2025 auditory cortex paper reports splatter evident below about 1 ms rise time, from the authors' experience rather than a measured threshold ([PMC12630032](https://pmc.ncbi.nlm.nih.gov/articles/PMC12630032/)).
- **Gap:** no acoustic study found that specifies edge tapers for gamma bursts.

## Computed spectra

`burst_spectra.py` in this folder. Focus layout: 250 Hz gamma PAC carrier, bursts centered on 6 Hz theta reference peaks, raised-cosine edges inside the 50 ms. Value is the worst line at or above 394 Hz, in dB relative to the layer's strongest line. Worse than -40 fails spacing against the 450 Hz theta reference.

| Reading | Gamma rate | 0 ms | 2 ms | 5 ms | 10 ms | 12.5 ms |
| --- | --- | --- | --- | --- | --- | --- |
| Depth-gated | 40 Hz | -64.8 | -63.5 | -56.9 | -57.2 | -63.3 |
| Depth-gated | 45 Hz | -52.1 | -57.9 | -60.6 | -58.1 | -59.2 |
| Depth-gated | 60 Hz | -35.7 | -37.3 | -41.5 | -51.3 | -55.3 |
| Carrier-gated | 40 Hz | -21.1 | -21.7 | -23.9 | -38.5 | -45.0 |
| Carrier-gated | 45 Hz | -23.2 | -23.0 | -24.0 | -41.7 | -49.1 |
| Carrier-gated | 60 Hz | -41.8 | -40.7 | -34.7 | -33.8 | -44.5 |

- **Depth-gated:** the carrier plays continuously; the burst gates AM depth (CAP-4 wording). **Carrier-gated:** the carrier is silent between bursts.
- At 40 Hz, depth-gated rectangular bursts pass only because 50 ms is exactly two AM cycles, so the edges land where the modulation term is zero with zero slope. At 45 Hz that edge jumps by about 15 percent of carrier amplitude (a click); at 60 Hz it fails spacing.
- Depth-gated with 10 ms edges passes across the range checked, worst -51.3 dB at 60 Hz.

## Outcome

Depth-gated bursts with 10 ms raised-cosine edges inside the 50 ms (30 ms plateau). Engineering default, weak evidence. Logged in design log 2026-10-28 (o). S2.4 must reproduce these figures through the signal spec, the reference renderer, and the validator's component model; this script is evidence for a proposal, not a test.
