// Must-fail fixture: an extended precision type.
double widen(double x) {
  __float128 wide = x;
  return static_cast<double>(wide);
}
