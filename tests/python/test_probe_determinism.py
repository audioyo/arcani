"""Hash probe block-size components and the expected entries for every component (Story 1.6).

Android runs no ctest, so the hash probe carries the block-size invariance
proof to every platform.

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- The probe source embeds the block sizes as exactly one array, written
  `constexpr std::size_t kBlockSizes[] = {1, 64, 512, 4096, 997};` (integer
  literals, comma separated, no suffixes). Its members, in order, equal the
  members of threshold row `block-sizes` (tests/tables/thresholds.tsv). A
  doctored copy of the source fails the comparison with a message naming
  both lists.
- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/stub-chain-blocks-44100.f32
  and OUT_DIR/stub-chain-blocks-48000.f32: the stub chain recipe of the
  stub-chain-<fs> components, compiled the same way, rendered through the
  public C API in successive arc_render calls whose frame counts cycle
  through kBlockSizes (the last call shortened to the frames left). The
  bytes must equal OUT_DIR/stub-chain-<fs>.f32 exactly.
- Every component the probe writes has an entry in ci/hash_expected.json,
  and every entry names a component the probe writes. On a windows-x64 host
  (the reference platform) each component's sha256 and sample count equal
  its entry; other hosts skip that one test, since the cross-platform job
  compares them.

The real build follows tests/python/test_probe_sine.py (platform preset,
ARCANI_BUILD_TESTS=OFF, only arcani-hashprobe, on Windows through
tools/dev.ps1). It skips only when cmake is not on PATH, or when Windows
application control blocks the probe binary (winerror 4551 or 1260).
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from assertions import row as table_row
from assertions.tables import load_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_SOURCE = REPO_ROOT / "tests" / "hashprobe" / "main.cpp"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"

SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
BLOCK_SIZES_ARRAY = re.compile(
    r"constexpr\s+std::size_t\s+kBlockSizes\s*\[\s*\]\s*=\s*\{([^}]*)\}\s*;")


def block_sizes_row():
    r = table_row("block-sizes")
    assert r.unit == "frames per call", r
    return [int(v) for v in r.values]


def embedded_block_sizes(text):
    found = BLOCK_SIZES_ARRAY.findall(text)
    assert len(found) == 1, f"expected exactly one kBlockSizes array in the probe source, found {len(found)}"
    members = [m.strip() for m in found[0].split(",") if m.strip()]
    assert all(re.fullmatch(r"[0-9]+", m) for m in members), members
    return [int(m) for m in members]


def check_embedded_sizes(text, row_sizes):
    embedded = embedded_block_sizes(text)
    assert embedded == row_sizes, (
        f"probe kBlockSizes {embedded} differs from row block-sizes {row_sizes}")


# ------------------------------------------------- without a build


def test_probe_embeds_the_block_sizes_row():
    check_embedded_sizes(PROBE_SOURCE.read_text(encoding="utf-8"), block_sizes_row())


def test_doctored_probe_sizes_fail_naming_both_lists():
    sizes = block_sizes_row()
    short = sizes[:-1]
    array = "constexpr std::size_t kBlockSizes[] = {" + ", ".join(map(str, short)) + "};"
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    doctored = BLOCK_SIZES_ARRAY.sub(array, text)
    if doctored == text:
        doctored = text + "\n" + array + "\n"
    with pytest.raises(AssertionError) as info:
        check_embedded_sizes(doctored, sizes)
    message = str(info.value)
    assert str(short) in message and str(sizes) in message, message


def test_probe_source_names_the_block_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"stub-chain-blocks-{fs}" in text, fs


# ------------------------------------------------------------- real build


def cmake_command(args):
    if sys.platform == "win32":
        return [
            "powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"),
            "cmake", *args,
        ]
    return [CMAKE, *args]


def run_cmake(args):
    result = subprocess.run(cmake_command(args), cwd=REPO_ROOT, capture_output=True, text=True,
                            timeout=600, env=os.environ.copy())
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(scope="module")
def probe_output(tmp_path_factory):
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    build = tmp_path_factory.mktemp("hashprobe-blocks") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-blocks-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=300)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_block_component_equals_one_call_component(probe_output, fs):
    one_call = probe_output / f"stub-chain-{fs}.f32"
    blocks = probe_output / f"stub-chain-blocks-{fs}.f32"
    assert one_call.is_file() and blocks.is_file(), sorted(p.name for p in probe_output.iterdir())
    a, b = one_call.read_bytes(), blocks.read_bytes()
    assert len(a) > 0 and len(a) == len(b), (len(a), len(b))
    if a != b:
        first = next(i for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4]) // 4
        pytest.fail(f"stub-chain-blocks-{fs} differs from stub-chain-{fs}, first at sample {first}")


def probe_components(out_dir):
    return {p.stem: p.read_bytes() for p in out_dir.glob("*.f32")}


def test_every_probe_component_has_an_expected_entry(probe_output):
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    written = set(probe_components(probe_output))
    assert written == set(expected), (
        f"probe writes {sorted(written)}, ci/hash_expected.json has {sorted(expected)}")


def is_windows_x64():
    return sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64")


@pytest.mark.skipif(not is_windows_x64(), reason="the reference platform is windows-x64")
def test_windows_x64_probe_matches_every_expected_entry(probe_output):
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    problems = []
    for name, data in sorted(probe_components(probe_output).items()):
        entry = expected.get(name)
        found = hashlib.sha256(data).hexdigest()
        if entry is None:
            problems.append(f"{name}: no expected entry (sha256 {found})")
            continue
        if entry.get("sha256") != found or entry.get("samples") != len(data) // 4:
            problems.append(f"{name}: expected sha256 {entry.get('sha256')} ({entry.get('samples')} "
                            f"samples), found {found} ({len(data) // 4} samples)")
    assert not problems, "\n".join(problems)
