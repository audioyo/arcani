# reference

Python reference renderer. It renders the ideal signals from `docs/signal-spec.md` so engine output can be checked against them.

- `ideal.py`: the increment rule, the seconds-to-samples rule, and the ideal sine (signal spec, Core and Sine), plus the hash probe's ideal sine component.
- `theta.py`: the theta reference (signal spec, Theta reference): the four envelope shapes by the spec's integer segments with ideal NumPy cosines, the depth law, and `render(theta_reference, fs, frames)`, the theta tap of one channel.
- `stub_chain.py`: `render(recipe_path, fs, frames=None)` renders the stub chain (signal spec, Stub chain) from recipe JSON in binary64 with the ideal sine and the theta tap from `theta.py`, returning the output and the five taps (theta, gamma, bus, join, master) as interleaved stereo arrays. The reference match assertion (`tests/assertions/reference_match.py`) compares the engine with it.

This folder imports only the standard library, NumPy, and its own modules, and never reads engine code, engine binaries, or engine output (`tests/python/test_reference_independent.py`).
