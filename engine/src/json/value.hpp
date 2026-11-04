// Strict JSON parser and value tree (Story 1.1). RFC 8259 plus I-JSON
// (RFC 7493): no byte order mark, valid UTF-8 only, no comments, no trailing
// commas, no leading zeros, no NaN or Infinity, no number that overflows
// binary64, no duplicate keys (compared after unescaping), no lone surrogate
// escapes, and nesting no deeper than kMaxDepth. tools/recipe_hash.py applies
// the same rules in Python. No exceptions are thrown for bad input and there
// is no file I/O: callers pass the bytes.

#ifndef ARCANI_JSON_VALUE_HPP
#define ARCANI_JSON_VALUE_HPP

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace arcani::json {

enum class Kind { Null, Bool, Number, String, Array, Object };

class Value {
 public:
  using Member = std::pair<std::string, Value>;

  Value() noexcept = default;

  static Value null() { return Value(); }
  static Value boolean_value(bool b);
  // integral() is derived from the bits: true when x has no fractional part.
  static Value number_value(double x);
  static Value string_value(std::string s);
  static Value array_value(std::vector<Value> items);
  static Value object_value(std::vector<Member> members);

  Kind kind() const noexcept { return kind_; }
  bool boolean() const noexcept { return bool_; }
  double number() const noexcept { return number_; }
  // The number has no fractional part (7, 7.0, 1e0). False for non-numbers.
  bool integral() const noexcept { return integral_; }
  // UTF-8 with escapes decoded. Empty for non-strings.
  const std::string& string() const noexcept { return string_; }
  const std::vector<Value>& array() const noexcept { return array_; }
  // Members in document order.
  const std::vector<Member>& object() const noexcept { return object_; }
  // The member named key, or nullptr if absent or not an object.
  const Value* find(std::string_view key) const noexcept;

 private:
  Kind kind_ = Kind::Null;
  bool bool_ = false;
  bool integral_ = false;
  double number_ = 0.0;
  std::string string_;
  std::vector<Value> array_;
  std::vector<Member> object_;
};

struct Error {
  std::size_t offset = 0;  // byte offset of the fault
  std::string rule;        // json.* rule id, for example json.duplicate_key
  std::string value;       // offending text, may be empty
  std::string limit;       // for json.depth: the depth limit
};

struct ParseResult {
  std::optional<Value> value;  // empty on error
  Error error;
};

// Maximum nesting depth: "[]" is depth 1. Deeper input is rejected before the
// parser recurses further, so recursion depth stays bounded.
inline constexpr std::size_t kMaxDepth = 64;

ParseResult parse(std::string_view utf8);

}  // namespace arcani::json

#endif  // ARCANI_JSON_VALUE_HPP
