"""Structure of the fast and full CI workflows, presets, and platform pins.

Contract with .github/workflows/full.yml:

- Triggers exactly: `pull_request` with branches [main], `schedule` with one
  cron `0 3 * * *`, and `workflow_dispatch`.
- Jobs exactly: gate, windows-x64, windows-arm64, macos-arm64,
  android-build, android-arm64, contract-mustfail, hash-compare, verdict.
- runs-on (exact labels, no "or newer"): gate ubuntu-24.04, windows-x64
  windows-2025, windows-arm64 windows-11-arm, macos-arm64 macos-15,
  android-build ubuntu-24.04, android-arm64 ubuntu-24.04-arm,
  contract-mustfail ubuntu-24.04-arm, hash-compare ubuntu-24.04, verdict
  ubuntu-24.04. No `self-hosted` label anywhere in either workflow.
- Workflow-level `permissions` is exactly `contents: read` in both
  workflows. Only the gate job adds `actions: read` (its job-level
  permissions grant only read scopes, from contents and actions); no other
  job sets permissions beyond `contents: read`.
- `concurrency` has a group per ref (mentions github.ref or github.head_ref)
  and `cancel-in-progress` is an expression mentioning `pull_request`, so
  only pull request runs cancel each other.
- Every job other than gate depends on gate, directly or through another
  job; each job that needs gate directly (other than verdict) has an `if:`
  reading `needs.gate.outputs.run`. verdict has `if:` containing `always()`,
  needs every other job, and runs `tools/ci_verdict.py --needs` on
  `toJSON(needs)`. gate runs `tools/nightly_gate.py` with `--event`.
- windows-x64 and windows-arm64 use preset windows-clang-cl (windows-arm64
  reads the `windows_arm64` pins); macos-arm64 uses preset macos-appleclang
  and runs `xcode-select`; android-build reads `android_ndk` from
  toolchain.json, uses preset android-arm64, and runs
  tools/check_compile_flags.py and tools/check_engine_symbols.py;
  android-arm64 needs android-build. Each probe job (windows-x64,
  windows-arm64, macos-arm64, android-arm64) runs tools/hash_manifest.py
  with `--platform <job id>` and uploads artifact `hashprobe-<job id>`.
  hash-compare needs all four probe jobs and runs tools/hash_compare.py.
  contract-mustfail sets ARCANI_HASHPROBE_EXTRA_FLAGS with -ffp-contract=fast
  and runs `hash_compare.py --must-differ` (in one run step).
- ARCANI_HASHPROBE_EXTRA_FLAGS appears in no other job, nowhere in fast.yml,
  and in no preset. ARCANI_ENGINE_TEST_EXTRA_SOURCE appears in neither
  workflow.

Contract with both workflows (every job):

- The first step's `run` records the start time and contains
  `ARCANI_JOB_START` (for example `echo "ARCANI_JOB_START=$(date +%s)" >>
  "$GITHUB_ENV"`).
- One step uses `astral-sh/setup-uv@<sha>`.
- The last step has an `if:` containing `always()` and runs
  `tools/check_wall_time.py` with `--tier <fast|full>` (the workflow's tier),
  `--job <job id>`, and the recorded `ARCANI_JOB_START`.
- `timeout-minutes` is set.
- Every `uses:` (step or job level) is `owner/repo[/path]@<40 hex>`.

fast.yml keeps trigger `push` and exactly the jobs linux-x64 and windows-x64
(their `name:`, when set, equals the job id: the branch rule uses them).

fast.yml table checks (Story 0.3), in both jobs linux-x64 and windows-x64:

- The `actions/checkout` step has `with: fetch-depth: 0` (the table-log
  check needs the merge base with origin/main).
- A step whose `run` calls `tools/check_table_log.py` with `--base` and
  `git merge-base origin/main HEAD` comes before the step named
  "Configure, build, ctest".
- A step whose `run` calls `tools/check_row_coverage.py` comes after the
  step named "Python tests"; the wall-time step stays last.

fast.yml wording check (Story 0.4), in both jobs linux-x64 and windows-x64:
a step whose `run` calls `tools/check_wording.py` comes after the
`actions/checkout` step and before the step named "Configure, build, ctest".

CMakePresets.json gains configure presets `macos-appleclang` (condition
hostSystemName equals Darwin) and `android-arm64` (condition hostSystemName
equals Linux; toolchainFile, or cache CMAKE_TOOLCHAIN_FILE, is
`$env{ANDROID_NDK_ROOT}/build/cmake/android.toolchain.cmake`; cache
ANDROID_ABI arm64-v8a, ANDROID_PLATFORM `android-<api_level>` from
toolchain.json android_ndk, ARCANI_BUILD_TESTS OFF). cmake/Pins.cmake
mentions apple_clang, android_ndk, AppleClang, and ANDROID.
tests/hashprobe/CMakeLists.txt declares the ARCANI_HASHPROBE_EXTRA_FLAGS
cache variable.

Reference machine (Story 1.4): ARCANI_REFERENCE_MACHINE appears in no
workflow file (.github/workflows/*.yml and *.yaml) and not in
CMakePresets.json, so no CI job is ever the render speed reference machine.

YAML 1.1 parses the `on:` key as Python True; both spellings are handled.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
FULL_JOBS = ["gate", "windows-x64", "windows-arm64", "macos-arm64", "android-build",
             "android-arm64", "contract-mustfail", "hash-compare", "verdict"]
RUNS_ON = {
    "gate": "ubuntu-24.04",
    "windows-x64": "windows-2025",
    "windows-arm64": "windows-11-arm",
    "macos-arm64": "macos-15",
    "android-build": "ubuntu-24.04",
    "android-arm64": "ubuntu-24.04-arm",
    "contract-mustfail": "ubuntu-24.04-arm",
    "hash-compare": "ubuntu-24.04",
    "verdict": "ubuntu-24.04",
}
PROBE_JOBS = ["windows-x64", "windows-arm64", "macos-arm64", "android-arm64"]
TIERS = {"fast.yml": "fast", "full.yml": "full"}
USES_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")


def raw(name):
    path = WORKFLOWS / name
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def load(name):
    return yaml.safe_load(raw(name))


def triggers(wf):
    if "on" in wf:
        return wf["on"]
    assert True in wf, f"workflow has no on: key: {sorted(map(str, wf))}"
    return wf[True]


def job_text(job):
    return yaml.safe_dump(job, sort_keys=False, width=10_000)


def runs(job):
    return [s["run"] for s in job.get("steps", []) if isinstance(s.get("run"), str)]


def as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def all_uses(wf):
    for job_id, job in wf["jobs"].items():
        if "uses" in job:
            yield job_id, job["uses"]
        for step in job.get("steps", []):
            if "uses" in step:
                yield job_id, step["uses"]


both = pytest.mark.parametrize("name", ["fast.yml", "full.yml"])


# ---------------------------------------------------------------- full.yml


def test_full_triggers():
    on = triggers(load("full.yml"))
    assert set(on) == {"pull_request", "schedule", "workflow_dispatch"}, on
    assert on["pull_request"]["branches"] == ["main"], on["pull_request"]
    assert on["schedule"] == [{"cron": "0 3 * * *"}], on["schedule"]


def test_full_jobs_exact():
    assert set(load("full.yml")["jobs"]) == set(FULL_JOBS)


@pytest.mark.parametrize("job_id, label", sorted(RUNS_ON.items()))
def test_full_runner_labels(job_id, label):
    assert load("full.yml")["jobs"][job_id]["runs-on"] == label


@both
def test_no_self_hosted_runner(name):
    assert "self-hosted" not in raw(name).lower()


def test_verdict_always_runs_and_needs_every_job():
    job = load("full.yml")["jobs"]["verdict"]
    assert "always()" in str(job.get("if", "")), job.get("if")
    assert set(as_list(job.get("needs"))) == set(FULL_JOBS) - {"verdict"}
    assert any("tools/ci_verdict.py" in r and "--needs" in r for r in runs(job)), runs(job)
    assert "toJSON(needs)" in job_text(job)


def test_every_job_depends_on_gate():
    jobs = load("full.yml")["jobs"]

    def ancestors(job_id, seen=None):
        seen = set() if seen is None else seen
        for parent in as_list(jobs[job_id].get("needs")):
            if parent not in seen:
                seen.add(parent)
                ancestors(parent, seen)
        return seen

    for job_id in jobs:
        if job_id == "gate":
            continue
        assert "gate" in ancestors(job_id), job_id
        if "gate" in as_list(jobs[job_id].get("needs")) and job_id != "verdict":
            assert "needs.gate.outputs.run" in str(jobs[job_id].get("if", "")), (
                job_id, jobs[job_id].get("if"))


def test_gate_runs_nightly_gate():
    job = load("full.yml")["jobs"]["gate"]
    assert any("tools/nightly_gate.py" in r and "--event" in r for r in runs(job)), runs(job)


@both
def test_uses_pinned_by_full_sha(name):
    found = list(all_uses(load(name)))
    assert found, f"{name} uses no actions"
    for job_id, uses in found:
        assert USES_RE.match(uses.strip()), f"{name} {job_id}: {uses}"


@both
def test_workflow_permissions_read_only(name):
    wf = load(name)
    assert wf.get("permissions") == {"contents": "read"}, wf.get("permissions")
    for job_id, job in wf["jobs"].items():
        perms = job.get("permissions")
        if name == "full.yml" and job_id == "gate":
            assert isinstance(perms, dict) and perms.get("actions") == "read", perms
            assert set(perms) <= {"contents", "actions"}, perms
            assert all(v == "read" for v in perms.values()), perms
        else:
            assert perms in (None, {"contents": "read"}), (name, job_id, perms)


def test_full_concurrency_cancels_pull_requests_only():
    conc = load("full.yml").get("concurrency")
    assert isinstance(conc, dict), conc
    group = str(conc.get("group", ""))
    assert "github.ref" in group or "github.head_ref" in group, group
    cancel = conc.get("cancel-in-progress")
    assert isinstance(cancel, str) and "pull_request" in cancel, cancel


def test_windows_jobs_use_clang_cl_preset():
    jobs = load("full.yml")["jobs"]
    for job_id in ("windows-x64", "windows-arm64"):
        assert re.search(r"--preset[ =]windows-clang-cl\b", job_text(jobs[job_id])), job_id
    assert "windows_arm64" in job_text(jobs["windows-arm64"])


def test_macos_job_uses_appleclang_preset_and_pinned_xcode():
    text = job_text(load("full.yml")["jobs"]["macos-arm64"])
    assert re.search(r"--preset[ =]macos-appleclang\b", text), text
    assert "xcode-select" in text, text


def test_android_build_job():
    job = load("full.yml")["jobs"]["android-build"]
    text = job_text(job)
    assert re.search(r"--preset[ =]android-arm64\b", text), text
    assert "android_ndk" in text, text
    assert any("tools/check_compile_flags.py" in r for r in runs(job)), runs(job)
    assert any("tools/check_engine_symbols.py" in r for r in runs(job)), runs(job)


def test_android_run_job_needs_build():
    job = load("full.yml")["jobs"]["android-arm64"]
    assert "android-build" in as_list(job.get("needs"))


@pytest.mark.parametrize("job_id", PROBE_JOBS)
def test_probe_jobs_write_and_upload_manifest(job_id):
    job = load("full.yml")["jobs"][job_id]
    assert any("tools/hash_manifest.py" in r and re.search(rf"--platform[ =]{job_id}\b", r)
               for r in runs(job)), runs(job)
    assert f"hashprobe-{job_id}" in job_text(job)


def test_hash_compare_job():
    job = load("full.yml")["jobs"]["hash-compare"]
    assert set(PROBE_JOBS) <= set(as_list(job.get("needs"))), job.get("needs")
    assert any("tools/hash_compare.py" in r for r in runs(job)), runs(job)


def test_contract_mustfail_job():
    job = load("full.yml")["jobs"]["contract-mustfail"]
    text = job_text(job)
    assert "ARCANI_HASHPROBE_EXTRA_FLAGS" in text, text
    assert "-ffp-contract=fast" in text, text
    assert any("hash_compare.py" in r and "--must-differ" in r for r in runs(job)), runs(job)


def test_extra_flags_only_in_contract_mustfail():
    wf = load("full.yml")
    for job_id, job in wf["jobs"].items():
        if job_id != "contract-mustfail":
            assert "ARCANI_HASHPROBE_EXTRA_FLAGS" not in job_text(job), job_id
    top = {k: v for k, v in wf.items() if k != "jobs"}
    assert "ARCANI_HASHPROBE_EXTRA_FLAGS" not in yaml.safe_dump(top)
    assert "ARCANI_HASHPROBE_EXTRA_FLAGS" not in raw("fast.yml")
    presets = (REPO_ROOT / "CMakePresets.json").read_text(encoding="utf-8")
    assert "ARCANI_HASHPROBE_EXTRA_FLAGS" not in presets


@both
def test_engine_fault_injection_stays_out(name):
    assert "ARCANI_ENGINE_TEST_EXTRA_SOURCE" not in raw(name)


# ------------------------------------------------------- every job, both


def job_params():
    out = []
    for name in ("fast.yml", "full.yml"):
        path = WORKFLOWS / name
        jobs = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"] if path.is_file() else {}
        out += [(name, job_id) for job_id in jobs] or [(name, "<no jobs>")]
    return out


@pytest.mark.parametrize("name, job_id", job_params())
def test_job_records_start_first(name, job_id):
    steps = load(name)["jobs"][job_id]["steps"]
    assert "ARCANI_JOB_START" in str(steps[0].get("run", "")), steps[0]


@pytest.mark.parametrize("name, job_id", job_params())
def test_job_sets_up_uv(name, job_id):
    steps = load(name)["jobs"][job_id]["steps"]
    assert any(str(s.get("uses", "")).startswith("astral-sh/setup-uv@") for s in steps), job_id


@pytest.mark.parametrize("name, job_id", job_params())
def test_job_checks_wall_time_last(name, job_id):
    last = load(name)["jobs"][job_id]["steps"][-1]
    assert "always()" in str(last.get("if", "")), last
    text = str(last.get("run", ""))
    assert "tools/check_wall_time.py" in text, text
    assert re.search(rf"--tier[ =]{TIERS[name]}\b", text), text
    assert re.search(rf"--job[ =]{re.escape(job_id)}(?![\w-])", text), text
    assert "ARCANI_JOB_START" in text, text


@pytest.mark.parametrize("name, job_id", job_params())
def test_job_sets_timeout(name, job_id):
    job = load(name)["jobs"][job_id]
    assert isinstance(job.get("timeout-minutes"), int) and job["timeout-minutes"] > 0, job_id


# ---------------------------------------------------------------- fast.yml


def test_fast_keeps_trigger_and_jobs():
    wf = load("fast.yml")
    assert "push" in triggers(wf)
    assert set(wf["jobs"]) == {"linux-x64", "windows-x64"}
    for job_id, job in wf["jobs"].items():
        assert job.get("name", job_id) == job_id


# ----------------------------------------------------------- presets, pins


def load_presets():
    data = json.loads((REPO_ROOT / "CMakePresets.json").read_text(encoding="utf-8"))
    return {p["name"]: p for p in data["configurePresets"]}


def resolved(presets, name):
    """Returns (preset, merged cache variables) following inherits."""
    preset = presets[name]
    cache = {}
    for parent in reversed(as_list(preset.get("inherits"))):
        cache.update(resolved(presets, parent)[1])
    for key, value in preset.get("cacheVariables", {}).items():
        cache[key] = value["value"] if isinstance(value, dict) else value
    return preset, cache


def condition_host(preset):
    cond = preset.get("condition", {})
    assert cond.get("type") == "equals" and cond.get("lhs") == "${hostSystemName}", cond
    return cond.get("rhs")


def test_macos_preset():
    presets = load_presets()
    assert "macos-appleclang" in presets, sorted(presets)
    assert condition_host(presets["macos-appleclang"]) == "Darwin"


def test_android_preset():
    presets = load_presets()
    assert "android-arm64" in presets, sorted(presets)
    preset, cache = resolved(presets, "android-arm64")
    assert condition_host(preset) == "Linux"
    toolchain_file = preset.get("toolchainFile") or cache.get("CMAKE_TOOLCHAIN_FILE", "")
    assert toolchain_file.startswith("$env{ANDROID_NDK_ROOT}"), toolchain_file
    assert toolchain_file.endswith("build/cmake/android.toolchain.cmake"), toolchain_file
    api = json.loads((REPO_ROOT / "toolchain.json").read_text(encoding="utf-8"))["android_ndk"]["api_level"]
    assert cache.get("ANDROID_ABI") == "arm64-v8a", cache
    assert cache.get("ANDROID_PLATFORM") == f"android-{api}", cache
    assert str(cache.get("ARCANI_BUILD_TESTS")).upper() == "OFF", cache


def test_pins_cmake_covers_new_platforms():
    text = (REPO_ROOT / "cmake" / "Pins.cmake").read_text(encoding="utf-8")
    for needle in ("apple_clang", "android_ndk", "AppleClang", "ANDROID"):
        assert needle in text, needle


def test_hashprobe_declares_extra_flags_variable():
    path = REPO_ROOT / "tests" / "hashprobe" / "CMakeLists.txt"
    assert path.is_file(), f"missing {path}"
    text = path.read_text(encoding="utf-8")
    assert "arcani-hashprobe" in text
    assert "ARCANI_HASHPROBE_EXTRA_FLAGS" in text


# ------------------------------------------------------ fast.yml table checks

FAST_JOBS = ["linux-x64", "windows-x64"]


def step_index(steps, predicate, what):
    found = [i for i, s in enumerate(steps) if predicate(s)]
    assert found, f"no step {what}"
    return found[0]


def runs_tool(tool):
    return lambda s: tool in str(s.get("run", ""))


def named(name):
    return lambda s: s.get("name") == name


@pytest.mark.parametrize("job_id", FAST_JOBS)
def test_fast_checkout_fetches_full_history(job_id):
    steps = load("fast.yml")["jobs"][job_id]["steps"]
    checkout = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(checkout) == 1, checkout
    assert (checkout[0].get("with") or {}).get("fetch-depth") == 0, checkout[0]


@pytest.mark.parametrize("job_id", FAST_JOBS)
def test_fast_table_log_check_runs_before_build(job_id):
    steps = load("fast.yml")["jobs"][job_id]["steps"]
    at = step_index(steps, runs_tool("tools/check_table_log.py"), "running check_table_log.py")
    text = str(steps[at]["run"])
    assert "--base" in text, text
    assert "git merge-base origin/main HEAD" in text, text
    build = step_index(steps, named("Configure, build, ctest"), "named Configure, build, ctest")
    checkout = step_index(steps, lambda s: str(s.get("uses", "")).startswith("actions/checkout@"),
                          "using actions/checkout")
    assert checkout < at < build, (checkout, at, build)


@pytest.mark.parametrize("job_id", FAST_JOBS)
def test_fast_coverage_check_runs_after_pytest(job_id):
    steps = load("fast.yml")["jobs"][job_id]["steps"]
    at = step_index(steps, runs_tool("tools/check_row_coverage.py"), "running check_row_coverage.py")
    pytest_step = step_index(steps, named("Python tests"), "named Python tests")
    build = step_index(steps, named("Configure, build, ctest"), "named Configure, build, ctest")
    assert build < pytest_step < at < len(steps) - 1, (build, pytest_step, at, len(steps))
    assert "tools/check_wall_time.py" in str(steps[-1].get("run", "")), steps[-1]


# ---------------------------------------------------- fast.yml wording check


@pytest.mark.parametrize("job_id", FAST_JOBS)
def test_fast_wording_check_runs_before_build(job_id):
    steps = load("fast.yml")["jobs"][job_id]["steps"]
    at = step_index(steps, runs_tool("tools/check_wording.py"), "running check_wording.py")
    build = step_index(steps, named("Configure, build, ctest"), "named Configure, build, ctest")
    checkout = step_index(steps, lambda s: str(s.get("uses", "")).startswith("actions/checkout@"),
                          "using actions/checkout")
    assert checkout < at < build, (checkout, at, build)


# ------------------------------------------- reference machine (Story 1.4)

REFERENCE_ENV = "ARCANI_REFERENCE_MACHINE"


def workflow_texts():
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def sets_reference_machine(text):
    """True when a workflow or preset text names the reference machine variable at all."""
    return REFERENCE_ENV in text


def test_no_workflow_or_preset_sets_the_reference_machine():
    """Render speed is checked on the dev PC only; no CI job may claim to be it."""
    texts = workflow_texts()
    assert {"fast.yml", "full.yml"} <= set(texts), sorted(texts)
    for name, text in texts.items():
        assert not sets_reference_machine(text), f"{name} mentions {REFERENCE_ENV}"
    presets = (REPO_ROOT / "CMakePresets.json").read_text(encoding="utf-8")
    assert not sets_reference_machine(presets), f"CMakePresets.json mentions {REFERENCE_ENV}"


@pytest.mark.parametrize("addition", [
    f"\nenv:\n  {REFERENCE_ENV}: '1'\n",
    f"\n      - run: echo \"{REFERENCE_ENV}=1\" >> \"$GITHUB_ENV\"\n",
    f"\n        env:\n          {REFERENCE_ENV}: 1\n",
])
def test_reference_machine_check_catches_a_workflow_that_sets_it(addition):
    assert sets_reference_machine(raw("fast.yml") + addition)
