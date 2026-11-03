// C++ table loader and assertion call (Story 0.3, tests/assertions/tables.hpp).
// Fixtures live in tests/fixtures/tables/ (ARCANI_TABLE_FIXTURES_DIR) and are
// shared with tests/python/test_tables_loader.py: good/ loads, every case in
// bad/expected.tsv fails with a message naming file, ":<line>:", and id, and
// dup-across/ fails on an id present in both files. Fixture rows are made up.

#include "tables.hpp"

#include <catch2/catch_test_macros.hpp>

#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#ifndef ARCANI_TABLE_FIXTURES_DIR
#error "ARCANI_TABLE_FIXTURES_DIR must name tests/fixtures/tables"
#endif

namespace tables = arcani::test::tables;

namespace {

const std::string kFixtures = ARCANI_TABLE_FIXTURES_DIR;

std::vector<std::string> split_tabs(const std::string& line) {
  std::vector<std::string> out;
  std::string::size_type start = 0;
  for (;;) {
    const auto tab = line.find('\t', start);
    out.push_back(line.substr(start, tab == std::string::npos ? std::string::npos : tab - start));
    if (tab == std::string::npos) {
      return out;
    }
    start = tab + 1;
  }
}

struct BadCase {
  std::string file, kind, line, id;
};

std::vector<BadCase> bad_cases() {
  std::ifstream in(kFixtures + "/bad/expected.tsv", std::ios::binary);
  REQUIRE(in.good());
  std::vector<BadCase> out;
  std::string line;
  REQUIRE(std::getline(in, line));
  REQUIRE(line == "file\tkind\tline\tid");
  while (std::getline(in, line)) {
    const auto f = split_tabs(line);
    REQUIRE(f.size() == 4);
    out.push_back({f[0], f[1], f[2], f[3]});
  }
  return out;
}

// Runs fn, requires a TableError, and returns its message.
template <typename Fn>
std::string table_error_message(Fn fn) {
  try {
    fn();
  } catch (const tables::TableError& e) {
    return e.what();
  }
  FAIL("no TableError thrown");
  return {};
}

}  // namespace

TEST_CASE("loader reads the good thresholds fixture", "[tables][loader]") {
  const auto rows = tables::load_table(kFixtures + "/good/thresholds.tsv", "thresholds");
  REQUIRE(rows.size() == 3);
  CHECK(rows[0].id == "fixture-bound");
  CHECK(rows[0].kind == "thresholds");
  CHECK(rows[0].line == 2);
  CHECK(rows[0].unit == "dBFS");
  CHECK(rows[0].value_text == "-120");
  CHECK(rows[0].value() == -120.0);
  CHECK(rows[0].spec_row.empty());
  CHECK(rows[0].pending.empty());

  CHECK(rows[1].id == "fixture-set");
  CHECK(rows[1].value_text == "1 64 512 4096");
  CHECK(rows[1].values == std::vector<double>{1.0, 64.0, 512.0, 4096.0});
  CHECK(rows[1].unit == "frames");
  CHECK_THROWS_AS(rows[1].value(), tables::TableError);

  CHECK(rows[2].id == "fixture-small");
  CHECK(rows[2].line == 4);
  CHECK(rows[2].value_text == "0.01");
  CHECK(rows[2].value() == 0.01);
  CHECK(rows[2].spec_row == "Fixture md row");
  CHECK(rows[2].pending == "9-1-fixture-story");
  CHECK(rows[2].file.find("thresholds.tsv") != std::string::npos);
}

TEST_CASE("loader reads the good ranges fixture", "[tables][loader]") {
  const auto rows = tables::load_table(kFixtures + "/good/ranges.tsv", "ranges");
  REQUIRE(rows.size() == 3);
  CHECK(rows[0].id == "fixture-rate");
  CHECK(rows[0].kind == "ranges");
  CHECK(rows[0].min_text == "1");
  CHECK(rows[0].max_text == "6");
  CHECK(rows[0].min == 1.0);
  CHECK(rows[0].max == 6.0);
  CHECK(rows[0].max_bound == "inclusive");
  CHECK_THROWS_AS(rows[0].value(), tables::TableError);

  CHECK(rows[1].id == "fixture-below");
  CHECK(rows[1].min == 0.0);
  CHECK(rows[1].max == 1000.0);
  CHECK(rows[1].max_bound == "exclusive");

  CHECK(rows[2].id == "fixture-signed");
  CHECK(rows[2].min_text == "-1.5");
  CHECK(rows[2].max_text == "2.25");
  CHECK(rows[2].min == -1.5);
  CHECK(rows[2].max == 2.25);
  CHECK(rows[2].unit == "dB");
  CHECK(rows[2].pending == "9-1-fixture-story");
}

TEST_CASE("load_tables reads thresholds then ranges", "[tables][loader]") {
  const auto rows = tables::load_tables(kFixtures + "/good");
  std::vector<std::string> ids;
  for (const auto& r : rows) {
    ids.push_back(r.id);
  }
  CHECK(ids == std::vector<std::string>{"fixture-bound", "fixture-set", "fixture-small",
                                        "fixture-rate", "fixture-below", "fixture-signed"});
}

TEST_CASE("every bad fixture fails naming file, line, and id", "[tables][loader]") {
  const auto cases = bad_cases();
  REQUIRE(cases.size() >= 8);
  for (const auto& c : cases) {
    INFO(c.file << " (" << c.kind << ") line " << c.line << " id '" << c.id << "'");
    const std::string message =
        table_error_message([&] { tables::load_table(kFixtures + "/bad/" + c.file, c.kind); });
    INFO("message: " << message);
    CHECK(message.find(c.file) != std::string::npos);
    CHECK(message.find(":" + c.line + ":") != std::string::npos);
    if (!c.id.empty()) {
      CHECK(message.find(c.id) != std::string::npos);
    }
  }
}

TEST_CASE("an id in both tables fails", "[tables][loader]") {
  const std::string message =
      table_error_message([] { tables::load_tables(kFixtures + "/dup-across"); });
  INFO("message: " << message);
  CHECK(message.find("fixture-twice") != std::string::npos);
  CHECK(message.find("ranges.tsv") != std::string::npos);
  CHECK(message.find(":3:") != std::string::npos);
}

TEST_CASE("dump_line matches the cross-check format", "[tables][dump]") {
  const auto rows = tables::load_tables(kFixtures + "/good");
  REQUIRE(rows.size() == 6);
  // -120 = 0xc05e000000000000; 1 = 0x3ff0000000000000; 6 = 0x4018000000000000.
  CHECK(tables::dump_line(rows[0]) == "thresholds\tfixture-bound\tdBFS\t-120\tc05e000000000000");
  CHECK(tables::dump_line(rows[3]) ==
        "ranges\tfixture-rate\tHz\t1\t3ff0000000000000\t6\t4018000000000000\tinclusive");
}

TEST_CASE("row returns a known row from the repo tables", "[tables][row]") {
  const auto& r = tables::row("sine-error");
  CHECK(r.id == "sine-error");
  CHECK(r.kind == "thresholds");
  CHECK(r.unit == "dBFS");
  CHECK(&r == &tables::row("sine-error"));
}

TEST_CASE("row throws on an empty or unknown id", "[tables][row]") {
  CHECK_THROWS_AS(tables::row(""), tables::TableError);
  const std::string message = table_error_message([] { tables::row("no-such-row"); });
  CHECK(message.find("no-such-row") != std::string::npos);
}
