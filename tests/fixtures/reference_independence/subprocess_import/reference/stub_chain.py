"""Must-fail stand-in: loads subprocess while rendering (scan and isolated run)."""

import numpy as np


def render(recipe_path, fs, frames=None):
    import subprocess

    del subprocess
    return {"output": np.zeros(2)}
