"""Must-fail stand-in: calls os.add_dll_directory (independence scan)."""

import os

import numpy as np


def render(recipe_path, fs, frames=None):
    os.add_dll_directory(os.path.dirname(os.path.abspath(__file__)))
    return {"output": np.zeros(2)}
