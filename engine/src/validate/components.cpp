// Spectral component table (Story 3.1). Every formula is from
// docs/signal-spec.md, Components; the comments name the paragraph.

#include "validate/components.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <initializer_list>
#include <string>
#include <utility>

#include "core/envelope.hpp"
#include "core/rate_cycle.hpp"
#include "validate/validate.hpp"

namespace arcani::validate {

namespace {

constexpr double kPi = 0x1.921fb54442d18p+1;
constexpr std::uint64_t kQuarter = std::uint64_t{1} << 62;

// The search bounds stop where no further line can reach the threshold. They
// are compared with this slack, so a rounding of the bound can only make the
// search look one term further; the level test decides every row.
constexpr double kSearchSlack = 1.0 + 0x1p-20;

// cos(2 pi x) and sin(2 pi x) for x in cycles (Components, Engine).
double cos2pi(double x) noexcept { return core::cycle_cosine(core::cycles_to_units(x)); }
double sin2pi(double x) noexcept { return core::cycle_cosine(core::cycles_to_units(x) - kQuarter); }

// sin(pi y) and cos(pi y).
double sin_pi(double y) noexcept { return sin2pi(y * 0.5); }
double cos_pi(double y) noexcept { return cos2pi(y * 0.5); }

// P(k, w) = cos(pi k w) / (1 - (2 k w)^2), pi / 4 at 2 k w = 1, in the
// stable form near 2 k w = 1 (Components, Engine).
double edge_factor(double k, double w) noexcept {
  const double x = 2.0 * k * w;
  const double delta = x - 1.0;
  if (std::fabs(delta) >= 0x1p-5) {
    return cos_pi(k * w) / (1.0 - x * x);
  }
  const double y = (kPi / 2.0) * delta;
  const double y2 = y * y;
  const double s = 1.0 - y2 / 6.0 + (y2 * y2) / 120.0 - (y2 * y2 * y2) / 5040.0;
  return (kPi / 2.0) * s / (2.0 + delta);
}

// Pb(k, w) >= |P(k, w)| (Components, Search bound).
double edge_factor_bound(double k, double w) noexcept {
  const double x = 2.0 * k * w;
  const double x2 = x * x;
  return x2 <= 2.0 ? 1.0 : 1.0 / (x2 - 1.0);
}

// The smoothed on-off form of half on share h and edge share w: signed c_k.
double on_off_coefficient(int k, double h, double w) noexcept {
  const double width = 2.0 * h - w;
  if (k == 0) {
    return width;
  }
  const double kk = static_cast<double>(k < 0 ? -k : k);
  return sin_pi(kk * width) / (kPi * kk) * edge_factor(kk, w);
}

double on_off_bound(int k, double w) noexcept {
  const double kk = static_cast<double>(k);
  return edge_factor_bound(kk, w) / (kPi * kk);
}

// |c_k| of the sawtooth and the reverse saw, edge share w.
double sawtooth_coefficient(int k, double w) noexcept {
  if (k == 0) {
    return 0.5;
  }
  const double kk = static_cast<double>(k < 0 ? -k : k);
  const double pk = kPi * kk;
  return std::fabs(edge_factor(kk, w) + sin_pi(kk * w) / (pk * (1.0 - w))) / (2.0 * pk);
}

double sawtooth_bound(int k, double w) noexcept {
  const double kk = static_cast<double>(k);
  const double pk = kPi * kk;
  return (edge_factor_bound(kk, w) + 1.0 / (pk * (1.0 - w))) / (2.0 * pk);
}

bool has_cycle(const std::optional<recipe::RateCycle>& c) noexcept { return c && c->swing_hz > 0.0; }

// A line of one layer: gamma_mult i, theta_mult j, amplitude.
struct Line {
  std::int32_t i;
  std::int32_t j;
  double amp;
};

std::vector<Line> theta_lines(const recipe::ThetaReference& t) {
  const double d = t.am_depth_percent / 100.0;
  const double w = (core::kThetaEdgeMs / 1000.0) * t.rate_hz;
  std::vector<Line> out;
  if (t.shape == recipe::ThetaShape::Sine) {
    out.push_back({0, 0, 1.0 - d / 2.0});
    out.push_back({0, 1, d / 4.0});
    out.push_back({0, -1, d / 4.0});
    return out;
  }
  const bool on_off = t.shape == recipe::ThetaShape::SmoothedOnOff;
  const double c0 = on_off ? on_off_coefficient(0, 0.25, w) : 0.5;
  const double carrier = 1.0 - d + d * c0;
  out.push_back({0, 0, carrier});
  for (int k = 1;; ++k) {
    const double bound = on_off ? on_off_bound(k, w) : sawtooth_bound(k, w);
    if (!(d * bound * kSearchSlack >= kComponentThreshold * carrier)) {
      break;
    }
    const double c = on_off ? std::fabs(on_off_coefficient(k, 0.25, w)) : sawtooth_coefficient(k, w);
    out.push_back({0, k, d * c});
    out.push_back({0, -k, d * c});
  }
  return out;
}

struct Complex {
  double re;
  double im;
};

std::vector<Line> gamma_lines(const recipe::GammaPac& g, const recipe::ThetaReference* theta) {
  const double d = g.am_depth_percent / 100.0;
  std::vector<Line> out;
  if (g.coupling == recipe::GammaCoupling::Uncoupled) {
    out.push_back({0, 0, 1.0 - d / 2.0});
    out.push_back({1, 0, d / 4.0});
    out.push_back({-1, 0, d / 4.0});
    return out;
  }
  if (d == 0.0 || theta == nullptr) {
    // Gamma depth 0 (any theta reference), or no theta_reference field, which
    // compile accepts for coupled gamma only at depth 0: the carrier alone.
    out.push_back({0, 0, 1.0});
    return out;
  }
  if (g.coupling == recipe::GammaCoupling::SmoothSwell) {
    out.push_back({0, 0, 1.0 - d / 4.0});
    for (const std::int32_t j : {1, -1}) {
      out.push_back({0, j, d / 8.0});
    }
    for (const std::int32_t i : {1, -1}) {
      out.push_back({i, 0, d / 8.0});
    }
    for (const std::int32_t i : {1, -1}) {
      for (const std::int32_t j : {1, -1}) {
        out.push_back({i, j, d / 16.0});
      }
    }
    return out;
  }
  // Bursts (Components, Gamma PAC layer, bursts).
  const double theta_rate = theta->rate_hz;
  const double h = (core::kBurstWidthMs / 1000.0 / 2) * theta_rate;
  const double w = (core::kBurstEdgeMs / 1000.0) * theta_rate;
  const std::uint64_t c_units = g.coupling_phase_deg ? core::coupling_phase_units(*g.coupling_phase_deg) : 0;
  std::vector<double> gate;  // g_|j|, filled on demand
  auto gj = [&](int j) {
    const auto a = static_cast<std::size_t>(j < 0 ? -j : j);
    while (gate.size() <= a) {
      gate.push_back(on_off_coefficient(static_cast<int>(gate.size()), h, w));
    }
    return gate[a];
  };
  auto last_j = [&](double scale, double carrier) {
    int j = 0;
    while (scale * on_off_bound(j + 1, w) * kSearchSlack >= kComponentThreshold * carrier) {
      ++j;
    }
    return j;
  };
  auto rotated = [&](int j, double scale) {
    const std::uint64_t units = static_cast<std::uint64_t>(static_cast<std::int64_t>(j)) * c_units;
    const double v = scale * gj(j);
    return Complex{v * core::cycle_cosine(units), -v * core::cycle_cosine(units - kQuarter)};
  };
  auto magnitude = [](std::initializer_list<Complex> parts) {
    double re = 0.0;
    double im = 0.0;
    for (const Complex& p : parts) {
      re += p.re;
      im += p.im;
    }
    return std::sqrt(re * re + im * im);
  };

  // Twice the gamma rate a whole multiple of the theta rate, no cycle on either.
  int n2 = 0;
  bool summed = false;
  if (!has_cycle(g.rate_cycle) && !has_cycle(theta->rate_cycle)) {
    const double two = 2.0 * g.rate_hz;
    const double q = two / theta_rate;
    // The cap 2^30 keeps n2 an int; no locked rate pair comes near it
    // (Components, Bursts, lines at one frequency).
    if (q > 0.0 && is_whole(q) && q * theta_rate == two && q < 0x1p30) {
      n2 = static_cast<int>(q);
      summed = n2 > 0;
    }
  }
  if (summed && n2 % 2 == 0) {
    const int n = n2 / 2;
    auto line = [&](int m) {
      const Complex a = rotated(m, -d / 2.0);
      const Complex b = rotated(m - n, d / 4.0);
      const Complex c = rotated(m + n, d / 4.0);
      if (m == 0) {
        return magnitude({a, b, c, Complex{1.0, 0.0}});
      }
      return magnitude({a, b, c});
    };
    const double carrier = line(0);
    out.push_back({0, 0, carrier});
    const int last = n + last_j(d, carrier);
    for (int m = -last; m <= last; ++m) {
      if (m != 0) {
        out.push_back({0, m, line(m)});
      }
    }
    return out;
  }
  const double carrier = 1.0 - d * gj(0) / 2.0;
  out.push_back({0, 0, carrier});
  const int last = last_j(d / 2.0, carrier);
  for (int j = -last; j <= last; ++j) {
    if (j != 0) {
      out.push_back({0, j, d * std::fabs(gj(j)) / 2.0});
    }
  }
  if (!summed) {
    for (int j = -last; j <= last; ++j) {
      for (const std::int32_t i : {1, -1}) {
        out.push_back({i, j, d * std::fabs(gj(j)) / 4.0});
      }
    }
    return out;
  }
  // n2 odd: the line at f_G + f_M + j f_theta sums (1, j) and (-1, j + n2).
  for (int j = -n2 - last; j <= last; ++j) {
    const double amp = magnitude({rotated(j, d / 4.0), rotated(j + n2, d / 4.0)});
    const int other = j + n2;
    if ((j < 0 ? -j : j) < (other < 0 ? -other : other)) {
      out.push_back({1, j, amp});
    } else {
      out.push_back({-1, other, amp});
    }
  }
  return out;
}

// A row's (center, low, high) after the below-0 Hz rule (Components,
// Frequencies below 0).
struct Span {
  double center;
  double low;
  double high;
};

Span listed(double center, double half) noexcept {
  const double low = center - half;
  const double high = center + half;
  if (high <= 0.0) {
    return {-center, -high, -low};
  }
  if (low < 0.0) {
    return {std::fabs(center), 0.0, std::max(-low, high)};
  }
  return {center, low, high};
}

void sort_layer(std::vector<Component>& rows) {
  std::stable_sort(rows.begin(), rows.end(), [](const Component& a, const Component& b) {
    if (a.center_hz != b.center_hz) {
      return a.center_hz < b.center_hz;
    }
    if (a.gamma_mult != b.gamma_mult) {
      return a.gamma_mult < b.gamma_mult;
    }
    if (a.theta_mult != b.theta_mult) {
      return a.theta_mult < b.theta_mult;
    }
    return a.beat_mult < b.beat_mult;
  });
}

std::optional<recipe::Error> no_model(const recipe::Recipe& r) {
  const std::string rule(kNoComponentModelRule);
  if (r.theta_reference && r.theta_reference->shape == recipe::ThetaShape::Custom) {
    return recipe::Error{"/theta_reference/shape", "custom", rule, std::string(kModeledThetaShapes)};
  }
  if (r.gamma_pac) {
    if (r.gamma_pac->carrier_wave == recipe::GammaCarrierWave::Triangle) {
      return recipe::Error{"/gamma_pac/carrier_wave", "triangle", rule, std::string(kModeledGammaCarrierWaves)};
    }
    if (r.gamma_pac->carrier_wave == recipe::GammaCarrierWave::SoftenedSquare) {
      return recipe::Error{"/gamma_pac/carrier_wave", "softened_square", rule,
                           std::string(kModeledGammaCarrierWaves)};
    }
  }
  if (r.binaural && r.binaural->waveform == recipe::BinauralWaveform::Triangle) {
    return recipe::Error{"/binaural/waveform", "triangle", rule, std::string(kModeledBinauralWaveforms)};
  }
  return std::nullopt;
}

}  // namespace

ComponentResult build_components(const recipe::Recipe& r, MutedEar mute) {
  ComponentResult result;
  if (std::optional<recipe::Error> e = no_model(r)) {
    result.error = std::move(e);
    return result;
  }
  const recipe::ThetaReference* theta = r.theta_reference ? &*r.theta_reference : nullptr;
  const double swing_theta = theta && has_cycle(theta->rate_cycle) ? theta->rate_cycle->swing_hz : 0.0;
  const std::uint64_t start_theta =
      theta && has_cycle(theta->rate_cycle) ? core::coupling_phase_units(theta->rate_cycle->start_phase_deg) : 0;

  auto row = [](ComponentLayer layer, std::int32_t i, std::int32_t j, std::int32_t b, double center, double half,
                double level) {
    const Span s = listed(center, half);
    Component c;
    c.layer = layer;
    c.center_hz = s.center;
    c.low_hz = s.low;
    c.high_hz = s.high;
    c.level = level;
    c.gamma_mult = i;
    c.theta_mult = j;
    c.beat_mult = b;
    c.mirrored = center - half < 0.0;
    return c;
  };

  std::vector<Component> theta_rows;
  if (theta != nullptr) {
    const std::vector<Line> lines = theta_lines(*theta);
    const double carrier = lines.front().amp;
    for (const Line& l : lines) {
      const double level = l.amp / carrier;
      if (level >= kComponentThreshold) {
        const double k = static_cast<double>(l.j);
        theta_rows.push_back(row(ComponentLayer::ThetaReference, 0, l.j, 0, theta->carrier_hz + k * theta->rate_hz,
                                 std::fabs(k) * swing_theta, level));
      }
    }
    sort_layer(theta_rows);
  }

  std::vector<Component> gamma_rows;
  if (r.gamma_pac) {
    const recipe::GammaPac& g = *r.gamma_pac;
    const double theta_rate = theta != nullptr ? theta->rate_hz : 0.0;
    const bool gamma_cycle = has_cycle(g.rate_cycle);
    const double swing_gamma = gamma_cycle ? g.rate_cycle->swing_hz : 0.0;
    const std::uint64_t start_gamma = gamma_cycle ? core::coupling_phase_units(g.rate_cycle->start_phase_deg) : 0;
    const double cos_between = core::cycle_cosine(start_gamma - start_theta);
    const std::vector<Line> lines = gamma_lines(g, theta);
    const double carrier = lines.front().amp;
    for (const Line& l : lines) {
      const double level = l.amp / carrier;
      if (!(level >= kComponentThreshold)) {
        continue;
      }
      const double a = static_cast<double>(l.i) * swing_gamma;
      const double b = static_cast<double>(l.j) * swing_theta;
      // One sinusoid of amplitude half: both cycles share one period, since row
      // rate-cycle-period is a single value (Components, Rate cycles).
      double half = std::fabs(a) + std::fabs(b);
      if (a != 0.0 && b != 0.0) {
        const double s = a * a + b * b + 2.0 * a * b * cos_between;
        half = std::sqrt(s > 0.0 ? s : 0.0);
      }
      const double offset = static_cast<double>(l.i) * g.rate_hz + static_cast<double>(l.j) * theta_rate;
      gamma_rows.push_back(row(ComponentLayer::GammaPac, l.i, l.j, 0, g.carrier_hz + offset, half, level));
    }
    sort_layer(gamma_rows);
  }

  std::vector<Component> binaural_rows[2];
  if (r.binaural) {
    const recipe::Binaural& b = *r.binaural;
    if (mute != MutedEar::Left) {
      binaural_rows[0].push_back(row(ComponentLayer::Binaural, 0, 0, 0, b.carrier_left_hz, 0.0, 1.0));
    }
    if (mute != MutedEar::Right) {
      const double swing = has_cycle(b.beat_rate_cycle) ? b.beat_rate_cycle->swing_hz : 0.0;
      binaural_rows[1].push_back(
          row(ComponentLayer::Binaural, 0, 0, 1, b.carrier_left_hz + b.beat_rate_hz, swing, 1.0));
    }
  }

  for (const Ear ear : {Ear::Left, Ear::Right}) {
    for (const std::vector<Component>* layer :
         {&theta_rows, &gamma_rows, &binaural_rows[static_cast<int>(ear)]}) {
      for (Component c : *layer) {
        c.ear = ear;
        result.components.push_back(c);
      }
    }
  }
  return result;
}

}  // namespace arcani::validate
