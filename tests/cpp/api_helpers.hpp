// Helpers for the C API tests (Story 1.2): fixtures, owning handles, error
// poisoning, and whole renders. Reaches the engine only through the public
// header arcani/arcani.h.
//
// Every helper is defined only once the header declares the API (it defines
// ARC_ERROR_FIELD_BYTES); before that the test files compile to one failing
// test case each, so the rest of the suite still runs.

#pragma once

#include <arcani/arcani.h>

#ifdef ARC_ERROR_FIELD_BYTES

#include <catch2/catch_test_macros.hpp>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#ifndef ARCANI_RECIPES_DIR
#error "ARCANI_RECIPES_DIR must name recipes/"
#endif

namespace arcani::test::api {

inline std::string read_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  INFO(path);
  REQUIRE(in.good());
  std::stringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

inline std::string fixture(const std::string& folder, const std::string& name) {
  return read_file(std::string(ARCANI_RECIPES_DIR) + "/fixtures/" + folder + "/" + name);
}

inline std::string valid(const std::string& name) { return fixture("valid", name); }

inline const char* const kBeat0 = "stub-chain-1s-beat-0.json";
inline const char* const kBeat6 = "stub-chain-1s-beat-6.json";
inline const char* const kNoGain = "stub-chain-1s-no-gain.json";
inline const char* const kNoLayers = "stub-chain-1s-no-layers.json";

inline arc_compile_options options(arc_mode mode, std::uint32_t fs,
                                   arc_mute_ear mute = ARC_MUTE_NONE) {
  arc_compile_options o;
  std::memset(&o, 0, sizeof o);
  o.mode = mode;
  o.sample_rate = fs;
  o.mute_binaural_ear = mute;
  return o;
}

struct PlanRelease {
  void operator()(arc_plan* p) const { arc_plan_release(p); }
};
struct RendererDestroy {
  void operator()(arc_renderer* r) const { arc_renderer_destroy(r); }
};
using PlanPtr = std::unique_ptr<arc_plan, PlanRelease>;
using RendererPtr = std::unique_ptr<arc_renderer, RendererDestroy>;

// Fills every error field with 'X' and no terminator, so a field the call
// does not write is caught.
inline void poison(arc_error& e) { std::memset(&e, 'X', sizeof e); }

template <std::size_t N>
bool written(const char (&field)[N]) {
  return std::memchr(field, '\0', N) != nullptr;
}

inline bool all_written(const arc_error& e) {
  return written(e.parameter) && written(e.value) && written(e.rule) && written(e.limit);
}

inline std::string describe(const arc_error& e) {
  if (!all_written(e)) {
    return "(error fields not all written)";
  }
  return std::string("parameter '") + e.parameter + "', value '" + e.value + "', rule '" + e.rule +
         "', limit '" + e.limit + "'";
}

struct Compiled {
  arc_status status = ARC_ERR_INTERNAL;
  PlanPtr plan;
  arc_error error{};
};

inline Compiled compile(const std::string& text, const arc_compile_options& o) {
  Compiled c;
  poison(c.error);
  arc_plan* raw = reinterpret_cast<arc_plan*>(&c);  // must be overwritten
  c.status = arc_compile(text.data(), text.size(), &o, &raw, &c.error);
  if (c.status == ARC_OK) {
    c.plan.reset(raw);
  } else {
    CHECK(raw == nullptr);
  }
  return c;
}

inline PlanPtr compile_ok(const std::string& text, const arc_compile_options& o) {
  Compiled c = compile(text, o);
  INFO(describe(c.error));
  REQUIRE(c.status == ARC_OK);
  REQUIRE(c.plan != nullptr);
  return std::move(c.plan);
}

inline RendererPtr renderer(arc_plan* plan) {
  arc_error e;
  poison(e);
  arc_renderer* raw = nullptr;
  const arc_status s = arc_renderer_create(plan, &raw, &e);
  INFO(describe(e));
  REQUIRE(s == ARC_OK);
  REQUIRE(raw != nullptr);
  return RendererPtr(raw);
}

// One buffer per tap, each interleaved stereo over the same frames as the
// render output.
struct TapBuffers {
  std::vector<double> theta_reference, gamma_pac, stereo_bus, binaural_join, master;

  explicit TapBuffers(std::size_t frames)
      : theta_reference(2 * frames, -7.0),
        gamma_pac(2 * frames, -7.0),
        stereo_bus(2 * frames, -7.0),
        binaural_join(2 * frames, -7.0),
        master(2 * frames, -7.0) {}

  arc_taps taps() {
    arc_taps t;
    t.theta_reference = theta_reference.data();
    t.gamma_pac = gamma_pac.data();
    t.stereo_bus = stereo_bus.data();
    t.binaural_join = binaural_join.data();
    t.master = master.data();
    return t;
  }
};

// Renders `frames` frames; the buffer starts filled with a sentinel so an
// unwritten sample shows.
inline std::vector<double> render(arc_renderer* r, std::size_t frames, const arc_taps* taps = nullptr) {
  std::vector<double> out(2 * frames, -7.0);
  arc_error e;
  poison(e);
  const arc_status s = arc_render(r, out.data(), frames, taps, &e);
  INFO(describe(e));
  REQUIRE(s == ARC_OK);
  return out;
}

inline void seek(arc_renderer* r, std::uint64_t frame) {
  arc_error e;
  poison(e);
  const arc_status s = arc_seek(r, frame, &e);
  INFO(describe(e));
  REQUIRE(s == ARC_OK);
}

inline std::uint64_t bits(double x) {
  std::uint64_t b = 0;
  std::memcpy(&b, &x, sizeof b);
  return b;
}

inline bool same_bytes(const double* a, const double* b, std::size_t count) {
  return std::memcmp(a, b, count * sizeof(double)) == 0;
}

inline bool same_bytes(const std::vector<double>& a, const std::vector<double>& b) {
  return a.size() == b.size() && same_bytes(a.data(), b.data(), a.size());
}

inline bool all_exact_zero(const double* x, std::size_t count) {
  for (std::size_t i = 0; i < count; ++i) {
    if (bits(x[i]) != 0) {
      return false;  // +0.0 only: -0.0 and anything else fail
    }
  }
  return true;
}

inline bool all_exact_zero(const std::vector<double>& x) { return all_exact_zero(x.data(), x.size()); }

// One channel (0 left, 1 right) of an interleaved stereo buffer.
inline std::vector<double> channel(const std::vector<double>& stereo, int c) {
  std::vector<double> out(stereo.size() / 2);
  for (std::size_t n = 0; n < out.size(); ++n) {
    out[n] = stereo[2 * n + static_cast<std::size_t>(c)];
  }
  return out;
}

}  // namespace arcani::test::api

#endif  // ARC_ERROR_FIELD_BYTES
