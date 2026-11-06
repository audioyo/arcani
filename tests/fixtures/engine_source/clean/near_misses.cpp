// Clean fixture for tools/check_engine_source.py. Comments may name the banned
// forms: std::sin(x), sin(, exp(1.0), fma(a, b, c), long double, 1.0L, and
// #include <random> are all fine inside a comment.
/* A block comment: long double wide = std::pow(x, 0.5L); */
#include <cmath>
#include <cstdint>

namespace arcani::fixture {

double sine(double phase);  // a name that starts with sin

inline double use_sine(double phase) { return sine(phase); }

inline double root(double x) { return std::sqrt(x) + sqrt(x); }

inline long ten() { return 10L; }

inline unsigned long sixteen() { return 0x10L + 10UL - 10ul; }

inline long long big() { return 10LL; }

inline float scale(float x) { return x * 1.0f * 0x1p23f; }

inline double exact() { return 0x1p23 * 2.5e3; }

inline int sin_count = 0;  // a name, not a call

inline double my_sin(double x) { return x; }

inline double call_mine(double x) { return my_sin(x) + use_sine(x); }

template <typename Curve>
double members(const Curve& obj, const Curve* p, double x) {
  return obj.log(x) + p->exp(x);  // member calls, not libm calls
}

inline const char* text() { return "std::sin(x) and long double and 1.0L"; }

inline char letter() { return 'L'; }

}  // namespace arcani::fixture
