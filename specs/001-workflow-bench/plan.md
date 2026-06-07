# Implementation Plan: Workflow Bench

**Branch**: `feat/workflow-bench` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-workflow-bench/spec.md`

## Summary

Workflow Bench is a lean standalone Python CLI (`wfbench`) that benchmarks the owner's personal Claude Code workflows (slash-commands and skills such as `/somecode` or `/story-to-live`) against the deep-swe task corpus under `tasks/`, grading each produced code change with the task's own held-out verifier and reporting pass rate. It can run one workflow over a deterministic task subset and compare two-plus workflows over the identical subset.

Technical approach: a single `uv`-managed Python package in a new top-level `bench/` directory, standard-library only at runtime, shelling out to the `docker` CLI. A Claude Code runtime is built once for `linux/amd64` and cached, then mounted read-only into each task's own container. Each task runs in two phases inside one container: an online agent phase that drives the workflow headlessly (`claude -p ... --append-system-prompt <BENCHMARK_DIRECTIVE>`), then an offline grading phase that runs the task's `tests/test.sh`. Outcomes are classified (passed/failed/errored/not-attempted) and written under the gitignored `jobs/<run-id>/` tree as both machine-readable JSON and human-readable Markdown.

## Technical Context

**Language/Version**: Python 3.11+ (requires `tomllib` from the stdlib, present since 3.11), managed by `uv`.

**Primary Dependencies**: Standard library only at runtime - `argparse` (CLI), `tomllib` (parse `task.toml`), `subprocess` (drive the `docker` CLI and `claude`), `json`, `dataclasses`, `enum`, `pathlib`, `shutil` (config copy with symlink resolution), `random` (seeded subset selection), `secrets` (run-id suffix), `datetime` (run-id timestamp), `logging` (structured progress). Dev dependency: `pytest`. No third-party runtime dependencies (NFR-007).

**Storage**: Filesystem only. Run artifacts under the repository-root `jobs/` directory, which `.gitignore` already excludes (C-011, FR-024). A cached Claude runtime under a stable cache dir (default `jobs/.runtime-cache/`, also inside the gitignored tree, override via `--runtime-cache`).

**Testing**: `pytest`. Unit tests for pure logic (parsing, selection, reward classification, pass-rate math, comparison matrix, prompt and directive construction, preflight validation, CLI arg parsing). Docker- and network-dependent paths gated behind a `pytest` marker (`integration`) that auto-skips when docker or a credential is absent.

**Target Platform**: Host is an arm64 macOS developer machine with Docker Desktop; task images are `linux/amd64`. The harness runs on the host (Python); the workflow under test runs inside `linux/amd64` containers.

**Project Type**: Single-project CLI tool (standalone harness).

**Performance Goals**: Not throughput-bound. Sequential task execution is acceptable (FR-015). The only deliberate performance measure is building the Claude runtime once and reusing it across all 113 tasks rather than per task.

**Constraints**: Every `docker run`/`build`/`pull` invocation MUST pass `--platform linux/amd64` explicitly (the host zsh `docker` shell function that injects the flag is bypassed by `subprocess`, which calls `/usr/local/bin/docker` directly). Grading MUST run with no network (C-008, SC-008). The held-out tests MUST NOT exist in the container during the agent phase: `tests/` is never mounted at run; it is injected with `docker cp` only after the agent phase completes and the network is disconnected, immediately before grading (hard isolation for FR-005/FR-018, integrity for SC-007/SC-008). A directive forbidding test reads is defense-in-depth only and is NOT the isolation mechanism. The owner's workflow files MUST NOT be edited; neutralization is via `--append-system-prompt` only (C-010, FR-009). The corpus and verifiers are strictly read-only (C-004, FR-001). A credential and a model MUST be validated before any container is provisioned (FR-010, FR-025, SC-005).

**Scale/Scope**: 113 tasks across Go (34), Python (34), TypeScript (35), JavaScript (5), Rust (5). All tasks share `cpus = 2`, `memory_mb = 8192`, `allow_internet = false`. Per-task `agent.timeout_sec` and `verifier.timeout_sec` come from each `task.toml`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No project constitution is defined (`.specify/memory/constitution.md` is absent), so there are no explicit project gates to evaluate. The plan instead self-checks against the owner's engineering standards and the spec's constraints/NFRs:

- Lean footprint (NFR-007): stdlib-only runtime, single package, one dev dependency. PASS.
- Read-only corpus (C-004): no module writes under `tasks/`; all mounts of corpus content are `:ro`. PASS.
- Non-invasive neutralization (C-010): owner workflow files are copied read-only and behavior is steered only via `--append-system-prompt`. PASS.
- Fail-fast preconditions (NFR-006): preflight validates credential, model, and docker before provisioning. PASS.
- Functions < 50 lines, nesting <= 3, meaningful errors, docstrings on public functions: enforced by the module decomposition below and reflected in tasks.md. PASS (design-level).

**Result**: PASS (no constitution gates; standards-aligned). Re-checked after Phase 1: still PASS (design introduces no third-party runtime deps, no corpus writes, no owner-file edits).

## Project Structure

### Documentation (this feature)

```text
specs/001-workflow-bench/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli.md           # CLI command + output-artifact contracts
├── checklists/          # (pre-existing)
└── tasks.md             # Phase 2 output (/speckit-tasks - NOT created here)
```

### Source Code (repository root)

```text
bench/
├── pyproject.toml                 # uv project; console_scripts: wfbench = wfbench.cli:main
├── README.md                      # short usage pointer (optional)
├── src/
│   └── wfbench/
│       ├── __init__.py
│       ├── cli.py                 # argparse subcommands: run, compare, prepare-runtime
│       ├── config.py              # constants, mount paths, BENCHMARK_DIRECTIVE text, defaults
│       ├── errors.py              # custom exception hierarchy (PreflightError, CorpusError, ...)
│       ├── corpus.py              # Task dataclass, discovery, task.toml parsing
│       ├── selection.py           # deterministic (n, seed) selection + explicit-id resolution
│       ├── preflight.py           # credential + model + docker validation (before provisioning)
│       ├── docker_cli.py          # thin subprocess wrapper; injects --platform linux/amd64
│       ├── runtime.py             # build-once cached linux/amd64 Claude runtime; reuse mount
│       ├── claude_config.py       # writable resolved copy of owner ~/.claude (symlink-safe)
│       ├── prompt.py              # build per-task prompt (slash-command + instruction.md)
│       ├── agent_runner.py        # per-task container lifecycle + online agent exec phase
│       ├── grader.py              # offline verifier phase; reward.txt -> reward value
│       ├── results.py             # Outcome enum, Result/Run/Comparison dataclasses + math
│       ├── runner.py              # orchestration: per-task pipeline + batch continue-on-failure
│       ├── report.py              # run.json/report.md + comparison.json/comparison.md
│       └── logging_setup.py       # structured logging configuration
└── tests/
    ├── conftest.py                # markers (integration), fixtures (tmp corpus, fake docker)
    ├── fixtures/
    │   └── tasks/                 # tiny synthetic task dirs for parsing/selection tests
    ├── unit/
    │   ├── test_corpus.py
    │   ├── test_selection.py
    │   ├── test_preflight.py
    │   ├── test_prompt.py
    │   ├── test_results.py
    │   ├── test_report.py
    │   ├── test_claude_config.py  # symlink-resolution + exclusion logic (uses tmp dirs)
    │   └── test_cli.py            # arg parsing / dispatch (no docker)
    └── integration/
        └── test_docker_smoke.py   # gated: tiny synthetic task end-to-end when docker+cred present
```

Run outputs (gitignored, NOT in the source tree):

```text
jobs/
├── .runtime-cache/
│   └── runtime/                   # node + npm-global claude-code (linux/amd64), built once
└── <run-id>/                      # run-id = <UTC-timestamp>-<short-random>
    ├── run.json                   # machine-readable single run (FR-023)
    ├── report.md                  # human-readable single run (FR-028)
    ├── comparison.json            # only for `compare` (FR-021/FR-023)
    ├── comparison.md              # only for `compare` (FR-022)
    └── tasks/
        └── <task-id>/
            └── <workflow-slug>/
                ├── result.json    # per-attempt structured record (FR-019)
                ├── model.patch    # captured code change (test.sh -> /logs/artifacts -> copied out)
                ├── agent.json     # claude -p stdout JSON (tokens/cost) (FR-019)
                ├── agent.err      # claude -p stderr
                ├── verifier.log   # test.sh combined output
                └── reward.txt     # raw verifier reward (FR-016/FR-017)
```

The per-task path always nests one workflow level (`tasks/<task-id>/<workflow-slug>/...`) so that single runs and comparisons share one layout and multiple workflows on the same task never collide.

**Structure Decision**: Single-project CLI. The package lives under `bench/` (allowed by C-003) using a `src/` layout so the import package `wfbench` is unambiguous and test discovery stays clean. The CLI is exposed as a console script `wfbench` and run via `uv run wfbench ...` from the `bench/` directory. No web/mobile structure applies.

## Complexity Tracking

No constitution violations to justify. The design intentionally avoids added complexity: no plugin system, no parallelism, no abstraction layer over docker beyond a thin subprocess wrapper, no third-party runtime deps.

## Architecture and Data Flow

High-level flow for a single workflow over a subset:

1. `cli.py` parses the subcommand and flags, configures logging, and constructs a run config.
2. `preflight.py` validates exactly one credential (`ANTHROPIC_API_KEY` xor `CLAUDE_CODE_OAUTH_TOKEN`), that `--model` is set, and that `docker` is available - BEFORE any provisioning (FR-010/FR-025).
3. `corpus.py` discovers tasks under `tasks/`; `selection.py` resolves the subset (explicit ids, or deterministic `(n, seed)` sample). Unknown explicit ids error clearly (FR-027).
4. `runtime.py` ensures the cached `linux/amd64` Claude runtime exists (builds once if missing); `claude_config.py` materializes a per-run writable resolved copy of the owner's `~/.claude`.
5. `runner.py` iterates tasks sequentially (continue-on-failure, NFR-005). For each task:
   a. `agent_runner.py` starts the task container (`docker run -d --platform linux/amd64 --cpus --memory`, default bridge network ON, auth env, mounts: runtime `:ro`, the writable config copy at the container HOME `.claude`, a per-task host log dir at `/logs`, and a `/work` dir for the prompt). The held-out `tests/` directory is deliberately NOT mounted during the agent phase, so the hidden tests physically do not exist in the container while the workflow runs (hard isolation for FR-005/FR-018). The harness writes the prompt file, then `docker exec` runs `claude -p` headlessly with `HOME` set to the mounted config so `claude` discovers `.claude`, with a host-side timeout (`agent.timeout_sec`). stdout JSON -> `agent.json`, stderr -> `agent.err`.
   b. `grader.py` grades the SAME still-running container in this order: (1) disconnect the network (`docker network disconnect bridge <cid>`) so grading is offline; (2) inject the held-out tests into the running container with `docker cp <task_dir>/tests/. <cid>:/tests` (the daemon performs the copy over the host, so it works even with the container network disconnected); (3) pre-create `/logs/verifier` and `/logs/artifacts` (the harness owns `/logs/verifier`; `test.sh` only creates `/logs/artifacts`); (4) `docker exec bash /tests/test.sh` with a host-side timeout (`verifier.timeout_sec`). `test.sh` writes `model.patch` to `/logs/artifacts` and the reward to `/logs/verifier/reward.txt`; the harness reads the reward and copies artifacts out. Because the working tree stays in place across both phases, `model.patch` still captures the agent's exact change.
   c. `results.py` classifies the outcome and builds a `Result`.
   d. The container is force-removed.
6. `results.py` aggregates the `Run` (pass rate = passed/attempted, plus selected/not-attempted reconciliation, FR-020).
7. `report.py` writes `run.json` + `report.md` and prints an at-a-glance summary (FR-028).

For `compare`, `runner.py` runs every workflow over the identical resolved subset, then `results.py` builds a `Comparison` with per-workflow own pass rate and a common-attempted pass rate over the intersection (FR-021), and `report.py` emits `comparison.json` + `comparison.md` with a per-task outcome matrix (FR-022).

Key cross-cutting decisions are recorded in [research.md](./research.md); entity shapes in [data-model.md](./data-model.md); command/output contracts in [contracts/cli.md](./contracts/cli.md); a runnable walkthrough in [quickstart.md](./quickstart.md).
