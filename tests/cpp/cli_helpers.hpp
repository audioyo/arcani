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
// Story 2.7: a looping recipe's report has the member loop right after
// frames, with exactly opening_end_frame, seam_frames, and end_frame (in that
// order): the seams ascending, each above the opening end and below the end,
// and the end equal to frames. A report without loop is unchanged.
// Story 3.2: a report of a recipe with a spacing pair in at least one ear has
// the member spacing after loop (or after frames without it) and before
// determinism_key, with exactly left and right; each ear is null or an
// object with exactly min_distance_hz, margin_hz, component_1, component_2,
// pair (in that order): numbers, margin 0 or more and at most the minimum
// distance, component_1 below component_2, pair a non-empty string. At least
// one ear is not null. A report without spacing is unchanged.
inline void spacing_problems(const json::Value& spacing, std::vector<std::string>& p) {
  if (!members_are(spacing, {"left", "right"})) {
    p.push_back("spacing members are not exactly left, right (in that order)");
    return;
  }
  int pairs = 0;
  for (const char* ear : {"left", "right"}) {
    const json::Value& e = *spacing.find(ear);
    if (e.kind() == json::Kind::Null) {
      continue;
    }
    ++pairs;
    const std::string where = std::string("spacing ") + ear + " ";
    if (!members_are(e, {"min_distance_hz", "margin_hz", "component_1", "component_2", "pair"})) {
      p.push_back(where + "members are not exactly min_distance_hz, margin_hz, component_1, component_2, pair");
      continue;
    }
    const json::Value* distance = e.find("min_distance_hz");
    const json::Value* margin = e.find("margin_hz");
    const json::Value* c1 = e.find("component_1");
    const json::Value* c2 = e.find("component_2");
    const json::Value* pair = e.find("pair");
    if (distance->kind() != json::Kind::Number) p.push_back(where + "min_distance_hz is not a number");
    if (margin->kind() != json::Kind::Number) p.push_back(where + "margin_hz is not a number");
    if (distance->kind() == json::Kind::Number && margin->kind() == json::Kind::Number &&
        !(margin->number() >= 0.0 && margin->number() <= distance->number())) {
      p.push_back(where + "margin_hz is not in [0, min_distance_hz]");
    }
    if (!is_count(c1) || !is_count(c2)) {
      p.push_back(where + "component_1 or component_2 is not a non-negative integer");
    } else if (!(c1->number() < c2->number())) {
      p.push_back(where + "component_1 is not below component_2");
    }
    if (!is_string(pair) || pair->string().empty()) p.push_back(where + "pair is not a non-empty string");
  }
  if (pairs == 0) {
    p.push_back("spacing is written with no ear holding a pair");
  }
}

inline bool members_are(const json::Value& v, const std::vector<std::string>& names) {
  if (v.kind() != json::Kind::Object || v.object().size() != names.size()) {
    return false;
  }
  for (std::size_t i = 0; i < names.size(); ++i) {
    if (v.object()[i].first != names[i]) {
      return false;
    }
  }
  return true;
}

// Story 3.3: a preview report has the member preview after spacing (or loop,
// or frames) and before determinism_key, with exactly signed, peak_dbfs,
// layers_per_ear, gain, seconds (in that order): signed the JSON literal
// false, peak_dbfs a number at most 0, layers_per_ear a non-negative
// integer, gain a number above 0, and seconds exactly frames / sample_rate
// (one binary64 division). Its loop block, when present, is the plan's own,
// so end_frame is at least frames instead of equal to it.
inline void preview_problems(const json::Value& r, std::vector<std::string>& p) {
  const json::Value& preview = *r.find("preview");
  if (!members_are(preview, {"signed", "peak_dbfs", "layers_per_ear", "gain", "seconds"})) {
    p.push_back("preview members are not exactly signed, peak_dbfs, layers_per_ear, gain, seconds (in that order)");
    return;
  }
  const json::Value* signed_ = preview.find("signed");
  if (signed_->kind() != json::Kind::Bool || signed_->boolean()) {
    p.push_back("preview signed is not false");
  }
  const json::Value* peak = preview.find("peak_dbfs");
  if (peak->kind() != json::Kind::Number || !(peak->number() <= 0.0)) {
    p.push_back("preview peak_dbfs is not a number at most 0");
  }
  if (!is_count(preview.find("layers_per_ear"))) {
    p.push_back("preview layers_per_ear is not a non-negative integer");
  }
  const json::Value* gain = preview.find("gain");
  if (gain->kind() != json::Kind::Number || !(gain->number() > 0.0)) {
    p.push_back("preview gain is not a number above 0");
  }
  const json::Value* seconds = preview.find("seconds");
  const json::Value* frames = r.find("frames");
  const json::Value* rate = r.find("sample_rate");
  if (seconds->kind() != json::Kind::Number) {
    p.push_back("preview seconds is not a number");
  } else if (is_count(frames) && is_count(rate) && rate->number() > 0.0 &&
             seconds->number() != frames->number() / rate->number()) {
    p.push_back("preview seconds is not frames / sample_rate");
  }
}

inline std::vector<std::string> report_problems(const json::Value& r) {
  std::vector<std::string> p;
  const bool has_loop = r.kind() == json::Kind::Object && r.find("loop") != nullptr;
  const bool has_spacing = r.kind() == json::Kind::Object && r.find("spacing") != nullptr;
  const bool has_preview = r.kind() == json::Kind::Object && r.find("preview") != nullptr;
  const bool looping = has_loop;
  std::vector<std::string> names = {"engine_version", "seed", "sample_rate", "mode", "frames"};
  if (has_loop) names.push_back("loop");
  if (has_spacing) names.push_back("spacing");
  if (has_preview) names.push_back("preview");
  names.push_back("determinism_key");
  names.push_back("assertions");
  const bool shape = members_are(r, names);
  if (!shape) {
    p.push_back("top-level members are not exactly engine_version, seed, sample_rate, mode, "
                "frames, [loop,] [spacing,] [preview,] determinism_key, assertions (in that order)");
    return p;
  }
  if (has_preview) {
    preview_problems(r, p);
  }
  if (has_spacing) {
    spacing_problems(*r.find("spacing"), p);
  }
  if (looping) {
    const json::Value& loop = *r.find("loop");
    if (!members_are(loop, {"opening_end_frame", "seam_frames", "end_frame"})) {
      p.push_back("loop members are not exactly opening_end_frame, seam_frames, end_frame (in that order)");
    } else {
      const json::Value* opening = loop.find("opening_end_frame");
      const json::Value* end = loop.find("end_frame");
      const json::Value* seams = loop.find("seam_frames");
      if (!is_count(opening)) p.push_back("loop opening_end_frame is not a non-negative integer");
      if (!is_count(end)) p.push_back("loop end_frame is not a non-negative integer");
      if (is_count(end) && is_count(r.find("frames")) && !has_preview &&
          end->number() != r.find("frames")->number()) {
        p.push_back("loop end_frame differs from frames");
      }
      if (is_count(end) && is_count(r.find("frames")) && has_preview && end->number() < r.find("frames")->number()) {
        p.push_back("loop end_frame of a preview is below frames");
      }
      if (is_count(opening) && is_count(end) && !(opening->number() < end->number())) {
        p.push_back("loop opening_end_frame is not below end_frame");
      }
      if (seams->kind() != json::Kind::Array) {
        p.push_back("loop seam_frames is not an array");
      } else {
        double last = is_count(opening) ? opening->number() : -1.0;
        for (const json::Value& s : seams->array()) {
          if (!is_count(&s)) {
            p.push_back("loop seam_frames holds a value that is not a non-negative integer");
            break;
          }
          if (!(s.number() > last)) {
            p.push_back("loop seam_frames are not ascending above opening_end_frame");
            break;
          }
          if (is_count(end) && !(s.number() < end->number())) {
            p.push_back("loop seam_frames holds a frame at or past end_frame");
            break;
          }
          last = s.number();
        }
      }
    }
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
