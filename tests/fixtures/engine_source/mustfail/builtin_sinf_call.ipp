// Must-fail fixture: the float variant of a builtin transcendental.
inline float s(float x) {
  return __builtin_sinf(x);
}
