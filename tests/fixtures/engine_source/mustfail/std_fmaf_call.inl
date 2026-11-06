// Must-fail fixture: the float std:: fused multiply-add.
inline float fused_f(float a, float b, float c) {
  return std::fmaf(a, b, c);
}
