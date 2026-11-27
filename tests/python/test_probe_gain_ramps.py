"""Hash probe gain ramp components (Story 4.4; docs/signal-spec.md, Gain ramps,
Vectors: gain fixtures).

Contract with the probe (tests/hashprobe/main.cpp, target arcani-hashprobe):

- `arcani-hashprobe OUT_DIR` also writes OUT_DIR/gain-ramps-44100.f32 and
  OUT_DIR/gain-ramps-48000.f32: the four gain ramp render fixtures
  (gain_constants render_fixtures, in that order) embedded in the probe
  (it reads no file) with the values of the fixture files, each compiled
  in measure mode at that rate; for each fixture, the windows of
  gain_windows probe_starts in order, each of probe_window_frames frames,
  rendered by arc_seek and one arc_render, output only, interleaved stereo,
  each binary64 sample converted to float32, windows one after another.
- Each window matches the Python reference output (reference.stub_chain
  .render of the fixture file with start and frames) within row
  `reference-match` per channel wherever both sides are above row
  `reference-match-min-level`, and its largest difference is below row
  `reference-match` everywhere (a fade to silence leaves windows of exact
  zeros).
- The earlier components keep their bytes.
- The expected entries `gain-ramps-44100` and `gain-ramps-48000` (scope
  `engine`) are pinned from the dev PC probe and confirmed by the next full
  run; until then that test fails.

The real build follows tests/python/test_probe_loop.py and skips only when
cmake is not on PATH, or when Windows application control blocks the probe
binary (winerror 4551 or 1260).
"""

import json
import os
import subprocess
import sys

import numpy as np
import pytest

import gain_common as gc
from assertions import row as table_row

REPO_ROOT = gc.REPO_ROOT
PROBE_SOURCE = REPO_ROOT / "tests" / "hashprobe" / "main.cpp"
EXPECTED = REPO_ROOT / "ci" / "hash_expected.json"
SAMPLE_RATES = gc.sample_rates()
RENDER_FIXTURES = gc.constants()["render_fixtures"]
EARLIER_COMPONENTS = ("probe-arith", "sine-", "stub-chain-", "stub-chain-blocks-", "theta-envelopes-",
                      "gamma-uncoupled-", "gamma-swell-", "binaural-cycle-", "gamma-bursts-", "rate-curves-",
                      "loop-")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"


def windows(fs):
    """[(fixture, start, frames)] in component order."""
    out = []
    for fixture in RENDER_FIXTURES:
        v = gc.window(fixture, fs)
        out += [(fixture, int(s), int(v["probe_window_frames"])) for s in v["probe_starts"]]
    return out


def component_samples(fs):
    return sum(2 * frames for _, _, frames in windows(fs))


# ------------------------------------------------- without a build


def test_probe_windows_follow_the_window_rule():
    for fs in SAMPLE_RATES:
        for fixture in RENDER_FIXTURES:
            v = gc.window(fixture, fs)
            end = int(v["end_frame"])
            want = [gc.window_start(e, fs, end)[0] for e in gc.edges(fixture, fs)]
            assert [int(s) for s in v["probe_starts"]] == want, (fixture, fs)
            assert int(v["probe_window_frames"]) == gc.seconds_to_samples(float(gc.constants()["probe_window_s"]), fs)


def test_probe_source_names_the_gain_ramp_components():
    text = PROBE_SOURCE.read_text(encoding="utf-8")
    for fs in SAMPLE_RATES:
        assert f"gain-ramps-{fs}" in text, fs
    assert "arc_seek" in text
    # The four fixtures are embedded: each carries a gain member, and the
    # master members of the two master fades.
    assert text.count('"gain') + text.count('\\"gain') >= 4
    assert '"master' in text or '\\"master' in text


def test_expected_entries_name_the_gain_ramp_components():
    components = json.loads(EXPECTED.read_text(encoding="utf-8"))["components"]
    for fs in SAMPLE_RATES:
        entry = components.get(f"gain-ramps-{fs}")
        assert entry is not None, f"no ci/hash_expected.json entry gain-ramps-{fs} (pin from the dev PC probe)"
        assert entry.get("scope") == "engine", entry
        assert entry.get("samples") == component_samples(fs), entry
    assert components["gain-ramps-44100"]["sha256"] != components["gain-ramps-48000"]["sha256"]


# ------------------------------------------------------------- real build


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [gc.common.CMAKE, *args]


def run_cmake(args):
    result = subprocess.run(cmake_command(args), cwd=REPO_ROOT, capture_output=True, text=True,
                            timeout=600, env=os.environ.copy())
    return result.returncode, result.stdout + result.stderr


@pytest.fixture(scope="module")
def probe_output(tmp_path_factory):
    if gc.common.CMAKE is None:
        pytest.skip("cmake is not on PATH")
    build = tmp_path_factory.mktemp("hashprobe-gain") / "build"
    code, out = run_cmake(["--preset", PRESET, "-B", str(build), "-DARCANI_BUILD_TESTS=OFF"])
    if code == 0:
        code2, out2 = run_cmake(["--build", str(build), "--target", "arcani-hashprobe"])
        code, out = code2, out + out2
    assert code == 0, out
    exe = build / "tests" / "hashprobe" / (
        "arcani-hashprobe.exe" if sys.platform == "win32" else "arcani-hashprobe")
    assert exe.is_file(), f"probe binary not at {exe}"
    out_dir = tmp_path_factory.mktemp("hashprobe-gain-out")
    try:
        result = subprocess.run([str(exe), str(out_dir)], capture_output=True, text=True, timeout=600)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked the probe (winerror {e.winerror})")
        raise
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_gain_ramp_component_windows_match_the_reference(probe_output, fs):
    sc = gc.stub_chain()
    match = gc.reference_match()
    threshold = table_row("reference-match").value
    floor = table_row("reference-match-min-level").value
    path = probe_output / f"gain-ramps-{fs}.f32"
    assert path.is_file(), sorted(p.name for p in probe_output.iterdir())
    data = np.fromfile(path, dtype="<f4").astype(np.float64)
    assert data.size == component_samples(fs), data.size
    failed = []
    at = 0
    for fixture, start, frames in windows(fs):
        segment = data[at:at + 2 * frames]
        at += 2 * frames
        want = sc.render(gc.FIXTURES_VALID / fixture, fs, start=start, frames=frames)["output"]
        name = f"{fixture} {fs} from {start}"
        if not match.difference_dbfs(segment, want) < threshold:
            failed.append(f"{name}: difference {match.difference_dbfs(segment, want)} dBFS")
        for c in (0, 1):
            e, r = segment[c::2], want[c::2]
            if match.level_dbfs(e) >= floor and match.level_dbfs(r) >= floor:
                a = match.match(f"{name} {c}", e, r)
                if a["result"] != "pass":
                    failed.append(str(a))
    assert not failed, failed


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_earlier_components_are_still_written(probe_output, fs):
    names = {p.stem for p in probe_output.iterdir() if p.suffix == ".f32"}
    for prefix in EARLIER_COMPONENTS:
        want = prefix if prefix == "probe-arith" else f"{prefix}{fs}"
        assert want in names, (want, sorted(names))
