"""Cross-platform hash probe manifests and the hash compare tool (AD-9).

Contract with tools/hash_manifest.py (stdlib only):

- `python tools/hash_manifest.py --platform NAME --check-json PATH
  --probe-dir DIR [--out FILE]`; FILE defaults to DIR/manifest.json.
- Reads `toolchain_name` and `toolchain_version` from the check JSON (the
  build's `arcani_engine_check.json`).
- For each `*.f32` file in DIR: component = file stem, `samples` = file size
  / 4, `sha256` = lowercase hex SHA-256 of the file bytes.
- Writes JSON:
    {"platform": NAME,
     "toolchain": {"name": <toolchain_name>, "version": <toolchain_version>},
     "components": {"probe-arith": {"samples": 4096, "sha256": "<hex>"}}}
- Exit 0 on success. Exit 1, with one line naming the problem, when a data
  file's size is not a multiple of 4, when DIR holds no `.f32` file, or when
  the check JSON is missing, unreadable, or lacks a toolchain key.

Contract with tools/hash_compare.py (stdlib only):

- Compare mode: `python tools/hash_compare.py ROOT [--platforms a,b,c,d]
  [--reference windows-x64] [--expected FILE] [--tolerance FILE]
  [--design-log FILE]`. Defaults: platforms
  `windows-x64,windows-arm64,macos-arm64,android-arm64`, reference
  `windows-x64`, expected `ci/hash_expected.json`, tolerance
  `ci/hash_tolerance.json`, design log `docs/design-log.md`, all relative to
  the repo root (not the working directory).
- Each platform's files live in `ROOT/hashprobe-<platform>/`: `manifest.json`
  (schema above) plus `<component>.f32` (raw little-endian float32).
- Exit 0 when nothing fails, else exit 1 with one output line per violation
  (stdout or stderr). Violations:
    * a platform manifest is missing: the line names the platform;
    * a manifest's `platform` differs from its directory's platform name;
    * a manifest `sha256` differs from the SHA-256 of its data file, or a
      listed data file is missing;
    * a platform's component set differs from the reference platform's: the
      line names the platform and the component;
    * a component's sample count differs from the reference's: the line names
      both counts;
    * exact mode (no tolerance entry for that platform and component): the
      bytes differ from the reference platform's; the line names both
      platforms, the component, and `sample <index>` of the first differing
      sample (bitwise compare of the float32 words);
    * expected-hash check: when `components` of the expected file has an
      entry for a component, every platform's component without a tolerance
      entry must have exactly that `sha256` and `samples`; the line names the
      component, the expected hash, and the found hash. Four identically
      wrong platforms therefore fail.
- Tolerance mode, for a (platform, component) listed in the tolerance file:
  compared against the reference platform; measured =
  `20*log10(max|a-b|)` in float64 on the decoded samples (math.log10, full
  scale 1.0; zero difference is minus infinity); passes only when measured is
  strictly below `bound_dbfs`; the failure line names the measured dBFS and
  the bound. Such a (platform, component) is exempt from the expected-hash
  check (its sample count must still match).
- Tolerance file schema:
    {"bound_dbfs": -100, "source": "AD-9; design log 2026-10-27 (j)",
     "entries": [{"platform": ..., "component": ..., "design_log":
                  "2026-11-02 (z)", "reason": ...}]}
  The bound comes only from this file, never from code. Exit 1 when
  `bound_dbfs` is missing or not a number, when `source` is missing or empty,
  when an entry's `design_log` is missing or empty or names no heading
  `### <design_log>: <title>` in the design log (the line names the entry's
  platform and component), or when an entry names the reference platform.
- Expected file schema (written by tools/probe_reference.py; other top-level
  keys allowed):
    {"components": {"probe-arith": {"samples": 4096, "sha256": "<hex>"}}}
- Must-differ mode: `python tools/hash_compare.py --must-differ DIR
  [--expected FILE]`. DIR holds one manifest.json and its data files. Each
  component's hash is the SHA-256 of its data file (a manifest sha256 that
  disagrees with its data file fails). Exit 0 only when every component that
  has an expected entry has a different sha256 from expected; the output
  prints the found hash. Exit 1 when any matches (the line names the
  component and the hash) or when no component has an expected entry.

Real data files: `ci/hash_tolerance.json` has bound -100, a source naming
AD-9 and `2026-10-27 (j)`, and no entries; `ci/hash_expected.json` has a
`probe-arith` entry with 4096 samples and a 64-hex sha256.
"""

import hashlib
import json
import math
import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPARE = REPO_ROOT / "tools" / "hash_compare.py"
MANIFEST = REPO_ROOT / "tools" / "hash_manifest.py"
PLATFORMS = ["windows-x64", "windows-arm64", "macos-arm64", "android-arm64"]
REFERENCE = "windows-x64"
COMPONENT = "probe-arith"
TEST_LOG_ENTRY = "2026-11-02 (zz)"


def run(script, *args, cwd=None):
    result = subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd,
    )
    return result.returncode, result.stdout + result.stderr


def assert_one_line_names(output, *needles):
    lines = [line for line in output.splitlines() if all(n in line for n in needles)]
    assert lines, f"no single line names all of {needles}:\n{output}"


# ------------------------------------------------------------- samples


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def from_bits(word):
    return struct.unpack("<f", struct.pack("<I", word))[0]


def to_bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def base_samples(n=64):
    return [f32(math.sin(0.1 * i) * 0.5) for i in range(n)]


def encode(samples):
    return struct.pack(f"<{len(samples)}f", *samples)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def measured_dbfs(a, b):
    """The contract's formula on float32 sample lists, in float64."""
    peak = max(abs(x - y) for x, y in zip(a, b))
    return -math.inf if peak == 0 else 20 * math.log10(peak)


# ------------------------------------------------------------- fixtures


def write_platform(root, platform, components, manifest_platform=None, sha_override=None):
    """Writes ROOT/hashprobe-<platform>/ with data files and a manifest."""
    d = root / f"hashprobe-{platform}"
    d.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name, samples in components.items():
        data = encode(samples)
        (d / f"{name}.f32").write_bytes(data)
        entries[name] = {"samples": len(samples), "sha256": sha(data)}
    if sha_override:
        for name, value in sha_override.items():
            entries[name]["sha256"] = value
    manifest = {
        "platform": manifest_platform or platform,
        "toolchain": {"name": "clang", "version": "23.1.4"},
        "components": entries,
    }
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


def write_all(root, components_by_platform):
    for platform, components in components_by_platform.items():
        write_platform(root, platform, components)


def write_expected(tmp_path, components):
    path = tmp_path / "hash_expected.json"
    path.write_text(json.dumps({"components": components}), encoding="utf-8")
    return path


def expected_for(samples, name=COMPONENT):
    return {name: {"samples": len(samples), "sha256": sha(encode(samples))}}


def write_tolerance(tmp_path, entries=(), bound=-100, source="AD-9; design log 2026-10-27 (j)",
                    raw=None):
    path = tmp_path / "hash_tolerance.json"
    if raw is None:
        raw = {"bound_dbfs": bound, "source": source, "entries": list(entries)}
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def write_design_log(tmp_path):
    path = tmp_path / "design-log.md"
    path.write_text(
        "# Design log\n\n"
        f"### {TEST_LOG_ENTRY}: Test tolerance\n\n"
        "Synthetic entry for the hash compare tests.\n\n"
        "### 2026-10-27 (j): Determinism scope\n\nText.\n",
        encoding="utf-8",
    )
    return path


def entry(platform, design_log=TEST_LOG_ENTRY, component=COMPONENT, drop_log=False):
    e = {"platform": platform, "component": component, "design_log": design_log,
         "reason": "synthetic test entry"}
    if drop_log:
        del e["design_log"]
    return e


def compare(tmp_path, root, expected, tolerance=None, design_log=None, *extra):
    tolerance = tolerance or write_tolerance(tmp_path)
    design_log = design_log or write_design_log(tmp_path)
    return run(COMPARE, root, "--expected", expected, "--tolerance", tolerance,
               "--design-log", design_log, *extra)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "artifacts"
    r.mkdir()
    return r


# ------------------------------------------------------------ exact mode


def test_all_match_passes(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 0, out


def test_component_without_expected_entry_passes_when_platforms_match(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    code, out = compare(tmp_path, root, write_expected(tmp_path, {}))
    assert code == 0, out


def test_one_lsb_flip_fails_naming_platforms_component_and_sample(tmp_path, root):
    samples = base_samples()
    flipped = list(samples)
    flipped[17] = from_bits(to_bits(flipped[17]) ^ 1)
    assert encode(flipped) != encode(samples)
    data = {p: {COMPONENT: samples} for p in PLATFORMS}
    data["windows-arm64"] = {COMPONENT: flipped}
    write_all(root, data)
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert_one_line_names(out, "windows-x64", "windows-arm64", COMPONENT, "sample 17")


def test_first_differing_sample_is_named(tmp_path, root):
    samples = base_samples()
    changed = list(samples)
    changed[40] = f32(changed[40] + 0.25)
    changed[50] = f32(changed[50] + 0.25)
    data = {p: {COMPONENT: samples} for p in PLATFORMS}
    data["android-arm64"] = {COMPONENT: changed}
    write_all(root, data)
    code, out = compare(tmp_path, root, write_expected(tmp_path, {}))
    assert code == 1, out
    assert_one_line_names(out, "windows-x64", "android-arm64", COMPONENT, "sample 40")


def test_all_wrong_alike_fails_against_expected(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    wrong = "0" * 64
    expected = write_expected(tmp_path, {COMPONENT: {"samples": len(samples), "sha256": wrong}})
    code, out = compare(tmp_path, root, expected)
    assert code == 1, out
    assert_one_line_names(out, COMPONENT, wrong, sha(encode(samples)))


def test_expected_sample_count_mismatch_fails(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    expected = write_expected(
        tmp_path, {COMPONENT: {"samples": len(samples) + 1, "sha256": sha(encode(samples))}})
    code, out = compare(tmp_path, root, expected)
    assert code == 1, out
    assert COMPONENT in out, out


def test_missing_platform_fails_naming_it(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS if p != "macos-arm64"})
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert "macos-arm64" in out, out


def test_platform_list_option_limits_the_compare(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in ("windows-x64", "windows-arm64")})
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)), None,
                        None, "--platforms", "windows-x64,windows-arm64")
    assert code == 0, out


def test_manifest_platform_must_match_directory(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS if p != "macos-arm64"})
    write_platform(root, "macos-arm64", {COMPONENT: samples}, manifest_platform="windows-arm64")
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert "macos-arm64" in out, out


def test_manifest_hash_must_match_data_file(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS if p != "android-arm64"})
    write_platform(root, "android-arm64", {COMPONENT: samples}, sha_override={COMPONENT: "a" * 64})
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert "android-arm64" in out, out


def test_missing_data_file_fails(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    (root / "hashprobe-windows-arm64" / f"{COMPONENT}.f32").unlink()
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert "windows-arm64" in out, out


def test_differing_component_sets_fail(tmp_path, root):
    samples = base_samples()
    extra = base_samples(32)
    data = {p: {COMPONENT: samples, "probe-extra": extra} for p in PLATFORMS}
    data["macos-arm64"] = {COMPONENT: samples}
    write_all(root, data)
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert_one_line_names(out, "macos-arm64", "probe-extra")


def test_extra_component_on_one_platform_fails(tmp_path, root):
    samples = base_samples()
    data = {p: {COMPONENT: samples} for p in PLATFORMS}
    data["android-arm64"] = {COMPONENT: samples, "probe-extra": base_samples(32)}
    write_all(root, data)
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 1, out
    assert_one_line_names(out, "android-arm64", "probe-extra")


def test_differing_sample_counts_fail_naming_both(tmp_path, root):
    samples = base_samples(64)
    data = {p: {COMPONENT: samples} for p in PLATFORMS}
    data["windows-arm64"] = {COMPONENT: samples[:63]}
    write_all(root, data)
    code, out = compare(tmp_path, root, write_expected(tmp_path, {}))
    assert code == 1, out
    assert_one_line_names(out, "64", "63")


# --------------------------------------------------------- tolerance mode


def tolerance_case(tmp_path, root, other_value, platform="macos-arm64", bound=-100,
                   reference_value=0.0, index=5):
    samples = base_samples()
    ref = list(samples)
    ref[index] = reference_value
    other = list(ref)
    other[index] = other_value
    data = {p: {COMPONENT: ref} for p in PLATFORMS}
    data[platform] = {COMPONENT: other}
    write_all(root, data)
    expected = write_expected(tmp_path, expected_for(ref))
    tolerance = write_tolerance(tmp_path, [entry(platform)], bound=bound)
    return ref, other, compare(tmp_path, root, expected, tolerance)


def test_tolerance_pass_below_bound(tmp_path, root):
    ref, other, (code, out) = tolerance_case(tmp_path, root, f32(10 ** (-100.5 / 20)))
    m = measured_dbfs(ref, other)
    assert m < -100 and abs(m - -100.5) < 0.01, m
    assert code == 0, out


def test_tolerance_zero_difference_passes(tmp_path, root):
    _, _, (code, out) = tolerance_case(tmp_path, root, 0.0)
    assert code == 0, out


def test_tolerance_fail_at_minus_90(tmp_path, root):
    ref, other, (code, out) = tolerance_case(tmp_path, root, f32(10 ** (-90 / 20)))
    m = measured_dbfs(ref, other)
    assert abs(m - -90) < 0.01, m
    assert code == 1, out
    assert_one_line_names(out, "-90", "-100")


def test_tolerance_fail_at_exactly_minus_100(tmp_path, root):
    # 1e-5 is not a float32, but this pair of float32 samples differs by a
    # float64 value whose 20*log10 is exactly -100.0: reference
    # 9.999999747378752e-06 (bits 925353388), other -2.526212474884132e-13
    # (bits 2861446799). Strictly below the bound is required, so it fails.
    ref_value = from_bits(925353388)
    other_value = from_bits(2861446799)
    ref, other, (code, out) = tolerance_case(
        tmp_path, root, other_value, reference_value=ref_value)
    assert measured_dbfs(ref, other) == -100.0
    assert code == 1, out
    assert "-100" in out, out


def test_bound_comes_from_the_tolerance_file(tmp_path, root):
    ref, other, (code, out) = tolerance_case(tmp_path, root, f32(10 ** (-90 / 20)), bound=-80)
    assert code == 0, out


def test_tolerance_entry_is_exempt_only_for_its_platform(tmp_path, root):
    samples = base_samples()
    changed = list(samples)
    changed[3] = f32(changed[3] + 1e-6)
    data = {p: {COMPONENT: samples} for p in PLATFORMS}
    data["macos-arm64"] = {COMPONENT: changed}
    data["windows-arm64"] = {COMPONENT: changed}
    write_all(root, data)
    tolerance = write_tolerance(tmp_path, [entry("macos-arm64")])
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)), tolerance)
    assert code == 1, out
    assert_one_line_names(out, "windows-arm64", COMPONENT, "sample 3")


def test_tolerance_entry_passes_alone(tmp_path, root):
    samples = base_samples()
    changed = list(samples)
    changed[3] = f32(changed[3] + 1e-6)
    data = {p: {COMPONENT: samples} for p in PLATFORMS}
    data["macos-arm64"] = {COMPONENT: changed}
    write_all(root, data)
    assert measured_dbfs(samples, changed) < -100
    tolerance = write_tolerance(tmp_path, [entry("macos-arm64")])
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)), tolerance)
    assert code == 0, out


@pytest.mark.parametrize("design_log, drop", [("", False), ("2026-11-02 (zy)", False), (None, True)],
                         ids=["empty", "unknown-heading", "missing"])
def test_uncited_tolerance_entry_fails(tmp_path, root, design_log, drop):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    tolerance = write_tolerance(tmp_path, [entry("macos-arm64", design_log=design_log or "",
                                                  drop_log=drop)])
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)), tolerance)
    assert code == 1, out
    assert_one_line_names(out, "macos-arm64", COMPONENT)


def test_cited_heading_must_be_a_heading_not_body_text(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    log = tmp_path / "design-log.md"
    log.write_text("# Design log\n\nSee 2026-11-02 (zz) for details.\n", encoding="utf-8")
    tolerance = write_tolerance(tmp_path, [entry("macos-arm64")])
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)),
                        tolerance, log)
    assert code == 1, out
    assert_one_line_names(out, "macos-arm64", COMPONENT)


def test_tolerance_entry_for_reference_platform_fails(tmp_path, root):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    tolerance = write_tolerance(tmp_path, [entry(REFERENCE)])
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)), tolerance)
    assert code == 1, out
    assert REFERENCE in out, out


@pytest.mark.parametrize(
    "raw",
    [
        {"source": "AD-9; design log 2026-10-27 (j)", "entries": []},
        {"bound_dbfs": "loud", "source": "AD-9; design log 2026-10-27 (j)", "entries": []},
        {"bound_dbfs": -100, "source": "", "entries": []},
        {"bound_dbfs": -100, "entries": []},
    ],
    ids=["no-bound", "non-numeric-bound", "empty-source", "no-source"],
)
def test_bad_tolerance_file_fails(tmp_path, root, raw):
    samples = base_samples()
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    tolerance = write_tolerance(tmp_path, raw=raw)
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)), tolerance)
    assert code == 1, out


# ------------------------------------------------------------ must-differ


def must_differ(tmp_path, samples, expected_components):
    d = write_platform(tmp_path / "mustfail", "android-arm64", {COMPONENT: samples})
    expected = write_expected(tmp_path, expected_components)
    return run(COMPARE, "--must-differ", d, "--expected", expected)


def test_must_differ_passes_when_hash_differs(tmp_path):
    samples = base_samples()
    other = list(samples)
    other[0] = from_bits(to_bits(other[0]) ^ 1)
    code, out = must_differ(tmp_path, other, expected_for(samples))
    assert code == 0, out
    assert sha(encode(other)) in out, out


def test_must_differ_fails_when_hash_matches(tmp_path):
    samples = base_samples()
    code, out = must_differ(tmp_path, samples, expected_for(samples))
    assert code == 1, out
    assert_one_line_names(out, COMPONENT, sha(encode(samples)))


def test_must_differ_fails_without_expected_entry(tmp_path):
    code, out = must_differ(tmp_path, base_samples(), {})
    assert code == 1, out


def test_must_differ_fails_when_manifest_disagrees_with_data(tmp_path):
    samples = base_samples()
    d = write_platform(tmp_path / "mustfail", "android-arm64", {COMPONENT: samples},
                       sha_override={COMPONENT: "b" * 64})
    expected = write_expected(tmp_path, expected_for(samples))
    code, out = run(COMPARE, "--must-differ", d, "--expected", expected)
    assert code == 1, out


# --------------------------------------------------------- hash_manifest


def write_check_json(tmp_path, name="clang", version="23.1.4"):
    path = tmp_path / "arcani_engine_check.json"
    path.write_text(json.dumps({"toolchain_name": name, "toolchain_version": version,
                                "source_dir": str(REPO_ROOT)}), encoding="utf-8")
    return path


def test_manifest_schema(tmp_path):
    probe = tmp_path / "probe"
    probe.mkdir()
    a = encode(base_samples(4096))
    b = encode(base_samples(10))
    (probe / "probe-arith.f32").write_bytes(a)
    (probe / "probe-other.f32").write_bytes(b)
    out_file = tmp_path / "out" / "m.json"
    out_file.parent.mkdir()
    code, out = run(MANIFEST, "--platform", "macos-arm64", "--check-json",
                    write_check_json(tmp_path, "AppleClang", "17.0.0.17000013"),
                    "--probe-dir", probe, "--out", out_file)
    assert code == 0, out
    manifest = json.loads(out_file.read_text(encoding="utf-8"))
    assert manifest == {
        "platform": "macos-arm64",
        "toolchain": {"name": "AppleClang", "version": "17.0.0.17000013"},
        "components": {
            "probe-arith": {"samples": 4096, "sha256": sha(a)},
            "probe-other": {"samples": 10, "sha256": sha(b)},
        },
    }


def test_manifest_default_output_path(tmp_path):
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "probe-arith.f32").write_bytes(encode(base_samples()))
    code, out = run(MANIFEST, "--platform", "windows-x64", "--check-json",
                    write_check_json(tmp_path), "--probe-dir", probe)
    assert code == 0, out
    manifest = json.loads((probe / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["components"]["probe-arith"]["samples"] == 64
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["components"]["probe-arith"]["sha256"])


def test_manifest_rejects_partial_sample(tmp_path):
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "probe-arith.f32").write_bytes(encode(base_samples()) + b"\x00")
    code, out = run(MANIFEST, "--platform", "windows-x64", "--check-json",
                    write_check_json(tmp_path), "--probe-dir", probe)
    assert code == 1, out
    assert "probe-arith" in out, out


def test_manifest_rejects_empty_probe_dir(tmp_path):
    probe = tmp_path / "probe"
    probe.mkdir()
    code, out = run(MANIFEST, "--platform", "windows-x64", "--check-json",
                    write_check_json(tmp_path), "--probe-dir", probe)
    assert code == 1, out


@pytest.mark.parametrize("content", [None, "not json", json.dumps({"toolchain_name": "clang"})],
                         ids=["missing", "garbage", "no-version"])
def test_manifest_rejects_bad_check_json(tmp_path, content):
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "probe-arith.f32").write_bytes(encode(base_samples()))
    check = tmp_path / "arcani_engine_check.json"
    if content is not None:
        check.write_text(content, encoding="utf-8")
    code, out = run(MANIFEST, "--platform", "windows-x64", "--check-json", check,
                    "--probe-dir", probe)
    assert code == 1, out


def test_manifests_from_the_tool_compare_clean(tmp_path, root):
    samples = base_samples()
    check = write_check_json(tmp_path)
    for p in PLATFORMS:
        d = root / f"hashprobe-{p}"
        d.mkdir()
        (d / f"{COMPONENT}.f32").write_bytes(encode(samples))
        code, out = run(MANIFEST, "--platform", p, "--check-json", check, "--probe-dir", d)
        assert code == 0, out
    code, out = compare(tmp_path, root, write_expected(tmp_path, expected_for(samples)))
    assert code == 0, out


# ------------------------------------------------------- real data files


def load_ci(name):
    path = REPO_ROOT / "ci" / name
    assert path.is_file(), f"missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_tolerance_file():
    data = load_ci("hash_tolerance.json")
    assert data["bound_dbfs"] == -100
    assert "AD-9" in data["source"] and "2026-10-27 (j)" in data["source"], data["source"]
    assert data["entries"] == []


def test_real_tolerance_source_names_a_design_log_heading():
    log = (REPO_ROOT / "docs" / "design-log.md").read_text(encoding="utf-8")
    assert re.search(r"^### 2026-10-27 \(j\): ", log, re.MULTILINE)


def test_real_expected_file_has_probe_arith():
    data = load_ci("hash_expected.json")
    probe = data["components"]["probe-arith"]
    assert probe["samples"] == 4096
    assert re.fullmatch(r"[0-9a-f]{64}", probe["sha256"]), probe


def test_defaults_use_repo_files(tmp_path, root):
    """With no file options, the real expected, tolerance, and design log files apply."""
    expected = load_ci("hash_expected.json")["components"]["probe-arith"]
    samples = base_samples(4096)
    write_all(root, {p: {COMPONENT: samples} for p in PLATFORMS})
    code, out = run(COMPARE, root, cwd=tmp_path)
    assert code == 1, out
    assert_one_line_names(out, COMPONENT, expected["sha256"], sha(encode(samples)))
