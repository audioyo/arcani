// Binaural isolation measurement and assertion (Story 1.2, FR-4). Test code
// only: the engine never measures itself.
//
// Muted-ear method. The plan is compiled with one ear's binaural oscillator
// muted (compile option mute_binaural_ear), so that ear's channel should hold
// nothing at the other ear's carrier. The measurement reads, over the whole
// render, a Hann-windowed single-bin DFT of each channel at the active ear's
// carrier f:
//
//   w[n]     = 0.5 - 0.5 * cos(2 * pi * n / N)            n = 0 .. N-1
//   X_c(f)   = sum over n of w[n] * x_c[n] * exp(-i * 2 * pi * f * n / fs)
//   level_db = 20 * log10(|X_muted(f)| / |X_active(f)|)
//
// The assertion passes when level_db <= -threshold, the threshold read from
// row binaural-isolation-engine (binaural join tap) or
// binaural-isolation-master (master output). It fails as silent when
// |X_active(f)| is exactly zero: a silent active ear proves nothing.
//
// Band mode (Story 2.5, measure_band below) is for a beat rate cycle, whose
// active carrier sweeps a band: it compares the two channels' energy over
// that band instead of one bin.
//
// The measurement is calibrated on Python-synthesized signals with known
// leakage (tools/isolation_calibration.py, tests/data/isolation_calibration.json,
// read here by load_calibration) before it judges any engine render.

#pragma once

#include "spec_helpers.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace arcani::test::isolation {

enum class Channel { Left = 0, Right = 1 };

inline Channel other(Channel c) { return c == Channel::Left ? Channel::Right : Channel::Left; }

inline const char* name(Channel c) { return c == Channel::Left ? "left" : "right"; }

// |X_c(f)| of one channel of an interleaved stereo buffer (left, right per
// frame). The angle is reduced exactly as far as binary64 allows
// (fmod(f * n, fs)) before the cosine and sine, so long renders keep their
// accuracy.
inline double hann_bin_magnitude(const std::vector<double>& stereo, Channel ch, double f_hz,
                                 std::uint32_t fs) {
  if (stereo.size() % 2 != 0) {
    throw std::runtime_error("isolation: stereo buffer has an odd sample count");
  }
  const std::size_t frames = stereo.size() / 2;
  if (frames == 0) {
    return 0.0;
  }
  const double two_pi = 6.283185307179586476925286766559;
  const double big_n = static_cast<double>(frames);
  const double rate = static_cast<double>(fs);
  const std::size_t offset = ch == Channel::Left ? 0 : 1;
  double re = 0.0;
  double im = 0.0;
  for (std::size_t n = 0; n < frames; ++n) {
    const double x = stereo[2 * n + offset];
    if (x == 0.0) {
      continue;
    }
    const double dn = static_cast<double>(n);
    const double w = 0.5 - 0.5 * std::cos(two_pi * dn / big_n);
    const double angle = two_pi * (std::fmod(f_hz * dn, rate) / rate);
    re += w * x * std::cos(angle);
    im -= w * x * std::sin(angle);
  }
  return std::hypot(re, im);
}

struct Measurement {
  Channel active = Channel::Left;
  double carrier_hz = 0.0;  // bin mode: the active carrier; band mode: the band center
  bool band = false;        // band mode (measure_band)
  double band_lo_hz = 0.0;  // band mode: the band the active carrier spans, before the guard
  double band_hi_hz = 0.0;
  double active_magnitude = 0.0;
  double muted_magnitude = 0.0;
  double level_db = 0.0;  // -inf when the muted channel measures exactly zero
  bool silent = false;    // the active carrier measured exactly zero
};

inline Measurement measure(const std::vector<double>& stereo, Channel active, double carrier_hz,
                           std::uint32_t fs) {
  Measurement m;
  m.active = active;
  m.carrier_hz = carrier_hz;
  m.active_magnitude = hann_bin_magnitude(stereo, active, carrier_hz, fs);
  m.muted_magnitude = hann_bin_magnitude(stereo, other(active), carrier_hz, fs);
  m.silent = m.active_magnitude == 0.0;
  if (m.silent) {
    m.level_db = std::numeric_limits<double>::quiet_NaN();
  } else if (m.muted_magnitude == 0.0) {
    m.level_db = -std::numeric_limits<double>::infinity();
  } else {
    m.level_db = 20.0 * std::log10(m.muted_magnitude / m.active_magnitude);
  }
  return m;
}

// ------------------------------------------------------------- band mode
//
// Story 2.5. Along a beat rate cycle the active ear's carrier sweeps a band,
// so one DFT bin no longer holds it. Band mode reads the muted channel's
// energy over the band the active carrier spans, extended by a guard of
// kBandGuardBins DFT bins of the render length (the Hann main lobe half
// width) on each side, against the active channel's energy over the same
// band:
//
//   X_c[k]   = FFT of w[n] * x_c[n], zero-padded to M = the next power of two >= N
//   band     = [band_lo - G * fs / N, band_hi + G * fs / N],  G = kBandGuardBins
//   E_c      = sum over k with k * fs / M in band of |X_c[k]|^2
//   level_db = 10 * log10(E_muted / E_active)
//
// with the same Hann window w[n] as bin mode. It fails as silent when
// E_active is exactly zero.

inline constexpr int kBandGuardBins = 2;

namespace detail {

// In-place iterative radix-2 FFT (decimation in time); size a power of two.
inline void fft(std::vector<std::complex<double>>& a) {
  const std::size_t n = a.size();
  for (std::size_t i = 1, j = 0; i < n; ++i) {
    std::size_t bit = n >> 1;
    for (; (j & bit) != 0; bit >>= 1) {
      j ^= bit;
    }
    j ^= bit;
    if (i < j) {
      std::swap(a[i], a[j]);
    }
  }
  const double two_pi = 6.283185307179586476925286766559;
  for (std::size_t len = 2; len <= n; len <<= 1) {
    const std::size_t half = len / 2;
    // Twiddles computed directly per index (not by repeated multiplication),
    // so long transforms keep their accuracy.
    std::vector<std::complex<double>> w(half);
    for (std::size_t k = 0; k < half; ++k) {
      const double angle = -two_pi * static_cast<double>(k) / static_cast<double>(len);
      w[k] = std::complex<double>(std::cos(angle), std::sin(angle));
    }
    for (std::size_t i = 0; i < n; i += len) {
      for (std::size_t k = 0; k < half; ++k) {
        const std::complex<double> u = a[i + k];
        const std::complex<double> v = a[i + k + half] * w[k];
        a[i + k] = u + v;
        a[i + k + half] = u - v;
      }
    }
  }
}

}  // namespace detail

inline Measurement measure_band(const std::vector<double>& stereo, Channel active, double band_lo_hz,
                                double band_hi_hz, std::uint32_t fs) {
  if (stereo.size() % 2 != 0) {
    throw std::runtime_error("isolation: stereo buffer has an odd sample count");
  }
  if (!(band_lo_hz <= band_hi_hz)) {
    throw std::runtime_error("isolation: band_lo_hz is above band_hi_hz");
  }
  Measurement m;
  m.active = active;
  m.band = true;
  m.band_lo_hz = band_lo_hz;
  m.band_hi_hz = band_hi_hz;
  m.carrier_hz = 0.5 * (band_lo_hz + band_hi_hz);
  const std::size_t frames = stereo.size() / 2;
  double e_active = 0.0;
  double e_muted = 0.0;
  if (frames > 0) {
    std::size_t size = 1;
    while (size < frames) {
      size <<= 1;
    }
    // One transform per channel, so a channel of exact zeros has exactly zero
    // energy.
    const double two_pi = 6.283185307179586476925286766559;
    const double big_n = static_cast<double>(frames);
    const double rate = static_cast<double>(fs);
    const double guard = static_cast<double>(kBandGuardBins) * rate / big_n;
    const double df = rate / static_cast<double>(size);
    const double lo = band_lo_hz - guard;
    const double hi = band_hi_hz + guard;
    const std::size_t first = lo <= 0.0 ? 0 : static_cast<std::size_t>(std::ceil(lo / df));
    const std::size_t last = std::min(size / 2, static_cast<std::size_t>(std::floor(hi / df)));
    double e[2] = {0.0, 0.0};
    std::vector<std::complex<double>> z(size);
    for (std::size_t c = 0; c < 2; ++c) {
      std::fill(z.begin(), z.end(), std::complex<double>(0.0, 0.0));
      for (std::size_t n = 0; n < frames; ++n) {
        const double w = 0.5 - 0.5 * std::cos(two_pi * static_cast<double>(n) / big_n);
        z[n] = std::complex<double>(w * stereo[2 * n + c], 0.0);
      }
      detail::fft(z);
      for (std::size_t k = first; k <= last; ++k) {
        e[c] += std::norm(z[k]);
      }
    }
    const std::size_t a = active == Channel::Left ? 0 : 1;
    e_active = e[a];
    e_muted = e[1 - a];
  }
  m.active_magnitude = std::sqrt(e_active);
  m.muted_magnitude = std::sqrt(e_muted);
  m.silent = e_active == 0.0;
  if (m.silent) {
    m.level_db = std::numeric_limits<double>::quiet_NaN();
  } else if (e_muted == 0.0) {
    m.level_db = -std::numeric_limits<double>::infinity();
  } else {
    m.level_db = 10.0 * std::log10(e_muted / e_active);
  }
  return m;
}

struct Verdict {
  std::string row_id;
  double threshold_db = 0.0;  // the row value: dB below the ear's own binaural carrier
  double measured_db = 0.0;
  bool silent = false;
  bool pass = false;
};

// The isolation assertion: reads the threshold row through the assertion
// call (recording its use) and judges one measurement.
inline Verdict judge(const Measurement& m, const char* row_id) {
  Verdict v;
  v.row_id = row_id;
  v.threshold_db = spec::db_row(row_id).value();
  v.measured_db = m.level_db;
  v.silent = m.silent;
  v.pass = !m.silent && m.level_db <= -v.threshold_db;
  return v;
}

inline std::string describe(const Verdict& v) {
  std::ostringstream s;
  s << v.row_id << ": " << (v.silent ? "silent" : (v.pass ? "pass" : "fail")) << ", measured "
    << v.measured_db << " dB, threshold -" << v.threshold_db << " dB";
  return s.str();
}

// Adds gain * the active channel into the muted channel, in place: the
// harness-side doctoring for must-fail cases (never done in engine/).
inline void add_crosstalk(std::vector<double>& stereo, Channel active, double gain) {
  const std::size_t a = active == Channel::Left ? 0 : 1;
  for (std::size_t n = 0; n + 1 < stereo.size(); n += 2) {
    stereo[n + (1 - a)] += gain * stereo[n + a];
  }
}

// ------------------------------------------------------------ calibration

namespace detail {

// Minimal JSON reader for the calibration file: objects, arrays, strings
// (with the standard escapes, no \u), numbers, true, false, null.
struct Json {
  enum class Kind { Null, Bool, Number, String, Array, Object } kind = Kind::Null;
  bool boolean = false;
  double number = 0.0;
  std::string string;
  std::vector<Json> array;
  std::map<std::string, Json> object;

  const Json& at(const std::string& key) const {
    const auto it = object.find(key);
    if (kind != Kind::Object || it == object.end()) {
      throw std::runtime_error("calibration json: missing key " + key);
    }
    return it->second;
  }
};

class JsonReader {
 public:
  explicit JsonReader(const std::string& text) : t_(text) {}

  Json document() {
    Json v = value();
    ws();
    if (i_ != t_.size()) {
      fail("trailing data");
    }
    return v;
  }

 private:
  [[noreturn]] void fail(const char* what) const {
    throw std::runtime_error(std::string("calibration json: ") + what + " at byte " +
                             std::to_string(i_));
  }
  void ws() {
    while (i_ < t_.size() && (t_[i_] == ' ' || t_[i_] == '\n' || t_[i_] == '\r' || t_[i_] == '\t')) {
      ++i_;
    }
  }
  void expect(char c) {
    ws();
    if (i_ >= t_.size() || t_[i_] != c) {
      fail("unexpected character");
    }
    ++i_;
  }
  bool literal(const char* word) {
    const std::size_t n = std::strlen(word);
    if (t_.compare(i_, n, word) == 0) {
      i_ += n;
      return true;
    }
    return false;
  }
  std::string str() {
    expect('"');
    std::string out;
    while (true) {
      if (i_ >= t_.size()) {
        fail("unterminated string");
      }
      const char c = t_[i_++];
      if (c == '"') {
        return out;
      }
      if (c != '\\') {
        out.push_back(c);
        continue;
      }
      if (i_ >= t_.size()) {
        fail("unterminated escape");
      }
      const char e = t_[i_++];
      switch (e) {
        case '"': out.push_back('"'); break;
        case '\\': out.push_back('\\'); break;
        case '/': out.push_back('/'); break;
        case 'n': out.push_back('\n'); break;
        case 't': out.push_back('\t'); break;
        case 'r': out.push_back('\r'); break;
        case 'b': out.push_back('\b'); break;
        case 'f': out.push_back('\f'); break;
        default: fail("unsupported escape");
      }
    }
  }
  Json value() {
    ws();
    if (i_ >= t_.size()) {
      fail("unexpected end");
    }
    Json v;
    const char c = t_[i_];
    if (c == '{') {
      v.kind = Json::Kind::Object;
      ++i_;
      ws();
      if (i_ < t_.size() && t_[i_] == '}') {
        ++i_;
        return v;
      }
      while (true) {
        std::string key = str();
        expect(':');
        v.object.emplace(std::move(key), value());
        ws();
        if (i_ < t_.size() && t_[i_] == ',') {
          ++i_;
          continue;
        }
        expect('}');
        return v;
      }
    }
    if (c == '[') {
      v.kind = Json::Kind::Array;
      ++i_;
      ws();
      if (i_ < t_.size() && t_[i_] == ']') {
        ++i_;
        return v;
      }
      while (true) {
        v.array.push_back(value());
        ws();
        if (i_ < t_.size() && t_[i_] == ',') {
          ++i_;
          continue;
        }
        expect(']');
        return v;
      }
    }
    if (c == '"') {
      v.kind = Json::Kind::String;
      v.string = str();
      return v;
    }
    if (literal("true")) {
      v.kind = Json::Kind::Bool;
      v.boolean = true;
      return v;
    }
    if (literal("false")) {
      v.kind = Json::Kind::Bool;
      return v;
    }
    if (literal("null")) {
      return v;
    }
    const std::size_t start = i_;
    while (i_ < t_.size() && std::strchr("+-0123456789.eE", t_[i_]) != nullptr) {
      ++i_;
    }
    if (start == i_) {
      fail("unexpected character");
    }
    v.kind = Json::Kind::Number;
    v.number = std::stod(t_.substr(start, i_ - start));
    return v;
  }

  const std::string& t_;
  std::size_t i_ = 0;
};

inline std::vector<unsigned char> base64_decode(const std::string& text) {
  auto digit = [](char c) -> int {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
  };
  if (text.size() % 4 != 0) {
    throw std::runtime_error("base64: length is not a multiple of 4");
  }
  std::vector<unsigned char> out;
  out.reserve(text.size() / 4 * 3);
  for (std::size_t i = 0; i < text.size(); i += 4) {
    int v[4];
    int pad = 0;
    for (int k = 0; k < 4; ++k) {
      const char c = text[i + static_cast<std::size_t>(k)];
      if (c == '=' && i + 4 == text.size() && k >= 2) {
        v[k] = 0;
        ++pad;
      } else {
        v[k] = digit(c);
        if (v[k] < 0 || pad > 0) {
          throw std::runtime_error("base64: bad character");
        }
      }
    }
    const unsigned word = (static_cast<unsigned>(v[0]) << 18) | (static_cast<unsigned>(v[1]) << 12) |
                          (static_cast<unsigned>(v[2]) << 6) | static_cast<unsigned>(v[3]);
    out.push_back(static_cast<unsigned char>((word >> 16) & 0xFFu));
    if (pad < 2) out.push_back(static_cast<unsigned char>((word >> 8) & 0xFFu));
    if (pad < 1) out.push_back(static_cast<unsigned char>(word & 0xFFu));
  }
  return out;
}

// Little-endian float32 samples, widened to binary64 (exact).
inline std::vector<double> decode_f32(const std::string& text) {
  const auto bytes = base64_decode(text);
  if (bytes.size() % 4 != 0) {
    throw std::runtime_error("calibration: payload is not whole float32 samples");
  }
  std::vector<double> out(bytes.size() / 4);
  for (std::size_t i = 0; i < out.size(); ++i) {
    std::uint32_t word = 0;
    for (int k = 0; k < 4; ++k) {
      word |= static_cast<std::uint32_t>(bytes[4 * i + static_cast<std::size_t>(k)]) << (8 * k);
    }
    float f = 0.0f;
    std::memcpy(&f, &word, sizeof f);
    out[i] = static_cast<double>(f);
  }
  return out;
}

}  // namespace detail

struct CalibrationCase {
  double level_db = 0.0;      // known level of the muted channel, dB re the active carrier
  std::vector<double> stereo;  // interleaved left, right
};

struct CalibrationSetup {
  std::string id;
  std::uint32_t fs = 0;
  double carrier_hz = 0.0;  // bin mode: the carrier; band mode: the sweep center
  Channel active = Channel::Left;
  bool band = false;        // mode "band" (Story 2.5): read with measure_band
  double band_lo_hz = 0.0;  // band mode: the swept carrier's minimum
  double band_hi_hz = 0.0;  // band mode: the swept carrier's maximum
  std::vector<CalibrationCase> cases;
};

inline std::vector<CalibrationSetup> load_calibration(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in.good()) {
    throw std::runtime_error("cannot read " + path + ": run python tools/isolation_calibration.py");
  }
  std::stringstream ss;
  ss << in.rdbuf();
  const std::string text = ss.str();
  const detail::Json doc = detail::JsonReader(text).document();
  if (doc.at("encoding").string != "base64 of little-endian float32") {
    throw std::runtime_error("calibration: unexpected encoding");
  }
  std::vector<CalibrationSetup> out;
  for (const detail::Json& s : doc.at("setups").array) {
    CalibrationSetup setup;
    setup.id = s.at("id").string;
    setup.fs = static_cast<std::uint32_t>(s.at("fs").number);
    setup.carrier_hz = s.at("carrier_hz").number;
    const std::string& ch = s.at("active_channel").string;
    if (ch != "left" && ch != "right") {
      throw std::runtime_error("calibration: bad active_channel " + ch);
    }
    setup.active = ch == "left" ? Channel::Left : Channel::Right;
    const auto mode = s.object.find("mode");
    const std::string mode_text = mode == s.object.end() ? std::string("bin") : mode->second.string;
    if (mode_text != "bin" && mode_text != "band") {
      throw std::runtime_error("calibration: bad mode " + mode_text);
    }
    setup.band = mode_text == "band";
    if (setup.band) {
      setup.band_lo_hz = s.at("band_lo_hz").number;
      setup.band_hi_hz = s.at("band_hi_hz").number;
    }
    const auto frames = static_cast<std::size_t>(s.at("frames").number);
    const std::vector<double> active = detail::decode_f32(s.at("active").string);
    if (active.size() != frames) {
      throw std::runtime_error("calibration: active channel length mismatch in " + setup.id);
    }
    for (const detail::Json& c : s.at("cases").array) {
      CalibrationCase cc;
      cc.level_db = c.at("level_db").number;
      const std::vector<double> muted = detail::decode_f32(c.at("muted").string);
      if (muted.size() != frames) {
        throw std::runtime_error("calibration: muted channel length mismatch in " + setup.id);
      }
      cc.stereo.resize(2 * frames);
      const std::size_t a = setup.active == Channel::Left ? 0 : 1;
      for (std::size_t n = 0; n < frames; ++n) {
        cc.stereo[2 * n + a] = active[n];
        cc.stereo[2 * n + (1 - a)] = muted[n];
      }
      setup.cases.push_back(std::move(cc));
    }
    out.push_back(std::move(setup));
  }
  return out;
}

}  // namespace arcani::test::isolation
