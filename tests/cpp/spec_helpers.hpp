// Lookups for the C++ tests. Spec vectors come from the generated
// spec_tables.hpp (tests/data/signal_spec_vectors.json); thresholds and
// ranges come from tests/tables/*.tsv through the assertion call
// arcani::test::tables::row (tests/assertions/tables.hpp), which records each
// row id for the coverage check. Values are converted by their unit, so no
// test carries a threshold or range as a literal. An unknown id or unit
// throws, which fails the calling test.

#pragma once

#include "spec_tables.hpp"
#include "tables.hpp"

#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace arcani::test::spec {

using tables::Row;

inline const Row& row(const char* id) { return tables::row(id); }

inline double unit_to_seconds(double value, const std::string& unit) {
  if (unit == "s") {
    return value;
  }
  if (unit == "ms") {
    return value / 1000.0;
  }
  if (unit == "h") {
    return value * 3600.0;
  }
  throw std::runtime_error("not a time unit: " + unit);
}

inline double unit_to_hz(double value, const std::string& unit) {
  if (unit == "Hz") {
    return value;
  }
  throw std::runtime_error("not a frequency unit: " + unit);
}

inline const Row& dbfs_row(const char* id) {
  const Row& r = row(id);
  if (r.unit != "dBFS") {
    throw std::runtime_error(std::string(id) + " unit is not dBFS: " + r.unit);
  }
  return r;
}

// Sine error bound as a linear amplitude (full scale 1.0).
inline double sine_error_bound_linear() {
  return std::pow(10.0, dbfs_row("sine-error").value() / 20.0);
}

inline double sine_error_bound_dbfs() { return dbfs_row("sine-error").value(); }

inline double frequency_accuracy_hz() {
  const Row& r = row("frequency-accuracy");
  return unit_to_hz(r.value(), r.unit);
}

inline double drift_bound_seconds() {
  const Row& r = row("drift-8h");
  return unit_to_seconds(r.value(), r.unit);
}

inline double session_length_seconds() {
  const Row& r = row("session-length");
  return unit_to_seconds(r.max, r.unit);
}

// A locked-range row whose unit is Hz.
inline const Row& hz_range(const char* id) {
  const Row& r = row(id);
  if (r.kind != "ranges") {
    throw std::runtime_error(std::string(id) + " is not a range row");
  }
  unit_to_hz(0.0, r.unit);
  return r;
}

inline std::vector<std::uint32_t> sample_rates() {
  const Row& r = row("sample-rates");
  unit_to_hz(0.0, r.unit);
  std::vector<std::uint32_t> out;
  for (const double v : r.values) {
    out.push_back(static_cast<std::uint32_t>(v));
  }
  return out;
}

}  // namespace arcani::test::spec
