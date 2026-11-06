// Clean fixture: a raw string literal holding banned text is stripped too.
#pragma once
inline const char* raw() {
  return R"(exp(1.0) long double 0.5L
#include <random>
std::fma(a, b, c))";
}
inline double after_raw(double x) { return x * 2.0; }
