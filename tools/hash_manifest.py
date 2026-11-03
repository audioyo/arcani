"""Writes the hash manifest for one platform's probe output (AD-9).

Usage:
  python tools/hash_manifest.py --platform NAME --check-json PATH --probe-dir DIR [--out FILE]

Reads toolchain_name and toolchain_version from PATH (the build's
arcani_engine_check.json). For each *.f32 file in DIR (raw little-endian
float32, one per component; the component is the file stem), records the
sample count and the SHA-256 of the file bytes. Writes FILE (default
DIR/manifest.json):

  {"platform": NAME,
   "toolchain": {"name": ..., "version": ...},
   "components": {"probe-arith": {"samples": 4096, "sha256": "..."}}}

Exit 0 on success; exit 1 with one line per problem (unreadable check JSON,
no .f32 file, a file size that is not a multiple of 4).

Standard library only.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main(argv):
    parser = argparse.ArgumentParser(description="Write a probe hash manifest.")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--check-json", required=True, type=Path)
    parser.add_argument("--probe-dir", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv[1:])

    problems = []
    try:
        check = json.loads(args.check_json.read_text(encoding="utf-8"))
        toolchain = {"name": str(check["toolchain_name"]), "version": str(check["toolchain_version"])}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f"hash manifest: cannot read toolchain from {args.check_json}: {exc}")
        toolchain = None

    components = {}
    files = sorted(args.probe_dir.glob("*.f32")) if args.probe_dir.is_dir() else []
    if not files:
        problems.append(f"hash manifest: no .f32 component files in {args.probe_dir}")
    for path in files:
        data = path.read_bytes()
        if len(data) % 4 != 0:
            problems.append(f"hash manifest: {path.name}: size {len(data)} bytes is not a multiple of 4")
            continue
        components[path.stem] = {"samples": len(data) // 4, "sha256": hashlib.sha256(data).hexdigest()}

    for line in problems:
        print(line)
    if problems:
        return 1

    manifest = {"platform": args.platform, "toolchain": toolchain, "components": components}
    out = args.out or (args.probe_dir / "manifest.json")
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, comp in components.items():
        print(f"{args.platform}: {name}: {comp['samples']} samples, sha256 {comp['sha256']}")
    print(f"{args.platform}: wrote {out} ({toolchain['name']} {toolchain['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
