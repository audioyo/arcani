"""Must-fail stand-in: runs code through exec (independence scan)."""

import numpy as np


def render(recipe_path, fs, frames=None):
    scope = {}
    exec("value = 0.0", scope)
    return {"output": np.zeros(2) + scope["value"]}
