# Glossary (v0.1)

Binding terms from PRD §3, limited to what v0.1 uses. Code, docs, and recipes use them exactly.

- **Carrier:** the audible tone of a signal, in Hz.
- **Rate:** how fast something repeats (beat, pulse, or modulation), in Hz.
- **AM:** amplitude modulation; a carrier's volume shaped by a slower wave.
- **Engine clock:** the single sample-accurate timebase driving every layer.
- **Theta reference:** a carrier AM at the theta rate. It exists in the file, so its phase is measurable. The only thing PAC couples to. In Sleep its rate is a delta rate (below 4 Hz); the term still applies.
- **Gamma PAC layer:** a separate carrier AM at the gamma rate, whose modulation depth follows the theta reference phase (from the engine clock) and peaks at the coupling phase.
- **Coupling phase:** where in each theta reference cycle gamma modulation depth peaks; 0 to 360 degrees on the theta reference envelope, 0 degrees at its maximum. Per shape, 0 degrees is: the peak (sine), the center of the on plateau (smoothed on-off), the top just before the drop (sawtooth), the top just after the rise (reverse saw). A recipe can set gamma uncoupled.
- **Binaural layer:** two pure sines, one per ear, whose frequencies may follow a recipe rate curve; their difference is the beat rate. Dichotic only. The beat exists only in the listener's brain, so nothing couples to it.
- **Monaural beat / isochronic:** a rhythm that exists in the file.
- **PAC (here):** gamma PAC layer strength rising and falling with the theta reference.
- **Recipe:** a versioned JSON file that fully specifies a session.
- **Mode:** a session family (Focus, Learn, Relax, Sleep); each is one or more recipes.
- **Locked range:** the allowed span for a recipe parameter, traced to the design log.
- **Validator:** the compiler check that rejects a recipe breaking a locked range, the carrier rule, or the spacing rule.
- **Carrier rule:** every modulated carrier is at least 4 times its modulation rate.
- **Spectral component:** any spectral line of a layer within 40 dB of that layer's strongest line, counting harmonics from bursts, envelope shapes, and non-sine carriers. 40 dB is a placeholder.
- **Spacing rule:** in each ear, at least 50 Hz between any spectral component of one layer and any of another, counting modulation side frequencies. A layer's own components and the binaural pair are exempt. 50 Hz is a placeholder.
- **Rate curve:** a scheduled change of a rate over the session, such as Sleep's cycling binaural beat rate.
- **Master chain:** the stages after the layers are mixed: per-channel gain and the stereo-linked limiter. Never mixes left and right.
- **Core zone:** theta reference, gamma PAC layer, and binaural layer, wired in code. Recipes set parameters, never routing.
- **Render plan:** the immutable output of compiling a validated recipe; the only input the renderer accepts.
- **Determinism key:** recipe hash + every pinned asset hash + engine version + sample rate.
- **Golden file:** a render Audio approved by ear; later renders of the same recipe must match it.
- **Engineering default:** a starting value chosen by engineering judgment, not a study; logged as such and never presented as a science claim.
- **Gate:** the pass condition that ends a phase.
