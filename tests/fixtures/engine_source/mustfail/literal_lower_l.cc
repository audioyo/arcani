// Must-fail fixture: a float literal with an exponent and an l suffix.
double big() {
  return static_cast<double>(2.5e3l);
}
