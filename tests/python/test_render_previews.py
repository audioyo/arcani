"""tools/render_previews.py: the preview set, the output directory refusal,
and the exit codes (Story 3.3; docs/signal-spec.md, Preview, Preview set).

Contract (spec Implementation Notes, Previews tool):

    uv run --locked python tools/render_previews.py [--out-dir DIR] [--rate 44100|48000]
                                                   [--renderer PATH] [--fixture PATH ...] [--list]

- Defaults: --out-dir build/previews (the repository root's), --rate 48000,
  --renderer the preset build of arcani-render, the preview set
  (recipes/fixtures/valid/<name> for each name of preview_constants.fixtures,
  in vector order).
- --fixture (repeatable) replaces the preview set. --list prints the
  selected recipe paths, one per line, renders nothing, creates nothing,
  exit 0.
- An output directory that resolves to the repository root or inside it,
  and not inside <repo>/build, is refused before anything is created: one
  stderr line `render_previews: refused: <dir> is inside the repository but
  not under build/`, exit 2. A directory outside the repository is allowed.
- Each recipe: `<renderer> RECIPE --out <dir>/<stem>.preview.wav --rate
  <rate> --preview` (report at <dir>/<stem>.preview.report.json); stdout
  `<stem>: <frames> frames, <seconds> s, gain <gain>`, then
  `render_previews: <count> previews, <total seconds> s of audio in <dir>`.
- Exit codes: 0 all rendered; 1 a render failed (the renderer's stderr is
  printed); 2 usage or refused directory; 3 the renderer is missing.

Only 1 s fixtures are rendered here, into a directory under build/ and one
outside the repository (pytest's tmp_path). The must-fail case runs a copy
of the tool in a doctored repository tree (a tmp_path tree with its own
docs/ and build/), where the copy refuses its own docs/ and allows its own
build/.

The tests skip only when cmake is not on PATH, or when Windows application
control blocks a binary.
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

import preview_common as common

TOOL = common.RENDER_PREVIEWS
ONE_SECOND = "stub-chain-1s-beat-6.json"
REJECTED = "spacing-binaural-250-256-gamma-260.json"   # Story 3.2's spacing must-fail fixture
REFUSED_LINE_START = "render_previews: refused: "
REFUSED_LINE_END = " is inside the repository but not under build/"


@pytest.fixture(scope="module")
def render():
    return common.build("arcani-render", common.RENDER)


def tool(args, cwd=None, script=TOOL, timeout=300):
    assert Path(script).is_file(), f"missing {script} (Story 3.3)"
    return common.run(sys.executable, [script, *args], timeout=timeout, cwd=str(cwd or common.REPO_ROOT))


def tree_snapshot(path):
    path = Path(path)
    if not path.exists():
        return None
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


def check_refused(result):
    lines = result.stderr.splitlines()
    assert result.returncode == 2, result.stdout + result.stderr
    assert len(lines) == 1, lines
    assert lines[0].startswith(REFUSED_LINE_START) and lines[0].endswith(REFUSED_LINE_END), lines[0]


# ------------------------------------------------------------ list


def test_list_names_the_preview_set_in_vector_order_and_creates_nothing():
    default_dir = common.REPO_ROOT / common.constants()["out_dir"]
    before = tree_snapshot(default_dir)
    r = tool(["--list"])
    assert r.returncode == 0, r.stdout + r.stderr
    want = [common.FIXTURES_VALID / name for name in common.constants()["fixtures"]]
    got = [Path(line) for line in r.stdout.splitlines() if line.strip()]
    assert [p.resolve() for p in got] == [p.resolve() for p in want]
    assert all(p.is_file() for p in want)
    assert tree_snapshot(default_dir) == before


def test_list_with_fixtures_names_only_those():
    paths = [common.FIXTURES_VALID / ONE_SECOND, common.FIXTURES_VALID / "theta-gamma-uncoupled.json"]
    r = tool(["--list", *[a for p in paths for a in ("--fixture", p)]])
    assert r.returncode == 0, r.stdout + r.stderr
    assert [Path(line).resolve() for line in r.stdout.splitlines() if line.strip()] == [p.resolve() for p in paths]


# ------------------------------------------------------------ refusal


@pytest.mark.parametrize("out_dir", ["docs", ".", "recipes/fixtures", "buildx", "build/../docs",
                                     "docs/render-previews-probe", "build/../buildx/previews"])
def test_an_output_directory_in_the_repository_but_not_under_build_is_refused(out_dir):
    target = (common.REPO_ROOT / out_dir).resolve()
    before = tree_snapshot(target)
    r = tool(["--out-dir", out_dir, "--fixture", common.FIXTURES_VALID / ONE_SECOND])
    check_refused(r)
    assert tree_snapshot(target) == before, f"{target} changed"
    if before is None:
        assert not target.exists()


def test_an_absolute_repository_directory_is_refused_too():
    target = common.REPO_ROOT / "docs"
    before = tree_snapshot(target)
    check_refused(tool(["--out-dir", target, "--fixture", common.FIXTURES_VALID / ONE_SECOND]))
    assert tree_snapshot(target) == before


# ------------------------------------------------------------ renders


def check_rendered(out_dir, result, stems, rate):
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == len(stems) + 1, lines
    total = 0.0
    for stem, line in zip(stems, lines):
        wav = Path(out_dir) / f"{stem}{common.constants()['wav_suffix']}"
        report_path = Path(out_dir) / f"{stem}{common.constants()['report_suffix']}"
        assert wav.is_file(), wav
        assert report_path.is_file(), report_path
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["sample_rate"] == rate
        member = report["preview"]
        assert member["signed"] is False
        _, frames, wav_rate = common.wav_layout(wav)
        assert wav_rate == rate and frames == report["frames"]
        m = re.fullmatch(rf"{re.escape(stem)}: ([0-9]+) frames, (\S+) s, gain (\S+)", line)
        assert m, line
        assert int(m.group(1)) == frames
        assert float(m.group(2)) == member["seconds"]
        assert common.bits(float(m.group(3))) == common.bits(member["gain"])
        total += member["seconds"]
    m = re.fullmatch(rf"render_previews: {len(stems)} previews, (\S+) s of audio in (.+)", lines[-1])
    assert m, lines[-1]
    assert float(m.group(1)) == total
    assert Path(m.group(2)).resolve() == Path(out_dir).resolve()
    names = sorted(p.name for p in Path(out_dir).iterdir())
    assert names == sorted(f"{s}{suffix}" for s in stems
                           for suffix in (common.constants()["wav_suffix"], common.constants()["report_suffix"]))


def test_a_directory_under_build_is_allowed_and_rendered(render):
    out_dir = common.REPO_ROOT / "build" / f"render-previews-test-{os.getpid()}"
    shutil.rmtree(out_dir, ignore_errors=True)
    try:
        r = tool(["--out-dir", out_dir, "--renderer", render, "--fixture", common.FIXTURES_VALID / ONE_SECOND])
        check_rendered(out_dir, r, [Path(ONE_SECOND).stem], common.constants()["listening_rate"])
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


@pytest.mark.parametrize("rate", [44100, 48000])
def test_a_directory_outside_the_repository_is_allowed_and_rendered(render, tmp_path, rate):
    assert not tmp_path.resolve().is_relative_to(common.REPO_ROOT.resolve())
    out_dir = tmp_path / "previews"
    fixtures = [common.FIXTURES_VALID / ONE_SECOND, common.FIXTURES_VALID / "stub-chain-1s-beat-0.json"]
    r = tool(["--out-dir", out_dir, "--renderer", render, "--rate", rate,
              *[a for p in fixtures for a in ("--fixture", p)]])
    check_rendered(out_dir, r, [p.stem for p in fixtures], rate)


def test_a_failed_render_exits_1_with_the_renderer_stderr(render, tmp_path):
    out_dir = tmp_path / "previews"
    r = tool(["--out-dir", out_dir, "--renderer", render, "--fixture", common.FIXTURES_VALID / REJECTED])
    assert r.returncode == 1, r.stdout + r.stderr
    assert "rejected: " in r.stderr


def test_a_missing_renderer_exits_3(tmp_path):
    r = tool(["--out-dir", tmp_path / "previews", "--renderer", tmp_path / "no-such-renderer",
              "--fixture", common.FIXTURES_VALID / ONE_SECOND])
    assert r.returncode == 3, r.stdout + r.stderr
    assert not (tmp_path / "previews" / f"{Path(ONE_SECOND).stem}{common.constants()['wav_suffix']}").exists()


@pytest.mark.parametrize("args", [["--rate", "12345"], ["--rate"], ["--bogus"], ["--out-dir"], ["--fixture"]])
def test_usage_errors_exit_2(args, tmp_path):
    r = tool([*args])
    assert r.returncode == 2, r.stdout + r.stderr


# ------------------------------------------------------------ must-fail: a doctored repository root


def test_must_fail_a_copy_in_a_doctored_repository_refuses_its_docs_and_allows_its_build(render, tmp_path):
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "build").mkdir()
    copy = root / "tools" / TOOL.name
    assert TOOL.is_file(), f"missing {TOOL} (Story 3.3)"
    shutil.copyfile(TOOL, copy)
    fixture = common.FIXTURES_VALID / ONE_SECOND
    # Its own docs/ and its own root are refused.
    for out_dir in (root / "docs", root, root / "build" / ".." / "docs"):
        check_refused(tool(["--out-dir", out_dir, "--renderer", render, "--fixture", fixture], cwd=root, script=copy))
    assert sorted(p.name for p in (root / "docs").iterdir()) == []
    # Its own build/ is allowed.
    out_dir = root / "build" / "previews"
    r = tool(["--out-dir", out_dir, "--renderer", render, "--fixture", fixture], cwd=root, script=copy)
    check_rendered(out_dir, r, [fixture.stem], common.constants()["listening_rate"])
    # The real repository's docs/ is outside this tree, so the copy allows it
    # as an outside directory; the real tool does not.
    check_refused(tool(["--out-dir", common.REPO_ROOT / "docs", "--fixture", fixture]))
