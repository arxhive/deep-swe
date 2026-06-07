---
description: "Task list for Workflow Bench implementation"
---

# Tasks: Workflow Bench

**Input**: Design documents from `/specs/001-workflow-bench/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md, quickstart.md

**Tests**: INCLUDED. The feature's technical approach explicitly requires a pytest suite for pure logic plus gated docker integration tests; test tasks are first-class below.

**Organization**: Tasks are grouped by user story. Setup and Foundational phases build the shared harness machinery (pure logic + docker/runtime plumbing) that all three user stories depend on. Each phase leaves the project importable, lint-clean, and unit-testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task).
- **[Story]**: US1 / US2 / US3 for user-story phases; omitted for Setup, Foundational, Polish.
- All paths are relative to the repository root. The package root is `bench/`; the import package is `bench/src/wfbench/`; tests are `bench/tests/`.

## Path Conventions

- Source: `bench/src/wfbench/<module>.py`
- Unit tests: `bench/tests/unit/test_<module>.py`
- Integration tests: `bench/tests/integration/test_<name>.py`
- Fixtures: `bench/tests/fixtures/tasks/<synthetic-task>/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `uv` package skeleton so everything else is importable and testable.

- [X] T001 Create the package layout: `bench/`, `bench/src/wfbench/__init__.py`, `bench/tests/unit/`, `bench/tests/integration/`, `bench/tests/fixtures/tasks/`, with empty `__init__.py` where needed, per plan.md Project Structure.
- [X] T002 Create `bench/pyproject.toml`: project name `wfbench`, `requires-python = ">=3.11"`, no runtime dependencies, `[project.optional-dependencies] dev = ["pytest"]`, `[project.scripts] wfbench = "wfbench.cli:main"`, and a `src/` layout build config (setuptools or hatchling). Honor NFR-007 (stdlib-only runtime).
- [X] T003 [P] Configure pytest in `bench/pyproject.toml` (or `bench/pytest.ini`): testpaths, and register the `integration` marker so docker tests can be selected/deselected.
- [X] T004 [P] Add `bench/README.md` with the one-paragraph purpose and a pointer to `specs/001-workflow-bench/quickstart.md`.
- [X] T005 [P] Create `bench/src/wfbench/logging_setup.py`: a `configure_logging(verbose: bool) -> None` that sets up structured logging (level, format with timestamps) to stderr. Docstring on the public function.
- [X] T006 [P] Create `bench/src/wfbench/errors.py`: custom exception hierarchy - `WfbenchError` (base), `PreflightError`, `CorpusError`, `SelectionError`, `RuntimeBuildError`, `ConfigError`, `DockerError`, `AgentError`, `GradingError`. Each carries a clear message; no logic.
- [X] T007 [P] Create `bench/src/wfbench/config.py`: module-level constants only (no logic) - default paths (`DEFAULT_CORPUS = "tasks"`, `DEFAULT_JOBS = "jobs"`, runtime cache subdir, container mount points `/opt/wfbench`, `/tests`, `/logs`, `/work`), pinned `CLAUDE_CODE_VERSION` and `NODE_IMAGE = "node:20-bookworm-slim"`, the `DOCKER_PLATFORM = "linux/amd64"` constant, env var names (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`), and the multi-line `BENCHMARK_DIRECTIVE` neutralization text (per research.md R6). No magic strings elsewhere.

**Checkpoint**: `cd bench && uv sync` succeeds; `uv run python -c "import wfbench"` works; `uv run pytest` collects zero tests without error.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: All pure logic and docker/runtime plumbing the user stories share. Pure-logic modules here are the primary unit-test surface (SC-002, SC-006). NOTHING in a user story can run until this phase is complete.

**CRITICAL**: No user-story phase may begin until Phase 2 is done.

### Corpus and selection (pure logic)

- [X] T008 [P] Implement `bench/src/wfbench/corpus.py`: `Task` dataclass (fields per data-model.md), `parse_task(task_dir: Path) -> Task` using `tomllib` (map `[metadata]`, `[task].base_commit_hash`, `[environment]`, `[agent]`, `[verifier]`), and `discover_tasks(corpus_root: Path) -> dict[str, Task]` that includes only dirs containing `task.toml` + `instruction.md` + `tests/test.sh`. Raise `CorpusError` (naming task id + missing key) on malformed toml. Functions < 50 lines; docstrings on public functions.
- [X] T009 [P] Implement `bench/src/wfbench/selection.py`: `Selection` dataclass and `resolve_selection(...)` supporting explicit single id, explicit id list, and deterministic `(n, seed)` sample. Algorithm per research.md R9 / contracts: sort ids lexicographically, then `random.Random(seed).sample(sorted_ids, min(n, len))`. Unknown explicit id -> `SelectionError` listing the unknown id(s) (FR-027). `n > corpus` caps and logs (edge case).
- [X] T010 [P] Implement `bench/src/wfbench/prompt.py`: `WorkflowRef` dataclass + `parse_workflow_ref(raw: str) -> WorkflowRef` (normalize leading `/`, derive `slug` and `token`), and `build_prompt(ref: WorkflowRef, instruction_text: str) -> str` placing the slash token as the FIRST line, blank line, then the verbatim instruction (research.md R5).

### Results model and math (pure logic)

- [X] T011 [P] Implement `bench/src/wfbench/results.py` entities: `Outcome` enum (`passed/failed/errored/not_attempted`), `Result`, `Run`, `Comparison` dataclasses per data-model.md, with `to_dict()` serializers that emit snake_case JSON, serialize `Outcome` as its value, and NEVER include any credential value.
- [X] T012 Implement results math in `bench/src/wfbench/results.py`: `classify_outcome(...)` mapping (reward==1 -> passed; reward present !=1 -> failed; agent timeout/crash or verifier crash or missing reward -> errored; provisioning failure -> not_attempted) with a reason string; `build_run(...)` computing counts and `pass_rate = passed/attempted` (0.0 when attempted==0); `build_comparison(runs)` computing `common_attempted_ids` (intersection of attempted ids), per-workflow own + common-attempted pass rates, the per-task `matrix`, and `ranking` (FR-020/FR-021). Depends on T011.

### Preflight (pure-ish; no provisioning)

- [X] T013 [P] Implement `bench/src/wfbench/preflight.py` as THREE independent checks so callers compose only what they need: `Credential` dataclass (kind + value, value never serialized) and `resolve_credential(env: Mapping) -> Credential` accepting exactly one of `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` (raise `PreflightError` with the exact actionable message from contracts/cli.md when none - naming both forms + `claude setup-token` - or when both are set, FR-025/SC-005); `require_model(model: str | None)` raising the no-default-model error (FR-010); and `check_docker(docker)` verifying docker availability via the wrapper (raise `PreflightError` on failure, NFR-006). Provide `preflight_run(env, model, docker)` composing all three for `run`/`compare`. `prepare-runtime` calls ONLY `check_docker` (no credential/model needed), so there is no contradiction between the full and partial preflight paths.

### Docker plumbing (side-effecting; thin)

- [X] T014 Implement `bench/src/wfbench/docker_cli.py`: a thin `DockerCli` wrapper over `subprocess` that injects `--platform linux/amd64` for `run`/`build`/`pull` ONLY (NOT for `exec`/`network`/`cp`/`rm`), and sets `DOCKER_DEFAULT_PLATFORM` in the child env as defense-in-depth (research.md R2). Expose `run_detached(...)`, `exec(..., timeout=...)`, `network_disconnect(cid, net)`, `cp(...)`, `rm_force(cid)`, `image_exists(ref)`, `pull(ref)`, `available() -> bool`. Each method returns a result object (exit code, stdout, stderr); raise `DockerError` only for harness-level failures, not for expected non-zero (callers decide). Functions < 50 lines.

### Runtime and config provisioning (side-effecting)

- [X] T015 Implement `bench/src/wfbench/runtime.py`: `ensure_runtime(cache_dir: Path, docker: DockerCli, force: bool=False) -> Path` that builds the `linux/amd64` Claude runtime ONCE via the one-time `docker run ... node:20-bookworm-slim` install (research.md R3), into `<cache>/runtime` (`npm/` global + `node` binary). No-op if already present unless `force`. Raise `RuntimeBuildError` with a clear message on failure (including pinned-version unavailability, R-RISK-2). Returns the runtime dir to mount read-only.
- [X] T016 Implement `bench/src/wfbench/claude_config.py`: `materialize_config(src: Path, dest: Path) -> Path` that copies a WRITABLE, symlink-resolved copy of the owner's `~/.claude` (research.md R4): include `commands/`, `skills/` (with `.speckit/` and `scripts/`), `settings.json`, `CLAUDE.md`; resolve symlinks (follow links); EXCLUDE the verified secret/large dirs (`projects/`, `file-history/`, `history.jsonl`, `sessions/`, `session-env/`, `security/`, `telemetry/`, `shell-snapshots/`, `tasks/`, `backups/`, `plugins/`, `paste-cache/`, `*cache*`, `debug/`, `ide/`, `*.jsonl`). Raise `ConfigError` if `commands/` or `skills/` are missing. Never copy any credential.

### Per-task execution (side-effecting; the two-phase core)

- [X] T017 Implement `bench/src/wfbench/agent_runner.py`: given a `Task`, `RunConfig`, `WorkflowRef`, runtime dir, config dir, and a per-task host log dir, start the container (`docker run -d --platform linux/amd64 --cpus <task.cpus> --memory <task.memory_mb>m`, default bridge network ON, `-e <cred>`, mounts: runtime `:ro` at `/opt/wfbench`, config (writable) at container HOME `.claude`, host log dir at `/logs`, a `/work` dir for the prompt; `PATH` prepends runtime bins; cwd `/app`). The held-out `tests/` directory is NOT mounted here - it is injected at grading time only (T018), so the hidden tests physically do not exist during the agent phase (hard isolation for FR-005/FR-018). Set `HOME` for the agent exec to the container HOME whose `.claude` is the mounted config (most swe-bench images run as root, so `HOME=/root` and the config mounts at `/root/.claude`) so `claude` discovers commands/skills/settings; pre-create `/logs/verifier` and `/logs/artifacts` (research.md R8 gotcha), write the prompt file into `/work`, then `docker exec` `claude -p ... --permission-mode bypassPermissions --output-format json --model <model> --append-system-prompt <BENCHMARK_DIRECTIVE>` with a host-side timeout = `task.agent_timeout_sec`. ROBUSTNESS: feed the prompt to `claude -p` without mangling special characters (backticks/quotes/newlines in `instruction.md`) - prefer piping the prompt file to `claude -p` on stdin, or pass it via an arg whose quoting is verified safe; do NOT rely on bare `"$(cat /work/prompt.txt)"` inside a shell-interpolated exec. The slash-command token MUST remain the FIRST token of the prompt so Claude Code expands it. Capture stdout -> `agent.json`, stderr -> `agent.err`; return exit code, duration, and timeout flag. Return the container id (kept running for grading). Break into helpers (<50 lines, nesting <=3): `_build_run_args`, `_start_container`, `_prepare_logs`, `_write_prompt`, `_exec_agent`.
- [X] T018 Implement `bench/src/wfbench/grader.py`: given the running container id and the `Task`, in this order: (1) take the SAME container offline (`docker network disconnect bridge <cid>`, research.md R7); (2) inject the held-out tests into the still-running container via `DockerCli.cp(...)` (`docker cp <task.tests_dir>/. <cid>:/tests`, research.md R8) - the daemon performs this copy over the host, so it succeeds even though the container network is disconnected, and it is the FIRST moment the hidden tests exist in the container (FR-005/FR-018 hard isolation); (3) ensure `/logs/verifier` and `/logs/artifacts` exist (idempotent; `test.sh` only creates `/logs/artifacts`, so the harness MUST own `/logs/verifier` or the reward write fails with exit 5, research.md R8); (4) `docker exec bash /tests/test.sh` with a host-side timeout = `task.verifier_timeout_sec`. Capture combined output -> `verifier.log`; read `/logs/verifier/reward.txt` -> reward (1.0 pass, else non-pass; missing/garbled -> None per FR-017); copy `model.patch` out of `/logs/artifacts`; return reward, verifier exit code, grading duration, and `patch_present`. Raise nothing for honest test failure; classification happens in results.

### Orchestration

- [X] T019 Implement `bench/src/wfbench/runner.py`: `run_task(task, cfg, ref, runtime_dir, config_dir) -> Result` wiring agent_runner -> grader -> `classify_outcome` -> write `result.json` + artifacts under `tasks/<task_id>/<slug>/`, ALWAYS force-removing the container in a `finally` (resource cleanup). Handle not-attempted (image pull/start failure -> NOT_ATTEMPTED, continue) and agent timeout (-> ERRORED, still attempt grading to capture partial change). `run_workflow(cfg, ref) -> Run` iterates the selection sequentially, continue-on-failure (NFR-005/FR-026), and returns a built `Run`. Functions < 50 lines; per-task structured logging (input/action/outcome).

### Foundational tests (pure logic) - write to define behavior before wiring user stories

- [X] T020 [P] Add fixtures: `bench/tests/fixtures/tasks/` with 2-3 tiny synthetic task dirs (valid `task.toml`, `instruction.md`, `tests/test.sh`) plus one malformed task (missing key) for negative tests. Add `bench/tests/conftest.py` registering the `integration` marker and a fixture pointing at the synthetic corpus.
- [X] T021 [P] `bench/tests/unit/test_corpus.py`: parse a synthetic `task.toml` into a `Task` (all fields), discovery skips non-task dirs, malformed toml raises `CorpusError` naming the missing key.
- [X] T022 [P] `bench/tests/unit/test_selection.py`: same `(n, seed)` yields identical ids across calls (SC-002); different seeds differ; `n > corpus` caps; explicit unknown id raises `SelectionError`; explicit list preserved.
- [X] T023 [P] `bench/tests/unit/test_results.py`: `classify_outcome` for all four outcomes incl. reward edge cases (1.0/0.0/None); `build_run` counts and `pass_rate` incl. attempted==0; `build_comparison` common-attempted intersection, per-workflow rates, matrix, and ranking (FR-020/FR-021/SC-006).
- [X] T024 [P] `bench/tests/unit/test_prompt.py`: `parse_workflow_ref` normalizes `/somecode`, `somecode`; `build_prompt` puts the token on line 1 then the instruction; slug is filesystem-safe.
- [X] T025 [P] `bench/tests/unit/test_preflight.py`: exactly-one-credential logic (none -> message names both forms + setup-token; both -> error; one -> ok); `require_model` rejects None/empty; messages match contracts/cli.md (FR-010/FR-025/SC-005).
- [X] T026 [P] `bench/tests/unit/test_claude_config.py`: against a temp fake `~/.claude` (with symlinked `commands/`/`skills/` and a secret dir), `materialize_config` resolves symlinks, copies allowed entries writable, excludes secrets, and raises `ConfigError` when `commands/` is absent (C-009/R4).

**Checkpoint**: `cd bench && uv run pytest` passes (pure-logic suite green); `uv run pylint src/wfbench` and `uv run python -m py_compile src/wfbench/*.py` clean. The harness machinery exists but is not yet wired to a CLI.

---

## Phase 3: User Story 1 - Benchmark one workflow against a deterministic task subset (Priority: P1) 🎯 MVP

**Goal**: From one command, drive a single workflow over a single task or a deterministic subset inside each task's sandbox, grade with the task's verifier, and produce a recorded run with an overall pass rate and per-task outcomes.

**Independent Test**: `wfbench run --command /somecode --model <m> --task <id>` produces exactly one recorded `Result` (workflow identity, task id, captured change, verifier reward, metadata) and a `run.json`/`report.md`; and `--n-tasks N --seed S` selects the deterministic subset and reports `passed/attempted`.

### Implementation for User Story 1

- [X] T027 [US1] Implement the `run` subcommand wiring in `bench/src/wfbench/cli.py`: argparse for `run` per contracts/cli.md (`--command`, `--model`, one-of `--task/--tasks/--n-tasks`, `--seed`, path overrides, `-v`), build a `RunConfig` (generate `run_id` = UTC timestamp + short `secrets` suffix, `run_dir` under `jobs/`), and a `main()` entry. Enforce "exactly one selection flag" (exit 2). Functions < 50 lines (delegate to helpers).
- [X] T028 [US1] Wire the `run` execution path in `cli.py`/`runner.py`: preflight (credential + model + docker) BEFORE any provisioning (FR-025/SC-005) -> resolve selection -> `ensure_runtime` + `materialize_config` -> `run_workflow` -> return a `Run`. Map preflight/selection errors to exit code 2; unexpected to exit 1; success to 0 even with failing tasks (FR-026).
- [X] T029 [P] [US1] Implement single-run reporting in `bench/src/wfbench/report.py`: `write_run(run, run_dir)` emitting `run.json` (machine-readable, FR-023) and `report.md` (human-readable per-task table + counts + pass rate, FR-023), and `print_summary(run)` to stdout (pass rate + artifacts path, FR-028). Paths serialized run-relative (data-model conventions).
- [X] T030 [US1] Implement the `prepare-runtime` subcommand in `cli.py` (per contracts/cli.md): builds the runtime (or `--force` rebuild), requires docker but NOT a credential, prints the cache path, exit 0.

### Tests for User Story 1

- [X] T031 [P] [US1] `bench/tests/unit/test_cli.py`: arg parsing/dispatch for `run` and `prepare-runtime` (no docker) - one-of selection enforced, `--model` required, run-id format, exit codes for usage errors. Use monkeypatched preflight/runner so no container starts.
- [X] T032 [P] [US1] `bench/tests/unit/test_report.py`: `write_run` produces valid JSON matching the data-model shape and a Markdown report containing the pass rate and every task row; `print_summary` includes the run dir; no credential value appears anywhere in outputs (NFR-004 / security).
- [~] T033 [US1] (PARTIAL - scaffolded + auto-skips; full assertion body deferred to a credentialed env, see env note) `bench/tests/integration/test_docker_smoke.py` (marked `integration`, auto-skip when docker or credential absent): run one tiny synthetic task end-to-end through `run_task`, asserting the two-phase flow (network connected during agent, disconnected during grading), that `/tests` does NOT exist in the container during the agent phase and DOES exist (via `docker cp` injection) at grading time (hard hidden-test isolation, FR-005/FR-018), `reward.txt` consumed, `model.patch` captured, container removed. Does NOT assert mock calls.

**Checkpoint**: MVP complete - a single workflow can be benchmarked over a single task or a deterministic subset and produces inspectable artifacts and a pass rate. US1 is independently testable without US2/US3.

---

## Phase 4: User Story 2 - Compare two or more workflows over the same subset (Priority: P1)

**Goal**: Run two-plus workflows over the IDENTICAL deterministic subset with the SAME model and emit a side-by-side comparison (per-workflow pass rate + common-attempted pass rate + per-task outcome matrix), human- and machine-readable.

**Independent Test**: `wfbench compare --command /somecode --command /story-to-live --model <m> --n-tasks 1` (or a small subset) yields `comparison.json` + `comparison.md` with a pass rate per workflow over the same task ids and a per-task matrix - verifiable even at subset size 1.

### Implementation for User Story 2

- [X] T034 [US2] Implement the `compare` subcommand in `bench/src/wfbench/cli.py` (per contracts/cli.md): repeatable `--command` (require >=2, else exit 2); identical other flags as `run`; build ONE `RunConfig` whose single resolved `Selection` and `--model` apply to every workflow (NFR-002). Reuse the `run` preflight path.
- [X] T035 [US2] Implement compare orchestration in `bench/src/wfbench/runner.py`: `run_comparison(cfg) -> Comparison` that runs `run_workflow` for each `WorkflowRef` over the identical selection (sequential, continue-on-failure), writes a per-workflow `run-<slug>.json`/`report-<slug>.md`, then calls `build_comparison(runs)`.
- [X] T036 [P] [US2] Implement comparison reporting in `bench/src/wfbench/report.py`: `write_comparison(comparison, run_dir)` emitting `comparison.json` (FR-021/FR-023) and `comparison.md` with the per-task outcome matrix, each workflow's own + common-attempted pass rate, and the ranking (FR-022/NFR-002); extend `print_summary` for the multi-workflow case (FR-028).

### Tests for User Story 2

- [X] T037 [P] [US2] Extend `bench/tests/unit/test_cli.py`: `compare` requires >=2 `--command`; the same selection/model object is shared across workflows (assert on the constructed `RunConfig`, not on mocks).
- [X] T038 [P] [US2] Extend `bench/tests/unit/test_results.py` and add `test_report.py` cases: comparison with a partially-failing workflow still ranks over the common-attempted set; `comparison.md` matrix shows each workflow's outcome per task; common-attempted empty is reported as not-comparable (FR-021/FR-022 edge case).

**Checkpoint**: Both US1 and US2 work independently. Comparison is fair (identical subset, same model, common-attempted ranking).

---

## Phase 5: User Story 3 - Inspect and trust a single task result (Priority: P2)

**Goal**: Guarantee that every attempted task's recorded artifacts are complete and auditable: captured code change, verifier reward, both logs, exit status, duration, model used, and any token/cost figures - sufficient to audit without re-running.

**Independent Test**: After a single-task run, the task's artifact dir contains `model.patch`, `reward.txt`, `agent.json`, `agent.err`, `verifier.log`, and a `result.json` whose fields include outcome, reward, duration, model, exit codes, tokens, cost, and a reason when non-pass; an errored-before-edit run records a non-pass with an empty captured change rather than aborting the batch.

### Implementation for User Story 3

- [ ] T039 [US3] Ensure full token/cost capture in `bench/src/wfbench/agent_runner.py` + `results.py`: parse `agent.json` for token usage and cost (tolerant of missing fields -> None) and populate `Result.tokens` / `Result.cost_usd` / `Result.agent_exit_code` / `Result.duration_sec` (FR-019/SC-004). Add a helper `parse_agent_usage(agent_json_text) -> tuple[dict|None, float|None]` (pure, unit-testable).
- [ ] T040 [US3] Harden the empty/partial-change path in `bench/src/wfbench/runner.py`: when the agent errors before editing (no usable change), still run grading, record a non-pass with `patch_present=False` and a `reason`, and never abort the batch (US3 acceptance #3 / FR-026). Ensure `result.json` always written even on errored/not-attempted.

### Tests for User Story 3

- [ ] T041 [P] [US3] `bench/tests/unit/` test for `parse_agent_usage`: extracts tokens/cost from a representative `agent.json` and returns None gracefully when fields are absent (no exception).
- [ ] T042 [P] [US3] Extend `bench/tests/unit/test_results.py`: a `Result` for an errored-before-edit attempt serializes with `outcome=errored`/`failed` as appropriate, `patch_present=False`, a non-null `reason`, and still appears in the run tally (SC-004/SC-006).

**Checkpoint**: Every recorded outcome is traceable to its captured change, reward, and logs (NFR-004). All three user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final hardening and validation across stories.

- [ ] T043 [P] Verify no-em-dash / no-attribution and docstring coverage across `bench/src/wfbench/*.py`; ensure every public function has a docstring and no function exceeds 50 lines / nesting 3 (owner standards).
- [ ] T044 [P] Add a structured-logging pass: confirm every user-facing action logs input received / action taken / outcome (success/failure with error detail) in `runner.py`, `agent_runner.py`, `grader.py`, `cli.py` (software-engineering skill requirement / Observability).
- [ ] T045 Confirm the credential value never reaches any artifact or log: grep-style unit assertion + manual review of `to_dict()` serializers and logging calls (security). Pass the credential to `docker run` as a name-only `-e ANTHROPIC_API_KEY` / `-e CLAUDE_CODE_OAUTH_TOKEN` (value inherited from the harness env via `DockerCli`'s child-process env), NOT as `-e NAME=<value>`, so the secret never appears in any argv that the docker wrapper or structured logging (T044) might record; if any argv is ever logged, redact credential env values.
- [ ] T046 Run the full gate from `bench/`: `uv run pytest`, `uv run pylint src/wfbench`, `uv run python -m py_compile src/wfbench/*.py`; fix all findings.
- [ ] T047 Execute the `quickstart.md` walkthrough end-to-end against a 1-task subset with a real credential (when available) to validate SC-001/SC-005/SC-007/SC-008/SC-009; record any deviations.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; BLOCKS all user stories.
- **User Story 1 (Phase 3, P1)**: depends on Foundational. MVP.
- **User Story 2 (Phase 4, P1)**: depends on Foundational; reuses US1's `RunConfig`/preflight/`run_workflow` and `report.py` (so practically sequenced after US1, though logically independent).
- **User Story 3 (Phase 5, P2)**: depends on Foundational; refines `agent_runner`/`runner`/`results` artifact completeness (sequenced after US1 since it hardens US1's per-task path).
- **Polish (Phase 6)**: depends on all desired user stories.

### Within Each Phase

- Pure-logic modules (corpus, selection, prompt, results, preflight, claude_config) are independent of each other -> heavily parallelizable ([P]).
- `docker_cli` (T014) precedes `runtime` (T015), `agent_runner` (T017), `grader` (T018), which precede `runner` (T019).
- `results` entities (T011) precede results math (T012).
- Tests for a module come after that module exists (foundational tests T021-T026 after T008-T016).
- Within a user story: implementation before that story's tests where the test imports the new symbol; `[P]` tests target different files.

### Critical Path

T001-T002 -> T008-T013 (pure logic) and T014 -> T015/T016/T017/T018 -> T019 -> T027/T028 (US1 run path) -> T034/T035 (US2 compare) -> T039/T040 (US3 hardening) -> T046/T047 (gate + quickstart).

---

## Parallel Opportunities

- Setup: T003, T004, T005, T006, T007 in parallel after T001/T002.
- Foundational pure logic: T008, T009, T010, T011, T013 in parallel; then T012 after T011.
- Foundational tests: T021-T026 in parallel once their modules exist.
- US1: T029 ([P]) alongside T027/T028; tests T031, T032 ([P]).
- US2: T036 ([P]) alongside T034/T035; tests T037, T038 ([P]).
- US3: tests T041, T042 ([P]).
- Polish: T043, T044 ([P]).

### Parallel Example: Foundational pure logic

```bash
Task: "Implement corpus.py (Task dataclass + discovery) in bench/src/wfbench/corpus.py"
Task: "Implement selection.py (deterministic subset) in bench/src/wfbench/selection.py"
Task: "Implement prompt.py (WorkflowRef + build_prompt) in bench/src/wfbench/prompt.py"
Task: "Implement results.py entities in bench/src/wfbench/results.py"
Task: "Implement preflight.py (credential + model) in bench/src/wfbench/preflight.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) - the shared harness, fully unit-tested.
2. Complete Phase 3 (US1) - the `run` path.
3. STOP and VALIDATE: benchmark one workflow over one task and a deterministic subset; inspect `jobs/<run-id>/`.

### Incremental delivery

- Add US2 (`compare`) for head-to-head pass rates over the identical subset.
- Add US3 hardening for full auditability of every attempt.
- Finish with Polish (gate + quickstart validation).

### Requirements coverage map (FR -> tasks)

- FR-001 corpus read-only: T008 (no writes); runtime/config mounts `:ro` (T017); tests are copied INTO the container via `docker cp` from the read-only corpus dir (T018) and never written back, so the corpus is never mutated.
- FR-002/003/004 selection: T009, T022.
- FR-005 instruction as input, hide hidden tests: T010 (prompt from instruction), T017 (tests NOT mounted during the agent phase), T018 (tests injected via `docker cp` only at grading time - hard isolation, not a directive).
- FR-006/007/008 workflow under test, headless, symlink-resolved config: T010, T017, T016.
- FR-009/C-010 neutralization via append-system-prompt: T007 (directive), T017.
- FR-010 model required, recorded: T013, T027, T011.
- FR-011 task environment + limits: T017.
- FR-012 capture change vs base: T018 (model.patch).
- FR-013/C-008 two-phase network: T017 (online), T018 (offline).
- FR-014 timeouts: T017 (agent), T018 (verifier).
- FR-015 sequential: T019.
- FR-016/017/018 grading + reward + hidden tests: T018 (verifier unchanged + reward parse + tests injected only at grading time so the agent never saw them), T012, T023.
- FR-019 record everything: T019, T029, T039.
- FR-020 outcome classification + counts + pass rate: T012, T023.
- FR-021/022/023 comparison + matrix + dual format: T035, T036, T012.
- FR-024 gitignored jobs + unique run id: T027 (run id), T029/T036 (writes under jobs).
- FR-025 credential validated up front: T013, T028.
- FR-026 continue-on-failure: T019, T040.
- FR-027 unknown task id: T009, T022.
- FR-028 end summary: T029, T036.

### Non-functional coverage map (NFR -> tasks)

- NFR-001 reproducibility (deterministic selection): T009, T022 (same seed -> identical ids).
- NFR-002 fair comparison (identical subset, same model, common-attempted ranking): T034, T035, T012, T037.
- NFR-003 isolation/safety (container per task, host untouched): T017 (per-task container, force-removed in T019).
- NFR-004 auditability (every outcome traceable to change/reward/logs): T019, T029, T039, T032.
- NFR-005 resilience (one failure never aborts the batch): T019, T040.
- NFR-006 clear early preconditions: T013, T028.
- NFR-007 lean footprint (stdlib-only runtime, one dev dep): T002.

### Constraint coverage notes (C-### -> tasks)

- C-004 corpus/verifiers read-only: T008; T017 mounts runtime/config `:ro`; T018 copies the verifier into the container via `docker cp` (read-only source, one-way copy) and never modifies `tasks/`.
- C-007 cross-arch runtime: T015 (build-once linux/amd64 runtime).
- C-008 two-phase network: T017 (agent online) + T018 (grade offline).
- C-009 symlinked workflow files resolved: T016, T026.
- C-010 non-invasive neutralization (no owner-file edits): T007 (directive constant) + T017 (`--append-system-prompt`).
- C-011 gitignored outputs: T027/T029/T036 (all writes under `jobs/`).
