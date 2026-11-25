// The stored loudness gain's tooling (Story 4.2). See recipe_write.hpp.

#include "recipe_write.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <stdexcept>
#include <system_error>

namespace arcani::cli {

namespace {

constexpr std::string_view kGainMember = "loudness_gain_db";
constexpr std::string_view kHashMember = "loudness_hash";
constexpr std::string_view kTargetMember = "loudness_target_lufs";

[[noreturn]] void bad(const std::string& what) { throw std::invalid_argument("recipe member scanner: " + what); }

bool is_ws(char c) noexcept { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

std::size_t skip_ws(std::string_view s, std::size_t i) noexcept {
  while (i < s.size() && is_ws(s[i])) {
    ++i;
  }
  return i;
}

// s[i] is the opening quote: the index just past the closing quote.
std::size_t string_end(std::string_view s, std::size_t i) {
  if (i >= s.size() || s[i] != '"') {
    bad("expected a string");
  }
  ++i;
  while (i < s.size() && s[i] != '"') {
    i += s[i] == '\\' ? 2 : 1;
  }
  if (i >= s.size()) {
    bad("unterminated string");
  }
  return i + 1;
}

std::size_t value_end(std::string_view s, std::size_t i) {
  if (i >= s.size()) {
    bad("missing value");
  }
  if (s[i] == '"') {
    return string_end(s, i);
  }
  if (s[i] == '{' || s[i] == '[') {
    int depth = 0;
    while (i < s.size()) {
      const char c = s[i];
      if (c == '"') {
        i = string_end(s, i);
        continue;
      }
      if (c == '{' || c == '[') {
        ++depth;
      } else if (c == '}' || c == ']') {
        if (--depth == 0) {
          return i + 1;
        }
      }
      ++i;
    }
    bad("unterminated value");
  }
  const std::size_t begin = i;
  while (i < s.size() && s[i] != ',' && s[i] != '}' && s[i] != ']' && !is_ws(s[i])) {
    ++i;
  }
  if (i == begin) {
    bad("missing value");
  }
  return i;
}

int hex_digit(char c) noexcept {
  if (c >= '0' && c <= '9') {
    return c - '0';
  }
  if (c >= 'a' && c <= 'f') {
    return c - 'a' + 10;
  }
  if (c >= 'A' && c <= 'F') {
    return c - 'A' + 10;
  }
  return -1;
}

unsigned hex4(std::string_view s, std::size_t i) {
  if (i + 4 > s.size()) {
    bad("short \\u escape");
  }
  unsigned v = 0;
  for (std::size_t j = i; j < i + 4; ++j) {
    const int d = hex_digit(s[j]);
    if (d < 0) {
      bad("bad \\u escape");
    }
    v = v * 16u + static_cast<unsigned>(d);
  }
  return v;
}

void append_utf8(std::string& out, unsigned cp) {
  if (cp < 0x80) {
    out += static_cast<char>(cp);
  } else if (cp < 0x800) {
    out += static_cast<char>(0xC0 | (cp >> 6));
    out += static_cast<char>(0x80 | (cp & 0x3F));
  } else if (cp < 0x10000) {
    out += static_cast<char>(0xE0 | (cp >> 12));
    out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
    out += static_cast<char>(0x80 | (cp & 0x3F));
  } else {
    out += static_cast<char>(0xF0 | (cp >> 18));
    out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
    out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
    out += static_cast<char>(0x80 | (cp & 0x3F));
  }
}

// The unescaped text of the string token [begin, end) (quotes included).
std::string unescape(std::string_view s, std::size_t begin, std::size_t end) {
  std::string out;
  for (std::size_t i = begin + 1; i + 1 < end; ++i) {
    if (s[i] != '\\') {
      out += s[i];
      continue;
    }
    const char e = s[++i];
    switch (e) {
      case '"':
      case '\\':
      case '/':
        out += e;
        break;
      case 'b':
        out += '\b';
        break;
      case 'f':
        out += '\f';
        break;
      case 'n':
        out += '\n';
        break;
      case 'r':
        out += '\r';
        break;
      case 't':
        out += '\t';
        break;
      case 'u': {
        unsigned cp = hex4(s, i + 1);
        i += 4;
        if (cp >= 0xD800 && cp < 0xDC00 && i + 6 < end && s[i + 1] == '\\' && s[i + 2] == 'u') {
          const unsigned lo = hex4(s, i + 3);
          if (lo >= 0xDC00 && lo < 0xE000) {
            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
            i += 6;
          }
        }
        append_utf8(out, cp);
        break;
      }
      default:
        bad("bad escape");
    }
  }
  return out;
}

std::string shortest(double x) {
  if (std::isinf(x)) {
    return x > 0 ? "inf" : "-inf";
  }
  if (std::isnan(x)) {
    return "nan";
  }
  char buf[64];
  const auto r = std::to_chars(buf, buf + sizeof buf, x);
  return std::string(buf, r.ptr);
}

// The integer nearest x, a tie away from zero, in exact steps (|x| < 2^62).
std::int64_t round_half_away(double x) {
  const bool negative = x < 0.0;
  const double a = negative ? -x : x;
  auto n = static_cast<std::int64_t>(a);  // truncation, exact
  if (a - static_cast<double>(n) >= 0.5) {  // the remainder is exact
    ++n;
  }
  return negative ? -n : n;
}

}  // namespace

std::vector<Member> top_level_members(std::string_view s) {
  std::size_t i = skip_ws(s, 0);
  if (i >= s.size() || s[i] != '{') {
    bad("not a JSON object");
  }
  ++i;
  std::vector<Member> out;
  std::size_t lead = i;  // just after '{'
  i = skip_ws(s, i);
  if (i < s.size() && s[i] == '}') {
    ++i;
  } else {
    while (true) {
      Member m;
      m.lead_begin = lead;
      m.key_begin = skip_ws(s, lead);
      m.key_end = string_end(s, m.key_begin);
      m.name = unescape(s, m.key_begin, m.key_end);
      std::size_t j = skip_ws(s, m.key_end);
      if (j >= s.size() || s[j] != ':') {
        bad("expected ':'");
      }
      m.value_begin = skip_ws(s, j + 1);
      m.value_end = value_end(s, m.value_begin);
      out.push_back(m);
      j = skip_ws(s, m.value_end);
      if (j < s.size() && s[j] == ',') {
        lead = j + 1;
        continue;
      }
      if (j < s.size() && s[j] == '}') {
        i = j + 1;
        break;
      }
      bad("expected ',' or '}'");
    }
  }
  if (skip_ws(s, i) != s.size()) {
    bad("bytes after the root object");
  }
  return out;
}

std::optional<double> top_level_number(std::string_view s, std::string_view name) {
  for (const Member& m : top_level_members(s)) {
    if (m.name != name) {
      continue;
    }
    // strtod in the default "C" locale, correctly rounded, as the tables
    // reader does (tests/assertions/tables.cpp); Apple libc++ has no
    // floating-point std::from_chars.
    const std::string token(s.substr(m.value_begin, m.value_end - m.value_begin));
    if (token.empty() || token[0] == '"' || token[0] == '{' || token[0] == '[') {
      return std::nullopt;
    }
    char* end = nullptr;
    const double v = std::strtod(token.c_str(), &end);
    if (end != token.c_str() + token.size()) {
      return std::nullopt;
    }
    return v;
  }
  return std::nullopt;
}

std::string rewrite_loudness_members(std::string_view s, std::string_view gain, std::string_view hash) {
  const std::vector<Member> members = top_level_members(s);
  const Member* target = nullptr;
  const Member* gain_member = nullptr;
  const Member* hash_member = nullptr;
  for (const Member& m : members) {
    if (m.name == kTargetMember) {
      target = &m;
    } else if (m.name == kGainMember) {
      gain_member = &m;
    } else if (m.name == kHashMember) {
      hash_member = &m;
    }
  }
  if (target == nullptr) {
    bad("no loudness_target_lufs member");
  }
  const std::string hash_value = "\"" + std::string(hash) + "\"";
  struct Edit {
    std::size_t begin;
    std::size_t end;
    std::string text;
  };
  std::vector<Edit> edits;
  if (gain_member != nullptr) {
    edits.push_back({gain_member->value_begin, gain_member->value_end, std::string(gain)});
  }
  if (hash_member != nullptr) {
    edits.push_back({hash_member->value_begin, hash_member->value_end, hash_value});
  }
  if (gain_member == nullptr || hash_member == nullptr) {
    const std::string_view lead = s.substr(target->lead_begin, target->key_begin - target->lead_begin);
    const std::string_view sep = s.substr(target->key_end, target->value_begin - target->key_end);
    std::string run;
    if (gain_member == nullptr) {
      run += ",";
      run += lead;
      run += "\"loudness_gain_db\"";
      run += sep;
      run += gain;
    }
    if (hash_member == nullptr) {
      run += ",";
      run += lead;
      run += "\"loudness_hash\"";
      run += sep;
      run += hash_value;
    }
    edits.push_back({target->value_end, target->value_end, run});
  }
  // Apply from the last offset to the first, so earlier offsets stay valid.
  std::string out(s);
  std::sort(edits.begin(), edits.end(), [](const Edit& a, const Edit& b) { return a.begin > b.begin; });
  for (const Edit& e : edits) {
    out.replace(e.begin, e.end - e.begin, e.text);
  }
  return out;
}

std::string gain_text(std::int64_t k) {
  const std::uint64_t m = k < 0 ? static_cast<std::uint64_t>(-(k + 1)) + 1u : static_cast<std::uint64_t>(k);
  std::string s = k < 0 ? "-" : "";
  s += std::to_string(m / 100u);
  s += '.';
  const std::uint64_t r = m % 100u;
  s += static_cast<char>('0' + r / 10u);
  s += static_cast<char>('0' + r % 10u);
  return s;
}

GainStep gain_step(double window_lufs, double target_lufs, const arcani::test::tables::Row& row) {
  namespace tables = arcani::test::tables;
  if (row.kind != "ranges" || row.unit != "dB" || !std::isfinite(row.min) || !std::isfinite(row.max)) {
    throw tables::TableError("row " + row.id + ": the loudness gain row must be a ranges row in dB with finite bounds");
  }
  const std::string min_limit = ">= " + row.min_text + " " + row.unit + " (row " + row.id + ")";
  const bool max_exclusive = row.max_bound == "exclusive";
  const std::string max_limit =
      std::string(max_exclusive ? "< " : "<= ") + row.max_text + " " + row.unit + " (row " + row.id + ")";
  GainStep g;
  const double d = target_lufs - window_lufs;  // one rounding
  const double x = 100.0 * d;                  // one rounding
  if (!std::isfinite(x) || std::fabs(x) >= 0x1p62) {
    g.value = shortest(x);
    const bool low = x < 0.0;
    g.rule = low ? "range.min" : "range.max";
    g.limit = low ? min_limit : max_limit;
    return g;
  }
  g.k = round_half_away(x);
  const double v = static_cast<double>(g.k) / 100.0;  // one correctly rounded division
  if (!(v >= row.min)) {
    g.value = shortest(v);
    g.rule = "range.min";
    g.limit = min_limit;
    return g;
  }
  if (max_exclusive ? !(v < row.max) : !(v <= row.max)) {
    g.value = shortest(v);
    g.rule = "range.max";
    g.limit = max_limit;
    return g;
  }
  g.stored = true;
  g.gain_text = gain_text(g.k);
  return g;
}

}  // namespace arcani::cli
