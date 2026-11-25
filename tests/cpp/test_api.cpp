// C API surface, errors, and plan handles (Story 1.2). Includes only the
// public header (through api_helpers.hpp and host_fp_mode.hpp, test code).
//
// Expected interface (engine/include/arcani/arcani.h, plain C, extern "C",
// include guard ARCANI_ARCANI_H; <stddef.h> and <stdint.h> only):
//
//   #define ARC_ERROR_FIELD_BYTES 256
//
//   typedef enum arc_status {
//     ARC_OK = 0, ARC_ERR_INVALID_ARGUMENT = 1, ARC_ERR_REJECTED = 2,
//     ARC_ERR_OUT_OF_MEMORY = 3, ARC_ERR_INTERNAL = 4 } arc_status;
//   typedef enum arc_mode { ARC_MODE_MEASURE = 0, ARC_MODE_FINAL = 1 } arc_mode;
//   typedef enum arc_mute_ear {
//     ARC_MUTE_NONE = 0, ARC_MUTE_LEFT = 1, ARC_MUTE_RIGHT = 2 } arc_mute_ear;
//   typedef enum arc_stage_kind {
//     ARC_STAGE_THETA_REFERENCE = 0, ARC_STAGE_GAMMA_PAC = 1,
//     ARC_STAGE_STEREO_BUS = 2, ARC_STAGE_BINAURAL_JOIN = 3,
//     ARC_STAGE_MASTER_CHAIN = 4 } arc_stage_kind;
//
//   typedef struct arc_error {          // every field NUL-terminated; a longer
//     char parameter[ARC_ERROR_FIELD_BYTES];   // text is cut to
//     char value[ARC_ERROR_FIELD_BYTES];       // ARC_ERROR_FIELD_BYTES - 1 bytes
//     char rule[ARC_ERROR_FIELD_BYTES];        // ending in "..."
//     char limit[ARC_ERROR_FIELD_BYTES];
//   } arc_error;
//
//   typedef struct arc_compile_options {
//     arc_mode mode;
//     uint32_t sample_rate;               // 44100 or 48000, else rejected
//     arc_mute_ear mute_binaural_ear;     // offline measurement control (FR-4)
//   } arc_compile_options;
//
//   typedef struct arc_taps {             // each NULL (not wanted) or 2 * frames
//     double* theta_reference;            // doubles, interleaved left, right
//     double* gamma_pac;
//     double* stereo_bus;
//     double* binaural_join;              // the engine output point
//     double* master;                     // equals the render output
//   } arc_taps;
//
//   typedef struct arc_plan arc_plan;          // opaque, immutable, reference-counted
//   typedef struct arc_renderer arc_renderer;  // opaque
//
//   const char* arc_engine_version(void);
//   arc_status arc_compile(const char* utf8, size_t length,
//                          const arc_compile_options* options,
//                          arc_plan** out_plan, arc_error* error);
//   void arc_plan_retain(arc_plan* plan);             // NULL is a no-op
//   void arc_plan_release(arc_plan* plan);            // NULL is a no-op
//   uint64_t arc_plan_frame_count(const arc_plan* plan);   // 0 for NULL
//   size_t arc_plan_stage_count(const arc_plan* plan);     // 0 for NULL
//   arc_status arc_plan_stage(const arc_plan* plan, size_t index,
//                             arc_stage_kind* out_kind, arc_error* error);
//   size_t arc_plan_warning_count(const arc_plan* plan);   // 0 for NULL
//   arc_status arc_plan_warning(const arc_plan* plan, size_t index,
//                               arc_error* out_warning, arc_error* error);
//   arc_status arc_renderer_create(arc_plan* plan, arc_renderer** out_renderer,
//                                  arc_error* error);   // the renderer holds a plan reference
//   arc_status arc_render(arc_renderer* renderer, double* out, size_t frames,
//                         const arc_taps* taps, arc_error* error);  // taps may be NULL
//   arc_status arc_seek(arc_renderer* renderer, uint64_t frame, arc_error* error);
//   void arc_renderer_destroy(arc_renderer* renderer);  // NULL is a no-op
//
// Error contract (settled by the tests):
// - `error` may be NULL on every call. When it is not, a failing call writes
//   all four fields (each NUL-terminated) and a successful call leaves no
//   promise about them.
// - A failing arc_compile sets *out_plan to NULL; a failing
//   arc_renderer_create sets *out_renderer to NULL (when those are not NULL).
// - Null pointer argument: ARC_ERR_INVALID_ARGUMENT, parameter = the argument
//   name as declared above ("utf8", "options", "out_plan", "plan",
//   "out_renderer", "renderer", "out", "out_kind", "out_warning"), value
//   "null", rule "argument.null", limit "non-null".
// - Index out of range (arc_plan_stage, arc_plan_warning):
//   ARC_ERR_INVALID_ARGUMENT, parameter "index", rule "argument.index", value
//   the index in decimal, limit the count in decimal.
// - Bad enum in options (mode, mute_binaural_ear): ARC_ERR_INVALID_ARGUMENT,
//   parameter the field name, rule "argument.enum", value in decimal, limit
//   non-empty.
// - Sample rate: ARC_ERR_REJECTED, parameter "sample_rate", value "32000",
//   rule "sample_rate", limit "44100 48000".
// - Parse fault: ARC_ERR_REJECTED with the Story 1.1 parameter and rule
//   passed through, and value and limit as recipes/fixtures/invalid-expected.json
//   lists them where it does.
// - final mode: a missing loudness_gain_db (then loudness_hash) is
//   ARC_ERR_REJECTED, parameter "/loudness_gain_db" (or "/loudness_hash"),
//   rule "final.required", limit non-empty.
// - Input over 1 MiB (1048576 bytes): ARC_ERR_REJECTED, parameter "" (the
//   whole document), value the length in decimal, rule "input.max_bytes",
//   limit "1048576". Exactly 1048576 bytes is accepted.
//
// The host floating-point mode tests (Story 1.2, AD-9) are here too: they
// set FTZ and DAZ (FZ on AArch64) in the host and check that every call
// leaves the host mode unchanged and renders the same bytes as in IEEE mode.
// The engine-internal guard itself is tested in test_fp_mode.cpp.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#ifdef ARC_ERROR_FIELD_BYTES

#include "api_helpers.hpp"
#include "host_fp_mode.hpp"
#include "loudness_gain_helpers.hpp"
#include "spec_helpers.hpp"

#include <cmath>
#include <cstring>
#include <iterator>
#include <map>
#include <string>
#include <type_traits>
#include <vector>

namespace api = arcani::test::api;
namespace fp = arcani::test::fp;

namespace {

constexpr std::size_t kMiB = 1048576;

void require_filled(const arc_error& e) {
  INFO(api::describe(e));
  REQUIRE(api::all_written(e));
  CHECK(std::strlen(e.rule) > 0);
}

void require_null_argument(arc_status s, const arc_error& e, const char* parameter) {
  INFO(api::describe(e));
  CHECK(s == ARC_ERR_INVALID_ARGUMENT);
  require_filled(e);
  CHECK(std::string(e.parameter) == parameter);
  CHECK(std::string(e.value) == "null");
  CHECK(std::string(e.rule) == "argument.null");
  CHECK(std::string(e.limit) == "non-null");
}

// Removes the first line containing `needle` (fixture edits for one-off cases).
std::string drop_line(std::string text, const std::string& needle) {
  const auto at = text.find(needle);
  REQUIRE(at != std::string::npos);
  const auto start = text.rfind('\n', at) + 1;
  const auto end = text.find('\n', at);
  text.erase(start, end - start + 1);
  return text;
}

}  // namespace

// ------------------------------------------------------------- the header

TEST_CASE("public header declares the C API with plain C types", "[api]") {
  STATIC_REQUIRE(ARC_ERROR_FIELD_BYTES >= 64);
  STATIC_REQUIRE(sizeof(arc_error{}.parameter) == ARC_ERROR_FIELD_BYTES);
  STATIC_REQUIRE(sizeof(arc_error{}.value) == ARC_ERROR_FIELD_BYTES);
  STATIC_REQUIRE(sizeof(arc_error{}.rule) == ARC_ERROR_FIELD_BYTES);
  STATIC_REQUIRE(sizeof(arc_error{}.limit) == ARC_ERROR_FIELD_BYTES);
  STATIC_REQUIRE(std::is_standard_layout_v<arc_error>);
  STATIC_REQUIRE(std::is_trivially_copyable_v<arc_error>);
  STATIC_REQUIRE(std::is_standard_layout_v<arc_compile_options>);
  STATIC_REQUIRE(std::is_trivially_copyable_v<arc_compile_options>);
  STATIC_REQUIRE(std::is_standard_layout_v<arc_taps>);
  STATIC_REQUIRE(ARC_OK == 0);
  STATIC_REQUIRE(ARC_ERR_INVALID_ARGUMENT != ARC_OK && ARC_ERR_REJECTED != ARC_OK &&
                 ARC_ERR_OUT_OF_MEMORY != ARC_OK && ARC_ERR_INTERNAL != ARC_OK);
  // Exact signatures: each assignment fails to compile if a declaration drifts.
  const char* (*version)(void) = &arc_engine_version;
  arc_status (*compile)(const char*, size_t, const arc_compile_options*, arc_plan**, arc_error*) =
      &arc_compile;
  void (*retain)(arc_plan*) = &arc_plan_retain;
  void (*release)(arc_plan*) = &arc_plan_release;
  uint64_t (*frame_count)(const arc_plan*) = &arc_plan_frame_count;
  size_t (*stage_count)(const arc_plan*) = &arc_plan_stage_count;
  arc_status (*stage)(const arc_plan*, size_t, arc_stage_kind*, arc_error*) = &arc_plan_stage;
  size_t (*warning_count)(const arc_plan*) = &arc_plan_warning_count;
  arc_status (*warning)(const arc_plan*, size_t, arc_error*, arc_error*) = &arc_plan_warning;
  arc_status (*create)(arc_plan*, arc_renderer**, arc_error*) = &arc_renderer_create;
  arc_status (*render)(arc_renderer*, double*, size_t, const arc_taps*, arc_error*) = &arc_render;
  arc_status (*seek)(arc_renderer*, uint64_t, arc_error*) = &arc_seek;
  void (*destroy)(arc_renderer*) = &arc_renderer_destroy;
  CHECK(version != nullptr);
  CHECK(compile != nullptr);
  CHECK(retain != nullptr);
  CHECK(release != nullptr);
  CHECK(frame_count != nullptr);
  CHECK(stage_count != nullptr);
  CHECK(stage != nullptr);
  CHECK(warning_count != nullptr);
  CHECK(warning != nullptr);
  CHECK(create != nullptr);
  CHECK(render != nullptr);
  CHECK(seek != nullptr);
  CHECK(destroy != nullptr);
}

// ---------------------------------------------------------------- compile

TEST_CASE("compile valid: plan, five stages, no warnings, frame count from length_s", "[api][compile]") {
  for (const std::uint32_t fs : {44100u, 48000u}) {
    for (const arc_mode mode : {ARC_MODE_MEASURE, ARC_MODE_FINAL}) {
      INFO("fs " << fs << ", mode " << mode);
      auto plan = api::compile_ok(api::valid(api::kBeat6), api::options(mode, fs));
      CHECK(arc_plan_stage_count(plan.get()) == 5);
      CHECK(arc_plan_warning_count(plan.get()) == 0);
      CHECK(arc_plan_frame_count(plan.get()) == fs);  // length_s 1
    }
  }
}

TEST_CASE("compile accepts every stub chain fixture in measure mode", "[api][compile]") {
  for (const char* name : {api::kBeat0, api::kBeat6, api::kNoGain, api::kNoLayers}) {
    INFO(name);
    auto plan = api::compile_ok(api::valid(name), api::options(ARC_MODE_MEASURE, 48000));
    CHECK(arc_plan_frame_count(plan.get()) == 48000);
  }
}

TEST_CASE("compile passes every Story 1.1 parse fault through, with no plan", "[api][compile]") {
  // recipes/fixtures/invalid-expected.json, read with a plain scan: the C API
  // tests do not link the engine's JSON parser. Each fixture entry is
  // "name.json": { "key": "text", ... } with string values only.
  const std::string text = api::read_file(std::string(ARCANI_RECIPES_DIR) + "/fixtures/invalid-expected.json");
  std::map<std::string, std::map<std::string, std::string>> expected;
  std::size_t at = text.find("\"fixtures\"");
  REQUIRE(at != std::string::npos);
  auto read_string = [&](std::size_t& i) {
    REQUIRE(text[i] == '"');
    std::string out;
    for (++i; text[i] != '"'; ++i) {
      if (text[i] == '\\') {
        ++i;
        out.push_back(text[i] == 'n' ? '\n' : text[i]);
      } else {
        out.push_back(text[i]);
      }
    }
    ++i;
    return out;
  };
  for (std::size_t i = text.find('{', at) + 1; i < text.size();) {
    const std::size_t q = text.find_first_of("\"}", i);
    if (q == std::string::npos || text[q] == '}') {
      break;
    }
    i = q;
    const std::string name = read_string(i);
    i = text.find('{', i) + 1;
    auto& entry = expected[name];
    while (true) {
      const std::size_t k = text.find_first_of("\"}", i);
      REQUIRE(k != std::string::npos);
      if (text[k] == '}') {
        i = k + 1;
        break;
      }
      i = k;
      const std::string key = read_string(i);
      i = text.find('"', text.find(':', i));
      entry[key] = read_string(i);
    }
  }
  REQUIRE(expected.size() >= 40);
  for (const auto& [name, want] : expected) {
    INFO(name);
    const api::Compiled c = api::compile(api::fixture("invalid", name), api::options(ARC_MODE_MEASURE, 48000));
    INFO(api::describe(c.error));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
    require_filled(c.error);
    for (const char* key : {"parameter", "rule", "value", "limit"}) {
      const auto it = want.find(key);
      if (it == want.end()) {
        continue;
      }
      const std::string got = std::string(key) == "parameter" ? c.error.parameter
                              : std::string(key) == "rule"    ? c.error.rule
                              : std::string(key) == "value"   ? c.error.value
                                                              : c.error.limit;
      CHECK(got == it->second);
    }
    if (want.count("parameter") == 0) {
      // json.* syntax faults: the parameter is the byte offset in decimal.
      const std::string p = c.error.parameter;
      CHECK_FALSE(p.empty());
      CHECK(p.find_first_not_of("0123456789") == std::string::npos);
    }
  }
}

TEST_CASE("compile rejects a sample rate other than 44100 and 48000", "[api][compile]") {
  for (const std::uint32_t fs : {32000u, 0u, 44101u, 96000u}) {
    INFO(fs);
    const api::Compiled c = api::compile(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, fs));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
    require_filled(c.error);
    CHECK(std::string(c.error.parameter) == "sample_rate");
    CHECK(std::string(c.error.value) == std::to_string(fs));
    CHECK(std::string(c.error.rule) == "sample_rate");
    CHECK(std::string(c.error.limit) == "44100 48000");
  }
}

TEST_CASE("final mode requires the stored gain and the loudness hash", "[api][compile]") {
  SECTION("no loudness_gain_db") {
    const api::Compiled c = api::compile(api::valid(api::kNoGain), api::options(ARC_MODE_FINAL, 48000));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
    require_filled(c.error);
    CHECK(std::string(c.error.parameter) == "/loudness_gain_db");
    CHECK(std::string(c.error.rule) == "final.required");
    CHECK(std::strlen(c.error.limit) > 0);
  }
  SECTION("gain but no loudness_hash") {
    const std::string text = drop_line(api::valid(api::kBeat6), "\"loudness_hash\"");
    const api::Compiled c = api::compile(text, api::options(ARC_MODE_FINAL, 48000));
    CHECK(c.status == ARC_ERR_REJECTED);
    require_filled(c.error);
    CHECK(std::string(c.error.parameter) == "/loudness_hash");
    CHECK(std::string(c.error.rule) == "final.required");
  }
  SECTION("measure mode accepts the same recipe") {
    auto plan = api::compile_ok(api::valid(api::kNoGain), api::options(ARC_MODE_MEASURE, 48000));
    CHECK(arc_plan_warning_count(plan.get()) == 0);
  }
}

TEST_CASE("compile caps the input at 1 MiB", "[api][compile]") {
  const std::string base = api::valid(api::kBeat6);
  REQUIRE(base.size() < kMiB);
  SECTION("exactly 1 MiB (trailing whitespace) compiles") {
    const std::string text = base + std::string(kMiB - base.size(), ' ');
    REQUIRE(text.size() == kMiB);
    auto plan = api::compile_ok(text, api::options(ARC_MODE_MEASURE, 48000));
    CHECK(plan != nullptr);
  }
  SECTION("1 MiB plus one byte is rejected") {
    const std::string text = base + std::string(kMiB + 1 - base.size(), ' ');
    const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, 48000));
    CHECK(c.status == ARC_ERR_REJECTED);
    CHECK(c.plan == nullptr);
    require_filled(c.error);
    CHECK(std::string(c.error.parameter).empty());
    CHECK(std::string(c.error.value) == std::to_string(kMiB + 1));
    CHECK(std::string(c.error.rule) == "input.max_bytes");
    CHECK(std::string(c.error.limit) == std::to_string(kMiB));
  }
}

TEST_CASE("a long error field is truncated with a trailing ...", "[api][compile]") {
  std::string text = api::valid(api::kBeat6);
  const std::string date = "\"date\": \"2026-11-04\"";
  const auto at = text.find(date);
  REQUIRE(at != std::string::npos);
  const std::string long_value(3 * ARC_ERROR_FIELD_BYTES, 'd');
  text.replace(at, date.size(), "\"date\": \"" + long_value + "\"");
  const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, 48000));
  CHECK(c.status == ARC_ERR_REJECTED);
  require_filled(c.error);
  CHECK(std::string(c.error.parameter) == "/date");
  CHECK(std::string(c.error.rule) == "pattern");
  const std::string value = c.error.value;
  REQUIRE(value.size() == ARC_ERROR_FIELD_BYTES - 1);
  CHECK(value.substr(value.size() - 3) == "...");
  CHECK(value.substr(0, value.size() - 3) == long_value.substr(0, value.size() - 3));
}

namespace {

// Strict UTF-8 check: well-formed sequences only (no overlong forms,
// surrogates, or values above U+10FFFF).
bool valid_utf8(const std::string& s) {
  std::size_t i = 0;
  while (i < s.size()) {
    const auto b = static_cast<unsigned char>(s[i]);
    std::size_t n = 0;
    std::uint32_t cp = 0;
    if (b < 0x80) {
      ++i;
      continue;
    } else if ((b & 0xE0) == 0xC0) {
      n = 1;
      cp = b & 0x1F;
    } else if ((b & 0xF0) == 0xE0) {
      n = 2;
      cp = b & 0x0F;
    } else if ((b & 0xF8) == 0xF0) {
      n = 3;
      cp = b & 0x07;
    } else {
      return false;
    }
    if (i + n >= s.size()) {
      return false;
    }
    for (std::size_t k = 1; k <= n; ++k) {
      const auto c = static_cast<unsigned char>(s[i + k]);
      if ((c & 0xC0) != 0x80) {
        return false;
      }
      cp = (cp << 6) | (c & 0x3F);
    }
    const std::uint32_t min[] = {0, 0x80, 0x800, 0x10000};
    if (cp < min[n] || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) {
      return false;
    }
    i += n + 1;
  }
  return true;
}

}  // namespace

TEST_CASE("truncation never splits a UTF-8 sequence", "[api][compile]") {
  // "d" then 400 two-byte characters (U+00E9): the 252-byte cut point lands
  // on the second byte of a character, so the cut backs up one byte.
  std::string long_value = "d";
  for (int i = 0; i < 400; ++i) {
    long_value += "\xC3\xA9";
  }
  REQUIRE((static_cast<unsigned char>(long_value[ARC_ERROR_FIELD_BYTES - 4]) & 0xC0) == 0x80);
  std::string text = api::valid(api::kBeat6);
  const std::string date = "\"date\": \"2026-11-04\"";
  const auto at = text.find(date);
  REQUIRE(at != std::string::npos);
  text.replace(at, date.size(), "\"date\": \"" + long_value + "\"");
  const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, 48000));
  CHECK(c.status == ARC_ERR_REJECTED);
  require_filled(c.error);
  CHECK(std::string(c.error.parameter) == "/date");
  const std::string value = c.error.value;
  INFO(value.size());
  CHECK(value.size() <= ARC_ERROR_FIELD_BYTES - 1);
  CHECK(value.size() >= ARC_ERROR_FIELD_BYTES - 1 - 3);
  REQUIRE(value.size() > 3);
  CHECK(value.substr(value.size() - 3) == "...");
  CHECK(valid_utf8(value));
  CHECK(value.substr(0, value.size() - 3) == long_value.substr(0, value.size() - 3));
  // Must-fail side of the check: a cut mid-character is not valid UTF-8.
  CHECK_FALSE(valid_utf8(long_value.substr(0, ARC_ERROR_FIELD_BYTES - 4) + "..."));
}

TEST_CASE("compile rejects a bad options enum as an invalid argument", "[api][compile]") {
  const std::string text = api::valid(api::kBeat6);
  SECTION("mode") {
    arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
    o.mode = static_cast<arc_mode>(7);
    const api::Compiled c = api::compile(text, o);
    CHECK(c.status == ARC_ERR_INVALID_ARGUMENT);
    require_filled(c.error);
    CHECK(std::string(c.error.parameter) == "mode");
    CHECK(std::string(c.error.value) == "7");
    CHECK(std::string(c.error.rule) == "argument.enum");
    CHECK(std::strlen(c.error.limit) > 0);
  }
  SECTION("mute_binaural_ear") {
    arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
    o.mute_binaural_ear = static_cast<arc_mute_ear>(9);
    const api::Compiled c = api::compile(text, o);
    CHECK(c.status == ARC_ERR_INVALID_ARGUMENT);
    require_filled(c.error);
    CHECK(std::string(c.error.parameter) == "mute_binaural_ear");
    CHECK(std::string(c.error.value) == "9");
    CHECK(std::string(c.error.rule) == "argument.enum");
  }
}

// ----------------------------------------------------------- null pointers

TEST_CASE("every call returns invalid argument for a null pointer, with all four fields", "[api][null]") {
  const std::string text = api::valid(api::kBeat6);
  const arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
  auto plan = api::compile_ok(text, o);
  auto r = api::renderer(plan.get());
  arc_error e;
  arc_plan* out_plan = nullptr;
  arc_renderer* out_renderer = nullptr;
  double buffer[2] = {0.0, 0.0};
  arc_stage_kind kind = ARC_STAGE_THETA_REFERENCE;
  arc_error warning;

  api::poison(e);
  require_null_argument(arc_compile(nullptr, text.size(), &o, &out_plan, &e), e, "utf8");
  CHECK(out_plan == nullptr);
  api::poison(e);
  require_null_argument(arc_compile(text.data(), text.size(), nullptr, &out_plan, &e), e, "options");
  api::poison(e);
  require_null_argument(arc_compile(text.data(), text.size(), &o, nullptr, &e), e, "out_plan");
  api::poison(e);
  require_null_argument(arc_renderer_create(nullptr, &out_renderer, &e), e, "plan");
  CHECK(out_renderer == nullptr);
  api::poison(e);
  require_null_argument(arc_renderer_create(plan.get(), nullptr, &e), e, "out_renderer");
  api::poison(e);
  require_null_argument(arc_render(nullptr, buffer, 1, nullptr, &e), e, "renderer");
  api::poison(e);
  require_null_argument(arc_render(r.get(), nullptr, 1, nullptr, &e), e, "out");
  api::poison(e);
  require_null_argument(arc_seek(nullptr, 0, &e), e, "renderer");
  api::poison(e);
  require_null_argument(arc_plan_stage(nullptr, 0, &kind, &e), e, "plan");
  api::poison(e);
  require_null_argument(arc_plan_stage(plan.get(), 0, nullptr, &e), e, "out_kind");
  api::poison(e);
  require_null_argument(arc_plan_warning(nullptr, 0, &warning, &e), e, "plan");
  api::poison(e);
  require_null_argument(arc_plan_warning(plan.get(), 0, nullptr, &e), e, "out_warning");
}

TEST_CASE("a null error pointer is allowed on every call", "[api][null]") {
  const std::string text = api::valid(api::kBeat6);
  const arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
  arc_plan* plan = nullptr;
  CHECK(arc_compile(text.data(), text.size(), &o, &plan, nullptr) == ARC_OK);
  REQUIRE(plan != nullptr);
  const arc_compile_options bad = api::options(ARC_MODE_MEASURE, 32000);
  arc_plan* none = nullptr;
  CHECK(arc_compile(text.data(), text.size(), &bad, &none, nullptr) == ARC_ERR_REJECTED);
  CHECK(none == nullptr);
  arc_renderer* r = nullptr;
  CHECK(arc_renderer_create(plan, &r, nullptr) == ARC_OK);
  REQUIRE(r != nullptr);
  double buffer[8] = {};
  CHECK(arc_render(r, buffer, 4, nullptr, nullptr) == ARC_OK);
  CHECK(arc_render(r, nullptr, 4, nullptr, nullptr) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(arc_seek(r, 3, nullptr) == ARC_OK);
  arc_stage_kind kind = ARC_STAGE_THETA_REFERENCE;
  CHECK(arc_plan_stage(plan, 99, &kind, nullptr) == ARC_ERR_INVALID_ARGUMENT);
  arc_renderer_destroy(r);
  arc_plan_release(plan);
  arc_plan_release(nullptr);
  arc_plan_retain(nullptr);
  arc_renderer_destroy(nullptr);
  CHECK(arc_plan_frame_count(nullptr) == 0);
  CHECK(arc_plan_stage_count(nullptr) == 0);
  CHECK(arc_plan_warning_count(nullptr) == 0);
}

TEST_CASE("index out of range on the stage and warning lists", "[api][null]") {
  auto plan = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 48000));
  arc_error e;
  arc_stage_kind kind = ARC_STAGE_THETA_REFERENCE;
  api::poison(e);
  CHECK(arc_plan_stage(plan.get(), 5, &kind, &e) == ARC_ERR_INVALID_ARGUMENT);
  require_filled(e);
  CHECK(std::string(e.parameter) == "index");
  CHECK(std::string(e.value) == "5");
  CHECK(std::string(e.rule) == "argument.index");
  CHECK(std::string(e.limit) == "5");
  arc_error warning;
  api::poison(e);
  CHECK(arc_plan_warning(plan.get(), 0, &warning, &e) == ARC_ERR_INVALID_ARGUMENT);
  require_filled(e);
  CHECK(std::string(e.parameter) == "index");
  CHECK(std::string(e.value) == "0");
  CHECK(std::string(e.limit) == "0");
}

TEST_CASE("the error-field check catches an unwritten field", "[api][null]") {
  // Must-fail for require_filled: a poisoned struct reads as not written.
  arc_error e;
  api::poison(e);
  CHECK_FALSE(api::all_written(e));
  std::memcpy(e.parameter, "p", 2);
  std::memcpy(e.value, "v", 2);
  std::memcpy(e.rule, "r", 2);
  CHECK_FALSE(api::all_written(e));
  std::memcpy(e.limit, "l", 2);
  CHECK(api::all_written(e));
}

// ----------------------------------------------------------- plan handles

TEST_CASE("plan is reference-counted and a renderer keeps its plan alive", "[api][plan]") {
  arc_plan* plan = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 48000)).release();
  arc_plan_retain(plan);
  arc_plan_release(plan);  // one reference left
  CHECK(arc_plan_frame_count(plan) == 48000);
  auto r = api::renderer(plan);
  arc_plan_release(plan);  // the renderer's reference is the last one
  const auto out = api::render(r.get(), 256);
  CHECK(out.size() == 512);
  CHECK(api::bits(out[2]) != 0);  // sample 1 of the 400 Hz left ear sine
}

TEST_CASE("two renderers on one plan render the same bytes", "[api][plan]") {
  auto plan = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 44100));
  auto a = api::renderer(plan.get());
  auto b = api::renderer(plan.get());
  const auto first = api::render(a.get(), 1000);
  const auto second = api::render(b.get(), 1000);
  CHECK(api::same_bytes(first, second));
}

// --------------------------------------------------------- host fp mode

TEST_CASE("host flush-to-zero: every call leaves the host mode unchanged", "[api][fp_mode]") {
  if (!fp::supported()) {
    SKIP("no floating-point mode control on this target");
  }
  const std::string text = api::valid(api::kBeat6);
  const arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
  constexpr std::size_t kFrames = 4096;

  // IEEE-mode reference render.
  std::vector<double> ieee;
  {
    fp::HostMode host(fp::controls() & ~fp::flush_bits());
    auto plan = api::compile_ok(text, o);
    auto r = api::renderer(plan.get());
    ieee = api::render(r.get(), kFrames);
  }

  const std::uint64_t flushed = fp::controls() | fp::flush_bits();
  fp::HostMode host(flushed);
  REQUIRE(fp::controls() == flushed);
  // Premise: in this host mode a denormal product flushes to zero.
  CHECK(fp::half_of_smallest_normal() == 0.0);

  arc_error e;
  arc_plan* raw = nullptr;
  api::poison(e);
  CHECK(arc_compile(text.data(), text.size(), &o, &raw, &e) == ARC_OK);
  CHECK(fp::controls() == flushed);
  REQUIRE(raw != nullptr);
  api::PlanPtr plan(raw);

  arc_renderer* rr = nullptr;
  CHECK(arc_renderer_create(plan.get(), &rr, &e) == ARC_OK);
  CHECK(fp::controls() == flushed);
  REQUIRE(rr != nullptr);
  api::RendererPtr r(rr);

  std::vector<double> out(2 * kFrames, -7.0);
  CHECK(arc_render(r.get(), out.data(), kFrames, nullptr, &e) == ARC_OK);
  CHECK(fp::controls() == flushed);
  CHECK(api::same_bytes(out, ieee));

  CHECK(arc_seek(r.get(), 37, &e) == ARC_OK);
  CHECK(fp::controls() == flushed);
  std::vector<double> tail(2 * (kFrames - 37), -7.0);
  CHECK(arc_render(r.get(), tail.data(), kFrames - 37, nullptr, &e) == ARC_OK);
  CHECK(fp::controls() == flushed);
  CHECK(api::same_bytes(tail.data(), ieee.data() + 2 * 37, tail.size()));

  // Error returns restore the host mode too.
  const arc_compile_options bad_rate = api::options(ARC_MODE_MEASURE, 32000);
  arc_plan* none = nullptr;
  CHECK(arc_compile(text.data(), text.size(), &bad_rate, &none, &e) == ARC_ERR_REJECTED);
  CHECK(fp::controls() == flushed);
  const std::string broken = text.substr(0, text.size() / 2);
  CHECK(arc_compile(broken.data(), broken.size(), &o, &none, &e) == ARC_ERR_REJECTED);
  CHECK(fp::controls() == flushed);
  CHECK(arc_render(r.get(), nullptr, 4, nullptr, &e) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(fp::controls() == flushed);
  CHECK(arc_render(nullptr, out.data(), 4, nullptr, &e) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(fp::controls() == flushed);
  CHECK(arc_seek(nullptr, 0, &e) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(fp::controls() == flushed);
  CHECK(arc_compile(nullptr, 0, &o, &none, &e) == ARC_ERR_INVALID_ARGUMENT);
  CHECK(fp::controls() == flushed);
}

TEST_CASE("host round toward zero: output equals the IEEE render, host mode unchanged", "[api][fp_mode]") {
  if (!fp::supported()) {
    SKIP("no floating-point mode control on this target");
  }
#if defined(__x86_64__) || defined(_M_X64)
  constexpr std::uint64_t kRoundingBits = 0x6000u;     // MXCSR RC, bits 13 and 14
  constexpr std::uint64_t kTowardZero = 0x6000u;       // RC = 11
#else
  constexpr std::uint64_t kRoundingBits = std::uint64_t{3} << 22;  // FPCR RMode
  constexpr std::uint64_t kTowardZero = std::uint64_t{3} << 22;    // RMode = 11 (RZ)
#endif
  const std::string text = api::valid(api::kBeat6);
  const arc_compile_options o = api::options(ARC_MODE_MEASURE, 48000);
  constexpr std::size_t kFrames = 4096;

  std::vector<double> ieee;
  {
    fp::HostMode host(fp::controls() & ~fp::flush_bits() & ~kRoundingBits);
    auto plan = api::compile_ok(text, o);
    auto r = api::renderer(plan.get());
    ieee = api::render(r.get(), kFrames);
  }

  const std::uint64_t toward_zero = (fp::controls() & ~kRoundingBits) | kTowardZero;
  fp::HostMode host(toward_zero);
  REQUIRE(fp::controls() == toward_zero);
  // Premise: in this host mode 1 + 2^-53 * 1.5 rounds down to 1.
  {
    volatile double one = 1.0;
    volatile double small = 0x1.8p-53;
    volatile double sum = one + small;
    CHECK(sum == 1.0);
  }

  arc_error e;
  arc_plan* raw = nullptr;
  api::poison(e);
  CHECK(arc_compile(text.data(), text.size(), &o, &raw, &e) == ARC_OK);
  CHECK(fp::controls() == toward_zero);
  REQUIRE(raw != nullptr);
  api::PlanPtr plan(raw);

  arc_renderer* rr = nullptr;
  CHECK(arc_renderer_create(plan.get(), &rr, &e) == ARC_OK);
  CHECK(fp::controls() == toward_zero);
  REQUIRE(rr != nullptr);
  api::RendererPtr r(rr);

  std::vector<double> out(2 * kFrames, -7.0);
  CHECK(arc_render(r.get(), out.data(), kFrames, nullptr, &e) == ARC_OK);
  CHECK(fp::controls() == toward_zero);
  CHECK(api::same_bytes(out, ieee));

  CHECK(arc_seek(r.get(), 37, &e) == ARC_OK);
  CHECK(fp::controls() == toward_zero);
  std::vector<double> tail(2 * (kFrames - 37), -7.0);
  CHECK(arc_render(r.get(), tail.data(), kFrames - 37, nullptr, &e) == ARC_OK);
  CHECK(fp::controls() == toward_zero);
  CHECK(api::same_bytes(tail.data(), ieee.data() + 2 * 37, tail.size()));
}

TEST_CASE("host mode check catches a call that changes the host mode", "[api][fp_mode]") {
  // Must-fail for the check above: a call that clears the flush bits and does
  // not restore them is seen.
  if (!fp::supported()) {
    SKIP("no floating-point mode control on this target");
  }
  const std::uint64_t flushed = fp::controls() | fp::flush_bits();
  fp::HostMode host(flushed);
  fp::set(flushed & ~fp::flush_bits());  // a leaky call
  CHECK(fp::controls() != flushed);
  CHECK(fp::half_of_smallest_normal() != 0.0);
}

// ------------------------------------------------ stored loudness gain (4.2)
//
// docs/signal-spec.md, Loudness gain. Contracts (spec Implementation Notes):
//   arc_status arc_plan_loudness_hash(const arc_plan* plan, char out_hash[65], arc_error* error);
//   64 lowercase hex digits and a NUL into out_hash, in both modes. NULL plan
//   or out_hash: ARC_ERR_INVALID_ARGUMENT, parameter "plan" or "out_hash",
//   value "null", rule "argument.null", limit "non-null" (the C API error
//   contract above).
//   The range check on loudness_gain_db (row loudness-gain) runs in both
//   modes; final mode then checks final.required (unchanged) and
//   final.loudness_hash: parameter /loudness_hash, value the stored hash,
//   limit "= " + H computed for the recipe.
//   The master tap and the output are the binaural join times g (Linear
//   gain) in final mode, times 1.0 in measure mode; every other tap is the
//   same in both modes.
// Vectors: kLoudnessHashes, kLoudnessGainValues, kLoudnessGain_*; row
// loudness-gain through the assertion call. Harness copies of the fixtures
// are the doctored cases.

namespace {

namespace lg = arcani::test::loudness;
namespace spec = arcani::test::spec;

bool is_store_fixture(const std::string& name) {
  for (const char* f : spec::kLoudnessGain_store_fixtures) {
    if (name == f) {
      return true;
    }
  }
  return false;
}

const spec::LoudnessHashVector& loudness_hash_vector(const std::string& fixture) {
  for (const auto& v : spec::kLoudnessHashes) {
    if (fixture == v.fixture) {
      return v;
    }
  }
  FAIL("no loudness hash vector for " << fixture);
  return spec::kLoudnessHashes[0];
}

const spec::LoudnessGainValueVector& gain_value(const std::string& text) {
  for (const auto& v : spec::kLoudnessGainValues) {
    if (text == v.text) {
      return v;
    }
  }
  FAIL("no stored gain vector for " << text);
  return spec::kLoudnessGainValues[0];
}

void require_loudness_hash_declared() {
  if (!lg::kHaveLoudnessHash) {
    FAIL("not implemented: arcani/arcani.h does not declare arc_plan_loudness_hash (Story 4.2)");
  }
}

// The text with a top-level member's value text replaced.
std::string with_member(std::string text, const std::string& name, const std::string& value_text) {
  INFO("member " << name);
  REQUIRE(lg::replace_member_value(text, name, value_text));
  return text;
}

// The stored hash of a fixture text, without its quotes.
std::string stored_hash(const std::string& text) {
  const std::string v = lg::member_value(text, "loudness_hash");
  REQUIRE(v.size() == 66);
  return v.substr(1, 64);
}

struct TapRender {
  std::vector<double> out;
  api::TapBuffers taps;
  explicit TapRender(std::size_t frames) : taps(frames) {}
};

TapRender render_taps(const std::string& text, arc_mode mode, std::uint32_t fs) {
  api::PlanPtr plan = api::compile_ok(text, api::options(mode, fs));
  const std::size_t frames = static_cast<std::size_t>(arc_plan_frame_count(plan.get()));
  REQUIRE(frames > 0);
  TapRender r(frames);
  api::RendererPtr renderer = api::renderer(plan.get());
  arc_taps t = r.taps.taps();
  r.out = api::render(renderer.get(), frames, &t);
  return r;
}

// Every master sample is the join sample times g, bit for bit.
std::size_t master_mismatches(const TapRender& r, double g) {
  std::size_t bad = 0;
  for (std::size_t i = 0; i < r.taps.master.size(); ++i) {
    if (api::bits(r.taps.master[i]) != api::bits(r.taps.binaural_join[i] * g)) {
      ++bad;
    }
  }
  return bad;
}

}  // namespace

TEST_CASE("loudness hash: arc_plan_loudness_hash gives every loudness hash vector in both modes and rates",
          "[api][loudness-gain]") {
  require_loudness_hash_declared();
  std::size_t accepted = 0;
  for (const auto& v : spec::kLoudnessHashes) {
    INFO("fixture " << v.fixture);
    const std::string text = api::valid(v.fixture);
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("fs " << fs);
      const api::Compiled c = api::compile(text, api::options(ARC_MODE_MEASURE, fs));
      if (c.status != ARC_OK) {
        // Only the loudness target variant is refused (row loudness-tones).
        CHECK(std::string(v.fixture) == "both-layers-loudness-target-changed.json");
        continue;
      }
      ++accepted;
      char buffer[65];
      std::memset(buffer, 'X', sizeof buffer);
      arc_error e;
      api::poison(e);
      const lg::HashCall h = lg::call_loudness_hash(c.plan.get(), buffer, &e);
      CHECK(h.status == ARC_OK);
      CHECK(h.terminated);
      CHECK(h.hash == v.loudness_hash);
      CHECK(std::string(arc_plan_recipe_hash(c.plan.get())) == v.recipe_hash);
    }
  }
  CHECK(accepted == spec::sample_rates().size() * (std::size(spec::kLoudnessHashes) - 1));
}

TEST_CASE("loudness hash: a NULL plan or buffer is ARC_ERR_INVALID_ARGUMENT", "[api][loudness-gain]") {
  require_loudness_hash_declared();
  api::PlanPtr plan = api::compile_ok(api::valid(api::kBeat6), api::options(ARC_MODE_MEASURE, 48000));
  char buffer[65];
  arc_error e;
  api::poison(e);
  lg::HashCall c = lg::call_loudness_hash(nullptr, buffer, &e);
  require_null_argument(c.status, e, "plan");
  api::poison(e);
  c = lg::call_loudness_hash(plan.get(), nullptr, &e);
  require_null_argument(c.status, e, "out_hash");
  // error may be NULL.
  c = lg::call_loudness_hash(plan.get(), buffer, nullptr);
  CHECK(c.status == ARC_OK);
  CHECK(c.hash == loudness_hash_vector(api::kBeat6).loudness_hash);
}

TEST_CASE("final mode: every loudness hash fixture compiles but the refused ones", "[api][loudness-gain]") {
  for (const auto& v : spec::kLoudnessHashes) {
    const std::string name = v.fixture;
    INFO("fixture " << name);
    const std::string text = api::valid(name);
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("fs " << fs);
      const api::Compiled c = api::compile(text, api::options(ARC_MODE_FINAL, fs));
      INFO(api::describe(c.error));
      if (name == "both-layers-loudness-target-changed.json") {
        CHECK(c.status == ARC_ERR_REJECTED);
        CHECK(std::string(c.error.parameter) == "/loudness_target_lufs");
        CHECK(std::string(c.error.rule).rfind("range.", 0) == 0);
      } else if (name == api::kNoGain || is_store_fixture(name)) {
        CHECK(c.status == ARC_ERR_REJECTED);
        CHECK(std::string(c.error.parameter) == "/loudness_gain_db");
        CHECK(std::string(c.error.rule) == "final.required");
      } else {
        CHECK(c.status == ARC_OK);
        if (c.status == ARC_OK) {
          CHECK(lg::plan_loudness_hash(c.plan.get()) == v.loudness_hash);
        }
      }
    }
  }
}

TEST_CASE("final mode: a stored placeholder hash is stale (final.loudness_hash)", "[api][loudness-gain]") {
  std::size_t checked = 0;
  for (const auto& v : spec::kLoudnessHashes) {
    const std::string name = v.fixture;
    if (name == "both-layers-loudness-target-changed.json" || name == api::kNoGain || is_store_fixture(name)) {
      continue;
    }
    INFO("fixture " << name);
    const std::string text = with_member(api::valid(name), "loudness_hash",
                                         std::string("\"") + lg::kPlaceholderHash + "\"");
    for (const std::uint32_t fs : spec::sample_rates()) {
      INFO("fs " << fs);
      const api::Compiled c = api::compile(text, api::options(ARC_MODE_FINAL, fs));
      INFO(api::describe(c.error));
      CHECK(c.status == ARC_ERR_REJECTED);
      CHECK(c.plan == nullptr);
      REQUIRE(api::all_written(c.error));
      CHECK(std::string(c.error.parameter) == spec::kLoudnessGain_hash_parameter);
      CHECK(std::string(c.error.value) == lg::kPlaceholderHash);
      CHECK(std::string(c.error.rule) == spec::kLoudnessGain_hash_rule);
      CHECK(std::string(c.error.limit) == std::string("= ") + v.loudness_hash);
      // Measure mode never compares the stored hash.
      api::compile_ok(text, api::options(ARC_MODE_MEASURE, fs));
    }
    ++checked;
  }
  CHECK(checked >= 10);
}

TEST_CASE("final mode: a loudness-relevant edit after storing is stale; metadata edits compile",
          "[api][loudness-gain]") {
  require_loudness_hash_declared();
  const std::string base = api::valid(api::kBeat6);
  const std::string stored = stored_hash(base);
  CHECK(stored == loudness_hash_vector(api::kBeat6).loudness_hash);

  SECTION("stale: length_s, a theta carrier, or a beat rate edited; a respelled length is not") {
    const std::vector<std::string> stale = {
        with_member(base, "length_s", "2"),
        with_member(base, "length_s", "1.5"),
    };
    std::vector<std::string> all = stale;
    std::string carrier = base;
    const auto at = carrier.find("\"carrier_hz\": 300");
    REQUIRE(at != std::string::npos);
    carrier.replace(at, std::string("\"carrier_hz\": 300").size(), "\"carrier_hz\": 301");
    all.push_back(carrier);
    std::string beat = base;
    const auto b = beat.find("\"beat_rate_hz\": 6");
    REQUIRE(b != std::string::npos);
    beat.replace(b, std::string("\"beat_rate_hz\": 6").size(), "\"beat_rate_hz\": 5");
    all.push_back(beat);
    for (const std::string& text : all) {
      INFO(text);
      const std::string h = lg::engine_loudness_hash(text);
      REQUIRE(h.size() == 64);
      CHECK(h != stored);
      for (const std::uint32_t fs : spec::sample_rates()) {
        const api::Compiled c = api::compile(text, api::options(ARC_MODE_FINAL, fs));
        INFO(api::describe(c.error));
        CHECK(c.status == ARC_ERR_REJECTED);
        REQUIRE(api::all_written(c.error));
        CHECK(std::string(c.error.parameter) == "/loudness_hash");
        CHECK(std::string(c.error.value) == stored);
        CHECK(std::string(c.error.rule) == "final.loudness_hash");
        CHECK(std::string(c.error.limit) == "= " + h);
      }
    }
    // The same binary64 written another way keeps the hash.
    const std::string respelled = with_member(base, "length_s", "1.0");
    CHECK(lg::engine_loudness_hash(respelled) == stored);
    api::compile_ok(respelled, api::options(ARC_MODE_FINAL, 48000));
  }

  SECTION("not stale: author, date, rationale, seed, and the stored gain") {
    const std::vector<std::string> edits = {
        with_member(base, "author", "\"Someone else\""),
        with_member(base, "date", "\"2027-01-02\""),
        with_member(base, "rationale", "\"Edited after storing the gain.\""),
        with_member(base, "seed", "7"),
        with_member(base, "loudness_gain_db", "-20.00"),
    };
    for (const std::string& text : edits) {
      INFO(text);
      for (const std::uint32_t fs : spec::sample_rates()) {
        api::PlanPtr p = api::compile_ok(text, api::options(ARC_MODE_FINAL, fs));
        CHECK(lg::plan_loudness_hash(p.get()) == stored);
      }
    }
  }
}

TEST_CASE("range: loudness_gain_db is held to row loudness-gain in both modes", "[api][loudness-gain]") {
  const arcani::test::tables::Row& r = spec::row(spec::kLoudnessGain_row);
  REQUIRE(r.kind == "ranges");
  REQUIRE(r.unit == "dB");
  CHECK(r.min == spec::kLoudnessGain_min_db);
  CHECK(r.max == spec::kLoudnessGain_max_db);
  CHECK(">= " + r.min_text + " dB (row " + r.id + ")" == spec::kLoudnessGain_min_limit);
  CHECK("<= " + r.max_text + " dB (row " + r.id + ")" == spec::kLoudnessGain_max_limit);
  const std::string base = api::valid(api::kBeat6);
  struct Case {
    const char* text;
    const char* rule;  // nullptr: compiles
    const char* limit;
  };
  const Case cases[] = {
      {"-60.01", "range.min", spec::kLoudnessGain_min_limit},
      {"-61", "range.min", spec::kLoudnessGain_min_limit},
      {"0.01", "range.max", spec::kLoudnessGain_max_limit},
      {"1.5", "range.max", spec::kLoudnessGain_max_limit},
      {"-60", nullptr, nullptr},
      {"-60.00", nullptr, nullptr},
      {"0", nullptr, nullptr},
      {"-0.00", nullptr, nullptr},
  };
  for (const Case& k : cases) {
    INFO("loudness_gain_db " << k.text);
    const std::string text = with_member(base, "loudness_gain_db", k.text);
    for (const arc_mode mode : {ARC_MODE_MEASURE, ARC_MODE_FINAL}) {
      for (const std::uint32_t fs : spec::sample_rates()) {
        INFO("mode " << mode << ", fs " << fs);
        const api::Compiled c = api::compile(text, api::options(mode, fs));
        INFO(api::describe(c.error));
        if (k.rule == nullptr) {
          CHECK(c.status == ARC_OK);
          continue;
        }
        CHECK(c.status == ARC_ERR_REJECTED);
        REQUIRE(api::all_written(c.error));
        CHECK(std::string(c.error.parameter) == spec::kLoudnessGain_gain_parameter);
        CHECK(std::string(c.error.value) == k.text);
        CHECK(std::string(c.error.rule) == k.rule);
        CHECK(std::string(c.error.limit) == k.limit);
      }
    }
  }
}

TEST_CASE("applied gain: the final master is the join times g of -1.5 dB; every other tap is measure's",
          "[api][loudness-gain]") {
  const std::string text = api::valid(spec::kLoudnessGain_final_fixture);
  CHECK(lg::member_value(text, "loudness_gain_db") == "-1.5");
  const spec::LoudnessGainValueVector& v = gain_value("-1.5");
  CHECK(v.k == -150);
  CHECK(api::bits(v.g) == v.g_bits);
  CHECK(api::bits(lg::harness_linear_gain(v.k, spec::kLoudnessGain_c)) == v.g_bits);
  for (const std::uint32_t fs : spec::sample_rates()) {
    INFO("fs " << fs);
    const TapRender m = render_taps(text, ARC_MODE_MEASURE, fs);
    const TapRender f = render_taps(text, ARC_MODE_FINAL, fs);
    CHECK(api::same_bytes(f.taps.theta_reference, m.taps.theta_reference));
    CHECK(api::same_bytes(f.taps.gamma_pac, m.taps.gamma_pac));
    CHECK(api::same_bytes(f.taps.stereo_bus, m.taps.stereo_bus));
    CHECK(api::same_bytes(f.taps.binaural_join, m.taps.binaural_join));
    CHECK(master_mismatches(f, v.g) == 0);
    CHECK(api::same_bytes(f.out, f.taps.master));
    // Measure mode is unit gain, so the gain did change the final output.
    CHECK(master_mismatches(m, 1.0) == 0);
    CHECK_FALSE(api::same_bytes(f.out, m.out));
  }
}

TEST_CASE("applied gain: every stored gain vector applies its g bit for bit; a zero gain changes nothing",
          "[api][loudness-gain]") {
  const std::string base = api::valid(spec::kLoudnessGain_final_fixture);
  const std::uint32_t fs = spec::sample_rates().back();
  const TapRender m = render_taps(base, ARC_MODE_MEASURE, fs);
  for (const auto& v : spec::kLoudnessGainValues) {
    INFO("stored gain " << v.text);
    CHECK(api::bits(lg::harness_linear_gain(v.k, spec::kLoudnessGain_c)) == v.g_bits);
    const std::string text = with_member(base, "loudness_gain_db", v.text);
    const TapRender f = render_taps(text, ARC_MODE_FINAL, fs);
    CHECK(api::same_bytes(f.taps.binaural_join, m.taps.binaural_join));
    CHECK(master_mismatches(f, v.g) == 0);
    if (v.k == 0) {
      CHECK(api::same_bytes(f.out, m.out));
      CHECK(api::same_bytes(f.taps.master, m.taps.master));
    } else {
      CHECK_FALSE(api::same_bytes(f.out, m.out));
    }
    // Measure mode ignores the stored gain.
    const TapRender mm = render_taps(text, ARC_MODE_MEASURE, fs);
    CHECK(api::same_bytes(mm.out, m.out));
  }
  // The zero texts at both rates, and the must-fail: a g one ulp off.
  for (const std::uint32_t rate : spec::sample_rates()) {
    INFO("fs " << rate);
    const TapRender mr = render_taps(base, ARC_MODE_MEASURE, rate);
    for (const char* zero : {"0.00", "-0.00"}) {
      INFO("stored gain " << zero);
      const TapRender f = render_taps(with_member(base, "loudness_gain_db", zero), ARC_MODE_FINAL, rate);
      CHECK(api::same_bytes(f.out, mr.out));
    }
    const TapRender f = render_taps(base, ARC_MODE_FINAL, rate);
    CHECK(master_mismatches(f, std::nextafter(gain_value("-1.5").g, 1.0)) > 0);
  }
}

#else  // ARC_ERROR_FIELD_BYTES

TEST_CASE("public header declares the C API with plain C types", "[api]") {
  FAIL("arcani/arcani.h does not declare the Story 1.2 C API yet (no ARC_ERROR_FIELD_BYTES)");
}

#endif  // ARC_ERROR_FIELD_BYTES
