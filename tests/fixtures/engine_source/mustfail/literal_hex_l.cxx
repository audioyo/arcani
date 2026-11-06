// Must-fail fixture: a hexadecimal float literal with an L suffix.
double eighth() {
  return static_cast<double>(0x1p-3L);
}
