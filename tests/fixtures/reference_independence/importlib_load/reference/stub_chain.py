"""Must-fail stand-in: imports importlib, which can load modules the scan never sees."""

import importlib

import numpy as np


def render(recipe_path, fs, frames=None):
    importlib.invalidate_caches()
    return {"output": np.zeros(2)}
