// RFC 8785 JSON Canonicalization Scheme (Story 1.1). Generic JSON, not
// recipe-specific: object members sorted by the UTF-16 code units of their
// keys, ECMAScript number serialization, the RFC's string escaping, no
// whitespace.

#ifndef ARCANI_JSON_CANONICAL_HPP
#define ARCANI_JSON_CANONICAL_HPP

#include <string>

#include "json/value.hpp"

namespace arcani::json {

// Canonical UTF-8 text of v. Preconditions: every number in v is finite and
// every string and key is valid UTF-8. Values from parse() always meet both;
// a value built by hand must too (invalid UTF-8 is not detected and gives
// wrong key order and output).
std::string canonicalize(const Value& v);

}  // namespace arcani::json

#endif  // ARCANI_JSON_CANONICAL_HPP
