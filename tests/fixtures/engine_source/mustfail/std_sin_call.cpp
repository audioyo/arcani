// Must-fail fixture: std::sin with a constant argument. The compiler folds it,
// so no libm symbol is left for the symbol check; only a source scan sees it.
#include <cmath>
/* A block comment
   over three lines, so the reported line number must count them. */
double folded() { return std::sin(0.25); }
