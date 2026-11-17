// Spacing rule per ear, whole session (Story 3.2; docs/signal-spec.md,
// Spacing). See spacing.hpp.

#include "validate/spacing.hpp"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>

#include "core/envelope.hpp"
#include "core/rate_cycle.hpp"
#include "json/number.hpp"

namespace arcani::validate {

namespace {

constexpr std::uint64_t kQuarter = std::uint64_t{1} << 62;
constexpr std::uint64_t kHalf = std::uint64_t{1} << 63;

// One rate's cycle constants (Spacing, Engine): swing 0 and cos = sin = 0.0
// without a cycle of swing above 0, or for a layer the recipe does not have.
struct Cycle {
  bool present = false;  // the recipe has this layer (its rate is named in the detail)
  double rate_hz = 0.0;  // the center
  double swing_hz = 0.0;
  std::uint64_t p0 = 0;
  double cos_phi = 0.0;
  double sin_phi = 0.0;
  double period_s = 0.0;
};

Cycle make_cycle(bool present, double rate_hz, const std::optional<recipe::RateCycle>& c) noexcept {
  Cycle out;
  out.present = present;
  out.rate_hz = rate_hz;
  if (present && c && c->swing_hz > 0.0) {
    out.swing_hz = c->swing_hz;
    out.p0 = core::coupling_phase_units(c->start_phase_deg);
    out.cos_phi = core::cycle_cosine(out.p0);
    out.sin_phi = core::cycle_cosine(out.p0 - kQuarter);
    out.period_s = c->period_s;
  }
  return out;
}

// [0] gamma, [1] theta, [2] beat.
using Cycles = std::array<Cycle, 3>;

Cycles cycles_of(const recipe::Recipe& r) noexcept {
  Cycles c;
  if (r.gamma_pac) {
    c[0] = make_cycle(true, r.gamma_pac->rate_hz, r.gamma_pac->rate_cycle);
  }
  if (r.theta_reference) {
    c[1] = make_cycle(true, r.theta_reference->rate_hz, r.theta_reference->rate_cycle);
  }
  if (r.binaural) {
    c[2] = make_cycle(true, r.binaural->beat_rate_hz, r.binaural->beat_rate_cycle);
  }
  return c;
}

// The closed form of one pair (Spacing, Engine), in the spec's order.
struct Form {
  double c = 0.0;
  double x = 0.0;
  double y = 0.0;
  double h = 0.0;
  double dist = 0.0;
  bool sweeps = false;
};

Form form(double c, const int (&d)[3], const Cycles& cy, bool sweeps) noexcept {
  Form f;
  f.c = c;
  f.sweeps = sweeps;
  const double a = static_cast<double>(d[0]) * cy[0].swing_hz;
  const double b = static_cast<double>(d[1]) * cy[1].swing_hz;
  const double e = static_cast<double>(d[2]) * cy[2].swing_hz;
  f.x = (a * cy[0].cos_phi + b * cy[1].cos_phi) + e * cy[2].cos_phi;
  f.y = (a * cy[0].sin_phi + b * cy[1].sin_phi) + e * cy[2].sin_phi;
  f.h = std::sqrt(f.x * f.x + f.y * f.y);
  const double dist = std::fabs(c) - f.h;
  f.dist = dist < 0.0 ? 0.0 : dist;
  return f;
}

bool row_sweeps(const Component& r, const Cycles& cy) noexcept {
  return (r.gamma_mult != 0 && cy[0].swing_hz > 0.0) || (r.theta_mult != 0 && cy[1].swing_hz > 0.0) ||
         (r.beat_mult != 0 && cy[2].swing_hz > 0.0);
}

// The first cycle phase advance of the minimum of a sweeping pair.
std::uint64_t first_units(const Form& f) noexcept {
  if (f.h == 0.0) {
    return 0;
  }
  const double sigma = f.c >= 0.0 ? 1.0 : -1.0;
  const std::uint64_t alpha = acos_units((-sigma * f.y) / f.h);
  const std::uint64_t m = -sigma * f.x >= 0.0 ? alpha : std::uint64_t{0} - alpha;
  if (std::fabs(f.c) >= f.h) {
    return m;
  }
  const std::uint64_t beta = acos_units(std::fabs(f.c) / f.h);
  const std::uint64_t lo = m - beta;
  const std::uint64_t hi = m + beta;
  return lo < hi ? lo : hi;
}

struct PairResult {
  double dist = 0.0;
  bool mirrored = false;
  bool sweeps = false;
  Form f;
};

PairResult pair(const Component& r1, const Component& r2, const Cycles& cy) noexcept {
  PairResult p;
  p.sweeps = row_sweeps(r1, cy) || row_sweeps(r2, cy);
  p.mirrored = r1.mirrored || r2.mirrored;
  if (p.mirrored) {
    double dist = 0.0;
    const double g1 = r2.low_hz - r1.high_hz;
    const double g2 = r1.low_hz - r2.high_hz;
    if (g1 > dist) {
      dist = g1;
    }
    if (g2 > dist) {
      dist = g2;
    }
    p.dist = dist;
    return p;
  }
  const int d[3] = {r1.gamma_mult - r2.gamma_mult, r1.theta_mult - r2.theta_mult, r1.beat_mult - r2.beat_mult};
  p.f = form(r1.center_hz - r2.center_hz, d, cy, p.sweeps);
  p.dist = p.f.dist;
  return p;
}

const char* layer_name(ComponentLayer l) noexcept {
  switch (l) {
    case ComponentLayer::ThetaReference:
      return "theta_reference";
    case ComponentLayer::GammaPac:
      return "gamma_pac";
    case ComponentLayer::Binaural:
      return "binaural";
  }
  return "theta_reference";
}

std::string row_text(const Component& c) {
  return std::string(layer_name(c.layer)) + " (" + std::to_string(c.gamma_mult) + ", " +
         std::to_string(c.theta_mult) + ", " + std::to_string(c.beat_mult) + ") at " + shortest_text(c.center_hz) +
         " Hz";
}

std::string where_text(const PairResult& p, const Cycles& cy) {
  if (!p.sweeps) {
    return "whole session";
  }
  if (p.mirrored) {
    return "listed intervals, a row mirrored below 0 Hz";
  }
  const std::uint64_t u = first_units(p.f);
  double period = 0.0;
  for (const Cycle& c : cy) {
    if (c.swing_hz > 0.0) {
      period = c.period_s;
      break;
    }
  }
  const double t = (static_cast<double>(u) * 0x1p-64) * period;
  std::string out = "first at " + shortest_text(t) + " s";
  const char* names[3] = {"gamma", "theta", "beat"};
  for (int k = 0; k < 3; ++k) {
    const Cycle& c = cy[static_cast<std::size_t>(k)];
    out += std::string(", ") + names[k] + " rate ";
    if (!c.present) {
      out += "none";
      continue;
    }
    double rate = c.rate_hz;
    if (c.swing_hz > 0.0) {
      rate = c.rate_hz + c.swing_hz * core::cycle_cosine(c.p0 + u - kQuarter);
    }
    out += shortest_text(rate) + " Hz";
  }
  return out;
}

const char* carrier_field(ComponentLayer later) noexcept {
  return later == ComponentLayer::GammaPac ? "/gamma_pac/carrier_hz" : "/binaural/carrier_left_hz";
}

}  // namespace

std::uint64_t acos_units(double v) {
  if (core::cycle_cosine(0) <= v) {
    return 0;
  }
  std::uint64_t lo = 0;
  std::uint64_t hi = kHalf;
  while (hi - lo > 1) {
    const std::uint64_t mid = lo + (hi - lo) / 2;
    if (core::cycle_cosine(mid) <= v) {
      hi = mid;
    } else {
      lo = mid;
    }
  }
  return hi;
}

SpacingPairForm spacing_pair_form(const SpacingPairInput& in) {
  const auto cycle = [](double swing, double start) {
    recipe::RateCycle rc;
    rc.swing_hz = swing;
    rc.period_s = 60.0;
    rc.start_phase_deg = start;
    return make_cycle(true, 0.0, std::optional<recipe::RateCycle>(rc));
  };
  const Cycles cy = {cycle(in.swing_gamma_hz, in.start_gamma_deg), cycle(in.swing_theta_hz, in.start_theta_deg),
                     cycle(in.swing_beat_hz, in.start_beat_deg)};
  const int d[3] = {in.di, in.dj, in.db};
  const bool sweeps = (in.di != 0 && cy[0].swing_hz > 0.0) || (in.dj != 0 && cy[1].swing_hz > 0.0) ||
                      (in.db != 0 && cy[2].swing_hz > 0.0);
  const Form f = form(in.c_hz, d, cy, sweeps);
  SpacingPairForm out;
  out.x = f.x;
  out.y = f.y;
  out.h = f.h;
  out.min_distance_hz = f.dist;
  out.sweeps = sweeps;
  out.first_units = sweeps ? first_units(f) : 0;
  return out;
}

SpacingResult check_spacing(const recipe::Recipe& r, std::span<const Component> table) {
  SpacingResult result;
  const Cycles cy = cycles_of(r);
  bool failed = false;
  double fail_dist = 0.0;
  std::size_t fail_1 = 0;
  std::size_t fail_2 = 0;
  int fail_ear = 0;
  for (int ear = 0; ear < 2; ++ear) {
    const Ear e = ear == 0 ? Ear::Left : Ear::Right;
    std::optional<SpacingPair>& worst = result.ears[static_cast<std::size_t>(ear)];
    for (std::size_t i = 0; i < table.size(); ++i) {
      if (table[i].ear != e) {
        continue;
      }
      for (std::size_t j = i + 1; j < table.size(); ++j) {
        if (table[j].ear != e || table[j].layer == table[i].layer) {
          continue;
        }
        const double dist = pair(table[i], table[j], cy).dist;
        if (!worst || dist < worst->min_distance_hz) {
          SpacingPair p;
          p.min_distance_hz = dist;
          p.margin_hz = dist - kSpacingRuleHz;
          p.component_1 = i;
          p.component_2 = j;
          worst = p;
        }
        if (!(dist >= kSpacingRuleHz) && (!failed || dist < fail_dist)) {
          failed = true;
          fail_dist = dist;
          fail_1 = i;
          fail_2 = j;
          fail_ear = ear;
        }
      }
    }
  }
  if (failed) {
    const Component& r1 = table[fail_1];
    const Component& r2 = table[fail_2];
    const PairResult p = pair(r1, r2, cy);
    const ComponentLayer later = static_cast<int>(r2.layer) > static_cast<int>(r1.layer) ? r2.layer : r1.layer;
    recipe::Error err;
    err.parameter = carrier_field(later);
    err.value = shortest_text(p.dist);
    err.rule = std::string(kSpacingRule);
    err.limit = ">= " + shortest_text(kSpacingRuleHz) + " Hz (row spacing-rule)";
    err.detail = std::string(fail_ear == 0 ? "left" : "right") + " ear: " + row_text(r1) + " and " + row_text(r2) +
                 "; " + where_text(p, cy);
    result.error = std::move(err);
  }
  return result;
}

std::string shortest_text(double x) {
  // json::format_number gives the shortest digits (the closest among them);
  // rewrite them in the std::to_chars form.
  const bool negative = std::signbit(x);
  const std::string s = json::format_number(negative ? -x : x);
  std::string digits;
  long long exponent = 0;  // value = digits * 10^exponent
  std::size_t k = 0;
  bool after_point = false;
  for (; k < s.size() && s[k] != 'e' && s[k] != 'E'; ++k) {
    if (s[k] == '.') {
      after_point = true;
    } else {
      digits.push_back(s[k]);
      if (after_point) {
        --exponent;
      }
    }
  }
  if (k < s.size()) {
    ++k;
    bool neg = false;
    if (k < s.size() && (s[k] == '+' || s[k] == '-')) {
      neg = s[k] == '-';
      ++k;
    }
    long long e = 0;
    for (; k < s.size(); ++k) {
      e = e * 10 + (s[k] - '0');
    }
    exponent += neg ? -e : e;
  }
  std::size_t lead = 0;
  while (lead + 1 < digits.size() && digits[lead] == '0') {
    ++lead;
  }
  digits.erase(0, lead);
  while (digits.size() > 1 && digits.back() == '0') {
    digits.pop_back();
    ++exponent;
  }
  const std::string sign = negative ? "-" : "";
  if (digits == "0") {
    return sign + "0";
  }
  const long long n = static_cast<long long>(digits.size());
  std::string fixed;
  if (exponent >= 0) {
    fixed = digits + std::string(static_cast<std::size_t>(exponent), '0');
  } else if (-exponent < n) {
    fixed = digits.substr(0, static_cast<std::size_t>(n + exponent)) + "." +
            digits.substr(static_cast<std::size_t>(n + exponent));
  } else {
    fixed = "0." + std::string(static_cast<std::size_t>(-exponent - n), '0') + digits;
  }
  const long long sci_exp = exponent + n - 1;
  std::string sci = digits.substr(0, 1);
  if (n > 1) {
    sci += "." + digits.substr(1);
  }
  const long long mag = sci_exp < 0 ? -sci_exp : sci_exp;
  std::string exp_digits = std::to_string(mag);
  if (exp_digits.size() < 2) {
    exp_digits = "0" + exp_digits;
  }
  sci += std::string("e") + (sci_exp < 0 ? "-" : "+") + exp_digits;
  return sign + (sci.size() < fixed.size() ? sci : fixed);
}

}  // namespace arcani::validate
