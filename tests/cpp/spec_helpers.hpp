// Lookups over the generated spec tables (spec_tables.hpp). Thresholds and
// ranges are found by id and converted by their unit, so no test carries a
// threshold or range as a literal. An unknown id or unit throws, which fails
// the calling test.

#pragma once

#include "spec_tables.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

namespace arcani::test::spec {

inline const Threshold& threshold(const char* id) {
  for (const Threshold& t : kThresholds) {
    if (std::strcmp(t.id, id) == 0) {
      return t;
    }
  }
  throw std::runtime_error(std::string("no threshold row with id ") + id);
}

inline double unit_to_seconds(double value, const char* unit) {
  if (std::strcmp(unit, "s") == 0) {
    return value;
  }
  if (std::strcmp(unit, "ms") == 0) {
    return value / 1000.0;
  }
  if (std::strcmp(unit, "h") == 0) {
    return value * 3600.0;
  }
  throw std::runtime_error(std::string("not a time unit: ") + unit);
}

inline double unit_to_hz(double value, const char* unit) {
  if (std::strcmp(unit, "Hz") == 0) {
    return value;
  }
  throw std::runtime_error(std::string("not a frequency unit: ") + unit);
}

// Sine error bound as a linear amplitude (full scale 1.0).
inline double sine_error_bound_linear() {
  const Threshold& t = threshold("sine-error");
  if (std::strcmp(t.unit, "dBFS") != 0) {
    throw std::runtime_error(std::string("sine-error unit is not dBFS: ") + t.unit);
  }
  return std::pow(10.0, t.value / 20.0);
}

inline double sine_error_bound_dbfs() {
  const Threshold& t = threshold("sine-error");
  if (std::strcmp(t.unit, "dBFS") != 0) {
    throw std::runtime_error(std::string("sine-error unit is not dBFS: ") + t.unit);
  }
  return t.value;
}

inline double frequency_accuracy_hz() {
  const Threshold& t = threshold("frequency-accuracy");
  return unit_to_hz(t.value, t.unit);
}

inline double drift_bound_seconds() {
  const Threshold& t = threshold("drift-8h");
  return unit_to_seconds(t.value, t.unit);
}

inline double session_length_seconds() {
  return unit_to_seconds(kSessionLengthMax, kSessionLengthUnit);
}

inline const HzRange* find_hz_range(const char* id) {
  for (const HzRange& r : kHzRanges) {
    if (std::strcmp(r.id, id) == 0) {
      return &r;
    }
  }
  return nullptr;
}

}  // namespace arcani::test::spec
