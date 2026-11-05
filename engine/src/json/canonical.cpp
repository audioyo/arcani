// RFC 8785 canonical JSON writer.

#include "json/canonical.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

#include "json/number.hpp"

namespace arcani::json {

namespace {

// UTF-16 code units of a valid UTF-8 string (the parser guarantees validity).
std::u16string to_utf16(std::string_view s) {
  std::u16string out;
  out.reserve(s.size());
  std::size_t i = 0;
  while (i < s.size()) {
    const auto c = static_cast<unsigned char>(s[i]);
    std::uint32_t cp = 0;
    std::size_t len = 1;
    if (c < 0x80u) {
      cp = c;
    } else if (c < 0xE0u) {
      cp = c & 0x1Fu;
      len = 2;
    } else if (c < 0xF0u) {
      cp = c & 0x0Fu;
      len = 3;
    } else {
      cp = c & 0x07u;
      len = 4;
    }
    for (std::size_t k = 1; k < len && i + k < s.size(); ++k) {
      cp = (cp << 6) | (static_cast<unsigned char>(s[i + k]) & 0x3Fu);
    }
    i += len;
    if (cp >= 0x10000u) {
      cp -= 0x10000u;
      out.push_back(static_cast<char16_t>(0xD800u + (cp >> 10)));
      out.push_back(static_cast<char16_t>(0xDC00u + (cp & 0x3FFu)));
    } else {
      out.push_back(static_cast<char16_t>(cp));
    }
  }
  return out;
}

void write_string(std::string& out, std::string_view s) {
  static constexpr char kHex[] = "0123456789abcdef";
  out.push_back('"');
  for (const char ch : s) {
    const auto c = static_cast<unsigned char>(ch);
    switch (c) {
      case '"':
        out += "\\\"";
        break;
      case '\\':
        out += "\\\\";
        break;
      case '\b':
        out += "\\b";
        break;
      case '\t':
        out += "\\t";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\f':
        out += "\\f";
        break;
      case '\r':
        out += "\\r";
        break;
      default:
        if (c < 0x20u) {
          out += "\\u00";
          out.push_back(kHex[c >> 4]);
          out.push_back(kHex[c & 0x0Fu]);
        } else {
          out.push_back(ch);
        }
    }
  }
  out.push_back('"');
}

void write(std::string& out, const Value& v) {
  switch (v.kind()) {
    case Kind::Null:
      out += "null";
      return;
    case Kind::Bool:
      out += v.boolean() ? "true" : "false";
      return;
    case Kind::Number:
      out += format_number(v.number());
      return;
    case Kind::String:
      write_string(out, v.string());
      return;
    case Kind::Array: {
      out.push_back('[');
      bool first = true;
      for (const auto& item : v.array()) {
        if (!first) {
          out.push_back(',');
        }
        first = false;
        write(out, item);
      }
      out.push_back(']');
      return;
    }
    case Kind::Object: {
      const auto& members = v.object();
      std::vector<std::pair<std::u16string, std::size_t>> order;
      order.reserve(members.size());
      for (std::size_t k = 0; k < members.size(); ++k) {
        order.emplace_back(to_utf16(members[k].first), k);
      }
      std::sort(order.begin(), order.end());
      out.push_back('{');
      bool first = true;
      for (const auto& [key16, k] : order) {
        if (!first) {
          out.push_back(',');
        }
        first = false;
        write_string(out, members[k].first);
        out.push_back(':');
        write(out, members[k].second);
      }
      out.push_back('}');
      return;
    }
  }
}

}  // namespace

std::string canonicalize(const Value& v) {
  std::string out;
  write(out, v);
  return out;
}

}  // namespace arcani::json
