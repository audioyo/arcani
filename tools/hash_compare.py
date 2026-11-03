"""Compares probe hashes across platforms (AD-9 cross-platform bit-exactness).

Usage:
  python tools/hash_compare.py ROOT [--platforms a,b,c,d] [--reference windows-x64]
                               [--expected FILE] [--tolerance FILE] [--design-log FILE]
  python tools/hash_compare.py --must-differ DIR [--expected FILE]

Compare mode: each platform's output is in ROOT/hashprobe-<platform>/, a
manifest.json (tools/hash_manifest.py) plus one <component>.f32 file per
component (raw little-endian float32). windows-x64 is the reference platform.

- Exact mode (default for every platform and component): any byte difference
  from the reference fails, naming both platforms, the component, and the
  first differing sample index. Every platform is also checked against
  ci/hash_expected.json where a component has an entry, so platforms that are
  all wrong in the same way still fail.
- Tolerance mode: only for a (platform, component) listed in
  ci/hash_tolerance.json, measured against the reference platform. It passes
  only when 20*log10(max|a-b|) (full scale 1.0, float64 on the decoded
  samples; zero difference is minus infinity) is strictly below the file's
  bound_dbfs. Every entry must cite a design log entry heading that exists in
  docs/design-log.md. A tolerance entry exempts that pair from the expected
  hash check, since its bytes differ by definition.
- A missing platform manifest, a manifest that does not match its data file,
  differing component sets, or differing sample counts fail.

Must-differ mode: DIR holds one manifest and its data. Exit 0 only when every
component with an expected entry has its data file, the expected sample
count, and a hash different from the expected one (the contraction must-fail
job); exit 1 when any matches, a data file is missing, a sample count
differs, or no component has an entry.

Exit 0 or 1, one line per violation. Standard library only.
"""

import argparse
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLATFORMS = ["windows-x64", "windows-arm64", "macos-arm64", "android-arm64"]
DEFAULT_REFERENCE = "windows-x64"
DEFAULT_EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
DEFAULT_TOLERANCE = REPO_ROOT / "ci" / "hash_tolerance.json"
DEFAULT_DESIGN_LOG = REPO_ROOT / "docs" / "design-log.md"


class Platform:
    def __init__(self, name, directory):
        self.name = name
        self.directory = directory
        self.manifest = None
        self.data = {}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_platform(name, directory, problems):
    """Loads one platform's manifest and data files; returns None when unusable."""
    plat = Platform(name, directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        problems.append(f"{name}: missing platform manifest {manifest_path}")
        return None
    try:
        manifest = load_json(manifest_path)
        components = manifest["components"]
        if not isinstance(components, dict):
            raise ValueError("components is not an object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f"{name}: cannot read manifest {manifest_path}: {exc}")
        return None
    if manifest.get("platform") != name:
        problems.append(
            f"{name}: manifest platform is {manifest.get('platform')!r}, expected {name!r} ({manifest_path})"
        )
    plat.manifest = manifest
    for comp, info in components.items():
        path = directory / f"{comp}.f32"
        try:
            data = path.read_bytes()
        except OSError as exc:
            problems.append(f"{name}: {comp}: cannot read data file {path}: {exc}")
            continue
        found = hashlib.sha256(data).hexdigest()
        if str(info.get("sha256", "")).lower() != found:
            problems.append(
                f"{name}: {comp}: manifest sha256 {info.get('sha256')} does not match data file sha256 {found}"
            )
        if len(data) % 4 != 0:
            problems.append(f"{name}: {comp}: data size {len(data)} bytes is not a multiple of 4")
            continue
        if info.get("samples") != len(data) // 4:
            problems.append(
                f"{name}: {comp}: manifest samples {info.get('samples')} does not match data file ({len(data) // 4})"
            )
        plat.data[comp] = data
    return plat


def words(data):
    return struct.unpack(f"<{len(data) // 4}I", data)


def floats(data):
    return struct.unpack(f"<{len(data) // 4}f", data)


def first_difference(a, b):
    for i, (x, y) in enumerate(zip(words(a), words(b))):
        if x != y:
            return i
    return None


def measured_dbfs(a, b):
    """20*log10(max|a-b|) in float64 on decoded float32 samples; -inf when equal."""
    peak = 0.0
    for x, y in zip(floats(a), floats(b)):
        d = abs(float(x) - float(y))
        if d > peak or math.isnan(d):
            peak = d
    if math.isnan(peak):
        return math.inf
    if peak == 0.0:
        return -math.inf
    return 20.0 * math.log10(peak)


def design_log_headings(path):
    text = Path(path).read_text(encoding="utf-8")
    return {m.group(1).strip() for m in re.finditer(r"^### (.+?):", text, re.MULTILINE)}


def load_tolerance(path, design_log, reference, problems):
    """Returns (bound, {(platform, component): entry}); problems on any invalid field."""
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        problems.append(f"tolerance: cannot read {path}: {exc}")
        return None, {}
    bound = data.get("bound_dbfs")
    if isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound):
        problems.append(f"tolerance: {path}: bound_dbfs must be a number, found {bound!r}")
        bound = None
    if not isinstance(data.get("source"), str) or not data["source"].strip():
        problems.append(f"tolerance: {path}: source must name where the bound comes from")
    entries = data.get("entries")
    if not isinstance(entries, list):
        problems.append(f"tolerance: {path}: entries must be a list")
        return bound, {}
    try:
        headings = design_log_headings(design_log)
    except OSError as exc:
        problems.append(f"tolerance: cannot read design log {design_log}: {exc}")
        headings = set()
    table = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(f"tolerance: entry {index} is not an object")
            continue
        platform = entry.get("platform")
        component = entry.get("component")
        cite = entry.get("design_log")
        label = f"tolerance entry {index} ({platform}, {component})"
        if not isinstance(cite, str) or not cite.strip():
            problems.append(f"{label}: no design_log citation")
            continue
        if cite.strip() not in headings:
            problems.append(f"{label}: design_log {cite!r} names no entry heading in {design_log}")
            continue
        if platform == reference:
            problems.append(f"{label}: the reference platform cannot have a tolerance entry")
            continue
        table[(platform, component)] = entry
    return bound, table


def load_expected(path, problems):
    try:
        data = load_json(path)
        components = data["components"]
        if not isinstance(components, dict):
            raise ValueError("components is not an object")
        return components
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append(f"expected: cannot read {path}: {exc}")
        return {}


def check_expected(plat, comp, expected, problems):
    want = expected[comp]
    info = plat.manifest["components"][comp]
    found = str(info.get("sha256", "")).lower()
    if str(want.get("sha256", "")).lower() != found:
        problems.append(
            f"{plat.name}: {comp}: does not match ci/hash_expected.json: "
            f"expected sha256 {want.get('sha256')}, found sha256 {found}"
        )
    if want.get("samples") != info.get("samples"):
        problems.append(
            f"{plat.name}: {comp}: expected {want.get('samples')} samples, found {info.get('samples')}"
        )


def compare(args):
    problems = []
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    if args.reference not in platforms:
        problems.append(f"reference platform {args.reference} is not in the platform list {platforms}")
    expected = load_expected(args.expected, problems)
    bound, tolerance = load_tolerance(args.tolerance, args.design_log, args.reference, problems)

    loaded = {}
    for name in platforms:
        plat = load_platform(name, args.root / f"hashprobe-{name}", problems)
        if plat is not None:
            loaded[name] = plat

    ref = loaded.get(args.reference)
    if ref is not None:
        ref_components = set(ref.manifest["components"])
        for name in platforms:
            plat = loaded.get(name)
            if plat is None or plat is ref:
                continue
            components = set(plat.manifest["components"])
            for comp in sorted(ref_components - components):
                problems.append(f"{name}: component {comp} is missing (present on {ref.name})")
            for comp in sorted(components - ref_components):
                problems.append(f"{name}: component {comp} is not on the reference platform {ref.name}")
            for comp in sorted(components & ref_components):
                a, b = ref.data.get(comp), plat.data.get(comp)
                if a is None or b is None:
                    continue
                if len(a) != len(b):
                    problems.append(
                        f"{ref.name} vs {name}: {comp}: sample counts differ: "
                        f"{len(a) // 4} on {ref.name}, {len(b) // 4} on {name}"
                    )
                    continue
                entry = tolerance.get((name, comp))
                if entry is None:
                    index = first_difference(a, b)
                    if index is not None:
                        problems.append(
                            f"{ref.name} vs {name}: {comp}: bytes differ, first at sample {index}"
                        )
                elif bound is not None:
                    level = measured_dbfs(a, b)
                    if not level < bound:
                        problems.append(
                            f"{ref.name} vs {name}: {comp}: tolerance mode: measured {level:.4f} dBFS, "
                            f"bound {bound} dBFS (must be strictly below; {entry.get('design_log')})"
                        )

    for name in platforms:
        plat = loaded.get(name)
        if plat is None:
            continue
        for comp in sorted(plat.manifest["components"]):
            if comp in expected and (name, comp) not in tolerance:
                check_expected(plat, comp, expected, problems)

    for line in problems:
        print(line)
    if problems:
        return 1
    components = sorted(ref.manifest["components"]) if ref is not None else []
    print(
        f"hash compare: {len(platforms)} platforms match {args.reference} "
        f"for {len(components)} component(s): {', '.join(components)}"
    )
    return 0


def must_differ(args):
    problems = []
    expected = load_expected(args.expected, problems)
    directory = Path(args.must_differ)
    try:
        manifest = load_json(directory / "manifest.json")
        components = manifest["components"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"must-differ: cannot read manifest in {directory}: {exc}")
        return 1
    checked = 0
    for comp, info in sorted(components.items()):
        if comp not in expected:
            continue
        checked += 1
        found = str(info.get("sha256", "")).lower()
        data_path = directory / f"{comp}.f32"
        if not data_path.is_file():
            problems.append(f"must-differ: {comp}: data file {data_path} is missing")
            continue
        data = data_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != found:
            problems.append(f"must-differ: {comp}: manifest sha256 {found} does not match its data file")
        want_samples = expected[comp].get("samples")
        if (not isinstance(want_samples, int) or info.get("samples") != want_samples
                or len(data) != 4 * want_samples):
            problems.append(
                f"must-differ: {comp}: expected {want_samples} samples, found {info.get('samples')} "
                f"in the manifest and {len(data) / 4:g} in the data file"
            )
            continue
        if found == str(expected[comp].get("sha256", "")).lower():
            problems.append(
                f"must-differ: {comp}: sha256 {found} equals ci/hash_expected.json; "
                "the contracted build was expected to differ"
            )
        else:
            print(f"must-differ: {comp}: sha256 {found} differs from expected {expected[comp].get('sha256')}")
    if checked == 0:
        problems.append(f"must-differ: no component in {directory} has an expected entry")
    for line in problems:
        print(line)
    return 1 if problems else 0


def main(argv):
    parser = argparse.ArgumentParser(description="Compare probe hashes across platforms.")
    parser.add_argument("root", nargs="?", type=Path)
    parser.add_argument("--must-differ", type=Path)
    parser.add_argument("--platforms", default=",".join(DEFAULT_PLATFORMS))
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--tolerance", type=Path, default=DEFAULT_TOLERANCE)
    parser.add_argument("--design-log", type=Path, default=DEFAULT_DESIGN_LOG)
    args = parser.parse_args(argv[1:])
    if args.must_differ is not None:
        return must_differ(args)
    if args.root is None:
        parser.error("ROOT is required unless --must-differ is given")
    return compare(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
