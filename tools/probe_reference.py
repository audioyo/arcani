"""NumPy float32 reference of the hash probe component probe-arith (AD-9).

Usage:
  python tools/probe_reference.py            print the reference SHA-256
  python tools/probe_reference.py --out DIR  write DIR/probe-arith.f32
  python tools/probe_reference.py --write    update ci/hash_expected.json
  python tools/probe_reference.py --check    exit 0 if ci/hash_expected.json matches, else 1
  --expected FILE selects another expected file for --write and --check.
  --write updates only the probe-arith entry and keeps every other key.

Every operation is rounded to float32 on its own, as in the C++ probe built
with -ffp-contract=off and no fast-math. Same operation order as
tests/hashprobe/main.cpp, side by side:

  C++ (tests/hashprobe/main.cpp)        Python (probe_arith below)
  float s = seed;      // 0.3125        s = SEED
  const float t = r * s;                t = f32(R * s)
  s = t - t * s;       // contractable  s = f32(t - f32(t * s))
  out[i] = s * a + b;  // contractable  out[i] = f32(f32(s * A) + B)

The two contractable expressions are the ones a compiler fuses into one
multiply-add when contraction is on. probe_arith_fused() computes them with a
single rounding (float64 product and sum, then one round to float32), to show
the probe is sensitive to contraction.

Every constant is exact in float32 and in decimal.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
COMPONENT = "probe-arith"
SAMPLES = 4096

f32 = np.float32
SEED = f32(0.3125)
R = f32(3.8984375)
A = f32(0.7109375)
B = f32(0.1015625)


def probe_arith():
    """Returns the probe-arith samples, each operation rounded to float32."""
    out = np.empty(SAMPLES, dtype=np.float32)
    s = SEED
    for i in range(SAMPLES):
        t = f32(R * s)
        s = f32(t - f32(t * s))
        out[i] = f32(f32(s * A) + B)
    return out


def probe_arith_fused():
    """Same sequence with the two contractable expressions rounded once each."""
    out = np.empty(SAMPLES, dtype=np.float32)
    s = SEED
    for i in range(SAMPLES):
        t = f32(R * s)
        s = f32(float(t) - float(t) * float(s))
        out[i] = f32(float(s) * float(A) + float(B))
    return out


def to_bytes(samples):
    return np.asarray(samples, dtype="<f4").tobytes()


def entry(samples):
    return {"samples": int(len(samples)), "sha256": hashlib.sha256(to_bytes(samples)).hexdigest()}


SOURCE = "tools/probe_reference.py: NumPy float32 reference, each operation rounded separately"


def updated_document(path, samples):
    """The expected file at path with its probe-arith entry replaced."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("source", SOURCE)
    components = doc.get("components")
    if not isinstance(components, dict):
        components = {}
    components[COMPONENT] = entry(samples)
    doc["components"] = components
    return doc


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--out", type=Path, help="write DIR/probe-arith.f32")
    group.add_argument("--write", action="store_true", help="update ci/hash_expected.json")
    group.add_argument("--check", action="store_true", help="compare with ci/hash_expected.json")
    parser.add_argument("--expected", type=Path, default=EXPECTED, help="expected file (default ci/hash_expected.json)")
    args = parser.parse_args(argv[1:])

    samples = probe_arith()
    ref = entry(samples)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{COMPONENT}.f32"
        path.write_bytes(to_bytes(samples))
        print(f"{COMPONENT}: wrote {path} ({ref['samples']} samples, sha256 {ref['sha256']})")
        return 0
    if args.write:
        doc = updated_document(args.expected, samples)
        args.expected.parent.mkdir(parents=True, exist_ok=True)
        args.expected.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"{COMPONENT}: wrote {args.expected} (sha256 {ref['sha256']})")
        return 0
    if args.check:
        try:
            stored = json.loads(args.expected.read_text(encoding="utf-8"))["components"][COMPONENT]
        except (OSError, ValueError, KeyError) as exc:
            print(f"{COMPONENT}: cannot read expected entry from {args.expected}: {exc}")
            return 1
        if stored.get("sha256") != ref["sha256"] or stored.get("samples") != ref["samples"]:
            print(
                f"{COMPONENT}: {args.expected}: expected sha256 {stored.get('sha256')} "
                f"({stored.get('samples')} samples), found reference sha256 {ref['sha256']} ({ref['samples']} samples)"
            )
            return 1
        print(f"{COMPONENT}: {args.expected} matches the reference (sha256 {ref['sha256']})")
        return 0
    print(f"{COMPONENT}: {ref['samples']} samples, sha256 {ref['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
