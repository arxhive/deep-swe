# CLI Contract: Workflow Bench (`wfbench`)

The tool's external interface is its command line plus the artifact files it writes. This document is the authoritative contract referenced by tasks.md and the integration tests. Invocation: `uv run wfbench <command> [options]` from the `bench/` directory (console entry point `wfbench` -> `wfbench.cli:main`).

## Global behavior

- Exit code `0` on success (run/comparison completed, even if some tasks failed - a failing task is a recorded non-pass, not a tool error, per NFR-005/FR-026).
- Exit code `2` on a usage/precondition error (missing credential, missing model, unknown task id, docker unavailable, no tasks selected). These abort BEFORE provisioning (FR-025/SC-005).
- Exit code `1` on an unexpected internal error.
- All progress is logged in structured form (input received, action taken, outcome) to stderr; the final at-a-glance summary is printed to stdout (FR-028).
- A credential is read from the environment (`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`); it is never a CLI flag and never written to artifacts.

## Command: `run` (User Story 1)

Benchmark exactly one workflow over a selected subset.

```text
wfbench run --command <workflow> --model <model> (--task <id> | --tasks <id,...> | --n-tasks <N> [--seed <S>]) [options]
```

| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--command <workflow>` | yes | - | The workflow under test; accepts `/somecode`, `somecode`, or a skill name. |
| `--model <model>` | yes | none (FR-010) | Model id passed to `claude --model`. Tool refuses to start without it. |
| `--task <id>` | one-of | - | Single task id (FR-002). |
| `--tasks <id,...>` | one-of | - | Comma-separated explicit ids (FR-003). |
| `--n-tasks <N>` | one-of | - | Deterministic sample of size N (FR-004). |
| `--seed <S>` | no | `0` | Seed for `--n-tasks` (NFR-001/SC-002). |
| `--corpus <path>` | no | `./tasks` | Corpus root. |
| `--jobs-dir <path>` | no | `./jobs` | Gitignored output root (C-011). |
| `--runtime-cache <path>` | no | `<jobs>/.runtime-cache` | Cached Claude runtime location. |
| `--claude-config <path>` | no | `~/.claude` | Owner config to resolve+copy (C-009). |
| `-v/--verbose` | no | off | Debug logging. |

Exactly one of `--task`/`--tasks`/`--n-tasks` MUST be provided (else exit 2).

Behavior: preflight (credential + model + docker) -> resolve selection -> ensure runtime + config -> run each task (agent online, grade offline) continue-on-failure -> write `run.json` + `report.md` -> print summary.

## Command: `compare` (User Story 2)

Benchmark two or more workflows over the identical subset.

```text
wfbench compare --command <wf1> --command <wf2> [--command <wf3> ...] --model <model> (--task | --tasks | --n-tasks [--seed]) [options]
```

- `--command` is repeatable and MUST appear at least twice (else exit 2).
- All other flags are identical to `run`.
- The SAME resolved subset and the SAME `--model` apply to every workflow (NFR-002).
- Behavior: same per-task pipeline as `run`, executed for every workflow over the identical task ids, then emit `comparison.json` + `comparison.md` (per-task outcome matrix + per-workflow own and common-attempted pass rates + ranking) and a `run.json`/`report.md` per workflow under the same run dir.

## Command: `prepare-runtime`

Build (or rebuild) the cached `linux/amd64` Claude runtime without running any task.

```text
wfbench prepare-runtime [--runtime-cache <path>] [--force]
```

- Builds the runtime if missing (or `--force` to rebuild), prints the cache path, exits 0.
- `run`/`compare` build the runtime lazily on first use, so this command is optional (convenience / pre-warming).
- Does NOT require a credential (no model interaction), but DOES require docker.

## Output artifacts contract

Written under `<jobs>/<run-id>/` (run-id = `<UTC timestamp>-<short suffix>`, FR-024). Nothing from a prior run is overwritten (each run-id is unique).

Single `run`:
```text
<run-id>/run.json                                   # machine-readable (FR-023), schema per data-model Run
<run-id>/report.md                                  # human-readable (FR-023/FR-028)
<run-id>/tasks/<task-id>/<workflow-slug>/result.json
<run-id>/tasks/<task-id>/<workflow-slug>/model.patch     # captured change (FR-019); may be empty
<run-id>/tasks/<task-id>/<workflow-slug>/agent.json      # claude -p JSON (tokens/cost)
<run-id>/tasks/<task-id>/<workflow-slug>/agent.err
<run-id>/tasks/<task-id>/<workflow-slug>/verifier.log
<run-id>/tasks/<task-id>/<workflow-slug>/reward.txt
```

`compare` adds:
```text
<run-id>/comparison.json    # machine-readable (FR-021/FR-023), schema per data-model Comparison
<run-id>/comparison.md      # human-readable per-task matrix + per-workflow pass rates + ranking (FR-022)
```
plus one `run.json`/`report.md` per workflow (suffixed by slug, e.g. `run-somecode.json`).

### `run.json` shape (summary)
```json
{
  "run_id": "20260607T013455Z-a1b2c3",
  "workflow_token": "/somecode",
  "workflow_slug": "somecode",
  "model": "<model>",
  "selection": {"mode": "sampled", "n": 10, "seed": 0, "task_ids": ["..."]},
  "counts": {"selected": 10, "attempted": 9, "passed": 4, "failed": 4, "errored": 1, "not_attempted": 1},
  "pass_rate": 0.4444,
  "started_at": "...", "finished_at": "...",
  "results": [ { "task_id": "...", "outcome": "passed", "reward": 1.0, "duration_sec": 123.4,
                 "agent_exit_code": 0, "verifier_exit_code": 0, "tokens": {"total": 12345},
                 "cost_usd": 0.12, "reason": null, "patch_present": true,
                 "artifacts_dir": "tasks/<id>/somecode" } ]
}
```

### `comparison.json` shape (summary)
```json
{
  "run_id": "...", "model": "<model>",
  "selection": {"mode": "sampled", "n": 10, "seed": 0, "task_ids": ["..."]},
  "common_attempted_ids": ["..."],
  "per_workflow": [
    {"workflow_slug": "somecode", "pass_rate": 0.44, "common_attempted_pass_rate": 0.5,
     "counts": {"selected": 10, "attempted": 9, "passed": 4, "failed": 4, "errored": 1, "not_attempted": 1}}
  ],
  "matrix": [ {"task_id": "...", "outcomes": {"somecode": "passed", "story-to-live": "failed"}} ],
  "ranking": ["somecode", "story-to-live"]
}
```

## Error message contract (exit 2, before provisioning)

- No credential: a single message naming BOTH accepted forms and how to obtain a token, e.g. "No Claude credential found. Set ANTHROPIC_API_KEY, or set CLAUDE_CODE_OAUTH_TOKEN (mint one with `claude setup-token`). Aborting before provisioning." (FR-025/SC-005)
- Both credentials set: error stating exactly one must be set (the clarification requires exactly one usable credential).
- No model: "A model is required; pass --model <model>. There is no default model." (FR-010)
- Unknown task id: "Unknown task id(s): <ids>. They are not present in the corpus; refusing to run." (FR-027)
- No selection flag: "Select tasks with one of --task, --tasks, or --n-tasks."
- Docker unavailable: "Docker is required but not available: <detail>."

## Determinism contract

Given identical `--n-tasks N --seed S` and corpus, `selection.task_ids` is byte-for-byte identical across runs and machines (SC-002). Algorithm: sort task ids lexicographically, then `random.Random(S).sample(sorted_ids, min(N, len(sorted_ids)))`.
