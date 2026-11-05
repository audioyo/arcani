// Recipe parse stage and recipe hash.

#include "recipe/recipe.hpp"

#include <utility>
#include <vector>

#include "crypto/sha256.hpp"
#include "json/canonical.hpp"
#include "json/value.hpp"
#include "recipe/field_table.hpp"

namespace arcani::recipe {

namespace {

using json::Kind;
using json::Value;

// String patterns, written as in recipes/recipe.schema.json (the limit of a
// pattern error). The checks below implement exactly these patterns.
constexpr std::string_view kSchemaVersionPattern = "^1\\.(0|[1-9][0-9]*)$(?!\\n)";
constexpr std::string_view kEngineVersionPattern =
    "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$(?!\\n)";
constexpr std::string_view kDatePattern =
    "^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$(?!\\n)";
constexpr std::string_view kLoudnessHashPattern = "^[0-9a-f]{64}$(?!\\n)";

// Seed bounds: 0 to 2^53 - 1, the largest integer a JSON number holds exactly.
constexpr double kSeedMax = 9007199254740991.0;
constexpr std::string_view kSeedMaxText = "9007199254740991";

bool is_digit(char c) noexcept { return c >= '0' && c <= '9'; }

bool all_digits(std::string_view s) noexcept {
  if (s.empty()) {
    return false;
  }
  for (const char c : s) {
    if (!is_digit(c)) {
      return false;
    }
  }
  return true;
}

// 0|[1-9][0-9]*
bool plain_number(std::string_view s) noexcept {
  return all_digits(s) && (s.size() == 1 || s[0] != '0');
}

std::vector<std::string_view> split_dots(std::string_view s) {
  std::vector<std::string_view> parts;
  std::size_t start = 0;
  for (;;) {
    const std::size_t dot = s.find('.', start);
    parts.push_back(s.substr(start, dot == std::string_view::npos ? dot : dot - start));
    if (dot == std::string_view::npos) {
      return parts;
    }
    start = dot + 1;
  }
}

bool date_ok(std::string_view s) noexcept {
  if (s.size() != 10 || s[4] != '-' || s[7] != '-') {
    return false;
  }
  for (const std::size_t i : {0u, 1u, 2u, 3u, 5u, 6u, 8u, 9u}) {
    if (!is_digit(s[i])) {
      return false;
    }
  }
  const int month = (s[5] - '0') * 10 + (s[6] - '0');
  const int day = (s[8] - '0') * 10 + (s[9] - '0');
  return month >= 1 && month <= 12 && day >= 1 && day <= 31;
}

bool hash_ok(std::string_view s) noexcept {
  if (s.size() != 64) {
    return false;
  }
  for (const char c : s) {
    if (!is_digit(c) && !(c >= 'a' && c <= 'f')) {
      return false;
    }
  }
  return true;
}

std::string pointer_part(std::string_view name) {
  std::string out;
  for (const char c : name) {
    if (c == '~') {
      out += "~0";
    } else if (c == '/') {
      out += "~1";
    } else {
      out.push_back(c);
    }
  }
  return out;
}

const Field* field_at(std::string_view path) noexcept {
  for (const auto& f : fields()) {
    if (f.path == path) {
      return &f;
    }
  }
  return nullptr;
}

// True when path is a direct child of prefix ("" is the root).
bool child_of(std::string_view path, std::string_view prefix) noexcept {
  return path.size() > prefix.size() + 1 && path.substr(0, prefix.size()) == prefix &&
         path[prefix.size()] == '/' && path.find('/', prefix.size() + 1) == std::string_view::npos;
}

std::string_view type_name(FieldType t) noexcept {
  switch (t) {
    case FieldType::String:
      return "string";
    case FieldType::Number:
      return "number";
    case FieldType::Integer:
      return "integer";
    case FieldType::Object:
      return "object";
  }
  return "";
}

bool type_ok(FieldType t, const Value& v) noexcept {
  switch (t) {
    case FieldType::String:
      return v.kind() == Kind::String;
    case FieldType::Number:
      return v.kind() == Kind::Number;
    case FieldType::Integer:
      return v.kind() == Kind::Number && v.integral();
    case FieldType::Object:
      return v.kind() == Kind::Object;
  }
  return false;
}

std::string as_text(const Value& v) {
  return v.kind() == Kind::String ? v.string() : json::canonicalize(v);
}

Error make_error(std::string parameter, std::string value, std::string_view rule,
                 std::string_view limit) {
  return Error{std::move(parameter), std::move(value), std::string(rule), std::string(limit)};
}

// Pattern and bound checks beyond the JSON type, for the fields that have them.
std::optional<Error> check_value(const Field& f, const Value& v) {
  const std::string pointer(f.path);
  if (f.path == "/schema_version") {
    const auto parts = split_dots(v.string());
    if (parts.size() == 2 && parts[0] == "1" && plain_number(parts[1])) {
      return std::nullopt;
    }
    if (parts.size() == 2 && plain_number(parts[0]) && plain_number(parts[1])) {
      return make_error(pointer, v.string(), "schema_version.major", kSupportedSchemaMajors);
    }
    return make_error(pointer, v.string(), "pattern", kSchemaVersionPattern);
  }
  if (f.path == "/engine_version") {
    const auto parts = split_dots(v.string());
    if (parts.size() == 3 && plain_number(parts[0]) && plain_number(parts[1]) &&
        plain_number(parts[2])) {
      return std::nullopt;
    }
    return make_error(pointer, v.string(), "pattern", kEngineVersionPattern);
  }
  if (f.path == "/date" && !date_ok(v.string())) {
    return make_error(pointer, v.string(), "pattern", kDatePattern);
  }
  if (f.path == "/loudness_hash" && !hash_ok(v.string())) {
    return make_error(pointer, v.string(), "pattern", kLoudnessHashPattern);
  }
  if (f.path == "/seed") {
    if (v.number() < 0.0) {
      return make_error(pointer, as_text(v), "minimum", "0");
    }
    if (v.number() > kSeedMax) {
      return make_error(pointer, as_text(v), "maximum", kSeedMaxText);
    }
  }
  return std::nullopt;
}

std::optional<Error> check_object(const Value& obj, const std::string& prefix) {
  std::vector<const Field*> children;
  for (const auto& f : fields()) {
    if (child_of(f.path, prefix)) {
      children.push_back(&f);
    }
  }
  for (const auto& [key, value] : obj.object()) {
    const std::string pointer = prefix + "/" + pointer_part(key);
    bool known = false;
    for (const Field* f : children) {
      known = known || f->path == pointer;
    }
    if (!known) {
      std::string allowed;
      for (const Field* f : children) {
        allowed += allowed.empty() ? "" : ", ";
        allowed += f->path.substr(prefix.size() + 1);
      }
      return make_error(pointer, key, "unknown_property", allowed);
    }
  }
  for (const Field* f : children) {
    const std::string_view name = f->path.substr(prefix.size() + 1);
    const Value* v = obj.find(name);
    if (v == nullptr) {
      if (f->required) {
        return make_error(std::string(f->path), "", "required", "present");
      }
      continue;
    }
    if (!type_ok(f->type, *v)) {
      return make_error(std::string(f->path), as_text(*v), "type", type_name(f->type));
    }
    std::optional<Error> err =
        f->type == FieldType::Object ? check_object(*v, std::string(f->path)) : check_value(*f, *v);
    if (err) {
      return err;
    }
  }
  return std::nullopt;
}

// The tree without hash-excluded fields.
Value strip_hash_excluded(const Value& v, const std::string& prefix) {
  if (v.kind() != Kind::Object) {
    return v;
  }
  std::vector<Value::Member> kept;
  for (const auto& [key, child] : v.object()) {
    const std::string pointer = prefix + "/" + pointer_part(key);
    const Field* f = field_at(pointer);
    if (f != nullptr && f->tag == FieldTag::HashExcluded) {
      continue;
    }
    kept.emplace_back(key, strip_hash_excluded(child, pointer));
  }
  return Value::object_value(std::move(kept));
}

double number_at(const Value& obj, std::string_view key) {
  const Value* v = obj.find(key);
  return v != nullptr ? v->number() : 0.0;
}

std::string string_at(const Value& obj, std::string_view key) {
  const Value* v = obj.find(key);
  return v != nullptr ? v->string() : std::string();
}

}  // namespace

ParseResult parse(std::string_view utf8) {
  ParseResult result;
  auto doc = json::parse(utf8);
  if (!doc.value) {
    result.error = make_error(std::to_string(doc.error.offset), std::move(doc.error.value),
                              doc.error.rule, doc.error.limit);
    return result;
  }
  const Value& root = *doc.value;
  if (root.kind() != Kind::Object) {
    result.error = make_error("", as_text(root), "type", "object");
    return result;
  }
  if (auto err = check_object(root, "")) {
    result.error = std::move(*err);
    return result;
  }

  Recipe r;
  r.schema_version = string_at(root, "schema_version");
  r.engine_version = string_at(root, "engine_version");
  r.seed = static_cast<std::uint64_t>(number_at(root, "seed"));  // checked: 0 to 2^53 - 1
  r.author = string_at(root, "author");
  r.date = string_at(root, "date");
  r.rationale = string_at(root, "rationale");
  r.length_s = number_at(root, "length_s");
  r.loudness_target_lufs = number_at(root, "loudness_target_lufs");
  if (root.find("loudness_gain_db") != nullptr) {
    r.loudness_gain_db = number_at(root, "loudness_gain_db");
  }
  if (root.find("loudness_hash") != nullptr) {
    r.loudness_hash = string_at(root, "loudness_hash");
  }
  if (const Value* theta = root.find("theta_reference")) {
    r.theta_reference = ThetaReference{number_at(*theta, "carrier_hz")};
  }
  if (const Value* bin = root.find("binaural")) {
    r.binaural = Binaural{number_at(*bin, "carrier_left_hz"), number_at(*bin, "beat_rate_hz")};
  }
  r.hash = crypto::sha256_hex(json::canonicalize(strip_hash_excluded(root, "")));
  result.recipe = std::move(r);
  return result;
}

}  // namespace arcani::recipe
