/* Must-fail fixture for the C header test (Story 1.2): a C++ reference
   parameter is not C, so the C-mode syntax check of this file must fail
   (ctest arcani_api_c_header_mustfail, WILL_FAIL). It proves the check really
   compiles as C. */
#include <arcani/arcani.h>

int arc_test_cpp_reference(arc_error& error);
