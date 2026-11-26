// The stored loudness gain's tooling for arcani-render --store-gain
// (Story 4.2; docs/signal-spec.md, Loudness gain: Gain rounding, File
// rewrite): the gain step from a window reading, the gain text, the
// top-level member scanner, and the rewrite of the two loudness members.
// Outside engine/: it reads the recipe bytes only after the engine has
// accepted them, and never includes engine/src.

#ifndef ARCANI_CLI_RECIPE_WRITE_HPP
#define ARCANI_CLI_RECIPE_WRITE_HPP

#include "tables.hpp"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace arcani::cli {

// One top-level member of the root object, as byte offsets into the text:
// the lead [lead_begin, key_begin) (whitespace after the preceding '{' or
// ','), the key token with its quotes [key_begin, key_end), the separator
// [key_end, value_begin) (whitespace, ':', whitespace), and the value token
// [value_begin, value_end). name is the key after JSON unescaping.
struct Member {
  std::string name;
  std::size_t lead_begin = 0;
  std::size_t key_begin = 0;
  std::size_t key_end = 0;
  std::size_t value_begin = 0;
  std::size_t value_end = 0;
};

// Every top-level member in file order. Throws std::invalid_argument unless
// the text is one JSON object (whitespace around it allowed).
std::vector<Member> top_level_members(std::string_view accepted_json);

// The value of a top-level member read with strtod in the "C" locale
// (correctly rounded); empty when the member is absent or its value is not a number.
std::optional<double> top_level_number(std::string_view accepted_json, std::string_view name);

// The file rewrite: a present loudness_gain_db or loudness_hash gets the new
// value text in place; the missing ones are inserted as one run right after
// the value of loudness_target_lufs, each as "," + its lead + the name +
// its separator + the value. Every other byte is kept. Throws
// std::invalid_argument when the text is not one object or has no
// loudness_target_lufs.
std::string rewrite_loudness_members(std::string_view accepted_json, std::string_view gain_text,
                                     std::string_view loudness_hash);

// k / 100 with exactly two decimals: "-35.27", "-0.05", "0.00".
std::string gain_text(std::int64_t k);

// The gain rounding of one window reading (Gain rounding). k is the
// rounded step whenever x = 100 * (target - window) is finite (stored or
// rejected), 0 when it is not; gain_text is set only when stored; value,
// rule, and limit only on a rejection (parameter /loudness_gain_db).
struct GainStep {
  bool stored = false;
  std::int64_t k = 0;
  std::string gain_text;
  std::string value;
  std::string rule;
  std::string limit;
};

// Throws TableError unless gain_row is a ranges row in dB with finite
// bounds. The limits come from its min_text and max_text, for example
// ">= -60 dB (row loudness-gain)".
GainStep gain_step(double window_lufs, double target_lufs, const arcani::test::tables::Row& gain_row);

// Story 4.3 (docs/signal-spec.md, True peak, Store step): the store's
// true-peak decision for the final-mode render of the new bytes. dbtp is
// 20 log10(tp_linear) (-infinity at 0). Stored when dbtp <= the row's value;
// otherwise line is "rejected: parameter=/loudness_gain_db value=<gain_text>
// rule=true_peak limit=<= <value> dBTP (row <id>) target_lufs=<T>
// true_peak_dbtp=<dbtp>" (T and dbtp as shortest round-trip texts). line is
// empty when stored. Throws TableError unless row is a thresholds row in
// dBTP with one finite value.
struct TruePeakStep {
  bool stored = false;
  double dbtp = 0.0;
  std::string line;
};

TruePeakStep true_peak_step(const arcani::test::tables::Row& row, double tp_linear, double target_lufs,
                            std::string_view gain_text);

}  // namespace arcani::cli

#endif  // ARCANI_CLI_RECIPE_WRITE_HPP
