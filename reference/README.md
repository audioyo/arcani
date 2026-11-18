# reference

Python reference renderer. It renders the ideal signals from `docs/signal-spec.md` so engine output can be checked against them.

- `ideal.py`: the increment rule, the seconds-to-samples rule, and the ideal sine (signal spec, Core and Sine), plus the hash probe's ideal sine component.
- `theta.py`: the theta reference (signal spec, Theta reference): the four envelope shapes by the spec's integer segments with ideal NumPy cosines, the depth law, and `render(theta_reference, fs, frames)`, the theta tap of one channel.
- `components.py` (Story 3.1): `component_table(recipe, mute="none")`, the spectral component table (signal spec, Components) from the closed-form line model in binary64 with NumPy's sine, cosine, and square root; nothing is rendered or sampled.
- `spacing.py` (Story 3.2): `spacing_margins(recipe, mute="none")`, `check_spacing(recipe, mute="none")`, and `pair_form(...)`, the spacing rule (signal spec, Spacing) on its own component table: the closed-form minimum distance per ear and pair, the worst pair per ear, and the error detail, in binary64 with NumPy; nothing is rendered or sampled.
- `preview.py` (Story 3.3): the listening preview (signal spec, Preview): `preview_frames(recipe, fs)`, `seams_heard(recipe, fs)`, `layers_per_ear(recipe, mute="none")`, the preview gain `gain(peak_dbfs, layers_max)` by the spec's binary64 steps, and `report_member(recipe, fs)`; nothing is rendered.
- `stub_chain.py`: `render(recipe_path, fs, frames=None)` renders the stub chain (signal spec, Stub chain) from recipe JSON in binary64 with the ideal sine and the theta tap from `theta.py`, returning the output and the five taps (theta, gamma, bus, join, master) as interleaved stereo arrays. The reference match assertion (`tests/assertions/reference_match.py`) compares the engine with it.

This folder imports only the standard library, NumPy, and its own modules, and never reads engine code, engine binaries, or engine output (`tests/python/test_reference_independent.py`).
