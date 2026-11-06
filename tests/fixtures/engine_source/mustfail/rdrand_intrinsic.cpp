// Must-fail fixture: a hardware random intrinsic leaves no symbol.
unsigned int draw(unsigned int value) {
  return _rdrand32_step(&value) ? value : 0u;
}
