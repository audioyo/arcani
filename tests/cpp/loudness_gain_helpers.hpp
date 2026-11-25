// Helpers for the Story 4.2 stored loudness gain tests (docs/signal-spec.md,
// Loudness gain). Test code only; reaches the engine through the public
// header arcani/arcani.h.
//
// arc_plan_loudness_hash probe. Until the public header declares
//   arc_status arc_plan_loudness_hash(const arc_plan* plan, char out_hash[65], arc_error* error);
// the call below resolves to the fallback template declared here, which
// writes nothing and returns the tag type LoudnessHashMissing, so every test
// file still compiles and the tests that need the accessor fail with a named
// message instead of a build error. Once the header declares it, overload
// resolution prefers the non-template function (every argument passed with
// its exact parameter type), and the fallback is never called.
//
// stored_hash_text(): the recipe hashes made in the harness before Story 4.2
// carried the shared placeholder loudness hash, which final mode now
// rejects (rule final.loudness_hash). The harness recipes that must compile
// in final mode put the loudness hash the engine computes for them (a
// measure-mode compile, arc_plan_loudness_hash) in place of the placeholder.
// The stored members are not loudness-relevant, so the hash of the text with
// the placeholder is the hash of the text with the real hash. When the
// accessor is missing or the measure compile refuses the text, the text is
// returned unchanged.

#pragma once

#include <arcani/arcani.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <optional>
#include <string>
#include <type_traits>
#include <utility>

struct LoudnessHashMissing {};

// Fallback, C++ linkage, overloading the C function of the same name.
template <class... A>
LoudnessHashMissing arc_plan_loudness_hash(A...) {
  return {};
}

namespace arcani::test::loudness {

// The shared placeholder of the Story 1.1 and 1.2 fixtures (and of the
// harness recipes made before Story 4.2).
inline constexpr const char* kPlaceholderHash = "6a29ccd608e4c1945bfff95af078a97daea48eca54a38e065ae33dfa9c2d83a6";

inline constexpr bool kHaveLoudnessHash =
    !std::is_same_v<decltype(arc_plan_loudness_hash(std::declval<const arc_plan*&>(), std::declval<char*&>(),
                                                    std::declval<arc_error*&>())),
                    LoudnessHashMissing>;

struct HashCall {
  bool declared = false;           // the accessor exists
  arc_status status = ARC_ERR_INTERNAL;
  std::string hash;                // the 64 characters before the terminator, on ARC_OK
  bool terminated = false;         // out_hash[64] is NUL, on ARC_OK
};

namespace detail {
template <class P>
HashCall call(P plan, char* out, arc_error* error) {
  HashCall r;
  auto s = arc_plan_loudness_hash(plan, out, error);
  if constexpr (std::is_same_v<decltype(s), LoudnessHashMissing>) {
    return r;
  } else {
    r.declared = true;
    r.status = s;
    if (s == ARC_OK && out != nullptr) {
      r.terminated = out[64] == '\0';
      r.hash.assign(out, 64);
    }
    return r;
  }
}
}  // namespace detail

// Calls arc_plan_loudness_hash(plan, out, error) with exactly the declared
// parameter types. `out` may be NULL (the argument check).
inline HashCall call_loudness_hash(const arc_plan* plan, char* out, arc_error* error) {
  return detail::call<const arc_plan*>(plan, out, error);
}

// The plan's loudness hash; empty when the accessor is missing or fails.
inline std::string plan_loudness_hash(const arc_plan* plan) {
  char buffer[65];
  std::memset(buffer, 'X', sizeof buffer);
  arc_error e;
  const HashCall c = call_loudness_hash(plan, buffer, &e);
  if (!c.declared || c.status != ARC_OK || !c.terminated) {
    return {};
  }
  return c.hash;
}

// The loudness hash the engine computes for `text` (measure mode, 48 kHz);
// empty when the accessor is missing or the compile refuses the text.
inline std::string engine_loudness_hash(const std::string& text, std::uint32_t fs = 48000) {
  arc_compile_options o;
  std::memset(&o, 0, sizeof o);
  o.mode = ARC_MODE_MEASURE;
  o.sample_rate = fs;
  o.mute_binaural_ear = ARC_MUTE_NONE;
  arc_plan* plan = nullptr;
  arc_error e;
  if (arc_compile(text.data(), text.size(), &o, &plan, &e) != ARC_OK || plan == nullptr) {
    return {};
  }
  const std::string h = plan_loudness_hash(plan);
  arc_plan_release(plan);
  return h;
}

// `text` with every placeholder loudness hash replaced by the engine's
// loudness hash of the text (see the file comment).
inline std::string stored_hash_text(std::string text) {
  const std::string placeholder = kPlaceholderHash;
  if (text.find(placeholder) == std::string::npos) {
    return text;
  }
  const std::string h = engine_loudness_hash(text);
  if (h.size() != placeholder.size()) {
    return text;
  }
  for (std::size_t at = text.find(placeholder); at != std::string::npos; at = text.find(placeholder, at)) {
    text.replace(at, placeholder.size(), h);
    at += h.size();
  }
  return text;
}

// Replaces the value text of a top-level member written as "name": <value>
// (the first occurrence of the key; the value runs to the next ',' or '\n').
// Returns false when the key is not found.
inline bool replace_member_value(std::string& text, const std::string& name, const std::string& value_text) {
  const std::string key = "\"" + name + "\":";
  const auto at = text.find(key);
  if (at == std::string::npos) {
    return false;
  }
  auto begin = at + key.size();
  while (begin < text.size() && (text[begin] == ' ' || text[begin] == '\t')) {
    ++begin;
  }
  auto end = begin;
  if (end < text.size() && text[end] == '"') {
    end = text.find('"', end + 1);
    if (end == std::string::npos) {
      return false;
    }
    ++end;
  } else {
    while (end < text.size() && text[end] != ',' && text[end] != '\n' && text[end] != '\r' && text[end] != '}') {
      ++end;
    }
  }
  text.replace(begin, end - begin, value_text);
  return true;
}

// The value text of a top-level member written as "name": <value>, or empty.
inline std::string member_value(const std::string& text, const std::string& name) {
  const std::string key = "\"" + name + "\":";
  const auto at = text.find(key);
  if (at == std::string::npos) {
    return {};
  }
  auto begin = at + key.size();
  while (begin < text.size() && (text[begin] == ' ' || text[begin] == '\t')) {
    ++begin;
  }
  auto end = begin;
  if (end < text.size() && text[end] == '"') {
    end = text.find('"', end + 1);
    if (end == std::string::npos) {
      return {};
    }
    ++end;
  } else {
    while (end < text.size() && text[end] != ',' && text[end] != '\n' && text[end] != '\r' && text[end] != '}') {
      ++end;
    }
  }
  return text.substr(begin, end - begin);
}

// Gain text of k by the spec rule (Loudness gain, Gain rounding, Gain text),
// written here on its own for the harness.
inline std::string harness_gain_text(std::int64_t k) {
  const std::uint64_t m = k < 0 ? static_cast<std::uint64_t>(-(k + 1)) + 1u : static_cast<std::uint64_t>(k);
  std::string s = k < 0 ? "-" : "";
  s += std::to_string(m / 100u);
  s += ".";
  const std::uint64_t r = m % 100u;
  s += static_cast<char>('0' + r / 10u);
  s += static_cast<char>('0' + r % 10u);
  return s;
}

// Linear gain by the spec steps (Loudness gain, Linear gain), harness copy.
inline double harness_linear_gain(std::int64_t k, double c) {
  std::uint64_t m = k < 0 ? static_cast<std::uint64_t>(-(k + 1)) + 1u : static_cast<std::uint64_t>(k);
  double p = 1.0;
  double b = c;
  while (m > 0) {
    if (m % 2u == 1u) {
      p = p * b;
    }
    m = m / 2u;
    if (m > 0) {
      b = b * b;
    }
  }
  return k < 0 ? 1.0 / p : p;
}

}  // namespace arcani::test::loudness
