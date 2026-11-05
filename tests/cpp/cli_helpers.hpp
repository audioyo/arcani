// Test harness for the command-line renderer (Story 1.4): the spec 24-bit
// rounding rule and the naive conversions the tests must catch, a WAV header
// builder and parser written from the WAV layout of the Story 1.4 spec and
// EBU Tech 3306 (RF64), and the report structure check. Test code only; no
// part of it lives in cli/ or engine/.
//
// Every conversion here is free of undefined behavior: a value is cast to an
// integer only after a clamp or a range check has put it in range, and NaN
// is never cast.

#pragma once

#include "json/value.hpp"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <initializer_list>
#include <iterator>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace arcani::test::cli {

// ------------------------------------------------------- 24-bit rounding

inline constexpr std::int32_t kQ24Max = 8388607;       // 2^23 - 1
inline constexpr std::int32_t kQ24Min = -8388607 - 1;  // -2^23

// Nearest integer to x, ties to even, for |x| < 2^52 (so floor and the
// fractional part are exact). Returned as a double holding an integer.
inline double round_half_even(double x) {
  const double f = std::floor(x);
  const double frac = x - f;
  if (frac > 0.5) {
    return f + 1.0;
  }
  if (frac < 0.5) {
    return f;
  }
  return std::fmod(f, 2.0) == 0.0 ? f : f + 1.0;
}

// docs/signal-spec.md, 24-bit rounding, written independently of cli/.
inline std::int32_t spec_quantize_24(double s) {
  if (std::isnan(s)) {
    return 0;
  }
  const double x = s * 0x1p23;
  if (x >= 8388607.0) {
    return kQ24Max;
  }
  if (x <= -8388608.0) {
    return kQ24Min;
  }
  return static_cast<std::int32_t>(round_half_even(x));  // |x| < 2^23: in range
}

// Must-fail conversions. Each breaks exactly one rule of the spec.

// No clamp: rounds ties to even, then keeps the low 24 bits (what a writer
// that stores the low 3 bytes of a wider integer does). Non-finite x gives 0.
inline std::int32_t naive_no_clamp(double s) {
  if (std::isnan(s)) {
    return 0;
  }
  const double x = s * 0x1p23;
  if (!std::isfinite(x)) {
    return 0;
  }
  double r = std::fmod(round_half_even(x), 16777216.0);  // exact, |r| < 2^24
  if (r >= 8388608.0) {
    r -= 16777216.0;
  } else if (r < -8388608.0) {
    r += 16777216.0;
  }
  return static_cast<std::int32_t>(r);
}

// No NaN rule: the clamp is written as !(x < max), so NaN lands on full scale.
inline std::int32_t naive_no_nan_rule(double s) {
  const double x = s * 0x1p23;
  if (!(x < 8388607.0)) {
    return kQ24Max;
  }
  if (x <= -8388608.0) {
    return kQ24Min;
  }
  return static_cast<std::int32_t>(round_half_even(x));
}

// Truncation toward zero instead of ties to even.
inline std::int32_t naive_truncate(double s) {
  if (std::isnan(s)) {
    return 0;
  }
  const double x = s * 0x1p23;
  if (x >= 8388607.0) {
    return kQ24Max;
  }
  if (x <= -8388608.0) {
    return kQ24Min;
  }
  return static_cast<std::int32_t>(std::trunc(x));
}

// Ties away from zero (std::round) instead of ties to even.
inline std::int32_t naive_half_away(double s) {
  if (std::isnan(s)) {
    return 0;
  }
  const double x = s * 0x1p23;
  if (x >= 8388607.0) {
    return kQ24Max;
  }
  if (x <= -8388608.0) {
    return kQ24Min;
  }
  return static_cast<std::int32_t>(std::round(x));
}

// 3 bytes, little-endian two's complement (conversion to unsigned is modular).
inline void put_le24(std::vector<std::uint8_t>& out, std::int32_t v) {
  const std::uint32_t u = static_cast<std::uint32_t>(v) & 0xFFFFFFu;
  out.push_back(static_cast<std::uint8_t>(u & 0xFFu));
  out.push_back(static_cast<std::uint8_t>((u >> 8) & 0xFFu));
  out.push_back(static_cast<std::uint8_t>((u >> 16) & 0xFFu));
}

// The WAV data bytes for interleaved stereo output, by the spec rule.
inline std::vector<std::uint8_t> spec_data_bytes(const std::vector<double>& interleaved) {
  std::vector<std::uint8_t> out;
  out.reserve(interleaved.size() * 3);
  for (double s : interleaved) {
    put_le24(out, spec_quantize_24(s));
  }
  return out;
}

// ----------------------------------------------------------- byte helpers

inline void put_tag(std::vector<std::uint8_t>& out, const char (&tag)[5]) {
  out.insert(out.end(), tag, tag + 4);
}

inline void put_u16(std::vector<std::uint8_t>& out, std::uint16_t v) {
  for (int i = 0; i < 2; ++i) {
    out.push_back(static_cast<std::uint8_t>((v >> (8 * i)) & 0xFFu));
  }
}

inline void put_u32(std::vector<std::uint8_t>& out, std::uint32_t v) {
  for (int i = 0; i < 4; ++i) {
    out.push_back(static_cast<std::uint8_t>((v >> (8 * i)) & 0xFFu));
  }
}

inline void put_u64(std::vector<std::uint8_t>& out, std::uint64_t v) {
  for (int i = 0; i < 8; ++i) {
    out.push_back(static_cast<std::uint8_t>((v >> (8 * i)) & 0xFFu));
  }
}

inline std::uint64_t get_le(const std::vector<std::uint8_t>& b, std::size_t at, int bytes) {
  std::uint64_t v = 0;
  for (int i = bytes - 1; i >= 0; --i) {
    v = (v << 8) | b[at + static_cast<std::size_t>(i)];
  }
  return v;
}

inline bool tag_at(const std::vector<std::uint8_t>& b, std::size_t at, const char* tag) {
  return b.size() >= at + 4 && std::memcmp(b.data() + at, tag, 4) == 0;
}

// --------------------------------------------------------------- WAV file

inline constexpr std::uint32_t kChannels = 2;
inline constexpr std::uint32_t kBlockAlign = 6;  // 2 channels x 3 bytes
inline constexpr std::uint64_t kU32Max = 0xFFFFFFFFull;

// RF64 when the RIFF size field (36 + data bytes) would not fit in 32 bits.
inline bool needs_rf64(std::uint64_t frames) { return 36 + frames * kBlockAlign > kU32Max; }

inline void put_fmt(std::vector<std::uint8_t>& out, std::uint32_t rate) {
  put_tag(out, "fmt ");
  put_u32(out, 16);
  put_u16(out, 1);  // WAVE_FORMAT_PCM
  put_u16(out, static_cast<std::uint16_t>(kChannels));
  put_u32(out, rate);
  put_u32(out, rate * kBlockAlign);
  put_u16(out, static_cast<std::uint16_t>(kBlockAlign));
  put_u16(out, 24);
}

// The header the spec requires: a pure function of frame count and rate.
// RIFF: 44 bytes. RF64 (EBU Tech 3306): 80 bytes, ds64 right after WAVE with
// riffSize = file size - 8, dataSize, sampleCount = frames, table length 0;
// the 32-bit RIFF and data sizes are 0xFFFFFFFF.
inline std::vector<std::uint8_t> expected_wav_header(std::uint64_t frames, std::uint32_t rate) {
  const std::uint64_t data = frames * kBlockAlign;
  std::vector<std::uint8_t> h;
  if (!needs_rf64(frames)) {
    put_tag(h, "RIFF");
    put_u32(h, static_cast<std::uint32_t>(36 + data));
    put_tag(h, "WAVE");
    put_fmt(h, rate);
    put_tag(h, "data");
    put_u32(h, static_cast<std::uint32_t>(data));
    return h;
  }
  put_tag(h, "RF64");
  put_u32(h, 0xFFFFFFFFu);
  put_tag(h, "WAVE");
  put_tag(h, "ds64");
  put_u32(h, 28);
  put_u64(h, 72 + data);  // riffSize: 80-byte header + data - 8
  put_u64(h, data);       // dataSize
  put_u64(h, frames);     // sampleCount
  put_u32(h, 0);          // table length
  put_fmt(h, rate);
  put_tag(h, "data");
  put_u32(h, 0xFFFFFFFFu);
  return h;
}

// Problems with a whole WAV file (header and data) against the spec layout,
// for `frames` frames at `rate`. Empty when the file is right. The data bytes
// themselves are compared by the caller.
inline std::vector<std::string> wav_problems(const std::vector<std::uint8_t>& b,
                                             std::uint64_t frames, std::uint32_t rate) {
  std::vector<std::string> p;
  const bool rf64 = tag_at(b, 0, "RF64");
  const std::size_t header = rf64 ? 80 : 44;
  if (b.size() < header) {
    p.push_back("file shorter than the header");
    return p;
  }
  if (!rf64 && !tag_at(b, 0, "RIFF")) {
    p.push_back("not RIFF or RF64");
    return p;
  }
  if (rf64 != needs_rf64(frames)) {
    p.push_back(rf64 ? "RF64 for a size that fits RIFF" : "RIFF for a size that needs RF64");
  }
  if (!tag_at(b, 8, "WAVE")) {
    p.push_back("no WAVE form type");
  }
  std::size_t at = 12;
  std::uint64_t ds64_riff = 0, ds64_data = 0, ds64_count = 0;
  if (rf64) {
    if (get_le(b, 4, 4) != kU32Max) {
      p.push_back("RF64 size field is not 0xFFFFFFFF");
    }
    if (!tag_at(b, at, "ds64") || get_le(b, at + 4, 4) != 28) {
      p.push_back("no 28-byte ds64 chunk right after WAVE");
      return p;
    }
    ds64_riff = get_le(b, at + 8, 8);
    ds64_data = get_le(b, at + 16, 8);
    ds64_count = get_le(b, at + 24, 8);
    if (get_le(b, at + 32, 4) != 0) {
      p.push_back("ds64 table length is not 0");
    }
    at += 36;
  }
  if (!tag_at(b, at, "fmt ") || get_le(b, at + 4, 4) != 16) {
    p.push_back("no 16-byte fmt chunk where expected");
    return p;
  }
  if (get_le(b, at + 8, 2) != 1) p.push_back("format tag is not WAVE_FORMAT_PCM (1)");
  if (get_le(b, at + 10, 2) != kChannels) p.push_back("not 2 channels");
  if (get_le(b, at + 12, 4) != rate) p.push_back("sample rate differs");
  if (get_le(b, at + 16, 4) != std::uint64_t{rate} * kBlockAlign) p.push_back("byte rate differs");
  if (get_le(b, at + 20, 2) != kBlockAlign) p.push_back("block align is not 6");
  if (get_le(b, at + 22, 2) != 24) p.push_back("not 24 bits per sample");
  at += 24;
  if (!tag_at(b, at, "data")) {
    p.push_back("data chunk does not follow fmt (another chunk is present)");
    return p;
  }
  const std::uint64_t data = frames * kBlockAlign;
  const std::uint64_t data_field = get_le(b, at + 4, 4);
  at += 8;
  if (rf64) {
    if (data_field != kU32Max) p.push_back("RF64 data size field is not 0xFFFFFFFF");
    if (ds64_data != data) p.push_back("ds64 data size differs from frames x 6");
    if (ds64_count != frames) p.push_back("ds64 sample count differs from frames");
    if (ds64_riff != b.size() - 8) p.push_back("ds64 RIFF size is not file size - 8");
  } else {
    if (data_field != data) p.push_back("data size differs from frames x 6");
    if (get_le(b, 4, 4) != b.size() - 8) p.push_back("RIFF size is not file size - 8");
  }
  if (b.size() != at + data) {
    p.push_back("file size is not header + frames x 6 (truncated or trailing bytes)");
  }
  return p;
}

// ---------------------------------------------------------------- report

inline bool is_lower_hex(const std::string& s, std::size_t length) {
  if (s.size() != length) {
    return false;
  }
  for (char c : s) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) {
      return false;
    }
  }
  return true;
}

inline bool members_are(const json::Value& v, std::initializer_list<const char*> names) {
  if (v.kind() != json::Kind::Object || v.object().size() != names.size()) {
    return false;
  }
  std::size_t i = 0;
  for (const char* n : names) {
    if (v.object()[i++].first != n) {
      return false;
    }
  }
  return true;
}

inline bool is_count(const json::Value* v) {
  return v != nullptr && v->kind() == json::Kind::Number && v->integral() && v->number() >= 0.0;
}

inline bool is_string(const json::Value* v) {
  return v != nullptr && v->kind() == json::Kind::String;
}

// Problems with a report's structure (the Story 1.4 Report decision).
// Members are checked in the order the spec lists them.
inline std::vector<std::string> report_problems(const json::Value& r) {
  std::vector<std::string> p;
  if (!members_are(r, {"engine_version", "seed", "sample_rate", "mode", "frames",
                       "determinism_key", "assertions"})) {
    p.push_back("top-level members are not exactly engine_version, seed, sample_rate, mode, "
                "frames, determinism_key, assertions (in that order)");
    return p;
  }
  if (!is_string(r.find("engine_version"))) p.push_back("engine_version is not a string");
  if (!is_count(r.find("seed"))) p.push_back("seed is not a non-negative integer");
  if (!is_count(r.find("sample_rate"))) p.push_back("sample_rate is not an integer");
  const json::Value* mode = r.find("mode");
  if (!is_string(mode) || (mode->string() != "measure" && mode->string() != "final")) {
    p.push_back("mode is not measure or final");
  }
  if (!is_count(r.find("frames"))) p.push_back("frames is not a non-negative integer");
  const json::Value& key = *r.find("determinism_key");
  if (!members_are(key, {"recipe_hash", "asset_hashes", "engine_version", "sample_rate"})) {
    p.push_back("determinism_key members are not exactly recipe_hash, asset_hashes, "
                "engine_version, sample_rate (in that order)");
  } else {
    if (!is_string(key.find("recipe_hash")) || !is_lower_hex(key.find("recipe_hash")->string(), 64)) {
      p.push_back("recipe_hash is not 64 lowercase hex digits");
    }
    const json::Value* assets = key.find("asset_hashes");
    if (assets->kind() != json::Kind::Array) {
      p.push_back("asset_hashes is not an array");
    } else {
      for (const json::Value& a : assets->array()) {
        if (a.kind() != json::Kind::String) p.push_back("asset_hashes holds a non-string");
      }
    }
    if (!is_string(key.find("engine_version")) || !is_string(r.find("engine_version")) ||
        key.find("engine_version")->string() != r.find("engine_version")->string()) {
      p.push_back("determinism_key engine_version differs from engine_version");
    }
    if (!is_count(key.find("sample_rate")) || !is_count(r.find("sample_rate")) ||
        key.find("sample_rate")->number() != r.find("sample_rate")->number()) {
      p.push_back("determinism_key sample_rate differs from sample_rate");
    }
  }
  const json::Value& list = *r.find("assertions");
  if (list.kind() != json::Kind::Array) {
    p.push_back("assertions is not an array");
    return p;
  }
  for (const json::Value& a : list.array()) {
    if (!members_are(a, {"name", "row", "threshold", "unit", "measured", "result", "note"})) {
      p.push_back("assertion members are not exactly name, row, threshold, unit, measured, "
                  "result, note (in that order)");
      continue;
    }
    for (const char* s : {"name", "row", "unit", "note"}) {
      if (!is_string(a.find(s))) p.push_back(std::string("assertion ") + s + " is not a string");
    }
    if (a.find("threshold")->kind() != json::Kind::Number) {
      p.push_back("assertion threshold is not a number");
    }
    const json::Value* result = a.find("result");
    const json::Value* measured = a.find("measured");
    const json::Value* note = a.find("note");
    const bool na = is_string(result) && result->string() == "not_applicable";
    if (!is_string(result) ||
        (result->string() != "pass" && result->string() != "fail" && !na)) {
      p.push_back("assertion result is not pass, fail, or not_applicable");
    }
    if (na && measured->kind() != json::Kind::Null) {
      p.push_back("not_applicable assertion has a measured value");
    }
    if (!na && measured->kind() != json::Kind::Number) {
      p.push_back("assertion measured is not a number");
    }
    if (is_string(note) && na == note->string().empty()) {
      p.push_back(na ? "not_applicable assertion has an empty note"
                     : "note is not empty on a pass or fail");
    }
  }
  return p;
}

// --------------------------------------------------------------- files

inline std::optional<std::vector<std::uint8_t>> read_bytes(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in.good()) {
    return std::nullopt;
  }
  return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(in),
                                   std::istreambuf_iterator<char>());
}

inline std::string as_text(const std::vector<std::uint8_t>& b) {
  return std::string(b.begin(), b.end());
}

}  // namespace arcani::test::cli
