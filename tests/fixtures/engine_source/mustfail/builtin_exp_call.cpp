// Must-fail fixture: a compiler builtin transcendental, folded at compile time.
double e() {
  return __builtin_exp(1.0);
}
