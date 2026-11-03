# Threshold and locked-range tables

`thresholds.tsv` and `ranges.tsv` hold every test threshold and locked range
as data, built from `_bmad-output/specs/spec-arcani-v0-1/thresholds-and-ranges.md`.
No test carries one of these values as a literal: C++ tests call
`arcani::test::tables::row(id)` (`tests/assertions/tables.hpp`) and Python
tests call `assertions.row(id)` (`tests/assertions/__init__.py`). Each call
records the id for the coverage check.

## Format

- UTF-8, LF line ends, tab-separated, one header line, then one row per line.
  No quoting, no blank lines, no comment lines.
- `thresholds.tsv` columns: `id, value, unit, spec_row, source, pending`.
- `ranges.tsv` columns: `id, min, max, max_bound, unit, spec_row, source, pending`.
- `id`: kebab-case, unique across both tables. Story 0.2's ids never change.
- Numbers are plain decimals (`-120`, `0.01`); no exponent, no plus sign. The
  loaders keep the exact text and its binary64 value.
- A set (sample rates, block sizes) is one thresholds row whose `value` lists
  its members separated by single spaces, such as `1 64 512 4096`.
- A qualitative pass condition is a count: `0` with a unit naming what is
  counted, such as `0` `differing bytes`.
- Ranges: `min` is always inclusive. `max_bound` is `inclusive` or
  `exclusive`; "below N" in the md is `exclusive`. A fixed value (burst width,
  the v0.1 starter max run times and loudness levels) has `min` equal to `max`.
  A range the md states only from above ("Below 1000 Hz", "Up to 8 h") has
  `min` 0.
- `unit`: what the number measures, such as `Hz`, `ms`, `dBFS`, `differing bytes`.

## Sources

- `spec_row` is the md table row's first-column text, verbatim. Every md row
  has at least one data row. Every number in a row appears in that md row's
  pass condition or range text, except 0 (a count, or the floor of a range
  stated only from above).
- A row the md does not list (`sine-error`, `sample-rates`,
  `binaural-carrier-right`) has an empty `spec_row` and a `source` that cites a
  design log entry or starts with `Derived`.
- `source` is never empty; both loaders fail on an uncited row.

## Pending rule

`pending` is empty when an assertion already reads the row. Otherwise it is
the sprint-status key of the story whose acceptance criteria first assert the
row (read from `_bmad-output/planning-artifacts/epics.md`). That story clears
the field when it adds the assertion. `tools/check_row_coverage.py` fails on a
row with no use and no `pending`, on a used row still `pending`, and on a
`pending` story that is unknown or `done`.

## Changing a row

Any added, removed, or changed row (any field except `pending`) needs a line
added to `docs/design-log.md` in the same branch naming the id in backticks,
such as `drift-8h`. `tools/check_table_log.py --base <merge base>` enforces it
in CI. Never weaken a value to make a test pass.
