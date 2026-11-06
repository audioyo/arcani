// Must-fail fixture: an explicit fused multiply-add.
#include <cmath>
double fused(double a, double b, double c) {
  return fma(a, b, c);
}
