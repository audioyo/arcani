// Decimal text to binary64 and back, with exact big-integer arithmetic.
//
// Reading: the decimal value D * 10^E is held exactly as a ratio of big
// integers, scaled by a power of two until the quotient has 53 bits, then
// rounded half to even on the exact remainder. Digits past the 800th only
// matter as "nonzero or not" (a binary64 rounding boundary has at most 767
// significant digits), so they collapse to one sticky digit.
//
// Writing: the free-format shortest digit generation of Burger and Dybvig
// (1996), on exact big integers, with the rounding boundaries inclusive when
// the significand is even (a reader rounds half to even). The last digit is
// chosen closest to x, ties to even, which matches the ECMAScript rule.

#include "json/number.hpp"

#include <bit>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace arcani::json {

namespace {

// Unsigned big integer, 32-bit limbs, least significant first, no high zero
// limbs (zero is the empty vector).
class Big {
 public:
  Big() = default;
  explicit Big(std::uint64_t v) {
    while (v != 0) {
      limbs_.push_back(static_cast<std::uint32_t>(v));
      v >>= 32;
    }
  }

  bool is_zero() const noexcept { return limbs_.empty(); }

  void mul_small(std::uint32_t m) {
    std::uint64_t carry = 0;
    for (auto& limb : limbs_) {
      const std::uint64_t t = std::uint64_t{limb} * m + carry;
      limb = static_cast<std::uint32_t>(t);
      carry = t >> 32;
    }
    if (carry != 0) {
      limbs_.push_back(static_cast<std::uint32_t>(carry));
    }
    trim();
  }

  void add_small(std::uint32_t a) {
    std::uint64_t carry = a;
    for (std::size_t i = 0; carry != 0; ++i) {
      if (i == limbs_.size()) {
        limbs_.push_back(0);
      }
      const std::uint64_t t = std::uint64_t{limbs_[i]} + carry;
      limbs_[i] = static_cast<std::uint32_t>(t);
      carry = t >> 32;
    }
  }

  void mul_pow10(std::int64_t n) {
    static constexpr std::uint32_t kPow10[10] = {1u,      10u,      100u,      1000u,      10000u,
                                                 100000u, 1000000u, 10000000u, 100000000u, 1000000000u};
    while (n >= 9) {
      mul_small(kPow10[9]);
      n -= 9;
    }
    if (n > 0) {
      mul_small(kPow10[n]);
    }
  }

  void shl(std::int64_t bits) {
    if (is_zero() || bits <= 0) {
      return;
    }
    const auto whole = static_cast<std::size_t>(bits / 32);
    const int part = static_cast<int>(bits % 32);
    std::vector<std::uint32_t> out(whole, 0u);
    out.reserve(whole + limbs_.size() + 1);
    std::uint32_t carry = 0;
    for (const std::uint32_t limb : limbs_) {
      if (part == 0) {
        out.push_back(limb);
      } else {
        out.push_back((limb << part) | carry);
        carry = limb >> (32 - part);
      }
    }
    if (carry != 0) {
      out.push_back(carry);
    }
    limbs_ = std::move(out);
  }

  void shr1() noexcept {
    for (std::size_t i = 0; i < limbs_.size(); ++i) {
      const std::uint32_t next = i + 1 < limbs_.size() ? limbs_[i + 1] : 0u;
      limbs_[i] = (limbs_[i] >> 1) | (next << 31);
    }
    trim();
  }

  std::int64_t bit_length() const noexcept {
    if (is_zero()) {
      return 0;
    }
    return static_cast<std::int64_t>(32 * (limbs_.size() - 1)) +
           (32 - std::countl_zero(limbs_.back()));
  }

  // *this += b
  void add(const Big& b) {
    if (limbs_.size() < b.limbs_.size()) {
      limbs_.resize(b.limbs_.size(), 0u);
    }
    std::uint64_t carry = 0;
    for (std::size_t i = 0; i < limbs_.size(); ++i) {
      const std::uint64_t t =
          std::uint64_t{limbs_[i]} + (i < b.limbs_.size() ? b.limbs_[i] : 0u) + carry;
      limbs_[i] = static_cast<std::uint32_t>(t);
      carry = t >> 32;
    }
    if (carry != 0) {
      limbs_.push_back(static_cast<std::uint32_t>(carry));
    }
  }

  // *this -= b, for *this >= b
  void sub(const Big& b) noexcept {
    std::int64_t borrow = 0;
    for (std::size_t i = 0; i < limbs_.size(); ++i) {
      std::int64_t t = std::int64_t{limbs_[i]} - (i < b.limbs_.size() ? b.limbs_[i] : 0u) - borrow;
      borrow = t < 0 ? 1 : 0;
      if (t < 0) {
        t += std::int64_t{1} << 32;
      }
      limbs_[i] = static_cast<std::uint32_t>(t);
    }
    trim();
  }

  std::uint64_t low64() const noexcept {
    std::uint64_t v = 0;
    if (!limbs_.empty()) {
      v = limbs_[0];
    }
    if (limbs_.size() > 1) {
      v |= std::uint64_t{limbs_[1]} << 32;
    }
    return v;
  }

  friend int compare(const Big& a, const Big& b) noexcept {
    if (a.limbs_.size() != b.limbs_.size()) {
      return a.limbs_.size() < b.limbs_.size() ? -1 : 1;
    }
    for (std::size_t i = a.limbs_.size(); i-- > 0;) {
      if (a.limbs_[i] != b.limbs_[i]) {
        return a.limbs_[i] < b.limbs_[i] ? -1 : 1;
      }
    }
    return 0;
  }

 private:
  void trim() noexcept {
    while (!limbs_.empty() && limbs_.back() == 0) {
      limbs_.pop_back();
    }
  }

  std::vector<std::uint32_t> limbs_;
};

Big sum(const Big& a, const Big& b) {
  Big t = a;
  t.add(b);
  return t;
}

constexpr std::uint64_t kSignBit = UINT64_C(0x8000000000000000);
constexpr std::uint64_t kFracMask = (UINT64_C(1) << 52) - 1;
constexpr std::uint64_t kHidden = UINT64_C(1) << 52;
constexpr std::size_t kMaxSignificantDigits = 800;
constexpr std::int64_t kExponentCap = 1000000000;

bool is_digit(char c) noexcept { return c >= '0' && c <= '9'; }

// Quotient (below 2^55) and remainder of num / den; num becomes the remainder.
std::uint64_t divide_small_quotient(Big& num, const Big& den) {
  Big t = den;
  t.shl(55);
  std::uint64_t q = 0;
  for (int i = 55; i >= 0; --i) {
    if (compare(num, t) >= 0) {
      num.sub(t);
      q |= UINT64_C(1) << i;
    }
    t.shr1();
  }
  return q;
}

// floor(n * 2^s / d) rounded half to even on the exact remainder.
std::uint64_t scaled_rounded(const Big& n, const Big& d, std::int64_t s) {
  Big num = n;
  Big den = d;
  if (s >= 0) {
    num.shl(s);
  } else {
    den.shl(-s);
  }
  std::uint64_t q = divide_small_quotient(num, den);
  num.shl(1);
  const int c = compare(num, den);
  if (c > 0 || (c == 0 && (q & 1u) != 0)) {
    ++q;
  }
  return q;
}

// Unrounded quotient only, to pick the scale.
std::uint64_t scaled_floor(const Big& n, const Big& d, std::int64_t s) {
  Big num = n;
  Big den = d;
  if (s >= 0) {
    num.shl(s);
  } else {
    den.shl(-s);
  }
  return divide_small_quotient(num, den);
}

// ceil(x) for |x| well inside the int64 range, without libm.
std::int64_t ceil_to_int(double x) noexcept {
  const auto t = static_cast<std::int64_t>(x);
  return static_cast<double>(t) >= x ? t : t + 1;
}

}  // namespace

bool is_integral(double x) noexcept {
  const auto bits = std::bit_cast<std::uint64_t>(x);
  const auto biased = static_cast<int>((bits >> 52) & 0x7ffu);
  if (biased == 0x7ff) {
    return false;
  }
  if ((bits & ~kSignBit) == 0) {
    return true;
  }
  if (biased == 0) {
    return false;  // nonzero subnormal: 0 < |x| < 1
  }
  const int exp = biased - 1075;  // |x| = significand * 2^exp
  if (exp >= 0) {
    return true;
  }
  if (exp <= -53) {
    return false;
  }
  const std::uint64_t significand = (bits & kFracMask) | kHidden;
  return (significand & ((UINT64_C(1) << -exp) - 1)) == 0;
}

NumberStatus parse_number_status(std::string_view text, double& out) {
  std::size_t i = 0;
  const std::size_t n = text.size();
  bool negative = false;
  if (i < n && text[i] == '-') {
    negative = true;
    ++i;
  }
  const std::size_t int_begin = i;
  if (i < n && text[i] == '0') {
    ++i;
  } else if (i < n && text[i] >= '1' && text[i] <= '9') {
    while (i < n && is_digit(text[i])) {
      ++i;
    }
  } else {
    return NumberStatus::BadGrammar;
  }
  const std::string_view int_digits = text.substr(int_begin, i - int_begin);
  std::string_view frac_digits;
  if (i < n && text[i] == '.') {
    const std::size_t frac_begin = ++i;
    while (i < n && is_digit(text[i])) {
      ++i;
    }
    if (i == frac_begin) {
      return NumberStatus::BadGrammar;
    }
    frac_digits = text.substr(frac_begin, i - frac_begin);
  }
  std::int64_t exponent = 0;
  if (i < n && (text[i] == 'e' || text[i] == 'E')) {
    ++i;
    bool exp_negative = false;
    if (i < n && (text[i] == '+' || text[i] == '-')) {
      exp_negative = text[i] == '-';
      ++i;
    }
    const std::size_t exp_begin = i;
    while (i < n && is_digit(text[i])) {
      if (exponent < kExponentCap) {
        exponent = exponent * 10 + (text[i] - '0');
      }
      ++i;
    }
    if (i == exp_begin) {
      return NumberStatus::BadGrammar;
    }
    if (exp_negative) {
      exponent = -exponent;
    }
  }
  if (i != n) {
    return NumberStatus::BadGrammar;
  }

  // Value = digits * 10^e10, digits without leading or trailing zeros.
  std::string digits;
  digits.reserve(int_digits.size() + frac_digits.size());
  digits.append(int_digits);
  digits.append(frac_digits);
  std::int64_t e10 = exponent - static_cast<std::int64_t>(frac_digits.size());
  const std::size_t first = digits.find_first_not_of('0');
  const double zero = negative ? -0.0 : 0.0;
  if (first == std::string::npos) {
    out = zero;
    return NumberStatus::Ok;
  }
  digits.erase(0, first);
  const std::size_t last = digits.find_last_not_of('0');
  e10 += static_cast<std::int64_t>(digits.size() - 1 - last);
  digits.erase(last + 1);
  if (digits.size() > kMaxSignificantDigits) {
    const bool sticky =
        digits.find_first_not_of('0', kMaxSignificantDigits) != std::string::npos;
    e10 += static_cast<std::int64_t>(digits.size() - kMaxSignificantDigits);
    digits.erase(kMaxSignificantDigits);
    if (sticky) {
      digits.push_back('1');
      e10 -= 1;
    }
  }
  // The value lies in [10^(magnitude - 1), 10^magnitude).
  const std::int64_t magnitude = static_cast<std::int64_t>(digits.size()) + e10;
  if (magnitude > 310) {
    return NumberStatus::Overflow;  // at least 10^309
  }
  if (magnitude < -324) {
    out = zero;  // below 10^-325, under half the smallest subnormal
    return NumberStatus::Ok;
  }

  Big num;
  for (std::size_t at = 0; at < digits.size(); at += 9) {
    const std::size_t len = digits.size() - at < 9 ? digits.size() - at : 9;
    std::uint32_t chunk = 0;
    std::uint32_t scale = 1;
    for (std::size_t j = 0; j < len; ++j) {
      chunk = chunk * 10u + static_cast<std::uint32_t>(digits[at + j] - '0');
      scale *= 10u;
    }
    num.mul_small(scale);
    num.add_small(chunk);
  }
  Big den(1);
  if (e10 >= 0) {
    num.mul_pow10(e10);
  } else {
    den.mul_pow10(-e10);
  }

  // Pick s so that floor(num * 2^s / den) has exactly 53 bits.
  std::int64_t s = 53 - (num.bit_length() - den.bit_length());
  if (scaled_floor(num, den, s) >= (UINT64_C(1) << 53)) {
    --s;
  }
  std::uint64_t bits = 0;
  if (s > 1074) {
    // Subnormal or the smallest normal: fixed scale 2^1074, bits = quotient.
    bits = scaled_rounded(num, den, 1074);
  } else {
    std::uint64_t q = scaled_rounded(num, den, s);
    std::int64_t e2 = -s;
    if (q == (UINT64_C(1) << 53)) {
      q >>= 1;
      ++e2;
    }
    const std::int64_t biased = e2 + 1075;
    if (biased >= 0x7ff) {
      return NumberStatus::Overflow;
    }
    bits = (static_cast<std::uint64_t>(biased) << 52) | (q & kFracMask);
  }
  if (negative) {
    bits |= kSignBit;
  }
  out = std::bit_cast<double>(bits);
  return NumberStatus::Ok;
}

bool parse_number(std::string_view text, double& out) {
  double value = 0.0;
  if (parse_number_status(text, value) != NumberStatus::Ok) {
    return false;
  }
  out = value;
  return true;
}

std::string format_number(double x) {
  const auto bits = std::bit_cast<std::uint64_t>(x);
  if ((bits & ~kSignBit) == 0) {
    return "0";
  }
  std::string out;
  if ((bits & kSignBit) != 0) {
    out.push_back('-');
  }
  const auto biased = static_cast<std::int64_t>((bits >> 52) & 0x7ffu);
  const std::uint64_t frac = bits & kFracMask;
  const std::uint64_t f = biased == 0 ? frac : (frac | kHidden);
  const std::int64_t e = biased == 0 ? -1074 : biased - 1075;
  const bool even = (f & 1u) == 0;

  // x = r / s; the round-trip interval is (x - mm / s, x + mp / s), its ends
  // included when the significand is even.
  Big r(f);
  Big s;
  Big mp;
  Big mm;
  const bool asymmetric = f == kHidden && biased > 1;  // lower neighbor is closer
  if (e >= 0) {
    if (!asymmetric) {
      r.shl(e + 1);
      s = Big(2);
      mp = Big(1);
      mp.shl(e);
      mm = mp;
    } else {
      r.shl(e + 2);
      s = Big(4);
      mp = Big(1);
      mp.shl(e + 1);
      mm = Big(1);
      mm.shl(e);
    }
  } else {
    if (!asymmetric) {
      r.shl(1);
      s = Big(1);
      s.shl(1 - e);
      mp = Big(1);
      mm = Big(1);
    } else {
      r.shl(2);
      s = Big(1);
      s.shl(2 - e);
      mp = Big(2);
      mm = Big(1);
    }
  }

  // k: the smallest integer with x + mp / s below (or at) 10^k. The estimate
  // from the bit length never exceeds it; the loop corrects it upward.
  const std::int64_t bit_len = std::bit_width(f);
  std::int64_t k = ceil_to_int(static_cast<double>(e + bit_len - 1) * 0.30102999566398114 - 1e-10);
  if (k >= 0) {
    s.mul_pow10(k);
  } else {
    r.mul_pow10(-k);
    mp.mul_pow10(-k);
    mm.mul_pow10(-k);
  }
  for (;;) {
    const int c = compare(sum(r, mp), s);
    if (even ? c >= 0 : c > 0) {
      s.mul_small(10);
      ++k;
    } else {
      break;
    }
  }

  std::string digits;
  for (;;) {
    r.mul_small(10);
    mp.mul_small(10);
    mm.mul_small(10);
    int d = 0;
    while (compare(r, s) >= 0) {
      r.sub(s);
      ++d;
    }
    const int c_low = compare(r, mm);
    const bool low = even ? c_low <= 0 : c_low < 0;
    const int c_high = compare(sum(r, mp), s);
    const bool high = even ? c_high >= 0 : c_high > 0;
    if (!low && !high) {
      digits.push_back(static_cast<char>('0' + d));
      continue;
    }
    if (low && high) {
      Big twice = r;
      twice.shl(1);
      const int c = compare(twice, s);
      if (c > 0 || (c == 0 && (d & 1) != 0)) {
        ++d;
      }
    } else if (high) {
      ++d;
    }
    digits.push_back(static_cast<char>('0' + d));
    break;
  }
  while (digits.size() > 1 && digits.back() == '0') {
    digits.pop_back();
  }

  // ECMAScript Number::toString: digits d1..dk with the decimal point after
  // position n (x = 0.d1..dk * 10^n).
  const auto len = static_cast<std::int64_t>(digits.size());
  const std::int64_t point = k;
  if (len <= point && point <= 21) {
    out += digits;
    out.append(static_cast<std::size_t>(point - len), '0');
  } else if (0 < point && point <= 21) {
    out.append(digits, 0, static_cast<std::size_t>(point));
    out.push_back('.');
    out.append(digits, static_cast<std::size_t>(point));
  } else if (-6 < point && point <= 0) {
    out += "0.";
    out.append(static_cast<std::size_t>(-point), '0');
    out += digits;
  } else {
    const std::int64_t exp10 = point - 1;
    out.push_back(digits[0]);
    if (len > 1) {
      out.push_back('.');
      out.append(digits, 1);
    }
    out.push_back('e');
    out.push_back(exp10 >= 0 ? '+' : '-');
    out += std::to_string(exp10 >= 0 ? exp10 : -exp10);
  }
  return out;
}

}  // namespace arcani::json
