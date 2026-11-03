// Clean fixture for tools/check_fp_pragmas.py: no floating-point pragma.
// A comment that mentions the banned form is fine:
// #pragma clang fp contract(fast) would turn contraction on, so it is banned.
#pragma once
#pragma warning(push)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-parameter"

inline double clean_scale(double x) { return x * 0.5; }

#pragma clang diagnostic pop
#pragma warning(pop)
