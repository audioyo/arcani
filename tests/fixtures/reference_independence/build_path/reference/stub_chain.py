"""Must-fail stand-in: names a build folder path (independence scan)."""

from pathlib import Path

import numpy as np

DUMP = Path(__file__).resolve().parents[1] / "build/windows-clang-cl"


def render(recipe_path, fs, frames=None):
    return {"output": np.zeros(2), "where": str(DUMP)}
