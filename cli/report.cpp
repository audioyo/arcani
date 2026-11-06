// The JSON report and the render speed assertion (Story 1.4). See
// report.hpp.

#include "report.hpp"

#include <charconv>
#include <cstring>
#include <system_error>

namespace arcani::cli {

namespace {

const char* result_text(Result r) noexcept {
  switch (r) {
    case Result::pass:
      return "pass";
    case Result::fail:
      return "fail";
    case Result::not_applicable:
      break;
  }
  return "not_applicable";
}

std::string integer(std::uint64_t v) {
  char buf[32];
  const auto r = std::to_chars(buf, buf + sizeof buf, v);
  return std::string(buf, r.ptr);
}

}  // namespace

std::string json_string(std::string_view utf8) {
  static const char kHex[] = "0123456789abcdef";
  std::string out = "\"";
  for (char c : utf8) {
    const auto b = static_cast<unsigned char>(c);
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\b':
        out += "\\b";
        break;
      case '\t':
        out += "\\t";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\f':
        out += "\\f";
        break;
      case '\r':
        out += "\\r";
        break;
      default:
        if (b < 0x20) {
          out += "\\u00";
          out += kHex[b >> 4];
          out += kHex[b & 0xF];
        } else {
          out += c;
        }
    }
  }
  out += '"';
  return out;
}

std::string json_number(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  if (r.ec != std::errc()) {
    return "null";  // not reached: 64 bytes hold any binary64
  }
  return std::string(buf, r.ptr);
}

std::string report_json(const Report& report) {
  const DeterminismKey& key = report.determinism_key;
  std::string out = "{\n";
  out += "  \"engine_version\": " + json_string(report.engine_version) + ",\n";
  out += "  \"seed\": " + integer(report.seed) + ",\n";
  out += "  \"sample_rate\": " + integer(report.sample_rate) + ",\n";
  out += "  \"mode\": " + json_string(report.mode) + ",\n";
  out += "  \"frames\": " + integer(report.frames) + ",\n";
  out += "  \"determinism_key\": {\n";
  out += "    \"recipe_hash\": " + json_string(key.recipe_hash) + ",\n";
  out += "    \"asset_hashes\": [";
  for (std::size_t i = 0; i < key.asset_hashes.size(); ++i) {
    out += (i == 0 ? "" : ", ") + json_string(key.asset_hashes[i]);
  }
  out += "],\n";
  out += "    \"engine_version\": " + json_string(key.engine_version) + ",\n";
  out += "    \"sample_rate\": " + integer(key.sample_rate) + "\n";
  out += "  },\n";
  out += "  \"assertions\": [";
  for (std::size_t i = 0; i < report.assertions.size(); ++i) {
    const Assertion& a = report.assertions[i];
    out += i == 0 ? "\n" : ",\n";
    out += "    {\"name\": " + json_string(a.name);
    out += ", \"row\": " + json_string(a.row);
    out += ", \"threshold\": " + json_number(a.threshold);
    out += ", \"unit\": " + json_string(a.unit);
    out += ", \"measured\": " + (a.measured ? json_number(*a.measured) : std::string("null"));
    out += ", \"result\": " + json_string(result_text(a.result));
    out += ", \"note\": " + json_string(a.note) + "}";
  }
  out += report.assertions.empty() ? "]\n" : "\n  ]\n";
  out += "}\n";
  return out;
}

bool is_reference_machine(const char* env_value) noexcept {
  return env_value != nullptr && std::strcmp(env_value, "1") == 0;
}

double elapsed_seconds(std::chrono::steady_clock::duration total) noexcept {
  using clock = std::chrono::steady_clock;
  const clock::duration counted = total.count() <= 0 ? clock::duration(1) : total;
  return std::chrono::duration<double>(counted).count();
}

Assertion render_speed(const arcani::test::tables::Row& row, std::uint64_t frames,
                       std::uint32_t rate, double elapsed_s, bool is_reference) {
  Assertion a;
  a.name = "render speed";
  a.row = row.id;
  a.threshold = row.value();
  a.unit = row.unit;
  if (frames == 0) {
    a.result = Result::not_applicable;
    a.note = "no frames";
    return a;
  }
  if (!is_reference) {
    a.result = Result::not_applicable;
    a.note = "not the reference machine";
    return a;
  }
  const double measured = (static_cast<double>(frames) / rate) / elapsed_s;
  a.measured = measured;
  a.result = measured >= a.threshold ? Result::pass : Result::fail;
  return a;
}

int assertions_exit_code(const std::vector<Assertion>& assertions) noexcept {
  for (const Assertion& a : assertions) {
    if (a.result == Result::fail) {
      return 4;
    }
  }
  return 0;
}

}  // namespace arcani::cli
