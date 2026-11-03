// arcani-render: command-line renderer. Stub for Story 0.1: only --version.

#include <arcani/arcani.h>

#include <cstdio>
#include <cstring>

namespace {

constexpr int kExitUsage = 2;

int print_usage() {
    std::fputs("usage: arcani-render --version\n", stderr);
    return kExitUsage;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--version") == 0) {
        std::printf("%s\n", arc_engine_version());
        return 0;
    }
    return print_usage();
}
