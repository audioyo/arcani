// Must-fail fixture for tools/check_engine_source.py: the long double type.
double widen(double x) {
  long double wide = x;
  return static_cast<double>(wide);
}
