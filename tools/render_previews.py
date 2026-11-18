"""Renders the Story 3.3 listening previews (docs/signal-spec.md, Preview, Preview set).

Usage:
  uv run --locked python tools/render_previews.py [--out-dir DIR] [--rate 44100|48000]
                                                 [--renderer PATH] [--fixture PATH ...] [--list]

Defaults: --out-dir build/previews under the repository root (the parent of
tools/), --rate 48000, --renderer the preset build of arcani-render, and the
preview set (recipes/fixtures/valid/<name> for each name of
preview_constants.fixtures in tests/data/signal_spec_vectors.json, in that
order). A relative --out-dir is relative to the current directory.

--fixture (repeatable) replaces the preview set. --list prints the selected
recipe paths, one per line, and renders nothing.

An output directory that resolves to the repository root or inside it, and
not inside <repo>/build, is refused before anything is created: previews are
never goldens and are never committed. A directory outside the repository is
allowed.

Each recipe is rendered with `<renderer> RECIPE --out <dir>/<stem>.preview.wav
--rate <rate> --preview`; the report lands at <dir>/<stem>.preview.report.json.
One stdout line per render, `<stem>: <frames> frames, <seconds> s, gain <gain>`,
then `render_previews: <count> previews, <total seconds> s of audio in <dir>`;
numbers are shortest round-trip text.

Exit codes: 0 all rendered; 1 a render failed (its stderr is printed); 2
usage or refused directory; 3 the renderer is missing.

Standard library only.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VECTORS = REPO_ROOT / "tests" / "data" / "signal_spec_vectors.json"
FIXTURES = REPO_ROOT / "recipes" / "fixtures" / "valid"
OUT_DIR = REPO_ROOT / "build" / "previews"
WAV_SUFFIX = ".preview.wav"
REPORT_SUFFIX = ".preview.report.json"
RATES = (44100, 48000)
LISTENING_RATE = 48000

if sys.platform == "win32":
    PRESET, EXE = "windows-clang-cl", ".exe"
elif sys.platform == "darwin":
    PRESET, EXE = "macos-appleclang", ""
else:
    PRESET, EXE = "linux-clang", ""
RENDERER = REPO_ROOT / "build" / PRESET / "cli" / f"arcani-render{EXE}"


def preview_set():
    """The preview set's recipe paths, from the signal spec vectors."""
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    return [FIXTURES / name for name in data["preview_constants"]["fixtures"]]


def refused(out_dir):
    """True when out_dir is the repository root or inside it, and not inside <repo>/build."""
    root = REPO_ROOT.resolve()
    target = Path(out_dir).resolve()
    if not (target == root or target.is_relative_to(root)):
        return False
    build = (root / "build").resolve()
    return not (target == build or target.is_relative_to(build))


def shortest(x):
    return repr(float(x))


def main(argv):
    parser = argparse.ArgumentParser(description="Render the Story 3.3 listening previews.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--rate", type=int, choices=RATES, default=LISTENING_RATE)
    parser.add_argument("--renderer", type=Path, default=RENDERER)
    parser.add_argument("--fixture", type=Path, action="append")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv[1:])

    recipes = args.fixture if args.fixture else preview_set()
    if args.list:
        for path in recipes:
            print(path)
        return 0

    out_dir = args.out_dir.resolve()
    if refused(out_dir):
        print(f"render_previews: refused: {out_dir} is inside the repository but not under build/", file=sys.stderr)
        return 2
    if not args.renderer.is_file():
        print(f"render_previews: the renderer is missing: {args.renderer} (build it first)", file=sys.stderr)
        return 3

    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0.0
    for recipe in recipes:
        stem = Path(recipe).stem
        wav = out_dir / f"{stem}{WAV_SUFFIX}"
        result = subprocess.run([str(args.renderer), str(recipe), "--out", str(wav), "--rate", str(args.rate),
                                 "--preview"], capture_output=True, text=True)
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            print(f"render_previews: {recipe} failed with exit code {result.returncode}", file=sys.stderr)
            return 1
        report = json.loads((out_dir / f"{stem}{REPORT_SUFFIX}").read_text(encoding="utf-8"))
        member = report["preview"]
        seconds = float(member["seconds"])
        total += seconds
        print(f"{stem}: {report['frames']} frames, {shortest(seconds)} s, gain {shortest(member['gain'])}")
    print(f"render_previews: {len(recipes)} previews, {shortest(total)} s of audio in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
