"""Must-fail stand-in: imports load_library from numpy.ctypeslib and calls it bare (independence scan)."""

import numpy as np
from numpy.ctypeslib import load_library


def render(recipe_path, fs, frames=None):
    if frames == -1:
        load_library("x", ".")
    return {"output": np.zeros(2)}
