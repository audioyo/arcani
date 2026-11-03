// Clean fixture in a subdirectory: the scan is recursive.
#include "../clean.hpp"

double nested_scale(double x) { return clean_scale(x) + 1.0; }
