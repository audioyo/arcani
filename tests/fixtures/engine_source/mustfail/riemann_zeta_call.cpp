// Must-fail fixture: a C++17 special math function.
#include <cmath>
double zeta(double x) { return std::riemann_zeta(x); }
