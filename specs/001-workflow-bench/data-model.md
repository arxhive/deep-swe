# Phase 1 Data Model: Workflow Bench

This document defines the in-memory entities (Python dataclasses/enums) and the persisted JSON shapes. Field names map directly to spec entities (Task, Workflow under test, Task subset, Task attempt/result, Run, Comparison) and to FR-019/FR-020/FR-021. All dataclasses are plain `@dataclass` (stdlib); enums are `enum.Enum`. Persisted JSON keys use snake_case and mirror the dataclass fields.

## Enums

### Outcome
The single outcome state for one workflow on one task (FR-020).

| Value | Meaning |
|-------|---------|
| `passed` | Verifier reward == 1 (hidden tests succeeded on the workflow's change). |
| `failed` | Workflow ran and was graded; verifier produced a reward != 1. |
| `errored` | Workflow run failed or timed out, verifier crashed, or no reward was produced. |
| `not_attempted` | Task could not be provisioned (image unavailable, container failed to start). |

`attempted` is derived: `passed + failed + errored`. `not_attempted` is excluded from `attempted`.

### CredentialKind
| Value | Env var |
|-------|---------|
| `api_key` | `ANTHROPIC_API_KEY` |
| `oauth_token` | `CLAUDE_CODE_OAUTH_TOKEN` |

## Core entities

### Task (corpus.py)
A read-only benchmark item discovered under `tasks/<task_id>/` and parsed from `task.toml`. Tasks are never mutated (C-004/FR-001).

| Field | Type | Source in task.toml | Notes |
|-------|------|---------------------|-------|
| `task_id` | `str` | `[metadata].task_id` | Stable id; also the directory name. |
| `language` | `str` | `[metadata].language` | go / python / typescript / javascript / rust. |
| `display_title` | `str` | `[metadata].display_title` | For reports. |
| `base_commit` | `str` | `[task].base_commit_hash` | Verifier resets to this; must exist in the image repo. |
| `docker_image` | `str` | `[environment].docker_image` | Prebuilt `linux/amd64` image ref. |
| `cpus` | `int` | `[environment].cpus` | Resource limit (verified 2 across corpus). |
| `memory_mb` | `int` | `[environment].memory_mb` | Resource limit (verified 8192). |
| `allow_internet` | `bool` | `[environment].allow_internet` | Verified false; grading is offline regardless. |
| `agent_timeout_sec` | `float` | `[agent].timeout_sec` | Host-side budget for the agent phase. |
| `verifier_timeout_sec` | `float` | `[verifier].timeout_sec` | Host-side budget for grading. |
| `build_timeout_sec` | `float` | `[environment].build_timeout_sec` | Parsed and recorded but UNUSED in v1: the harness uses the prebuilt `docker_image` only. Building from the `environment/Dockerfile` fallback is out of scope for v1; an unobtainable image is classified `not_attempted` (spec edge case "Prebuilt task image unavailable"). Captured now so a future fallback needs no model change. |
| `task_dir` | `Path` | n/a | Absolute path to `tasks/<task_id>/`. |
| `instruction_path` | `Path` | n/a | `task_dir/instruction.md` (the agent prompt, FR-005). |
| `tests_dir` | `Path` | n/a | `task_dir/tests/` (NOT mounted; injected into the container via `docker cp` only at grading time, so the agent never sees it - FR-005/FR-018). |

Validation rules:
- Directory must contain `task.toml`, `instruction.md`, and `tests/test.sh`; otherwise the task is skipped from discovery with a logged warning (it is not a valid corpus task).
- Missing required toml keys raise a `CorpusError` naming the task id and the missing key (fail fast).

### WorkflowRef (corpus.py or prompt.py)
The agent under test (spec "Workflow under test"). Identified by the name the owner uses locally.

| Field | Type | Notes |
|-------|------|-------|
| `raw` | `str` | As passed on the CLI, e.g. `/somecode`, `somecode`, or `story-to-live`. |
| `token` | `str` | Normalized leading prompt token, always starts with `/` (e.g. `/somecode`). |
| `slug` | `str` | Filesystem-safe label for artifact dirs (e.g. `somecode`). |

Construction: strip a leading `/`, derive `slug`; `token = "/" + slug`. The token is placed as the first line of the prompt (R5).

### Selection (selection.py)
A reproducible set of task ids (spec "Task subset"). Produced from one of:
- explicit `--task <id>` (single) or `--tasks <id,...>` (list), or
- `--n-tasks <N> --seed <S>` deterministic sample.

| Field | Type | Notes |
|-------|------|-------|
| `task_ids` | `list[str]` | Resolved, ordered ids (sorted canonical order). |
| `mode` | `str` | `"explicit"` or `"sampled"`. |
| `n` | `int | None` | Requested count when sampled. |
| `seed` | `int | None` | Seed when sampled. |

Validation rules:
- Explicit unknown id => `SelectionError` listing the unknown id(s) (FR-027); never silently substituted.
- Sampled `N > corpus size` => capped to corpus size (edge case), logged.

### RunConfig (cli.py -> runner.py)
Immutable configuration for one invocation.

| Field | Type | Notes |
|-------|------|-------|
| `workflows` | `list[WorkflowRef]` | One for `run`, two+ for `compare`. |
| `selection` | `Selection` | Resolved subset (identical across workflows in a compare). |
| `model` | `str` | Required (FR-010); no default. |
| `credential` | `Credential` | Validated kind + value (value not serialized). |
| `corpus_root` | `Path` | `tasks/`. |
| `jobs_root` | `Path` | `jobs/`. |
| `runtime_cache` | `Path` | Default `jobs/.runtime-cache/`. |
| `run_id` | `str` | `<UTC timestamp>-<short suffix>`. |
| `run_dir` | `Path` | `jobs/<run_id>/`. |

`Credential.value` is held only in memory and passed to docker via env; it is NEVER written to any artifact.

### Result (results.py)
The outcome of one workflow on one task (spec "Task attempt / result", FR-019). Serialized to `result.json`.

| Field | Type | FR | Notes |
|-------|------|----|-------|
| `workflow_slug` | `str` | FR-019 | Workflow identity. |
| `workflow_token` | `str` | FR-019 | e.g. `/somecode`. |
| `task_id` | `str` | FR-019 | |
| `outcome` | `Outcome` | FR-020 | Serialized as its string value. |
| `reward` | `float | None` | FR-016/017 | Raw verifier reward; None if absent. |
| `model` | `str` | FR-019 | Model used for this attempt. |
| `duration_sec` | `float` | FR-019 | Wall-clock for the agent phase. |
| `grading_duration_sec` | `float | None` | FR-019 | Wall-clock for grading. |
| `agent_exit_code` | `int | None` | FR-019 | `claude -p` exit status (None if killed by timeout). |
| `verifier_exit_code` | `int | None` | FR-019 | `test.sh` exit status. |
| `tokens` | `dict | None` | FR-019 | Token usage parsed from `agent.json` (input/output/total when present). |
| `cost_usd` | `float | None` | FR-019 | Cost parsed from `agent.json` if present. |
| `reason` | `str | None` | FR-020 | Failure/timeout/not-attempted reason. |
| `patch_present` | `bool` | US3 | Whether a non-empty `model.patch` was captured. |
| `artifacts_dir` | `str` | FR-024 | Relative path under the run dir. |

Artifact files written alongside `result.json` (FR-019, NFR-004): `model.patch`, `agent.json`, `agent.err`, `verifier.log`, `reward.txt`.

### Run (results.py)
One workflow over the subset (spec "Run"). Serialized to `run.json`.

| Field | Type | FR | Notes |
|-------|------|----|-------|
| `run_id` | `str` | FR-024 | |
| `workflow_slug` | `str` | | |
| `workflow_token` | `str` | | |
| `model` | `str` | FR-010 | |
| `selection` | `dict` | FR-004 | mode/n/seed/task_ids for reproducibility. |
| `results` | `list[Result]` | FR-019 | One per selected task. |
| `counts` | `dict` | FR-020 | `selected`, `attempted`, `passed`, `failed`, `errored`, `not_attempted`. |
| `pass_rate` | `float` | FR-020 | `passed / attempted` (0.0 if attempted == 0). |
| `started_at` / `finished_at` | `str` | | ISO timestamps. |

Derived properties (pure functions, primary unit-test targets):
- `attempted = passed + failed + errored`
- `pass_rate = passed / attempted if attempted else 0.0`

### Comparison (results.py)
Two-plus workflows over one identical subset (spec "Comparison"). Serialized to `comparison.json`.

| Field | Type | FR | Notes |
|-------|------|----|-------|
| `run_id` | `str` | | |
| `model` | `str` | FR-010 | Same model for all workflows (NFR-002). |
| `selection` | `dict` | FR-004 | Identical subset across workflows. |
| `runs` | `list[Run]` | FR-021 | One Run per workflow. |
| `common_attempted_ids` | `list[str]` | FR-021 | Intersection of each Run's attempted ids. |
| `per_workflow` | `list[dict]` | FR-021 | For each: own pass_rate, common_attempted pass_rate, counts. |
| `matrix` | `list[dict]` | FR-022 | Per task: `{task_id, outcomes: {slug: outcome}}`. |
| `ranking` | `list[str]` | FR-021/NFR-002 | Workflow slugs ordered by common-attempted pass rate (desc). |

Derivation rules:
- `common_attempted_ids` = set-intersection over `runs[i]` of task ids whose outcome is in {passed, failed, errored}.
- A workflow's common-attempted pass rate = (passed within common_attempted_ids) / len(common_attempted_ids); 0.0 if the common set is empty (logged as not-comparable).
- `ranking` uses common-attempted pass rate; ties broken by own pass_rate then slug.

## Persisted JSON conventions
- All Path fields are serialized as repo-relative or run-relative POSIX strings, never absolute host paths (portability of artifacts).
- `Outcome` serializes to its `.value` string.
- `Credential.value` is never serialized.
- Floats for pass rates are stored raw (not pre-rounded); Markdown reports format to a fixed precision.

## Entity relationships

```text
RunConfig 1───* WorkflowRef
RunConfig 1───1 Selection ───* Task (by id, read-only from corpus)
Run       1───* Result (one per selected Task)
Comparison 1──* Run (one per WorkflowRef)  ── derives ─> matrix, common_attempted, ranking
Result    1───1 Task   (task_id)
Result    1───1 WorkflowRef (workflow_slug/token)
```
