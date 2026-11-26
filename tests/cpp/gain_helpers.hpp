// Helpers for the Story 4.4 gain ramp tests (docs/signal-spec.md, Gain
// ramps). Test code only; reaches the engine through the public header
// arcani/arcani.h, plus the engine sine and ratio-to-phase rule
// (core/sine.hpp, core/envelope.hpp, both from before Story 4.4) for the
// harness copy of the ramp law.
//
// The Story 4.4 C API additions are reached through compile-time detection,
// so the suite builds before they exist and the tests that need them fail at
// run time with a named message:
//
// - the four after-gain and binaural taps of arc_taps (theta_reference_gained,
//   gamma_pac_gained, binaural, binaural_gained) through the concept
//   HasGainTaps, set and read only inside `if constexpr`;
// - arc_plan_gain_ramp_count and arc_plan_gain_ramp through calls whose
//   argument is of a dependent type, so the names are looked up (by ADL, in
//   the global namespace of arc_plan) only when the template is used. The
//   arc_gain_ramp out argument is a RampSink, whose conversion operator
//   template deduces the struct type from the declared parameter and copies
//   its members by name into GainRampRead.

#pragma once

#include <arcani/arcani.h>

#include "api_helpers.hpp"
#include "core/envelope.hpp"
#include "core/sine.hpp"
#include "spec_tables.hpp"

#include <concepts>
#include <cstddef>
#include <cstdint>
#include <new>
#include <optional>
#include <string>
#include <vector>

namespace arcani::test::gain {

// ------------------------------------------------------------ taps

using arcani::test::api::HasGainTaps;  // api_helpers.hpp

inline constexpr bool kHaveGainTaps = HasGainTaps<arc_taps>;

inline constexpr const char* kNoGainTaps =
    "not implemented: arc_taps has no theta_reference_gained, gamma_pac_gained, binaural, binaural_gained "
    "(Story 4.4)";

// Sets the four Story 4.4 taps; a no-op before they exist.
template <class T>
void set_gain_taps(T& t, double* theta_gained, double* gamma_gained, double* binaural, double* binaural_gained) {
  if constexpr (HasGainTaps<T>) {
    t.theta_reference_gained = theta_gained;
    t.gamma_pac_gained = gamma_gained;
    t.binaural = binaural;
    t.binaural_gained = binaural_gained;
  } else {
    (void)t;
    (void)theta_gained;
    (void)gamma_gained;
    (void)binaural;
    (void)binaural_gained;
  }
}

// ------------------------------------------------------------ the ramp API

struct GainRampRead {
  int target = -1;  // arc_gain_target: 0 theta reference, 1 gamma PAC, 2 binaural, 3 master
  std::uint64_t start_frame = 0;
  std::uint64_t end_frame = 0;
  double from = -7.0;
  double to = -7.0;
};

// Out argument for arc_plan_gain_ramp: converts to a pointer to whatever
// struct the declaration names, and remembers how to read it.
struct RampSink {
  alignas(16) unsigned char storage[256];
  void (*read)(const void*, GainRampRead&) = nullptr;

  template <class R>
  operator R*() {
    static_assert(sizeof(R) <= sizeof(storage));
    R* r = ::new (static_cast<void*>(storage)) R{};
    r->target = static_cast<decltype(r->target)>(-1);
    r->start_frame = UINT64_C(0xDEADBEEF);
    r->end_frame = UINT64_C(0xDEADBEEF);
    r->from = -7.0;
    r->to = -7.0;
    read = [](const void* p, GainRampRead& out) {
      const R& x = *static_cast<const R*>(p);
      out.target = static_cast<int>(x.target);
      out.start_frame = x.start_frame;
      out.end_frame = x.end_frame;
      out.from = x.from;
      out.to = x.to;
    };
    return r;
  }
};

template <class P>
concept HasGainRampApi = requires(const P* p, RampSink& sink, arc_error* e) {
  { arc_plan_gain_ramp_count(p) } -> std::convertible_to<std::size_t>;
  { arc_plan_gain_ramp(p, std::size_t{0}, sink, e) } -> std::convertible_to<int>;
};

inline constexpr bool kHaveGainRampApi = HasGainRampApi<arc_plan>;

inline constexpr const char* kNoGainRampApi =
    "not implemented: arcani/arcani.h declares no arc_plan_gain_ramp_count and arc_plan_gain_ramp (Story 4.4)";

// The ramp count; nullopt before the API exists.
template <class P>
std::optional<std::size_t> ramp_count(const P* plan) {
  if constexpr (HasGainRampApi<P>) {
    return static_cast<std::size_t>(arc_plan_gain_ramp_count(plan));
  } else {
    (void)plan;
    return std::nullopt;
  }
}

struct RampCall {
  bool declared = false;
  int status = -1;  // arc_status
  GainRampRead ramp;
};

template <class P>
RampCall ramp_at(const P* plan, std::size_t index, arc_error* error) {
  RampCall c;
  if constexpr (HasGainRampApi<P>) {
    c.declared = true;
    RampSink sink;
    c.status = static_cast<int>(arc_plan_gain_ramp(plan, index, sink, error));
    if (sink.read != nullptr) {
      sink.read(sink.storage, c.ramp);
    }
  } else {
    (void)plan;
    (void)index;
    (void)error;
  }
  return c;
}

// Schedule index (theta reference 0, gamma PAC 1, binaural 2, master 3) of a
// schedule name of the vectors; -1 for any other name.
inline int schedule_index(const std::string& name) {
  for (int i = 0; i < 4; ++i) {
    if (name == spec::kGain_schedules[i]) {
      return i;
    }
  }
  return -1;
}

// ------------------------------------------------------------ the law, harness copy

// Gain ramps, Law, engine: r = k / L, P = ratio_to_phase(r), c = sine(P + 2^62),
// h = (1 - c) * 0.5, g = a + (b - a) * h, each one binary64 operation in that order.
inline double harness_ramp(double a, double b, std::uint64_t k, std::uint64_t length) {
  const double r = static_cast<double>(k) / static_cast<double>(length);
  const std::uint64_t p = arcani::core::ratio_to_phase(r);
  const double c = arcani::core::sine(p + (UINT64_C(1) << 62));
  const double h = (1.0 - c) * 0.5;
  return a + (b - a) * h;  // -ffp-contract=off (top-level CMakeLists.txt): no fused multiply-add
}

struct HarnessRamp {
  std::uint64_t n0, length, n1;
  double a, b;
};

struct HarnessSchedule {
  bool present = false;  // false: no gain member, 1.0 everywhere
  double initial = 1.0;
  std::vector<HarnessRamp> ramps;
};

// Gain ramps, Law: the schedule's gain at frame n.
inline double harness_gain_at(const HarnessSchedule& s, std::uint64_t n) {
  if (!s.present) {
    return 1.0;
  }
  double value = s.initial;
  for (const HarnessRamp& r : s.ramps) {
    if (n < r.n0) {
      return value;
    }
    if (n < r.n1) {
      return harness_ramp(r.a, r.b, n - r.n0, r.length);
    }
    value = r.b;
  }
  return value;
}

// The four schedules of a render fixture at fs from kGainFixtureRamps (every
// fixture's gain members have an initial equal to the first ramp's from).
struct FixtureSchedules {
  HarnessSchedule s[4];  // theta reference, gamma PAC, binaural, master
};

inline FixtureSchedules fixture_schedules(const std::string& fixture, std::uint32_t fs) {
  FixtureSchedules out;
  for (const auto& v : spec::kGainFixtureRamps) {
    if (v.fs != fs || fixture != v.fixture) {
      continue;
    }
    const int i = schedule_index(v.schedule);
    if (i < 0) {
      continue;
    }
    HarnessSchedule& s = out.s[i];
    if (!s.present) {
      s.present = true;
      s.initial = v.from;
    }
    s.ramps.push_back({v.start_frame, v.length_frames, v.end_frame, v.from, v.to});
  }
  return out;
}

}  // namespace arcani::test::gain
