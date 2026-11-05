// Number text conversion for JSON (Story 1.1). Exact big-integer arithmetic,
// not std::from_chars or std::to_chars, whose floating-point overloads are
// missing from the pinned Apple libc++ (design log 2026-11-04 (ff)).

#ifndef ARCANI_JSON_NUMBER_HPP
#define ARCANI_JSON_NUMBER_HPP

#include <string>
#include <string_view>

namespace arcani::json {

// ECMAScript Number serialization (RFC 8785 section 3.2.2.3): the shortest
// digits that read back to x, the closest to x among them. -0 gives "0".
// x must be finite.
std::string format_number(double x);

// RFC 8259 number grammar, correctly rounded (round half to even). Returns
// false on bad grammar or on overflow to infinity; out is then unchanged.
bool parse_number(std::string_view text, double& out);

enum class NumberStatus { Ok, BadGrammar, Overflow };

// parse_number with the reason for a failure (used by the parser).
NumberStatus parse_number_status(std::string_view text, double& out);

// True when the finite x has no fractional part, read from its bits.
bool is_integral(double x) noexcept;

}  // namespace arcani::json

#endif  // ARCANI_JSON_NUMBER_HPP
