// arcani-render stub behavior.
//
// Contract with the build: tests/cpp CMake must define ARCANI_RENDER_PATH as a
// string literal holding the absolute path of the built arcani-render
// executable, for example
//   target_compile_definitions(arcani_tests PRIVATE
//       ARCANI_RENDER_PATH="$<TARGET_FILE:arcani-render>")
// and make the test target depend on arcani-render.
//
// Expected behavior:
//   arcani-render --version  -> prints arc_engine_version(), exit 0
//   no argument              -> usage text containing "usage", exit 2
//   any other argument(s)    -> usage text containing "usage", exit 2

#include <arcani/arcani.h>

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <string>

#ifndef ARCANI_RENDER_PATH
#error "ARCANI_RENDER_PATH must be defined by the build (path to arcani-render)"
#endif

#if defined(_WIN32)
#define ARC_POPEN _popen
#define ARC_PCLOSE _pclose
#else
#include <sys/wait.h>
#define ARC_POPEN popen
#define ARC_PCLOSE pclose
#endif

namespace {

struct RunResult {
    int exit_code;
    std::string output;
};

// Runs arcani-render with the given argument string. Captures stdout, and
// stderr too when merge_stderr is true.
RunResult run_cli(const std::string& args, bool merge_stderr) {
    std::string cmd = std::string("\"") + ARCANI_RENDER_PATH + "\"";
    if (!args.empty()) {
        cmd += " " + args;
    }
    if (merge_stderr) {
        cmd += " 2>&1";
    }
#if defined(_WIN32)
    // cmd /c strips one outer pair of quotes; wrap so the quoted path survives.
    cmd = "\"" + cmd + "\"";
#endif

    RunResult result{-1, {}};
    FILE* pipe = ARC_POPEN(cmd.c_str(), "r");
    REQUIRE(pipe != nullptr);
    char buffer[512];
    while (std::fgets(buffer, sizeof buffer, pipe) != nullptr) {
        result.output += buffer;
    }
    int status = ARC_PCLOSE(pipe);
#if defined(_WIN32)
    result.exit_code = status;
#else
    result.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
#endif
    return result;
}

std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}

std::string trim(const std::string& s) {
    const char* ws = " \t\r\n";
    const auto begin = s.find_first_not_of(ws);
    if (begin == std::string::npos) {
        return {};
    }
    const auto end = s.find_last_not_of(ws);
    return s.substr(begin, end - begin + 1);
}

void require_usage_exit_2(const std::string& args) {
    INFO("arguments: [" << args << "]");
    const RunResult r = run_cli(args, true);
    INFO("output: " << r.output);
    REQUIRE(r.exit_code == 2);
    REQUIRE(lower(r.output).find("usage") != std::string::npos);
}

}  // namespace

TEST_CASE("--version prints the engine version and exits 0", "[cli]") {
    const RunResult r = run_cli("--version", false);
    INFO("output: " << r.output);
    REQUIRE(r.exit_code == 0);
    REQUIRE(trim(r.output) == std::string(arc_engine_version()));
}

TEST_CASE("no argument prints usage and exits 2", "[cli]") {
    require_usage_exit_2("");
}

TEST_CASE("any other argument prints usage and exits 2", "[cli]") {
    require_usage_exit_2("--bogus");
    require_usage_exit_2("render");
    require_usage_exit_2("-v");
    require_usage_exit_2("--VERSION");
    require_usage_exit_2("--version extra");
}
