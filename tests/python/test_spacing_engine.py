"""Engine spacing rule from the tap dump and the command-line renderer against
the vectors and the Python reference (Story 3.2).

Contract with the tap dump (tests/tapdump/main.cpp, target arcani-tapdump;
Story 3.2 spec, Implementation Notes):

- `arcani-tapdump RECIPE RATE OUT_DIR --spacing [--mute left|right]`
  compiles in measure mode, renders nothing, writes OUT_DIR/spacing.tsv:
  the header `ear<TAB>has_pair<TAB>min_distance_hz<TAB>margin_hz<TAB>component_1<TAB>component_2`,
  then one line per ear (left, then right), has_pair 0 or 1, the doubles
  as %.17g, 0 in every field of an ear without a pair, LF line ends. It
  prints `arcani-tapdump: spacing` and exits 0.
- A rejected recipe prints the existing rejected line with ` detail=<detail>`
  appended when the detail is not empty, writes no spacing.tsv, and exits 1.
  Usage errors exit 2.

Contract with arcani-render (cli/main.cpp): a spacing rejection exits 1,
writes no WAV and no report, and prints
`rejected: parameter=P value=V rule=R limit=L detail=D` on stderr; a report
of a recipe with a pair holds the spacing block (Spacing, Report), each
ear's numbers within row component-frequency-error of the reference and its
pair named by the table rows; a recipe without a pair writes no spacing
member.

Every vector case, at both sample rates: the engine's margins equal the
vectors and the reference within row component-frequency-error, the table
indices are equal, and spacing.tsv is the same bytes at both rates. No audio
is rendered apart from three 10 s CLI renders.

The tests skip only when cmake is not on PATH, or when Windows application
control blocks a binary (OSError winerror 4551 or 1260).
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import spacing_common as common
from assertions.tables import load_tables

REPO_ROOT = common.REPO_ROOT
CMAKE = shutil.which("cmake")
if sys.platform == "win32":
    PRESET = "windows-clang-cl"
elif sys.platform == "darwin":
    PRESET = "macos-appleclang"
else:
    PRESET = "linux-clang"
EXE = ".exe" if sys.platform == "win32" else ""
TAPDUMP = REPO_ROOT / "build" / PRESET / "tests" / "tapdump" / f"arcani-tapdump{EXE}"
RENDER = REPO_ROOT / "build" / PRESET / "cli" / f"arcani-render{EXE}"
SAMPLE_RATES = [int(v) for v in load_tables()["sample-rates"].values]
HEADER = "ear\thas_pair\tmin_distance_hz\tmargin_hz\tcomponent_1\tcomponent_2"
DUMP_FILES = ("out.f64", "theta.f64", "gamma.f64", "bus.f64", "join.f64", "master.f64", "components.tsv")


def cmake_command(args):
    if sys.platform == "win32":
        return ["powershell", "-NoProfile", "-File", str(REPO_ROOT / "tools" / "dev.ps1"), "cmake", *args]
    return [CMAKE, *args]


def build(target, path):
    if CMAKE is None:
        pytest.skip("cmake is not on PATH")
    result = subprocess.run(cmake_command(["--build", "--preset", PRESET, "--target", target]),
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=900, env=os.environ.copy())
    assert result.returncode == 0, (
        f"building {target} failed (configure the {PRESET} preset first):\n{result.stdout}{result.stderr}")
    assert path.is_file(), f"{target} not at {path}"
    return path


@pytest.fixture(scope="module")
def tapdump():
    return build("arcani-tapdump", TAPDUMP)


@pytest.fixture(scope="module")
def render():
    return build("arcani-render", RENDER)


def run(exe, args, timeout=120):
    try:
        return subprocess.run([str(exe), *[str(a) for a in args]], capture_output=True, text=True, timeout=timeout)
    except OSError as e:
        if sys.platform == "win32" and getattr(e, "winerror", None) in (4551, 1260):
            pytest.skip(f"Windows application control blocked {exe.name} (winerror {e.winerror})")
        raise


def mute_args(mute):
    return [] if mute == "none" else ["--mute", mute]


def parse_tsv(data):
    """{ear: None or (min_distance_hz, margin_hz, component_1, component_2)} of spacing.tsv bytes."""
    assert b"\r" not in data, "spacing.tsv has a CR"
    text = data.decode("utf-8")
    assert text.endswith("\n"), "spacing.tsv does not end with LF"
    lines = text[:-1].split("\n")
    assert lines[0] == HEADER, lines[0]
    assert len(lines) == 3, lines
    out = {}
    for ear, raw in zip(common.EARS, lines[1:]):
        f = raw.split("\t")
        assert len(f) == 6 and f[0] == ear, raw
        assert f[1] in ("0", "1"), raw
        for t in f[2:4]:
            assert "%.17g" % float(t) == t, (t, "not %.17g")
        for t in f[4:6]:
            assert re.fullmatch(r"[0-9]+", t), raw
        values = (float(f[2]), float(f[3]), int(f[4]), int(f[5]))
        if f[1] == "0":
            assert values == (0.0, 0.0, 0, 0) and not f[2].startswith("-") and not f[3].startswith("-"), raw
            out[ear] = None
        else:
            out[ear] = values
    return out


def dump_spacing(exe, recipe_path, fs, out_dir, mute="none"):
    out_dir.mkdir(parents=True, exist_ok=True)
    result = run(exe, [recipe_path, fs, out_dir, "--spacing", *mute_args(mute)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "arcani-tapdump: spacing", result.stdout
    data = (out_dir / "spacing.tsv").read_bytes()
    for name in DUMP_FILES:
        assert not (out_dir / name).exists(), f"--spacing wrote {name}"
    return parse_tsv(data), data


def write_case(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{re.sub(r'[^A-Za-z0-9.-]', '_', name)}.json"
    path.write_bytes(common.case(name)["recipe"].encode("utf-8"))
    return path


def ear_problems(got, m, reference):
    """Problems of one ear of spacing.tsv against the margin vector and the reference SpacingPair."""
    if m["pairs"] == 0:
        return [] if got is None and reference is None else [f"a pair in an ear with none: {got}"]
    if got is None:
        return ["no pair, the vectors have one"]
    tol = common.frequency_error()
    distance, margin, c1, c2 = got
    problems = []
    for name, value, want in (("min distance", distance, common.ideal(m["distance"])),
                              ("margin", margin, common.ideal(m["margin"])),
                              ("min distance (reference)", distance, reference.min_distance_hz),
                              ("margin (reference)", margin, reference.margin_hz)):
        if not abs(value - want) < tol:
            problems.append(f"{name} {value!r}, want {want!r} (row {common.FREQUENCY_ROW})")
    if margin != distance - common.rule_hz():
        problems.append("margin is not one subtraction of row spacing-rule")
    if margin < 0.0:
        problems.append("a compiled plan has a margin below 0")
    if (c1, c2) != (int(m["index_1"]), int(m["index_2"])) or (c1, c2) != (reference.component_1,
                                                                        reference.component_2):
        problems.append(f"components {c1}, {c2}, want {m['index_1']}, {m['index_2']}")
    return problems


# ------------------------------------------------------------ format checks without the engine


def test_must_fail_the_tsv_format_check_catches_a_broken_file():
    good = (HEADER + "\nleft\t1\t50\t0\t0\t1\nright\t0\t0\t0\t0\t0\n").encode("utf-8")
    assert parse_tsv(good) == {"left": (50.0, 0.0, 0, 1), "right": None}
    for bad in (good.replace(b"\n", b"\r\n"),
                good[:-1],
                good.replace(b"ear\t", b"Ear\t"),
                good.replace(b"\t50\t", b"\t50.0\t"),
                good.replace(b"right\t0\t0", b"right\t0\t1"),
                good.replace(b"left\t1", b"left\t2"),
                good.replace(b"right\t", b"left\t"),
                good.replace(b"\t0\t1\n", b"\t0\t1.5\n"),
                good + b"extra\n"):
        with pytest.raises(AssertionError):
            parse_tsv(bad)


def test_must_fail_the_ear_comparison_catches_doctored_values():
    name = "spacing-exactly-50hz"
    m = common.margin(name, "left")
    reference = common.reference_spacing().spacing_margins(common.case_recipe(name))["left"]
    good = (common.rule_hz(), 0.0, int(m["index_1"]), int(m["index_2"]))
    assert ear_problems(good, m, reference) == []
    ft = common.frequency_error()
    for bad in ((common.rule_hz() + 2 * ft, 2 * ft, good[2], good[3]),
                (common.rule_hz(), ft / 2, good[2], good[3]),
                (common.rule_hz(), 0.0, good[2], good[3] + 1),
                None):
        assert ear_problems(bad, m, reference), bad


# ------------------------------------------------------------ the engine


@pytest.mark.parametrize("name", common.case_names())
def test_engine_spacing_equals_the_vectors_and_the_reference(name, tapdump, tmp_path):
    c = common.case(name)
    path = write_case(tmp_path, name)
    out = tmp_path / "out"
    out.mkdir()
    if c["result"] == "rejected":
        for fs in SAMPLE_RATES:
            result = run(tapdump, [path, fs, out, "--spacing", *mute_args(c["mute"])])
            assert result.returncode == 1, (result.stdout, result.stderr)
            assert not (out / "spacing.tsv").exists()
            line = result.stderr.strip()
            m = re.fullmatch(r"arcani-tapdump: rejected: parameter=(\S*) value=(\S*) rule=(\S*) "
                             r"limit=(.*?) detail=(.*)", line)
            assert m, line
            problems = common.error_problems(*m.groups(), c)
            assert not problems, f"{name} {fs}:\n" + "\n".join(problems)
        return
    reference = common.reference_spacing().spacing_margins(common.case_recipe(name), c["mute"])
    data_by_rate = {}
    for fs in SAMPLE_RATES:
        got, data = dump_spacing(tapdump, path, fs, tmp_path / f"out-{fs}", c["mute"])
        for ear in common.EARS:
            problems = ear_problems(got[ear], common.margin(name, ear), reference[ear])
            assert not problems, f"{name} {fs} {ear}:\n" + "\n".join(problems)
        data_by_rate[fs] = data
    assert len(set(data_by_rate.values())) == 1, f"{name}: spacing.tsv differs between sample rates"


@pytest.mark.parametrize("fixture", common.constants()["fixtures"])
def test_engine_spacing_of_the_story_fixtures(fixture, tapdump, tmp_path):
    name = fixture.removesuffix(".json")
    c = common.case(name)
    fs = SAMPLE_RATES[-1]
    if c["result"] == "rejected":
        out = tmp_path / "out"
        out.mkdir()
        result = run(tapdump, [common.FIXTURES_VALID / fixture, fs, out, "--spacing"])
        assert result.returncode == 1, (result.stdout, result.stderr)
        assert result.stderr.strip() == (
            "arcani-tapdump: rejected: parameter=/binaural/carrier_left_hz value=4 rule=spacing_rule "
            f"limit={common.limit_text()} detail=right ear: gamma_pac (-1, 0, 0) at 260 Hz and binaural "
            "(0, 0, 1) at 256 Hz; whole session")
        assert not (out / "spacing.tsv").exists()
        return
    got, _ = dump_spacing(tapdump, common.FIXTURES_VALID / fixture, fs, tmp_path / "out")
    reference = common.reference_spacing().spacing_margins(common.load_fixture(fixture))
    for ear in common.EARS:
        assert got[ear] is not None, (fixture, ear)
        problems = ear_problems(got[ear], common.margin(name, ear), reference[ear])
        assert not problems, f"{fixture} {ear}:\n" + "\n".join(problems)


def test_engine_spacing_mode_honors_the_muted_ear_and_refuses_bad_arguments(tapdump, tmp_path):
    fs = SAMPLE_RATES[0]
    sleep = common.FIXTURES_VALID / "starter-sleep-layers.json"
    full, _ = dump_spacing(tapdump, sleep, fs, tmp_path / "none")
    assert full["left"] is not None and full["right"] is not None
    recipe = common.load_fixture("starter-sleep-layers.json")
    tol = common.frequency_error()
    for mute, other in (("left", "right"), ("right", "left")):
        got, _ = dump_spacing(tapdump, sleep, fs, tmp_path / mute, mute)
        assert got[mute] is None, mute
        assert got[other] is not None, mute
        distance, margin, c1, c2 = got[other]
        # Muting removes rows, so the other ear's distances are those of the full table...
        assert (distance, margin) == full[other][:2], mute
        # ...while its indices are positions in the muted table (Spacing, Table index): the reference's.
        want = common.reference_spacing().spacing_margins(recipe, mute)[other]
        assert want is not None, mute
        assert (c1, c2) == (want.component_1, want.component_2), (mute, got[other], want)
        assert abs(distance - want.min_distance_hz) < tol, (mute, got[other], want)
        assert abs(margin - want.margin_hz) < tol, (mute, got[other], want)
    for args in (["--spacing", "--mute", "middle"], ["--spacing", "--mute"], ["--spacing", "extra"]):
        result = run(tapdump, [sleep, fs, tmp_path / "usage", *args])
        assert result.returncode == 2, (args, result.stdout, result.stderr)
        assert not (tmp_path / "usage" / "spacing.tsv").exists(), args
    # Another rule's rejection keeps its old line: no detail suffix.
    out = tmp_path / "triangle"
    out.mkdir()
    result = run(tapdump, [common.FIXTURES_VALID / "gamma-carrier-wave-triangle.json", fs, out, "--spacing"])
    assert result.returncode == 1
    assert "non-sine carrier not modeled" in result.stderr and " detail=" not in result.stderr, result.stderr


# ------------------------------------------------------------ the command-line renderer


def test_cli_spacing_rejection_writes_nothing_and_prints_the_detail(render, tmp_path):
    fixture = common.constants()["must_fail_fixture"]
    wav = tmp_path / "x.wav"
    result = run(render, [common.FIXTURES_VALID / fixture, "--out", wav])
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert list(tmp_path.iterdir()) == []
    c = common.case(fixture.removesuffix(".json"))
    m = re.fullmatch(r"rejected: parameter=(\S*) value=(\S*) rule=(\S*) limit=(.*?) detail=(.*)",
                     result.stderr.strip())
    assert m, result.stderr
    assert not common.error_problems(*m.groups(), c)


@pytest.mark.parametrize("name", ("spacing-exactly-50hz", "spacing-sweep-together", "ad5-swell-cycle-270deg"))
def test_cli_report_spacing_block_equals_the_reference(name, render, tmp_path):
    path = write_case(tmp_path, name)
    wav = tmp_path / "x.wav"
    result = run(render, [path, "--out", wav], timeout=300)
    assert result.returncode == 0, (result.stdout, result.stderr)
    wav.unlink()
    text = (tmp_path / "x.report.json").read_text(encoding="utf-8")
    report = json.loads(text)
    keys = list(report)
    assert keys.index("spacing") == keys.index("determinism_key") - 1, keys
    spacing = report["spacing"]
    assert list(spacing) == list(common.EARS)
    recipe = common.case_recipe(name)
    reference = common.reference_spacing().spacing_margins(recipe)
    table = common.reference_module("components").component_table(recipe)
    tol = common.frequency_error()
    for ear in common.EARS:
        got, want = spacing[ear], reference[ear]
        if want is None:
            assert got is None, ear
            continue
        assert list(got) == ["min_distance_hz", "margin_hz", "component_1", "component_2", "pair"], got
        assert abs(got["min_distance_hz"] - want.min_distance_hz) < tol, (ear, got)
        assert abs(got["margin_hz"] - want.margin_hz) < tol, (ear, got)
        assert (got["component_1"], got["component_2"]) == (want.component_1, want.component_2), (ear, got)
        r1, r2 = table[want.component_1], table[want.component_2]
        want_pair = (f"{r1.layer} ({r1.gamma_mult}, {r1.theta_mult}, {r1.beat_mult}) at {common.shortest(r1.center_hz)} "
                     f"Hz and {r2.layer} ({r2.gamma_mult}, {r2.theta_mult}, {r2.beat_mult}) at "
                     f"{common.shortest(r2.center_hz)} Hz")
        problems = common.compare_pair_texts(got["pair"], want_pair)
        assert not problems, f"{ear}:\n" + "\n".join(problems)


def test_cli_report_without_a_pair_has_no_spacing_member(render, tmp_path):
    for fixture in ("stub-chain-1s-beat-0.json", "stub-chain-1s-no-layers.json"):
        out = tmp_path / fixture.removesuffix(".json")
        out.mkdir()
        result = run(render, [common.FIXTURES_VALID / fixture, "--out", out / "x.wav"])
        assert result.returncode == 0, (fixture, result.stderr)
        text = (out / "x.report.json").read_text(encoding="utf-8")
        assert '"spacing"' not in text, fixture
        assert list(json.loads(text)) == ["engine_version", "seed", "sample_rate", "mode", "frames",
                                          "determinism_key", "assertions"], fixture
