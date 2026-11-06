"""Must-fail stand-in: imports ctypes (independence scan)."""

import ctypes

import numpy as np


def render(recipe_path, fs, frames=None):
    assert ctypes.sizeof(ctypes.c_double) == 8
    return {"output": np.zeros(2)}
