# CLAUDE.md

Procedural entrainment audio app. A desktop designer authors session recipes; a mobile app (Android first, then iOS) plays them. One C++ engine synthesizes every tone live, so the designer and the app sound identical.

Full plan: `docs/project-plan.md`. Evidence for every signal choice: `docs/research-library.md`. Read the relevant section before changing signal behavior.

## Current target: v0.1

Engine core + command-line renderer + four starter recipes + full test suite, desktop only. See "MVP scope (v0.1)" in the plan. Do not start the designer GUI, mobile apps, stems, spatial audio, accounts, or payments until v0.1 is done and signed off.

The stack is decided in the BMAD architecture step. Until then, keep the engine core in plain C++ with no framework dependency.

## Rules

1. **Testable and reproducible.** Same recipe + engine version + seed = byte-identical output. No unseeded randomness.
2. **Every rate is variable.** Theta rate, gamma rate, carriers, coupling phase, depth, and beat rate are recipe parameters with locked safe ranges. Never hard-code them.
3. **Science first.** Every default and range traces to a source in `docs/research-library.md`. If unsure, stop and ask; do not invent values.
4. **Double-check big decisions.** Stack, signal architecture, and defaults get an independent review before they lock.
5. **No ambiguity.** Name every signal by carrier frequency, modulation type, and modulation rate. Never write "60 Hz isochronic tone" or similar.
6. **Tests before code.** Write failing tests from a story's acceptance criteria first. Never weaken a threshold to make a test pass; propose the change with a reason instead.

## Signal facts

- **Binaural layer:** two steady sines, one per ear. It must reach the output on its own dichotic path. It never passes through spatial, HRTF, ambisonic, reverb, or stereo-width processing.
- **Theta reference:** a carrier amplitude-modulated at the theta rate. It exists in the file, so its phase is measurable. It is the only thing PAC couples to.
- **Gamma PAC layer:** a separate carrier, amplitude-modulated at the gamma rate. Its modulation depth follows the shared engine clock and peaks at the recipe's coupling phase.
- **Carrier rule:** every modulated carrier is at least 4 times its modulation rate.
- **Spacing rule:** at least 50 Hz between any two active spectral components, including modulation side frequencies.

## Never

- Route binaural carriers through any spatial or width stage. This exact bug broke an earlier project.
- Couple gamma to a binaural beat. It has no waveform in the file.
- Use Monroe, Hemi-Sync, Gateway, Focus-level, or SAM names or terms anywhere: code, comments, docs, UI, or store copy.
- Model session arcs on Monroe or Gateway programs.
- Write health, therapy, treatment, or "neurostimulation" claims in UI or store copy. Describe the sound, not outcomes.
- Use em dashes in docs, comments, or UI copy.

## Vocabulary

- **Carrier:** the audible tone, in Hz.
- **Rate:** how fast something repeats, in Hz.
- **AM:** amplitude modulation, a carrier's volume shaped by a slower wave.
- **Monaural beat / isochronic:** rhythm that exists in the file.
- **Binaural beat:** a rhythm that exists only in the listener's brain.
- **PAC (here):** gamma-layer strength rising and falling with the in-file theta reference.

## Tests

Thresholds are in "Test thresholds (provisional)" in the plan. Every render is checked for:

- binaural isolation
- coupling timing
- carrier ratio and spacing
- frequency accuracy
- 8-hour drift
- match against the Python reference renderer
- determinism
- clicks
- gain ramps
- loudness and true peak
- render speed

Commands (fill in once the architecture step creates the build):

- Build: `TBD`
- C++ tests: `TBD`
- Python reference and signal tests: `uv run pytest`
- Render a recipe: `TBD`

Run the fast tests after every change. Do not commit with failing tests. Golden files change only after a human listening sign-off.

## Workflow

- BMAD drives planning: brief (the plan doc), then PRD, architecture, and stories.
- One story per branch. Keep commits small, with messages that say what changed and why.
- Log every changed default or threshold in the design log with its source or test result.
