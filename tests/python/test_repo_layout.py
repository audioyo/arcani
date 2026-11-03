"""Source tree, Git LFS routing for golden files, and CLAUDE.md commands."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SPINE_DIRS = ["engine", "cli", "reference", "tests", "recipes", "golden", "docs"]


@pytest.mark.parametrize("name", SPINE_DIRS)
def test_spine_directory_exists(name):
    assert (REPO_ROOT / name).is_dir(), f"missing directory {name}/"


def test_golden_routed_to_lfs():
    attrs = REPO_ROOT / ".gitattributes"
    assert attrs.is_file(), "missing .gitattributes"
    lines = [
        line.strip()
        for line in attrs.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    matches = [
        line for line in lines
        if line.split()[0] == "golden/**" and "filter=lfs" in line.split()[1:]
    ]
    assert matches, "no .gitattributes line routes golden/** through filter=lfs"


def commands_block():
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Commands"))
    block = [lines[start]]
    seen_item = False
    for line in lines[start + 1:]:
        if line.startswith("- "):
            seen_item = True
            block.append(line)
        elif line.strip() == "" and not seen_item:
            continue
        else:
            break
    return block


def test_claude_md_commands_have_no_tbd():
    block = commands_block()
    assert len(block) > 1, "CLAUDE.md Commands block has no entries"
    assert not any("TBD" in line for line in block), "\n".join(block)


@pytest.mark.parametrize("label", ["Build", "C++ tests", "Render a recipe"])
def test_claude_md_command_is_filled(label):
    block = commands_block()
    entry = next((line for line in block if line.startswith(f"- {label}:")), None)
    assert entry is not None, f"CLAUDE.md Commands block has no '{label}' entry"
    command = re.search(r"`([^`]+)`", entry)
    assert command and command.group(1).strip() and command.group(1) != "TBD", entry
