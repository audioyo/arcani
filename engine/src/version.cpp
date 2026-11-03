#include <arcani/arcani.h>

#ifndef ARC_ENGINE_VERSION_STRING
#error "ARC_ENGINE_VERSION_STRING must be defined by the build"
#endif

extern "C" const char* arc_engine_version(void) {
    return ARC_ENGINE_VERSION_STRING;
}
