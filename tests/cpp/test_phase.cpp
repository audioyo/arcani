// Phase accumulator, phase increment rule, and seconds-to-samples rule
// (docs/signal-spec.md, Core). Vectors come from tests/data/signal_spec_vectors.json
// through the generated spec_tables.hpp, and bounds and ranges from
// tests/tables/*.tsv through the assertion call (spec_helpers.hpp); no value
// here is a literal copy of a table.

#include "core/phase.hpp"
#include "core/sine.hpp"
#include "spec_helpers.hpp"

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

namespace spec = arcani::test::spec;
using arcani::core::phase_increment;
using arcani::core::seconds_to_samples;
using arcani::core::SineOscillator;

static_assert(noexcept(phase_increment(1.0, 44100u)), "phase_increment must be noexcept");
static_assert(noexcept(seconds_to_samples(1.0, 44100u)), "seconds_to_samples must be noexcept");

TEST_CASE("phase_increment matches every increment vector", "[core][phase][vectors]") {
  REQUIRE(sizeof(spec::kIncrements) / sizeof(spec::kIncrements[0]) > 0);
  for (const auto& v : spec::kIncrements) {
    INFO(v.label << " at " << v.fs << " Hz sample rate");
    CHECK(phase_increment(v.f_hz, v.fs) == v.inc);
  }
}

TEST_CASE("phase_increment ties go to the even neighbour", "[core][phase][vectors]") {
  int ties = 0;
  for (const auto& v : spec::kIncrements) {
    if (std::strncmp(v.label, "tie:", 4) != 0) {
      continue;
    }
    ++ties;
    INFO(v.label << " at " << v.fs << " Hz sample rate");
    const std::uint64_t inc = phase_increment(v.f_hz, v.fs);
    CHECK(inc == v.inc);
    CHECK(inc % 2 == 0);
  }
  REQUIRE(ties > 0);
}

TEST_CASE("phase_increment gives 0 outside its domain", "[core][phase][vectors]") {
  int cases = 0;
  for (const auto& v : spec::kIncrements) {
    if (std::strncmp(v.label, "out_of_range:", 13) != 0) {
      continue;
    }
    ++cases;
    INFO(v.label << " at " << v.fs << " Hz sample rate");
    CHECK(v.inc == 0);
    CHECK(phase_increment(v.f_hz, v.fs) == 0);
  }
  REQUIRE(cases > 0);
}

TEST_CASE("seconds_to_samples matches every samples vector", "[core][samples][vectors]") {
  REQUIRE(sizeof(spec::kSamples) / sizeof(spec::kSamples[0]) > 0);
  for (const auto& v : spec::kSamples) {
    INFO(v.label << " at " << v.fs << " Hz sample rate");
    CHECK(seconds_to_samples(v.t_s, v.fs) == v.n);
  }
}

TEST_CASE("phase steps wrap modulo 2^64", "[core][phase][vectors]") {
  for (const auto& v : spec::kPhaseSteps) {
    INFO(v.label);
    // The accumulator rule in closed form: uint64 arithmetic wraps mod 2^64.
    CHECK(static_cast<std::uint64_t>(v.start + v.steps * v.inc) == v.phase);
    // The oscillator's own accumulator, step by step, where the step count
    // keeps the test fast. The 8-hour vector is covered by the closed form
    // above and by the 8-hour carrier sample in test_sine.cpp.
    if (v.steps <= (UINT64_C(1) << 20)) {
      SineOscillator osc(v.inc, v.start);
      REQUIRE(osc.phase() == v.start);
      REQUIRE(osc.increment() == v.inc);
      for (std::uint64_t k = 0; k < v.steps; ++k) {
        (void)osc.next();
      }
      CHECK(osc.phase() == v.phase);
    }
  }
}

// ------------------------------------------------- quantization and drift

namespace {

struct GridResult {
  double max_error_hz = 0.0;
  double max_drift_s = 0.0;
  double worst_error_f = 0.0;
  double worst_drift_f = 0.0;
  std::uint64_t points = 0;
  bool zero_gives_zero = true;
};

// Walks a 0.001 Hz grid from range.min to range.max (both included). Grid
// point k is (round(min * 1000) + k) / 1000, the binary64 nearest to that
// decimal frequency. For each point the engine's own increment (plus
// `offset`, which only the must-fail cases set) gives the played frequency
// f_q = inc * fs / 2^64, the error |f_q - f|, and the drift |f_q - f| * T / f
// for f > 0. Measuring in binary64 adds at most a few units in the last place
// of f (about 1e-13 Hz at 1030 Hz), 11 orders below the 0.01 Hz bound.
GridResult measure_grid(const spec::Row& range, std::uint32_t fs, double session_s,
                        std::uint64_t offset) {
  GridResult r;
  const long long lo = std::llround(range.min * 1000.0);
  const long long hi = std::llround(range.max * 1000.0);
  for (long long m = lo; m <= hi; ++m) {
    const double f = static_cast<double>(m) / 1000.0;
    const std::uint64_t inc = phase_increment(f, fs) + offset;
    ++r.points;
    if (f == 0.0) {
      if (offset == 0 && inc != 0) {
        r.zero_gives_zero = false;
      }
      continue;
    }
    const double f_q = static_cast<double>(inc) * static_cast<double>(fs) / 0x1p64;
    const double err = std::fabs(f_q - f);
    const double drift = err * session_s / f;
    if (err > r.max_error_hz) {
      r.max_error_hz = err;
      r.worst_error_f = f;
    }
    if (drift > r.max_drift_s) {
      r.max_drift_s = drift;
      r.worst_drift_f = f;
    }
  }
  return r;
}

const char* const kRequiredHzRanges[] = {
    "theta-rate", "theta-carrier", "gamma-rate", "gamma-carrier",
    "binaural-carrier", "binaural-carrier-right", "beat-rate",
};

}  // namespace

TEST_CASE("range table has every carrier and rate row in Hz", "[core][phase][ranges]") {
  for (const char* id : kRequiredHzRanges) {
    INFO("range row " << id);
    const spec::Row& r = spec::hz_range(id);
    CHECK(r.min >= 0.0);
    CHECK(r.max > r.min);
  }
  REQUIRE(spec::sample_rates().size() >= 2);
  REQUIRE(spec::session_length_seconds() > 0.0);
}

TEST_CASE("quantization error and 8-hour drift stay inside the bounds on a 0.001 Hz grid",
          "[core][phase][accuracy]") {
  const double accuracy = spec::frequency_accuracy_hz();
  const double drift_bound = spec::drift_bound_seconds();
  const double session = spec::session_length_seconds();
  for (const char* id : kRequiredHzRanges) {
    const spec::Row& range = spec::hz_range(id);
    for (const std::uint32_t fs : spec::sample_rates()) {
      const GridResult r = measure_grid(range, fs, session, 0);
      INFO(range.id << " " << range.min << " to " << range.max << " Hz at " << fs
                    << " Hz sample rate: " << r.points << " points, max error "
                    << r.max_error_hz << " Hz at " << r.worst_error_f << " Hz, max drift "
                    << r.max_drift_s << " s at " << r.worst_drift_f << " Hz");
      CHECK(r.points > 0);
      CHECK(r.zero_gives_zero);
      CHECK(r.max_error_hz < accuracy);
      CHECK(r.max_drift_s < drift_bound);
    }
  }
}

TEST_CASE("must fail: a doctored increment breaks the frequency accuracy bound",
          "[core][phase][accuracy][mustfail]") {
  const double accuracy = spec::frequency_accuracy_hz();
  const double session = spec::session_length_seconds();
  const spec::Row& range = spec::hz_range(kRequiredHzRanges[0]);
  for (const std::uint32_t fs : spec::sample_rates()) {
    // Two times the bound, in phase units.
    const auto offset = static_cast<std::uint64_t>(
        std::ceil(2.0 * accuracy * 0x1p64 / static_cast<double>(fs)));
    const GridResult r = measure_grid(range, fs, session, offset);
    INFO(range.id << " at " << fs << " Hz sample rate, offset " << offset);
    CHECK(r.max_error_hz >= accuracy);
  }
}

TEST_CASE("must fail: a doctored increment breaks the drift bound alone",
          "[core][phase][accuracy][mustfail]") {
  const double accuracy = spec::frequency_accuracy_hz();
  const double drift_bound = spec::drift_bound_seconds();
  const double session = spec::session_length_seconds();
  const spec::Row& range = spec::hz_range("binaural-carrier-right");
  for (const std::uint32_t fs : spec::sample_rates()) {
    // A frequency error of twice the drift bound at the top of the range:
    // 2 * drift * f_max / T Hz, well inside the accuracy bound.
    const double err_hz = 2.0 * drift_bound * range.max / session;
    REQUIRE(err_hz < accuracy);
    const auto offset =
        static_cast<std::uint64_t>(std::ceil(err_hz * 0x1p64 / static_cast<double>(fs)));
    const GridResult r = measure_grid(range, fs, session, offset);
    INFO(range.id << " at " << fs << " Hz sample rate, offset " << offset);
    CHECK(r.max_error_hz < accuracy);
    CHECK(r.max_drift_s >= drift_bound);
  }
}
