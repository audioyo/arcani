// Gain ramp law (docs/signal-spec.md, Gain ramps, Law).

#include "core/gain.hpp"

#include "core/envelope.hpp"
#include "core/sine.hpp"

namespace arcani::core {

double gain_ramp(double a, double b, std::uint64_t k, std::uint64_t length) noexcept {
  constexpr std::uint64_t kQuarter = std::uint64_t{1} << 62;  // sine(p + 2^62) is cos(p)
  const double r = static_cast<double>(k) / static_cast<double>(length);
  const std::uint64_t p = ratio_to_phase(r);
  const double c = sine(p + kQuarter);  // mod 2^64
  const double h = (1.0 - c) * 0.5;
  return a + (b - a) * h;
}

}  // namespace arcani::core
