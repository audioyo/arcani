// Must-fail fixture: a global-namespace pow call.
#pragma once
#include <math.h>
inline double square(double x) { return ::pow(x, 2.0); }
