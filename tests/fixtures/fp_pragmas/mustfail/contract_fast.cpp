// Must-fail fixture: clang fp contract pragma.

#pragma clang fp contract(fast)
double f(double a, double b, double c) { return a * b + c; }
