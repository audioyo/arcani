"""Must-fail stand-in: imports a package that is neither the standard library nor NumPy."""

import numpy as np


def render(recipe_path, fs, frames=None):
    import scipy.signal

    del scipy
    return {"output": np.zeros(2)}
