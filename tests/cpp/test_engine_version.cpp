// Engine version query, reached only through the public header.

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include <cstring>

TEST_CASE("arc_engine_version returns a non-empty string", "[engine][version]") {
    const char* version = arc_engine_version();
    REQUIRE(version != nullptr);
    REQUIRE(std::strlen(version) > 0);
}

TEST_CASE("arc_engine_version is stable across calls", "[engine][version]") {
    const char* first = arc_engine_version();
    const char* second = arc_engine_version();
    REQUIRE(first != nullptr);
    REQUIRE(second != nullptr);
    REQUIRE(std::strcmp(first, second) == 0);
}
