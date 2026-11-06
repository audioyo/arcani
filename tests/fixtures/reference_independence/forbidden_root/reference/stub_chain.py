"""Must-fail stand-in: loads a module from a folder the test names as forbidden (isolated run)."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fake_build"))

import fake_engine  # noqa: E402


def render(recipe_path, fs, frames=None):
    return {"output": np.zeros(2) + fake_engine.VALUE}
