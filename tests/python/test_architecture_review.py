"""Independent review of the pending architecture decisions (Story 0.5).

Checks that the review closed: the architecture spine has no
`[REVIEW PENDING]` tag left, the review file gives one verdict per decision,
design log entry (ee) names the review file, and the spine's Open Questions
row for the review is marked resolved.

Verdict table format (required in reviews/review-independent-s0-5.md):

    | Decision | Verdict | Source | Notes |
    | --- | --- | --- | --- |
    | AD-4 | lock | ... | ... |
    | AD-5 | change | ... | ... |

The header row's first two cells are exactly `Decision` and `Verdict`; more
columns may follow. Each data row's Decision cell is exactly one of `AD-4`,
`AD-5`, `AD-9`, `AD-19`, `AD-20`, `Stack`, and its Verdict cell is exactly
`lock` or `change` (surrounding backticks or `**` are ignored). Each of the
six decisions appears exactly once across all such tables in the file.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCH_DIR = (
    REPO_ROOT / "_bmad-output" / "planning-artifacts" / "architecture"
    / "architecture-Arcani-2026-10-27"
)
SPINE = ARCH_DIR / "ARCHITECTURE-SPINE.md"
REVIEW_NAME = "review-independent-s0-5.md"
REVIEW = ARCH_DIR / "reviews" / REVIEW_NAME
DESIGN_LOG = REPO_ROOT / "docs" / "design-log.md"

DECISIONS = ["AD-4", "AD-5", "AD-9", "AD-19", "AD-20", "Stack"]
VERDICTS = {"lock", "change"}


def read(path):
    return path.read_text(encoding="utf-8")


def cells(line):
    return [c.strip().strip("`*").strip() for c in line.strip().strip("|").split("|")]


def verdict_rows(text):
    """Return (decision, verdict) pairs from every Decision | Verdict table."""
    rows = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        row = cells(stripped)
        if len(row) >= 2 and row[0] == "Decision" and row[1] == "Verdict":
            in_table = True
            continue
        if not in_table or set(stripped) <= set("|-: "):
            continue
        if len(row) >= 2:
            rows.append((row[0], row[1]))
    return rows


def test_spine_has_no_review_pending_tag():
    lines = read(SPINE).splitlines()
    offending = [
        f"line {i}: {line.strip()}"
        for i, line in enumerate(lines, start=1)
        if "[REVIEW PENDING]" in line
    ]
    assert not offending, "spine still carries [REVIEW PENDING]:\n" + "\n".join(offending)


def test_review_file_exists():
    assert REVIEW.is_file(), f"missing review file {REVIEW.relative_to(REPO_ROOT).as_posix()}"


@pytest.mark.parametrize("decision", DECISIONS)
def test_review_gives_one_verdict(decision):
    assert REVIEW.is_file(), f"missing review file {REVIEW.relative_to(REPO_ROOT).as_posix()}"
    found = [v for d, v in verdict_rows(read(REVIEW)) if d == decision]
    assert found, f"review verdict table has no row for {decision}"
    assert len(found) == 1, f"review verdict table lists {decision} {len(found)} times"
    assert found[0] in VERDICTS, (
        f"{decision} verdict is '{found[0]}', expected one of {sorted(VERDICTS)}"
    )


def test_review_table_has_only_known_decisions():
    assert REVIEW.is_file(), f"missing review file {REVIEW.relative_to(REPO_ROOT).as_posix()}"
    unknown = [d for d, _ in verdict_rows(read(REVIEW)) if d not in DECISIONS]
    assert not unknown, f"review verdict table has unknown decisions: {unknown}"


def test_design_log_entry_ee_names_review_file():
    lines = read(DESIGN_LOG).splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("### ") and "(ee)" in line),
        None,
    )
    assert start is not None, "design log has no '### ' heading containing (ee)"
    body = []
    for line in lines[start + 1:]:
        if line.startswith("### "):
            break
        body.append(line)
    assert REVIEW_NAME in "\n".join(body), (
        f"design log entry (ee) does not name {REVIEW_NAME}: {lines[start]}"
    )


def test_spine_open_question_for_review_is_resolved():
    rows = [
        line for line in read(SPINE).splitlines()
        if line.strip().startswith("|") and "independent review" in line.lower()
    ]
    assert rows, "spine has no Open Questions row about the independent review"
    for row in rows:
        assert "resolved" in row and "(ee)" in row, (
            f"independent review row is not marked resolved with (ee): {row.strip()}"
        )
