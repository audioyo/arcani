// Must-fail fixture: long and double split by more than one space.
#pragma once
inline double split(double x) { return static_cast<long   double>(x) > 0 ? x : -x; }
