// Loader for the threshold and locked-range tables (tests/tables/*.tsv), and
// the C++ assertion call. Same rules as tests/assertions/tables.py; the
// cross-check test (tests/python/test_tables_crosscheck.py) proves both read
// the same rows. Format rules: tests/tables/README.md. Test code only.

#pragma once

#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace arcani::test::tables {

class TableError : public std::runtime_error {
 public:
  using std::runtime_error::runtime_error;
};

struct Row {
  std::string kind;  // "thresholds" or "ranges"
  std::string id;
  std::string unit;
  std::string spec_row;
  std::string source;
  std::string pending;
  std::string file;
  int line = 0;
  // thresholds
  std::string value_text;
  std::vector<double> values;
  // ranges
  std::string min_text;
  std::string max_text;
  double min = 0.0;
  double max = 0.0;
  std::string max_bound;

  // The value of a single-member threshold row; throws TableError for a set
  // or a range row.
  double value() const;
};

// Loads one table file; kind is "thresholds" or "ranges". Throws TableError
// naming the file, line, and id (or column) on any format error.
std::vector<Row> load_table(const std::string& path, const std::string& kind);

// Loads dir/thresholds.tsv then dir/ranges.tsv; ids are unique across both.
std::vector<Row> load_tables(const std::string& dir);

// One line of the cross-check dump format (no line end).
std::string dump_line(const Row& r);

// The assertion call: the row with this id from the repo tables
// (ARCANI_TABLES_DIR). Throws TableError on an empty or unknown id. Records
// the id in the file named by ARCANI_ROW_USAGE_FILE, when that is set.
const Row& row(std::string_view id);

}  // namespace arcani::test::tables
