"""The Story 3.3 listening checklist and the rule that previews are never
goldens (Story 3.3; docs/signal-spec.md, Preview; story decision 7).

The checklist (`_bmad-output/implementation-artifacts/listening-3-3-preview.md`)
must hold:

- the one render command (`tools/render_previews.py`) and the level note
  (the row preview-peak-level, -30 dBFS, and raising playback in Reaper);
- every file of the preview set by its `<stem>.preview.wav` name, each with
  its own `### ` section whose heading names the file and its length in
  seconds (the vectors' `seconds` at the listening rate), and a table whose
  header has `Earbuds` and `Headphones` columns;
- the budget: the one-pass total and the two-pass total equal the vectors'
  `seconds` summed (once and twice);
- the required lines: a tone line (harsh or not) naming every carrier of
  the preview set; a gamma pulse line (rough or not) for every render with
  a gamma PAC layer; for Focus, the free-running gamma envelope inside the
  50 ms bursts, each burst opening on a different gamma phase (design log
  (qq)); the opening end and first body seam lines of Focus and Learn at the
  vectors' `opening_end_s` and `first_seam_s`; the Sleep binaural beat
  cycle; the 250 Hz carrier with gamma AM at 60 Hz lines for the swell and
  the bursts;
- a `## Proposed changes` section and a `## Result` section that names
  "Nothing needs changing" as a valid result.

And nothing in `ci/`, `tools/hash_*.py`, or `tests/hashprobe/` names the
previews, git ignores `build/previews/`, and `git ls-files` lists no
committed preview file (`*.preview.wav` or `*.preview.report.json`).

Must-fails, doctored here: a checklist text with a wrong seam time, with a
missing Headphones column, a `ci/` text naming `build/previews`, and a
file listing holding a preview WAV or report, each caught.
"""

import re
import subprocess

import pytest

import preview_common as common

FS = common.constants()["listening_rate"]


def seconds_text(x):
    """A seconds value as the checklist writes it: an integer without a decimal part."""
    x = float(x)
    return str(int(x)) if x == int(x) else repr(x)


def checklist_text():
    assert common.CHECKLIST.is_file(), f"missing {common.CHECKLIST}"
    return common.CHECKLIST.read_text(encoding="utf-8")


def sections(text):
    """{heading: body} of every `### ` section."""
    out = {}
    parts = re.split(r"^### (.+)$", text, flags=re.M)
    for i in range(1, len(parts), 2):
        body = parts[i + 1].split("\n## ", 1)[0]
        out[parts[i].strip()] = body
    return out


def table_rows(body):
    """The rows of the first table in a section body, each a list of stripped cells; the header first."""
    rows = []
    for line in body.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r"-+", c) for c in cells):
                continue
            rows.append(cells)
        elif rows:
            break
    return rows


def render_sections(text):
    """{fixture: (heading, rows)} for each fixture of the preview set."""
    out = {}
    secs = sections(text)
    for fixture in common.constants()["fixtures"]:
        wav = fixture[:-len(".json")] + common.constants()["wav_suffix"]
        found = [(h, b) for h, b in secs.items() if f"`{wav}`" in h]
        out[fixture] = (found[0][0], table_rows(found[0][1])) if len(found) == 1 else None
    return out


def section_named(text, name):
    m = re.search(rf"^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    return m.group(1) if m else None


def carriers(recipe):
    out = []
    if "theta_reference" in recipe:
        out.append(recipe["theta_reference"]["carrier_hz"])
    if "gamma_pac" in recipe:
        out.append(recipe["gamma_pac"]["carrier_hz"])
    if "binaural" in recipe:
        out.append(recipe["binaural"]["carrier_left_hz"])
    return out


def hz(x):
    return f"{seconds_text(x)} Hz"


def checklist_problems(text):
    p = []
    c = common.constants()
    if "tools/render_previews.py" not in text:
        p.append("no render command")
    peak = seconds_text(common.peak_dbfs())
    if f"{peak} dBFS" not in text or "preview-peak-level" not in text or "Reaper" not in text:
        p.append("no level note naming the peak level, its row, and Reaper")
    renders = render_sections(text)
    total = 0.0
    tone_lines = []
    for fixture, found in renders.items():
        if found is None:
            p.append(f"no single section for {fixture}")
            continue
        heading, rows = found
        v = common.frame_row(fixture, FS)
        total += float(v["seconds"])
        if f"({seconds_text(v['seconds'])} s)" not in heading:
            p.append(f"{fixture}: heading does not give {seconds_text(v['seconds'])} s")
        if not rows or "Earbuds" not in rows[0] or "Headphones" not in rows[0]:
            p.append(f"{fixture}: the table has no Earbuds and Headphones columns")
            continue
        header = rows[0]
        e, hcol = header.index("Earbuds"), header.index("Headphones")
        for r in rows[1:]:
            if len(r) != len(header):
                p.append(f"{fixture}: a row has {len(r)} cells, the header {len(header)}")
            elif r[e] or r[hcol]:
                p.append(f"{fixture}: an observation cell is already filled")
        lines = [" | ".join(r) for r in rows[1:]]
        tone_lines += [line for line in lines if "harsh" in line]
        recipe = common.load_fixture(fixture)
        if "gamma_pac" in recipe and not any("rough" in line for line in lines):
            p.append(f"{fixture}: no gamma pulse line (rough or not)")
        if v["looping"] == "yes":
            for label, key in (("seam at the opening end", "opening_end_s"), ("first body seam", "first_seam_s")):
                seam = [r for r in rows[1:] if label in r[1]]
                if len(seam) != 1:
                    p.append(f"{fixture}: no single line for the {label}")
                elif seam[0][2] != f"{seconds_text(v[key])} s":
                    p.append(f"{fixture}: the {label} is at {seam[0][2]}, want {seconds_text(v[key])} s")
        if fixture == c["starter_fixtures"][0]:
            if not any("50 ms burst" in line and "different" in line and "(qq)" in line for line in lines):
                p.append("Focus: no line for the free-running gamma envelope inside the 50 ms bursts (qq)")
        if "binaural" in recipe and "beat_rate_cycle" in recipe["binaural"]:
            if not any("binaural beat" in line for line in lines):
                p.append(f"{fixture}: no binaural beat cycle line")
        if fixture in c["checklist_fixtures"]:
            g = recipe["gamma_pac"]
            if not any(hz(g["carrier_hz"]) in line and hz(g["rate_hz"]) in line for line in lines):
                p.append(f"{fixture}: no line for the {hz(g['carrier_hz'])} carrier with gamma AM at "
                         f"{hz(g['rate_hz'])}")
    for fixture in c["fixtures"]:
        for carrier in carriers(common.load_fixture(fixture)):
            if not any(hz(carrier) in line for line in tone_lines):
                p.append(f"no tone line (harsh or not) names the {hz(carrier)} carrier")
    budget = section_named(text, "Budget")
    if budget is None:
        p.append("no Budget section")
    else:
        one = re.search(r"\| One pass \| ([0-9,]+) s", budget)
        if not one or float(one.group(1).replace(",", "")) != total:
            p.append(f"one-pass total is not {seconds_text(total)} s")
        two_min = seconds_text(2 * total / 60.0)
        if f"{two_min} min of audio" not in budget:
            p.append(f"two-pass total is not {two_min} min")
    if section_named(text, "Proposed changes") is None:
        p.append("no Proposed changes section")
    result = section_named(text, "Result")
    if result is None or "Nothing needs changing" not in result:
        p.append("no Result section naming Nothing needs changing")
    return p


def test_the_checklist_holds_every_required_line():
    problems = checklist_problems(checklist_text())
    assert not problems, "\n".join(problems)


def test_must_fail_a_wrong_seam_time_is_caught():
    text = checklist_text()
    v = common.frame_row(common.constants()["starter_fixtures"][0], FS)
    want = f"| {seconds_text(v['first_seam_s'])} s |"
    lines = text.split("\n")
    at = next(i for i, line in enumerate(lines) if "first body seam" in line and want in line)
    lines[at] = lines[at].replace(want, f"| {seconds_text(float(v['first_seam_s']) + 1)} s |")
    bad = "\n".join(lines)
    assert any("first body seam" in p for p in checklist_problems(bad))


def test_must_fail_a_missing_headphones_column_is_caught():
    text = checklist_text()
    bad = text.replace("| Earbuds | Headphones |", "| Earbuds |", 1)
    assert bad != text
    assert any("Headphones" in p for p in checklist_problems(bad))


def test_must_fail_a_missing_section_or_line_is_caught():
    text = checklist_text()
    for doctor in (lambda t: t.replace("## Result", "## Outcome"),
                   lambda t: t.replace("## Proposed changes", "## Ideas"),
                   lambda t: t.replace("(design log (qq))", ""),
                   lambda t: t.replace("1,140 s", "1,150 s")):
        bad = doctor(text)
        assert bad != text
        assert checklist_problems(bad)


# ------------------------------------------------------------ never golden

PREVIEW_NAMES = re.compile(r"previews|\.preview\.")


def golden_readers():
    files = [p for p in (common.REPO_ROOT / "ci").rglob("*") if p.is_file()]
    files += sorted((common.REPO_ROOT / "tools").glob("hash_*.py"))
    files += [p for p in (common.REPO_ROOT / "tests" / "hashprobe").rglob("*") if p.is_file()]
    assert files
    return files


def preview_mentions(files_and_texts):
    return [name for name, text in files_and_texts if PREVIEW_NAMES.search(text)]


def test_nothing_in_ci_or_the_hash_probe_names_the_previews():
    found = preview_mentions((str(p), p.read_text(encoding="utf-8", errors="replace")) for p in golden_readers())
    assert not found, found


def test_must_fail_a_ci_text_naming_build_previews_is_caught():
    p = golden_readers()[0]
    text = p.read_text(encoding="utf-8", errors="replace")
    assert preview_mentions([(str(p), text + "\nbuild/" + "previews\n")])
    assert preview_mentions([(str(p), text + "\nx" + ".preview." + "wav\n")])


def test_git_ignores_the_previews_directory():
    out_dir = common.constants()["out_dir"]
    probe = f"{out_dir}/x{common.constants()['wav_suffix']}"
    r = subprocess.run(["git", "check-ignore", "-q", probe], cwd=common.REPO_ROOT, capture_output=True, text=True)
    if r.returncode == 128:
        pytest.skip(f"git check-ignore failed: {r.stderr}")
    assert r.returncode == 0, f"{probe} is not ignored"
    # Must-fail: a path outside build/ is not ignored.
    r = subprocess.run(["git", "check-ignore", "-q", f"docs/x{common.constants()['wav_suffix']}"],
                       cwd=common.REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 1


def committed_previews(paths):
    """The paths of a file listing that are preview files (`<stem>.preview.wav`, `<stem>.preview.report.json`)."""
    suffixes = (common.constants()["wav_suffix"], common.constants()["report_suffix"])
    return [p for p in paths if p.replace("\\", "/").rsplit("/", 1)[-1].endswith(suffixes)]


def git_files():
    r = subprocess.run(["git", "ls-files", "-z"], cwd=common.REPO_ROOT, capture_output=True)
    if r.returncode == 128:
        pytest.skip(f"git ls-files failed: {r.stderr!r}")
    assert r.returncode == 0
    files = [f for f in r.stdout.decode("utf-8").split("\0") if f]
    assert files
    return files


def test_no_preview_file_is_committed():
    found = committed_previews(git_files())
    assert not found, found


def test_must_fail_a_listing_with_a_preview_file_is_caught():
    files = git_files()
    assert committed_previews(files + [f"golden/x{common.constants()['wav_suffix']}"])
    assert committed_previews(files + [f"build/previews/x{common.constants()['report_suffix']}"])
    assert committed_previews(["recipes\\fixtures\\x" + common.constants()["wav_suffix"]])
    # Names that only look alike are not preview files.
    assert not committed_previews(["recipes/fixtures/valid/preview-gamma-250-am-60-swell.json",
                                   "docs/x.preview.md", "x.wav"])
