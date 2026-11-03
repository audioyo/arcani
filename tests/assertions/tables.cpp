// Threshold and range table loader and the C++ assertion call (tables.hpp).

#include "tables.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <mutex>
#include <set>

#ifndef ARCANI_TABLES_DIR
#error "ARCANI_TABLES_DIR must name the tests/tables directory"
#endif

namespace arcani::test::tables {

namespace {

const std::vector<std::string> kThresholdColumns = {"id",       "value",  "unit",
                                                    "spec_row", "source", "pending"};
const std::vector<std::string> kRangeColumns = {"id",   "min",      "max",    "max_bound",
                                                "unit", "spec_row", "source", "pending"};

[[noreturn]] void fail(const std::string& file, int line, const std::string& what,
                       const std::string& reason) {
  throw TableError(file + ":" + std::to_string(line) + ": " + what + ": " + reason);
}

std::vector<std::string> split(const std::string& s, char sep) {
  std::vector<std::string> out;
  std::string::size_type start = 0;
  while (true) {
    const auto pos = s.find(sep, start);
    if (pos == std::string::npos) {
      out.push_back(s.substr(start));
      return out;
    }
    out.push_back(s.substr(start, pos - start));
    start = pos + 1;
  }
}

bool is_digit(char c) { return c >= '0' && c <= '9'; }

// -?(0|[1-9][0-9]*)(\.[0-9]+)?
bool is_number(const std::string& s) {
  std::size_t i = 0;
  if (i < s.size() && s[i] == '-') {
    ++i;
  }
  if (i >= s.size() || !is_digit(s[i])) {
    return false;
  }
  if (s[i] == '0') {
    ++i;
  } else {
    while (i < s.size() && is_digit(s[i])) {
      ++i;
    }
  }
  if (i < s.size() && s[i] == '.') {
    ++i;
    if (i >= s.size() || !is_digit(s[i])) {
      return false;
    }
    while (i < s.size() && is_digit(s[i])) {
      ++i;
    }
  }
  return i == s.size();
}

// [a-z0-9]+(-[a-z0-9]+)*
bool is_kebab(const std::string& s) {
  if (s.empty() || s.front() == '-' || s.back() == '-') {
    return false;
  }
  for (std::size_t i = 0; i < s.size(); ++i) {
    const char c = s[i];
    const bool ok = (c >= 'a' && c <= 'z') || is_digit(c) || c == '-';
    if (!ok || (c == '-' && s[i + 1] == '-')) {
      return false;
    }
  }
  return true;
}

bool is_blank(const std::string& s) {
  return std::all_of(s.begin(), s.end(),
                     [](char c) { return c == ' ' || c == '\t' || c == '\r'; });
}

// Correctly rounded decimal to binary64 (strtod in the default "C" locale;
// the text is already checked to be a plain decimal number).
double parse_number(const std::string& file, int line, const std::string& id,
                    const std::string& column, const std::string& text) {
  if (!is_number(text)) {
    fail(file, line, id, column + " is not a number: '" + text + "'");
  }
  return std::strtod(text.c_str(), nullptr);
}

std::string bits_hex(double v) {
  std::uint64_t bits = 0;
  std::memcpy(&bits, &v, sizeof bits);
  char buf[17];
  std::snprintf(buf, sizeof buf, "%016llx", static_cast<unsigned long long>(bits));
  return buf;
}

}  // namespace

double Row::value() const {
  if (kind != "thresholds") {
    throw TableError(file + ":" + std::to_string(line) + ": " + id +
                     ": a range row has no single value");
  }
  if (values.size() != 1) {
    throw TableError(file + ":" + std::to_string(line) + ": " + id +
                     ": a set has no single value");
  }
  return values.front();
}

std::vector<Row> load_table(const std::string& path, const std::string& kind) {
  const std::vector<std::string>* columns = nullptr;
  if (kind == "thresholds") {
    columns = &kThresholdColumns;
  } else if (kind == "ranges") {
    columns = &kRangeColumns;
  } else {
    throw std::invalid_argument("unknown table kind: " + kind);
  }
  const std::string file = std::filesystem::path(path).filename().string();
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    fail(file, 0, "file", "cannot read " + path);
  }
  std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  if (!text.empty() && text.back() == '\n') {
    text.pop_back();
  }
  const std::vector<std::string> lines = split(text, '\n');
  const std::vector<std::string> header =
      lines.front().empty() ? std::vector<std::string>{} : split(lines.front(), '\t');
  for (const std::string& column : *columns) {
    if (std::find(header.begin(), header.end(), column) == header.end()) {
      fail(file, 1, column, "missing column");
    }
  }
  if (header != *columns) {
    fail(file, 1, "header", "columns are not in the required order");
  }

  std::vector<Row> rows;
  std::set<std::string> seen;
  for (std::size_t k = 1; k < lines.size(); ++k) {
    const int number = static_cast<int>(k) + 1;
    const std::string& raw = lines[k];
    const std::vector<std::string> fields = split(raw, '\t');
    const std::string& id = fields.front();
    if (!raw.empty() && raw.back() == '\r') {
      fail(file, number, id.empty() ? "row" : id, "CR line end");
    }
    if (is_blank(raw)) {
      fail(file, number, "row", "blank line");
    }
    if (fields.size() != columns->size()) {
      fail(file, number, id,
           std::to_string(fields.size()) + " fields, expected " +
               std::to_string(columns->size()) + " (missing column)");
    }
    std::map<std::string, std::string> f;
    for (std::size_t c = 0; c < columns->size(); ++c) {
      f[(*columns)[c]] = fields[c];
    }
    if (!is_kebab(id)) {
      fail(file, number, id.empty() ? "row" : id, "id is not kebab-case");
    }
    if (!seen.insert(id).second) {
      fail(file, number, id, "duplicate id");
    }
    if (is_blank(f["source"])) {
      fail(file, number, id, "empty source");
    }
    Row r;
    r.kind = kind;
    r.id = id;
    r.unit = f["unit"];
    r.spec_row = f["spec_row"];
    r.source = f["source"];
    r.pending = f["pending"];
    r.file = file;
    r.line = number;
    if (kind == "thresholds") {
      r.value_text = f["value"];
      for (const std::string& member : split(r.value_text, ' ')) {
        r.values.push_back(parse_number(file, number, id, "value", member));
      }
    } else {
      r.min_text = f["min"];
      r.max_text = f["max"];
      r.min = parse_number(file, number, id, "min", r.min_text);
      r.max = parse_number(file, number, id, "max", r.max_text);
      if (r.min > r.max) {
        fail(file, number, id, "min " + r.min_text + " is above max " + r.max_text);
      }
      r.max_bound = f["max_bound"];
      if (r.max_bound != "inclusive" && r.max_bound != "exclusive") {
        fail(file, number, id,
             "max_bound must be inclusive or exclusive: '" + r.max_bound + "'");
      }
    }
    rows.push_back(std::move(r));
  }
  return rows;
}

std::vector<Row> load_tables(const std::string& dir) {
  std::vector<Row> all;
  std::map<std::string, std::size_t> index;
  for (const char* kind : {"thresholds", "ranges"}) {
    const std::string path = (std::filesystem::path(dir) / (std::string(kind) + ".tsv")).string();
    for (Row& r : load_table(path, kind)) {
      const auto it = index.find(r.id);
      if (it != index.end()) {
        const Row& first = all[it->second];
        fail(r.file, r.line, r.id,
             "duplicate id, also " + first.file + ":" + std::to_string(first.line));
      }
      index[r.id] = all.size();
      all.push_back(std::move(r));
    }
  }
  return all;
}

std::string dump_line(const Row& r) {
  std::string out;
  if (r.kind == "thresholds") {
    std::string bits;
    for (std::size_t i = 0; i < r.values.size(); ++i) {
      if (i > 0) {
        bits += ' ';
      }
      bits += bits_hex(r.values[i]);
    }
    out = "thresholds\t" + r.id + "\t" + r.unit + "\t" + r.value_text + "\t" + bits;
  } else {
    out = "ranges\t" + r.id + "\t" + r.unit + "\t" + r.min_text + "\t" + bits_hex(r.min) + "\t" +
          r.max_text + "\t" + bits_hex(r.max) + "\t" + r.max_bound;
  }
  return out;
}

namespace {

struct Registry {
  std::vector<Row> rows;
  std::set<std::string> used;
  std::mutex mutex;
};

Registry& registry() {
  static Registry* r = [] {
    auto* reg = new Registry;
    reg->rows = load_tables(ARCANI_TABLES_DIR);
    return reg;
  }();
  return *r;
}

void write_usage(const std::set<std::string>& used) {
  const char* target = std::getenv("ARCANI_ROW_USAGE_FILE");
  if (target == nullptr || *target == '\0') {
    return;
  }
  const std::filesystem::path path(target);
  std::error_code ec;
  if (path.has_parent_path()) {
    std::filesystem::create_directories(path.parent_path(), ec);
  }
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  if (!out) {
    throw std::runtime_error(std::string("cannot write row usage file ") + target);
  }
  for (const std::string& id : used) {
    out << id << '\n';
  }
}

}  // namespace

const Row& row(std::string_view id) {
  if (id.empty()) {
    throw TableError("assertion asked for an empty row id");
  }
  Registry& reg = registry();
  for (const Row& r : reg.rows) {
    if (r.id == id) {
      std::lock_guard<std::mutex> lock(reg.mutex);
      if (reg.used.insert(r.id).second) {
        write_usage(reg.used);
      }
      return r;
    }
  }
  throw TableError("no threshold or range row with id '" + std::string(id) + "'");
}

}  // namespace arcani::test::tables
