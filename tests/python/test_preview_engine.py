"""arcani-render --preview against the engine output, the vectors, and the
Python reference (Story 3.3; docs/signal-spec.md, Preview).

Contract with arcani-render (spec Implementation Notes, Command line): with
`--preview` the WAV holds frames [0, F) of the recipe's own render, every
sample quantize_24(out * g) with g = 10^(P/20) / max(n_max, 1), P row
preview-peak-level; the report has `frames` F, the plan's own `loop` and
`spacing` blocks, then `preview` {signed false, peak_dbfs, layers_per_ear,
gain, seconds F / fs} before `determinism_key`, which is the recipe's own.

`out` comes from the tap dump (`--window START FRAMES` and `--output-only`),
the engine's render of the recipe with no preview. g is the gain vector
bits for P and the recipe's layer count. The analytic peak bound: every
sample at most 10^(P/20) of full scale, within half a 24-bit step.

One full-length preview only: Focus at 44.1 kHz (210 s), checked in three
0.5 s windows (around the opening end O, around the first body seam O + B,
and the last 0.5 s) and for its peak over the whole file. Short renders at
both rates: theta-gamma-uncoupled.json (10 s, so F = N) byte for byte over
the whole file, and minimal-no-layers.json (600 s, trimmed to 180 s of
silence). A repeat render is byte-identical (WAV, and the report up to its assertions).

Must-fails, doctored here: an expected WAV with one byte flipped, g times
1.001, and a window one frame late, each caught.

The tests skip only when cmake is not on PATH, or when Windows application
control blocks a binary (OSError winerror 4551 or 1260).
"""

import json

import numpy as np
import pytest

import preview_common as common
import spacing_common

SAMPLE_RATES = (44100, 48000)
FOCUS = common.constants()["starter_fixtures"][0]
SHORT = "theta-gamma-uncoupled.json"
SILENT = "minimal-no-layers.json"
HASHES = json.loads((common.REPO_ROOT / "tests" / "data" / "recipe_hash_vectors.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def render():
    return common.build("arcani-render", common.RENDER)


@pytest.fixture(scope="module")
def tapdump():
    return common.build("arcani-tapdump", common.TAPDUMP)


def preview(render, fixture, fs, out_dir, extra=()):
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "x.wav"
    r = common.run(render, [common.FIXTURES_VALID / fixture, "--out", wav, "--rate", fs, "--preview", *extra])
    assert r.returncode == 0, r.stdout + r.stderr
    report_text = (out_dir / "x.report.json").read_text(encoding="utf-8")
    return wav, report_text, json.loads(report_text)


def version(render):
    r = common.run(render, ["--version"])
    assert r.returncode == 0
    return r.stdout.strip()


def gain_for(recipe):
    n = max(common.layers_per_ear(recipe).values())
    return common.from_bits(common.gain_row(common.peak_dbfs(), n)["gain_bits"]), n


def bound_q():
    """The analytic peak bound in 24-bit steps: 10^(P/20) of full scale plus half a step."""
    return common.amplitude() * float(2 ** 23) + 0.5


def preview_block(peak, layers, gain, seconds):
    s = spacing_common.shortest
    return ("  \"preview\": {\n    \"signed\": false,\n"
            f"    \"peak_dbfs\": {s(peak)},\n    \"layers_per_ear\": {layers},\n"
            f"    \"gain\": {s(gain)},\n    \"seconds\": {s(seconds)}\n  }},\n")


def member_problems(member, peak, layers, gain, seconds):
    p = []
    if list(member) != ["signed", "peak_dbfs", "layers_per_ear", "gain", "seconds"]:
        return [f"preview keys {list(member)}"]
    if member["signed"] is not False:
        p.append("signed is not false")
    if member["peak_dbfs"] != peak:
        p.append(f"peak_dbfs {member['peak_dbfs']}")
    if member["layers_per_ear"] != layers:
        p.append(f"layers_per_ear {member['layers_per_ear']}")
    if common.bits(member["gain"]) != common.bits(gain):
        p.append(f"gain {member['gain']}")
    if common.bits(member["seconds"]) != common.bits(seconds):
        p.append(f"seconds {member['seconds']}")
    return p


def key_problems(report, fixture, fs, engine_version):
    key = report["determinism_key"]
    want = {"recipe_hash": HASHES[fixture], "asset_hashes": [], "engine_version": engine_version, "sample_rate": fs}
    return [] if key == want else [f"determinism_key {key}, want {want}"]


# ------------------------------------------------------------ the one full-length preview


@pytest.fixture(scope="module")
def focus_preview(render, tmp_path_factory):
    fs = SAMPLE_RATES[0]
    wav, text, report = preview(render, FOCUS, fs, tmp_path_factory.mktemp("preview-focus"))
    return fs, wav, text, report


def test_focus_preview_frames_report_and_key(render, focus_preview):
    fs, wav, text, report = focus_preview
    v = common.frame_row(FOCUS, fs)
    recipe = common.load_fixture(FOCUS)
    _, frames, rate = common.wav_layout(wav)
    assert rate == fs
    assert frames == int(v["preview_frames"])
    assert report["frames"] == frames
    assert report["mode"] == "measure"
    # The loop block is the plan's own: every seam up to N, past F too.
    o, first, n = int(v["opening_end_frame"]), int(v["first_seam_frame"]), int(v["end_frame"])
    b = first - o
    seams = []
    k = 1
    while o + k * b < n:
        seams.append(o + k * b)
        k += 1
    assert report["loop"] == {"opening_end_frame": o, "seam_frames": seams, "end_frame": n}
    assert any(s > frames for s in seams)
    assert "spacing" in report
    # The preview member against the vectors, and its bytes and place.
    g, layers = gain_for(recipe)
    assert layers == v["layers_max"]
    assert common.bits(g) == v["gain_bits"]
    assert not member_problems(report["preview"], common.peak_dbfs(), layers, g, float(v["seconds"]))
    block = preview_block(common.peak_dbfs(), layers, g, float(v["seconds"]))
    assert block in text
    assert text.index(block) + len(block) == text.index("  \"determinism_key\": {")
    assert text.index("\"spacing\"") < text.index(block)
    assert list(report) == ["engine_version", "seed", "sample_rate", "mode", "frames", "loop", "spacing", "preview",
                            "determinism_key", "assertions"]
    # The key is the recipe's own, as a render without --preview writes it.
    assert not key_problems(report, FOCUS, fs, version(render))


def test_focus_preview_member_equals_the_reference(focus_preview):
    fs, _, _, report = focus_preview
    ref = common.reference_preview()
    want = ref.report_member(common.load_fixture(FOCUS), fs)
    assert not member_problems(report["preview"], want["peak_dbfs"], want["layers_per_ear"], want["gain"],
                               want["seconds"])
    assert report["frames"] == ref.preview_frames(common.load_fixture(FOCUS), fs)
    assert (report["loop"]["opening_end_frame"], report["loop"]["seam_frames"][0]) == \
        ref.seams_heard(common.load_fixture(FOCUS), fs)


def _focus_windows(fs):
    v = common.frame_row(FOCUS, fs)
    half = fs // 4
    o, first, f = int(v["opening_end_frame"]), int(v["first_seam_frame"]), int(v["preview_frames"])
    return [("opening end", o - half, 2 * half), ("first body seam", first - half, 2 * half),
            ("last 0.5 s", f - 2 * half, 2 * half)]


def test_focus_preview_windows_are_the_engine_output_times_g(tapdump, focus_preview, tmp_path):
    fs, wav, _, _ = focus_preview
    g, _ = gain_for(common.load_fixture(FOCUS))
    recipe_path = common.FIXTURES_VALID / FOCUS
    for label, start, frames in _focus_windows(fs):
        out = common.tapdump_window(tapdump, recipe_path, fs, start, frames, tmp_path / label.replace(" ", "-"))
        want = common.preview_samples(out, g)
        got = common.read_frames(wav, start, frames)
        assert np.count_nonzero(want) > 0, f"{label}: the window is silent"
        assert np.array_equal(got, want), f"{label}: {np.count_nonzero(got != want)} samples differ"
        # Must-fail: g times 1.001, and the window one frame late, are caught.
        assert not np.array_equal(got, common.preview_samples(out, g * 1.001)), label
        late = common.read_frames(wav, start + 1, frames - 1)
        assert not np.array_equal(late, want[: 2 * (frames - 1)]), label
        # Must-fail: the plain render (no gain) is not the preview, and breaks the peak bound.
        plain = common.quantize_24(out)
        assert not np.array_equal(got, plain), label
        assert np.max(np.abs(plain.astype(np.int64))) > bound_q(), label
        assert np.max(np.abs(got.astype(np.int64))) <= bound_q(), label


def test_focus_preview_peak_stays_under_the_analytic_bound(focus_preview):
    fs, wav, _, _ = focus_preview
    _, frames, _ = common.wav_layout(wav)
    samples = common.read_frames(wav, 0, frames)
    peak = int(np.max(np.abs(samples.astype(np.int64))))
    assert 0 < peak <= bound_q(), (peak, bound_q())


# ------------------------------------------------------------ short renders


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_short_preview_is_the_whole_session_times_g_byte_for_byte(render, tapdump, fs, tmp_path):
    recipe = common.load_fixture(SHORT)
    g, layers = gain_for(recipe)
    wav, text, report = preview(render, SHORT, fs, tmp_path / "a")
    out = common.tapdump_whole(tapdump, common.FIXTURES_VALID / SHORT, fs, tmp_path / "dump")
    n = out.size // 2
    _, frames, _ = common.wav_layout(wav)
    assert frames == n, "a session shorter than the preview is previewed whole (F = N)"
    header, _, _ = common.wav_layout(wav)
    data = wav.read_bytes()[header:]
    want = common.data_bytes(common.preview_samples(out, g))
    assert np.count_nonzero(common.preview_samples(out, g)) > 0
    assert data == want
    assert report["frames"] == n
    assert "loop" not in report
    assert not member_problems(report["preview"], common.peak_dbfs(), layers, g, n / fs)
    assert not key_problems(report, SHORT, fs, version(render))
    peak = int(np.max(np.abs(common.read_frames(wav, 0, frames).astype(np.int64))))
    assert 0 < peak <= bound_q()
    # Must-fail: one flipped byte, and g times 1.001, are caught.
    flipped = bytearray(want)
    flipped[len(flipped) // 2] ^= 0x01
    assert data != bytes(flipped)
    assert data != common.data_bytes(common.preview_samples(out, g * 1.001))
    # A repeat render is byte-identical, WAV and report.
    # The report too, apart from the render speed assertion, which holds a
    # measured time on the reference machine.
    wav2, text2, report2 = preview(render, SHORT, fs, tmp_path / "b")
    assert wav2.read_bytes() == wav.read_bytes()
    assert text2[:text2.index("  \"assertions\"")] == text[:text.index("  \"assertions\"")]
    assert [a["name"] for a in report2["assertions"]] == [a["name"] for a in report["assertions"]]


@pytest.mark.parametrize("fs", SAMPLE_RATES)
def test_no_layer_preview_is_l_frames_of_silence(render, tapdump, fs, tmp_path):
    recipe = common.load_fixture(SILENT)
    assert max(common.layers_per_ear(recipe).values()) == 0
    g, layers = gain_for(recipe)
    wav, _, report = preview(render, SILENT, fs, tmp_path / "a")
    header, frames, _ = common.wav_layout(wav)
    # L from row preview-length, by the whole-sample product (180 s is whole at both rates).
    l_frames = int(common.length_s() * fs)
    assert l_frames == common.length_s() * fs
    assert frames == l_frames
    assert report["frames"] == l_frames
    out = common.tapdump_window(tapdump, common.FIXTURES_VALID / SILENT, fs, 0, fs, tmp_path / "dump")
    assert not np.any(common.preview_samples(out, g))
    data = wav.read_bytes()[header:]
    assert len(data) == 6 * l_frames
    assert data.count(0) == len(data), "a recipe with no layer previews as silence"
    assert not member_problems(report["preview"], common.peak_dbfs(), layers, g, l_frames / fs)
    assert report["preview"]["layers_per_ear"] == 0
