// Spacing error detail and pair texts (Story 3.2; docs/signal-spec.md,
// Spacing, Error and Report), read by their grammar:
//
//   <ear> ear: <layer 1> (<i>, <j>, <b>) at <center 1> Hz and <layer 2> (<i>, <j>, <b>) at <center 2> Hz; <where>
//   <where>:  whole session
//          |  listed intervals, a row mirrored below 0 Hz
//          |  first at <t> s, gamma rate <rate> Hz, theta rate <rate> Hz, beat rate <rate> Hz
//
// with a rate of a missing layer written `none` in place of `<rate> Hz`.
// The words are compared exactly and the numbers within the error rows the
// caller passes (read from the tables by the caller, never written here).
// Every number the engine writes is the shortest round-trip text of a
// binary64; the vector texts hold ideal numbers at 25 digits, so only the
// engine side is held to that.
//
// Pure text: no engine symbol, so any test file may include it.

#pragma once

#include <charconv>
#include <cmath>
#include <cstdlib>
#include <regex>
#include <string>
#include <system_error>
#include <vector>

namespace arcani::test::spacing {

inline const char* const kLayers[] = {"theta_reference", "gamma_pac", "binaural"};
inline const char* const kEars[] = {"left", "right"};
inline const char* const kWholeSession = "whole session";
inline const char* const kListedIntervals = "listed intervals, a row mirrored below 0 Hz";

// The shortest round-trip text of a binary64: exactly what std::to_chars writes.
inline std::string shortest(double x) {
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  return r.ec == std::errc() ? std::string(buf, r.ptr) : std::string("?");
}

inline bool is_shortest(const std::string& text) {
  if (text.empty()) {
    return false;
  }
  char* end = nullptr;
  const double x = std::strtod(text.c_str(), &end);
  return end != nullptr && *end == '\0' && shortest(x) == text;
}

inline double number(const std::string& text) { return std::strtod(text.c_str(), nullptr); }

struct NamedRow {
  std::string layer;
  int gamma_mult = 0;
  int theta_mult = 0;
  int beat_mult = 0;
  std::string center_text;
  double center_hz = 0.0;
};

struct Pair {
  NamedRow row_1;
  NamedRow row_2;
};

struct Where {
  std::string kind;  // kWholeSession, kListedIntervals, or "first"
  std::string time_text;
  double time_s = 0.0;
  std::string rate_text[3];  // gamma, theta, beat: "none" or the number text
  double rate_hz[3] = {0.0, 0.0, 0.0};
};

struct Detail {
  std::string ear;
  Pair pair;
  Where where;
};

inline const std::string& num_re() {
  static const std::string s = R"((-?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?))";
  return s;
}
inline const std::string& layer_re() {
  static const std::string s = "(theta_reference|gamma_pac|binaural)";
  return s;
}
inline const std::string& mults_re() {
  static const std::string s = R"(\((-?[0-9]+), (-?[0-9]+), (-?[0-9]+)\))";
  return s;
}

// "<layer> (<i>, <j>, <b>)", as the margin vectors name a row. No problems
// when it parses.
inline std::vector<std::string> parse_row_name(const std::string& text, NamedRow& out) {
  static const std::regex re("^" + layer_re() + " " + mults_re() + "$");
  std::smatch m;
  if (!std::regex_match(text, m, re)) {
    return {"row name does not follow the grammar: '" + text + "'"};
  }
  out.layer = m[1];
  out.gamma_mult = std::stoi(m[2]);
  out.theta_mult = std::stoi(m[3]);
  out.beat_mult = std::stoi(m[4]);
  return {};
}

// "<layer 1> (<i>, <j>, <b>) at <center 1> Hz and <layer 2> (<i>, <j>, <b>) at <center 2> Hz".
// engine: every number must be a shortest round-trip text.
inline std::vector<std::string> parse_pair(const std::string& text, Pair& out, bool engine) {
  static const std::regex re("^" + layer_re() + " " + mults_re() + " at " + num_re() + " Hz and " + layer_re() +
                             " " + mults_re() + " at " + num_re() + " Hz$");
  std::smatch m;
  if (!std::regex_match(text, m, re)) {
    return {"pair does not follow the grammar: '" + text + "'"};
  }
  NamedRow* rows[] = {&out.row_1, &out.row_2};
  for (int k = 0; k < 2; ++k) {
    const int at = 1 + 5 * k;
    rows[k]->layer = m[at];
    rows[k]->gamma_mult = std::stoi(m[at + 1]);
    rows[k]->theta_mult = std::stoi(m[at + 2]);
    rows[k]->beat_mult = std::stoi(m[at + 3]);
    rows[k]->center_text = m[at + 4];
    rows[k]->center_hz = number(rows[k]->center_text);
  }
  std::vector<std::string> problems;
  if (engine) {
    for (const NamedRow* r : rows) {
      if (!is_shortest(r->center_text)) {
        problems.push_back("center '" + r->center_text + "' is not a shortest round-trip text");
      }
    }
  }
  return problems;
}

inline std::vector<std::string> parse_where(const std::string& text, Where& out, bool engine) {
  if (text == kWholeSession || text == kListedIntervals) {
    out.kind = text;
    return {};
  }
  static const std::string rate = "(none|" + num_re().substr(1, num_re().size() - 2) + " Hz)";
  static const std::regex re("^first at " + num_re() + " s, gamma rate " + rate + ", theta rate " + rate +
                             ", beat rate " + rate + "$");
  std::smatch m;
  if (!std::regex_match(text, m, re)) {
    return {"where does not follow the grammar: '" + text + "'"};
  }
  std::vector<std::string> problems;
  out.kind = "first";
  out.time_text = m[1];
  out.time_s = number(out.time_text);
  if (engine && !is_shortest(out.time_text)) {
    problems.push_back("time '" + out.time_text + "' is not a shortest round-trip text");
  }
  for (int k = 0; k < 3; ++k) {
    std::string r = m[2 + k];
    if (r != "none") {
      r = r.substr(0, r.size() - 3);  // drop " Hz"
      out.rate_hz[k] = number(r);
      if (engine && !is_shortest(r)) {
        problems.push_back("rate '" + r + "' is not a shortest round-trip text");
      }
    }
    out.rate_text[k] = r;
  }
  return problems;
}

inline std::vector<std::string> parse_detail(const std::string& text, Detail& out, bool engine) {
  static const std::regex re("^(left|right) ear: ([^;]*); ([^;]*)$");
  std::smatch m;
  if (!std::regex_match(text, m, re)) {
    return {"detail does not follow the grammar: '" + text + "'"};
  }
  out.ear = m[1];
  std::vector<std::string> problems = parse_pair(m[2], out.pair, engine);
  for (const std::string& p : parse_where(m[3], out.where, engine)) {
    problems.push_back(p);
  }
  return problems;
}

// The distance from a to b around a cycle of period p: min(d mod p, p - d mod p).
inline double around_cycle(double a, double b, double p) {
  double d = std::fmod(std::fabs(a - b), p);
  return std::fmin(d, p - d);
}

struct Tolerances {
  double frequency_hz = 0.0;  // row component-frequency-error
  double time_s = 0.0;        // row spacing-time-error
  double rate_hz = 0.0;       // row frequency-accuracy
  double period_s = 0.0;      // row rate-cycle-period
};

inline void compare_rows(const NamedRow& g, const NamedRow& w, const char* which, const Tolerances& tol,
                         std::vector<std::string>& problems) {
  if (g.layer != w.layer || g.gamma_mult != w.gamma_mult || g.theta_mult != w.theta_mult ||
      g.beat_mult != w.beat_mult) {
    problems.push_back(std::string(which) + " is " + g.layer + " (" + std::to_string(g.gamma_mult) + ", " +
                       std::to_string(g.theta_mult) + ", " + std::to_string(g.beat_mult) + "), want " + w.layer +
                       " (" + std::to_string(w.gamma_mult) + ", " + std::to_string(w.theta_mult) + ", " +
                       std::to_string(w.beat_mult) + ")");
  }
  if (!(std::fabs(g.center_hz - w.center_hz) < tol.frequency_hz)) {
    problems.push_back(std::string(which) + " center " + g.center_text + " Hz, want " + w.center_text + " Hz");
  }
}

inline std::vector<std::string> compare_pairs(const Pair& g, const Pair& w, const Tolerances& tol) {
  std::vector<std::string> problems;
  compare_rows(g.row_1, w.row_1, "row 1", tol, problems);
  compare_rows(g.row_2, w.row_2, "row 2", tol, problems);
  return problems;
}

inline std::vector<std::string> compare_where(const Where& g, const Where& w, const Tolerances& tol) {
  std::vector<std::string> problems;
  if (g.kind != w.kind) {
    problems.push_back("where is '" + g.kind + "', want '" + w.kind + "'");
    return problems;
  }
  if (g.kind != "first") {
    return problems;
  }
  if (!(around_cycle(g.time_s, w.time_s, tol.period_s) < tol.time_s)) {
    problems.push_back("first time " + g.time_text + " s, want " + w.time_text + " s");
  }
  const char* const names[] = {"gamma", "theta", "beat"};
  for (int k = 0; k < 3; ++k) {
    const bool gn = g.rate_text[k] == "none";
    const bool wn = w.rate_text[k] == "none";
    if (gn != wn) {
      problems.push_back(std::string(names[k]) + " rate " + g.rate_text[k] + ", want " + w.rate_text[k]);
    } else if (!gn && !(std::fabs(g.rate_hz[k] - w.rate_hz[k]) < tol.rate_hz)) {
      problems.push_back(std::string(names[k]) + " rate " + g.rate_text[k] + " Hz, want " + w.rate_text[k] + " Hz");
    }
  }
  return problems;
}

// Problems of the engine detail `got` against the vector detail `want`
// (empty when it holds).
inline std::vector<std::string> compare_detail(const std::string& got, const std::string& want,
                                               const Tolerances& tol) {
  Detail g;
  Detail w;
  std::vector<std::string> problems = parse_detail(got, g, true);
  const std::vector<std::string> want_problems = parse_detail(want, w, false);
  if (!want_problems.empty()) {
    problems.push_back("the vector detail does not parse: " + want_problems.front());
    return problems;
  }
  if (!problems.empty() && g.ear.empty()) {
    return problems;
  }
  if (g.ear != w.ear) {
    problems.push_back("ear " + g.ear + ", want " + w.ear);
  }
  for (const std::string& p : compare_pairs(g.pair, w.pair, tol)) {
    problems.push_back(p);
  }
  for (const std::string& p : compare_where(g.where, w.where, tol)) {
    problems.push_back(p);
  }
  return problems;
}

inline std::string joined(const std::vector<std::string>& problems) {
  std::string out;
  for (const std::string& p : problems) {
    out += p + "\n";
  }
  return out;
}

}  // namespace arcani::test::spacing
