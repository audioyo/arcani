// Strict JSON parser (see value.hpp for the rules).

#include "json/value.hpp"

#include <cstdint>
#include <set>

#include "json/number.hpp"

namespace arcani::json {

Value Value::boolean_value(bool b) {
  Value v;
  v.kind_ = Kind::Bool;
  v.bool_ = b;
  return v;
}

Value Value::number_value(double x) {
  Value v;
  v.kind_ = Kind::Number;
  v.number_ = x;
  v.integral_ = is_integral(x);
  return v;
}

Value Value::string_value(std::string s) {
  Value v;
  v.kind_ = Kind::String;
  v.string_ = std::move(s);
  return v;
}

Value Value::array_value(std::vector<Value> items) {
  Value v;
  v.kind_ = Kind::Array;
  v.array_ = std::move(items);
  return v;
}

Value Value::object_value(std::vector<Member> members) {
  Value v;
  v.kind_ = Kind::Object;
  v.object_ = std::move(members);
  return v;
}

const Value* Value::find(std::string_view key) const noexcept {
  for (const auto& [name, value] : object_) {
    if (name == key) {
      return &value;
    }
  }
  return nullptr;
}

namespace {

// Offset of the first byte that starts an invalid UTF-8 sequence, or npos.
// Rejects overlong forms, encoded surrogates, and code points above U+10FFFF.
std::size_t first_invalid_utf8(std::string_view s) noexcept {
  const auto byte = [&](std::size_t i) { return static_cast<unsigned char>(s[i]); };
  const auto cont = [&](std::size_t i) { return i < s.size() && (byte(i) & 0xC0u) == 0x80u; };
  std::size_t i = 0;
  while (i < s.size()) {
    const unsigned char c = byte(i);
    if (c < 0x80u) {
      ++i;
    } else if (c >= 0xC2u && c <= 0xDFu) {
      if (!cont(i + 1)) {
        return i;
      }
      i += 2;
    } else if (c >= 0xE0u && c <= 0xEFu) {
      if (i + 1 >= s.size()) {
        return i;
      }
      const unsigned char c1 = byte(i + 1);
      const bool ok1 = c == 0xE0u   ? (c1 >= 0xA0u && c1 <= 0xBFu)
                       : c == 0xEDu ? (c1 >= 0x80u && c1 <= 0x9Fu)
                                    : (c1 & 0xC0u) == 0x80u;
      if (!ok1 || !cont(i + 2)) {
        return i;
      }
      i += 3;
    } else if (c >= 0xF0u && c <= 0xF4u) {
      if (i + 1 >= s.size()) {
        return i;
      }
      const unsigned char c1 = byte(i + 1);
      const bool ok1 = c == 0xF0u   ? (c1 >= 0x90u && c1 <= 0xBFu)
                       : c == 0xF4u ? (c1 >= 0x80u && c1 <= 0x8Fu)
                                    : (c1 & 0xC0u) == 0x80u;
      if (!ok1 || !cont(i + 2) || !cont(i + 3)) {
        return i;
      }
      i += 4;
    } else {
      return i;
    }
  }
  return std::string_view::npos;
}

void append_utf8(std::string& out, std::uint32_t cp) {
  if (cp < 0x80u) {
    out.push_back(static_cast<char>(cp));
  } else if (cp < 0x800u) {
    out.push_back(static_cast<char>(0xC0u | (cp >> 6)));
    out.push_back(static_cast<char>(0x80u | (cp & 0x3Fu)));
  } else if (cp < 0x10000u) {
    out.push_back(static_cast<char>(0xE0u | (cp >> 12)));
    out.push_back(static_cast<char>(0x80u | ((cp >> 6) & 0x3Fu)));
    out.push_back(static_cast<char>(0x80u | (cp & 0x3Fu)));
  } else {
    out.push_back(static_cast<char>(0xF0u | (cp >> 18)));
    out.push_back(static_cast<char>(0x80u | ((cp >> 12) & 0x3Fu)));
    out.push_back(static_cast<char>(0x80u | ((cp >> 6) & 0x3Fu)));
    out.push_back(static_cast<char>(0x80u | (cp & 0x3Fu)));
  }
}

class Parser {
 public:
  explicit Parser(std::string_view s) : s_(s) {}

  ParseResult run() {
    ParseResult result;
    if (s_.substr(0, 3) == "\xEF\xBB\xBF") {
      fail("json.bom", 0);
    } else if (const std::size_t bad = first_invalid_utf8(s_); bad != std::string_view::npos) {
      fail("json.invalid_utf8", bad);
    } else {
      Value v;
      if (skip_ws() && parse_value(v, 0) && skip_ws()) {
        if (i_ != s_.size()) {
          fail("json.trailing_data", i_);
        } else {
          result.value = std::move(v);
          return result;
        }
      }
    }
    result.error = std::move(error_);
    return result;
  }

 private:
  bool fail(const char* rule, std::size_t offset, std::string value = {}, std::string limit = {}) {
    error_.offset = offset;
    error_.rule = rule;
    error_.value = std::move(value);
    error_.limit = std::move(limit);
    return false;
  }

  bool at_end() const noexcept { return i_ >= s_.size(); }
  char peek() const noexcept { return at_end() ? '\0' : s_[i_]; }

  bool skip_ws() {
    while (!at_end()) {
      const char c = s_[i_];
      if (c == ' ' || c == '\t' || c == '\n' || c == '\r') {
        ++i_;
      } else if (c == '/') {
        const char next = i_ + 1 < s_.size() ? s_[i_ + 1] : '\0';
        return fail(next == '/' || next == '*' ? "json.comment" : "json.unexpected_char", i_);
      } else {
        break;
      }
    }
    return true;
  }

  bool unexpected() {
    return at_end() ? fail("json.unexpected_end", i_) : fail("json.unexpected_char", i_);
  }

  bool parse_value(Value& out, std::size_t depth) {
    if (at_end()) {
      return fail("json.unexpected_end", i_);
    }
    const char c = s_[i_];
    switch (c) {
      case '{':
        return parse_object(out, depth + 1);
      case '[':
        return parse_array(out, depth + 1);
      case '"': {
        std::string str;
        if (!parse_string(str)) {
          return false;
        }
        out = Value::string_value(std::move(str));
        return true;
      }
      case 't':
        return literal("true", Value::boolean_value(true), out);
      case 'f':
        return literal("false", Value::boolean_value(false), out);
      case 'n':
        return literal("null", Value::null(), out);
      case 'N':
      case 'I':
        if (s_.substr(i_, 3) == "NaN" || s_.substr(i_, 8) == "Infinity") {
          return fail("json.non_finite", i_);
        }
        return unexpected();
      default:
        if (c == '-' || (c >= '0' && c <= '9')) {
          return parse_number(out);
        }
        return unexpected();
    }
  }

  bool literal(std::string_view word, Value v, Value& out) {
    if (s_.substr(i_, word.size()) != word) {
      return fail("json.invalid_literal", i_);
    }
    i_ += word.size();
    out = std::move(v);
    return true;
  }

  bool enter(std::size_t depth) {
    if (depth > kMaxDepth) {
      return fail("json.depth", i_, {}, std::to_string(kMaxDepth));
    }
    ++i_;
    return skip_ws();
  }

  bool parse_array(Value& out, std::size_t depth) {
    if (!enter(depth)) {
      return false;
    }
    std::vector<Value> items;
    if (peek() == ']') {
      ++i_;
      out = Value::array_value(std::move(items));
      return true;
    }
    for (;;) {
      Value item;
      if (!parse_value(item, depth) || !skip_ws()) {
        return false;
      }
      items.push_back(std::move(item));
      const char c = peek();
      if (c == ',' && !at_end()) {
        ++i_;
        if (!skip_ws()) {
          return false;
        }
        if (peek() == ']') {
          return fail("json.trailing_comma", i_);
        }
      } else if (c == ']') {
        ++i_;
        out = Value::array_value(std::move(items));
        return true;
      } else {
        return at_end() ? fail("json.unexpected_end", i_) : fail("json.expected_comma", i_);
      }
    }
  }

  bool parse_object(Value& out, std::size_t depth) {
    if (!enter(depth)) {
      return false;
    }
    std::vector<Value::Member> members;
    std::set<std::string> seen;  // keys of the members read so far
    if (peek() == '}') {
      ++i_;
      out = Value::object_value(std::move(members));
      return true;
    }
    for (;;) {
      if (at_end()) {
        return fail("json.unexpected_end", i_);
      }
      if (peek() != '"') {
        return fail("json.expected_key", i_);
      }
      const std::size_t key_at = i_;
      std::string key;
      if (!parse_string(key)) {
        return false;
      }
      // Duplicate keys, compared after unescaping, as each key is read: the
      // first duplicate in document order is reported, at its opening quote.
      if (!seen.insert(key).second) {
        return fail("json.duplicate_key", key_at, key);
      }
      if (!skip_ws()) {
        return false;
      }
      if (peek() != ':' || at_end()) {
        return at_end() ? fail("json.unexpected_end", i_) : fail("json.expected_colon", i_);
      }
      ++i_;
      if (!skip_ws()) {
        return false;
      }
      Value value;
      if (!parse_value(value, depth) || !skip_ws()) {
        return false;
      }
      members.emplace_back(std::move(key), std::move(value));
      const char c = peek();
      if (c == ',' && !at_end()) {
        ++i_;
        if (!skip_ws()) {
          return false;
        }
        if (peek() == '}') {
          return fail("json.trailing_comma", i_);
        }
      } else if (c == '}') {
        ++i_;
        break;
      } else {
        return at_end() ? fail("json.unexpected_end", i_) : fail("json.expected_comma", i_);
      }
    }
    out = Value::object_value(std::move(members));
    return true;
  }

  // Four hex digits at position at, or -1.
  long hex4(std::size_t at) const noexcept {
    if (at + 4 > s_.size()) {
      return -1;
    }
    long v = 0;
    for (std::size_t k = 0; k < 4; ++k) {
      const char c = s_[at + k];
      int d = 0;
      if (c >= '0' && c <= '9') {
        d = c - '0';
      } else if (c >= 'a' && c <= 'f') {
        d = c - 'a' + 10;
      } else if (c >= 'A' && c <= 'F') {
        d = c - 'A' + 10;
      } else {
        return -1;
      }
      v = v * 16 + d;
    }
    return v;
  }

  bool parse_string(std::string& out) {
    ++i_;  // opening quote
    for (;;) {
      if (at_end()) {
        return fail("json.unexpected_end", i_);
      }
      const auto c = static_cast<unsigned char>(s_[i_]);
      if (c == '"') {
        ++i_;
        return true;
      }
      if (c < 0x20u) {
        return fail("json.control_character", i_);
      }
      if (c != '\\') {
        out.push_back(static_cast<char>(c));
        ++i_;
        continue;
      }
      const std::size_t esc_at = i_;
      const char e = i_ + 1 < s_.size() ? s_[i_ + 1] : '\0';
      i_ += 2;
      switch (e) {
        case '"':
          out.push_back('"');
          break;
        case '\\':
          out.push_back('\\');
          break;
        case '/':
          out.push_back('/');
          break;
        case 'b':
          out.push_back('\b');
          break;
        case 'f':
          out.push_back('\f');
          break;
        case 'n':
          out.push_back('\n');
          break;
        case 'r':
          out.push_back('\r');
          break;
        case 't':
          out.push_back('\t');
          break;
        case 'u': {
          const long cp = hex4(i_);
          if (cp < 0) {
            return fail("json.invalid_escape", esc_at);
          }
          i_ += 4;
          if (cp >= 0xDC00 && cp <= 0xDFFF) {
            return fail("json.lone_surrogate", esc_at);
          }
          if (cp >= 0xD800 && cp <= 0xDBFF) {
            if (s_.substr(i_, 2) != "\\u") {
              return fail("json.lone_surrogate", esc_at);
            }
            const long low = hex4(i_ + 2);
            if (low < 0) {
              return fail("json.invalid_escape", i_);
            }
            if (low < 0xDC00 || low > 0xDFFF) {
              return fail("json.lone_surrogate", esc_at);
            }
            i_ += 6;
            append_utf8(out, 0x10000u + ((static_cast<std::uint32_t>(cp) - 0xD800u) << 10) +
                                 (static_cast<std::uint32_t>(low) - 0xDC00u));
          } else {
            append_utf8(out, static_cast<std::uint32_t>(cp));
          }
          break;
        }
        default:
          return e == '\0' && esc_at + 1 >= s_.size() ? fail("json.unexpected_end", esc_at)
                                                       : fail("json.invalid_escape", esc_at);
      }
    }
  }

  bool parse_number(Value& out) {
    const std::size_t start = i_;
    const auto digit = [&] { return !at_end() && s_[i_] >= '0' && s_[i_] <= '9'; };
    if (peek() == '-') {
      ++i_;
      if (s_.substr(i_, 8) == "Infinity") {
        return fail("json.non_finite", start);
      }
    }
    if (peek() == '0' && !at_end()) {
      ++i_;
      if (digit()) {
        return fail("json.leading_zero", start);
      }
    } else if (digit()) {
      while (digit()) {
        ++i_;
      }
    } else {
      return fail("json.invalid_number", start);
    }
    if (peek() == '.' && !at_end()) {
      ++i_;
      if (!digit()) {
        return fail("json.invalid_number", start);
      }
      while (digit()) {
        ++i_;
      }
    }
    if (!at_end() && (peek() == 'e' || peek() == 'E')) {
      ++i_;
      if (!at_end() && (peek() == '+' || peek() == '-')) {
        ++i_;
      }
      if (!digit()) {
        return fail("json.invalid_number", start);
      }
      while (digit()) {
        ++i_;
      }
    }
    const std::string_view text = s_.substr(start, i_ - start);
    double x = 0.0;
    switch (parse_number_status(text, x)) {
      case NumberStatus::Ok:
        out = Value::number_value(x);
        return true;
      case NumberStatus::Overflow:
        return fail("json.number_overflow", start, std::string(text));
      case NumberStatus::BadGrammar:
        break;
    }
    return fail("json.invalid_number", start, std::string(text));
  }

  std::string_view s_;
  std::size_t i_ = 0;
  Error error_;
};

}  // namespace

ParseResult parse(std::string_view utf8) {
  return Parser(utf8).run();
}

}  // namespace arcani::json
