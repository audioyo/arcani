"""Wording check: listed terms and em dashes fail in scanned files (Story 0.4).

Contract with tools/check_wording.py (standard library only):

- CLI: `python tools/check_wording.py [--terms FILE] [--exempt FILE] [PATH ...]`.
  Defaults: `--terms tools/wording/terms.tsv`, `--exempt
  tools/wording/exempt.txt`, and the files from `git ls-files` in the repo
  root. A positional PATH replaces the `git ls-files` set; a directory PATH is
  walked recursively. Exemptions apply to positional paths too: each glob is
  matched against the file's repo-relative POSIX path.
- Term list: tab-separated, one header row `id, pattern, case, category,
  source`. `pattern` is a Python regex matched at word boundaries; `case` is
  `sensitive` or `insensitive`; `category` is `project-term`,
  `comparable-name`, or `claim`; `source` is not empty. A bad row (empty
  source, bad case or category, duplicate id, pattern that does not compile)
  is a setup error naming the file line (`:<line>:` or `line <line>`) and the
  row id.
- Exemption list: one glob per line, each followed by ` # reason`. A line
  with no reason is a setup error naming its line.
- Binary files (NUL byte in the first 8 KiB) are skipped. An undecodable
  non-binary file fails, naming the file.
- Output: one line per match, `<path>:<line>: <matched text>: term <id>` or
  `<path>:<line>: em dash` (U+2014). Exit 0 printing how many files were
  scanned; 1 on any match; 2 on a setup error (bad term row, unreasoned
  exemption, missing terms or exempt file, missing PATH).

Fixtures live in tests/fixtures/wording/ with their own terms.tsv and
exemption files. The repo's exempt.txt must cover the fixture terms.tsv,
mustfail/**, and research/** there. This file is not exempt, so it spells no
listed term: it reads them from the fixture term list.
"""

import csv
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "tools" / "check_wording.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "wording"
TERMS = FIXTURES / "terms.tsv"
EXEMPT = FIXTURES / "exempt.txt"
EXEMPT_NONE = FIXTURES / "exempt_none.txt"
MUSTFAIL = FIXTURES / "mustfail"
PASS = FIXTURES / "pass"
RESEARCH = FIXTURES / "research"
BAD = FIXTURES / "bad"
EM_DASH = "\u2014"

# Must-fail fixture -> (line, term id, or None for an em dash).
MUSTFAIL_HITS = {
    "em_dash.md": (3, None),
    "recipe_claim.json": (3, "claim-recipe"),
    "banned_comment.cpp": (2, "proj-comment"),
}

# Bad term list -> (line of the bad row, row id).
BAD_TERMS = {
    "empty_source.tsv": (3, "nosource"),
    "bad_regex.tsv": (2, "badre"),
    "dup_id.tsv": (3, "dup"),
    "bad_case.tsv": (3, "oddcase"),
    "bad_category.tsv": (2, "oddcat"),
}


def run_checker(*paths, terms=TERMS, exempt=EXEMPT, cwd=REPO_ROOT):
    assert CHECKER.is_file(), f"missing {CHECKER}"
    args = [sys.executable, str(CHECKER)]
    if terms is not None:
        args += ["--terms", str(terms)]
    if exempt is not None:
        args += ["--exempt", str(exempt)]
    result = subprocess.run(
        args + [str(p) for p in paths],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=cwd,
    )
    return result.returncode, result.stdout + result.stderr


def term_lines(out):
    return [line for line in out.splitlines() if re.search(r": term \S+$", line.rstrip())]


def dash_lines(out):
    return [line for line in out.splitlines() if line.rstrip().endswith(": em dash")]


def fixture_terms():
    with TERMS.open(encoding="utf-8", newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f, delimiter="\t")}


def names_line(out, line_no):
    return re.search(rf"(:{line_no}:|\bline {line_no}\b)", out)


def tmp_exempt(tmp_path):
    path = tmp_path / "exempt.txt"
    path.write_text("no/such/dir/** # nothing in this test is exempt\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- fixtures


def test_fixture_terms_cover_each_category():
    rows = fixture_terms()
    assert {r["category"] for r in rows.values()} == {"project-term", "comparable-name", "claim"}
    assert {"claim-recipe", "proj-comment"} <= set(rows)
    assert all(r["source"].strip() for r in rows.values())


def test_fixture_texts_have_no_stray_em_dash():
    for path in FIXTURES.rglob("*"):
        if path.is_file() and path.name != "em_dash.md":
            assert EM_DASH not in path.read_text(encoding="utf-8"), path


def test_pass_fixture_passes():
    code, out = run_checker(PASS)
    assert code == 0, out
    assert not term_lines(out) and not dash_lines(out), out
    count = len([p for p in PASS.rglob("*") if p.is_file()])
    assert re.search(rf"\b{count}\b", out), f"no scanned file count {count}: {out}"


def test_word_boundaries_hold():
    code, out = run_checker(PASS / "word_boundary.txt")
    assert code == 0, out


def test_mustfail_fixture_fails_with_one_line_per_hit():
    code, out = run_checker(MUSTFAIL)
    assert code == 1, out
    terms, dashes = term_lines(out), dash_lines(out)
    assert len(terms) + len(dashes) == len(MUSTFAIL_HITS), out
    for name, (line_no, term_id) in MUSTFAIL_HITS.items():
        pool = dashes if term_id is None else terms
        assert any(f"{name}:{line_no}: " in line for line in pool), (name, out)


@pytest.mark.parametrize("name", sorted(MUSTFAIL_HITS))
def test_each_mustfail_case_fails_alone(name):
    line_no, term_id = MUSTFAIL_HITS[name]
    code, out = run_checker(MUSTFAIL / name)
    assert code == 1, (name, out)
    if term_id is None:
        hits = dash_lines(out)
        assert len(hits) == 1 and not term_lines(out), out
        assert re.search(rf"{re.escape(name)}:{line_no}: em dash$", hits[0].rstrip()), hits[0]
    else:
        hits = term_lines(out)
        assert len(hits) == 1 and not dash_lines(out), out
        assert re.search(rf"{re.escape(name)}:{line_no}: .+: term {re.escape(term_id)}$",
                         hits[0].rstrip()), hits[0]


def test_matched_text_is_reported():
    code, out = run_checker(MUSTFAIL / "recipe_claim.json")
    assert code == 1, out
    pattern = fixture_terms()["claim-recipe"]["pattern"]
    matched = re.search(rf"\b(?:{pattern})\b", (MUSTFAIL / "recipe_claim.json").read_text(
        encoding="utf-8"), re.IGNORECASE).group(0)
    assert f": {matched}: term claim-recipe" in term_lines(out)[0], out


def test_research_fixture_passes_only_through_exemption():
    code, out = run_checker(RESEARCH, exempt=EXEMPT)
    assert code == 0, out
    code, out = run_checker(RESEARCH, exempt=EXEMPT_NONE)
    assert code == 1, out
    assert any("sources.md:3: " in line and line.rstrip().endswith("term proj-research")
               for line in term_lines(out)), out


def test_term_list_itself_is_not_scanned():
    code, out = run_checker(TERMS, exempt=EXEMPT)
    assert code == 0, out
    assert not term_lines(out), out


def test_whole_fixture_tree_with_fixture_exemptions():
    code, out = run_checker(MUSTFAIL, PASS, RESEARCH, TERMS)
    assert code == 1, out
    assert len(term_lines(out)) + len(dash_lines(out)) == len(MUSTFAIL_HITS), out


# ----------------------------------------------------- case and boundaries


def test_sensitive_term_ignores_other_case(tmp_path):
    word = fixture_terms()["proj-upper"]["pattern"]
    (tmp_path / "a.txt").write_text(f"one {word.lower()} two\n", encoding="utf-8")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code == 0, out
    (tmp_path / "b.txt").write_text(f"one {word} two\n", encoding="utf-8")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code == 1, out
    assert any("b.txt:1: " in line and line.rstrip().endswith("term proj-upper")
               for line in term_lines(out)), out


def test_insensitive_term_matches_any_case(tmp_path):
    word = fixture_terms()["comp-name"]["pattern"]
    (tmp_path / "a.md").write_text(f"x\nthe {word.upper()} app\n", encoding="utf-8")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code == 1, out
    assert any("a.md:2: " in line and line.rstrip().endswith("term comp-name")
               for line in term_lines(out)), out


def test_term_inside_a_longer_word_passes(tmp_path):
    rows = fixture_terms()
    text = (f"pre{rows['proj-comment']['pattern'].lower()}\n"
            f"{rows['comp-name']['pattern']}s2\n"
            f"x{rows['proj-upper']['pattern']}\n")
    (tmp_path / "a.txt").write_text(text, encoding="utf-8")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code == 0, out


def test_two_hits_on_one_line_give_two_lines(tmp_path):
    rows = fixture_terms()
    (tmp_path / "a.txt").write_text(
        f"{rows['proj-comment']['pattern']} and {rows['comp-name']['pattern']} {EM_DASH} x\n",
        encoding="utf-8")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code == 1, out
    assert len(term_lines(out)) == 2 and len(dash_lines(out)) == 1, out


# ------------------------------------------------------ binary, undecodable


def test_binary_file_is_skipped(tmp_path):
    word = fixture_terms()["proj-comment"]["pattern"]
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02 " + word.encode() + b"\n")
    (tmp_path / "ok.txt").write_text("plain text\n", encoding="utf-8")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code == 0, out


def test_undecodable_text_file_fails(tmp_path):
    (tmp_path / "bad.txt").write_bytes(b"caf\xe9 \xff\xfe text\n")
    code, out = run_checker(tmp_path, exempt=tmp_exempt(tmp_path))
    assert code != 0, out
    assert "bad.txt" in out, out


# ------------------------------------------------------------ setup errors


@pytest.mark.parametrize("name", sorted(BAD_TERMS))
def test_bad_term_row_is_a_setup_error(name):
    line_no, row_id = BAD_TERMS[name]
    code, out = run_checker(PASS, terms=BAD / name)
    assert code == 2, (name, out)
    assert names_line(out, line_no), (name, out)
    assert row_id in out, (name, out)


def test_unreasoned_exemption_is_a_setup_error():
    code, out = run_checker(PASS, exempt=BAD / "no_reason.txt")
    assert code == 2, out
    assert names_line(out, 2), out


def test_missing_terms_file_is_a_setup_error(tmp_path):
    code, out = run_checker(PASS, terms=tmp_path / "none.tsv")
    assert code == 2, out


def test_missing_exempt_file_is_a_setup_error(tmp_path):
    code, out = run_checker(PASS, exempt=tmp_path / "none.txt")
    assert code == 2, out


def test_missing_path_is_a_setup_error(tmp_path):
    code, out = run_checker(tmp_path / "does-not-exist")
    assert code == 2, out


# ---------------------------------------------------- repo defaults, real data


def test_repo_passes_by_default():
    code, out = run_checker(terms=None, exempt=None)
    assert code == 0, out
    assert re.search(r"\b\d+\b", out), out


def test_repo_term_list_is_exempt():
    code, out = run_checker(REPO_ROOT / "tools" / "wording" / "terms.tsv", terms=None, exempt=None)
    assert code == 0, out


@pytest.mark.parametrize("rel", ["docs/research-library.md", "docs/research-ip-and-clean-room.md"])
def test_repo_research_files_are_exempt(rel):
    path = REPO_ROOT / rel
    assert path.is_file(), f"missing {path}"
    code, out = run_checker(path, terms=None, exempt=None)
    assert code == 0, out


def test_repo_exempts_wording_fixtures_with_terms():
    code, out = run_checker(MUSTFAIL, RESEARCH, TERMS, terms=None, exempt=None)
    assert code == 0, out


def test_repo_terms_catch_the_mustfail_fixtures_without_exemption():
    code, out = run_checker(MUSTFAIL, terms=None, exempt=EXEMPT_NONE)
    assert code == 1, out
    for name, (line_no, _) in MUSTFAIL_HITS.items():
        assert f"{name}:{line_no}: " in out, (name, out)


def test_this_test_file_is_scanned_and_clean():
    code, out = run_checker(Path(__file__).resolve(), terms=None, exempt=None)
    assert code == 0, out
    assert re.search(r"\b1\b", out), f"this file was not scanned: {out}"


def test_repo_term_list_covers_each_category_with_sources():
    path = REPO_ROOT / "tools" / "wording" / "terms.tsv"
    assert path.is_file(), f"missing {path}"
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        assert reader.fieldnames == ["id", "pattern", "case", "category", "source"], reader.fieldnames
        rows = list(reader)
    assert {r["category"] for r in rows} == {"project-term", "comparable-name", "claim"}
    assert all(r["source"].strip() for r in rows)
