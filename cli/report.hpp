// The JSON report and the render speed assertion for arcani-render
// (Story 1.4).

#ifndef ARCANI_CLI_REPORT_HPP
#define ARCANI_CLI_REPORT_HPP

#include "tables.hpp"

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace arcani::cli {

enum class Result { pass, fail, not_applicable };

struct Assertion {
  std::string name;                // "render speed"
  std::string row;                 // table row id, "render-speed"
  double threshold = 0.0;          // the row's value
  std::string unit;                // the row's unit
  std::optional<double> measured;  // empty: written as null
  Result result = Result::not_applicable;
  std::string note;  // empty unless not_applicable
};

struct DeterminismKey {
  std::string recipe_hash;                // 64 lowercase hex digits
  std::vector<std::string> asset_hashes;  // empty in v0.1
  std::string engine_version;
  std::uint32_t sample_rate = 0;
};

struct Report {
  std::string engine_version;
  std::uint64_t seed = 0;
  std::uint32_t sample_rate = 0;
  std::string mode;  // "measure" or "final"
  std::uint64_t frames = 0;
  DeterminismKey determinism_key;
  std::vector<Assertion> assertions;
};

// A JSON string literal, quotes included. Escapes " and \, \b \t \n \f \r,
// every other byte below 0x20 as \u00xx (lowercase hex); nothing else.
std::string json_string(std::string_view utf8);

// Shortest round-trip text of a finite double (std::to_chars).
std::string json_number(double x);

// The report as one UTF-8 JSON object, members in struct order.
std::string report_json(const Report& report);

// True only when the value of ARCANI_REFERENCE_MACHINE (nullptr when unset)
// is exactly "1".
bool is_reference_machine(const char* env_value) noexcept;

// The summed arc_render time in seconds; a total of 0 ticks counts as 1.
double elapsed_seconds(std::chrono::steady_clock::duration total) noexcept;

// The render speed assertion against `row` (render-speed). frames == 0 is
// not applicable ("no frames"), checked first; then a machine other than
// the reference one ("not the reference machine"); else measured =
// (frames / rate) / elapsed_s, pass when measured >= threshold.
Assertion render_speed(const arcani::test::tables::Row& row, std::uint64_t frames,
                       std::uint32_t rate, double elapsed_s, bool is_reference);

// 4 when any assertion failed, else 0.
int assertions_exit_code(const std::vector<Assertion>& assertions) noexcept;

}  // namespace arcani::cli

#endif  // ARCANI_CLI_REPORT_HPP
