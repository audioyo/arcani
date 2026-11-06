"""Must-fail stand-in: uses numpy.ctypeslib to load a shared library (independence scan)."""

import numpy as np


def render(recipe_path, fs, frames=None):
    loader = np.ctypeslib.load_library
    del loader
    return {"output": np.zeros(2)}
