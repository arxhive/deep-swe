# wfbench - Workflow Bench

`wfbench` is a lean, standard-library-only Python CLI that benchmarks the owner's
personal Claude Code workflows (slash-commands and skills such as `/somecode` or
`/story-to-live`) against the deep-swe task corpus under `tasks/`. Each task runs the
workflow headlessly inside its own `linux/amd64` sandbox container (network on), then the
network is disconnected and the task's own held-out verifier grades the produced change.
Outcomes are classified (passed / failed / errored / not-attempted) and written under the
gitignored `jobs/<run-id>/` tree as both machine-readable JSON and human-readable Markdown.
It can benchmark one workflow over a deterministic task subset or compare two-plus workflows
over the identical subset with the same model.

See `specs/001-workflow-bench/quickstart.md` for a runnable walkthrough.

## Quick reference

```bash
cd bench
uv sync                                                  # create venv, install dev deps (pytest)
uv run wfbench run --command /somecode --model <m> --task <id>
uv run wfbench run --command none --model <m> --task <id>   # pure-model baseline (reference)
uv run wfbench compare --command /a --command /b --model <m> --n-tasks 10 --seed 0
uv run wfbench prepare-runtime                           # build the cached linux/amd64 runtime
uv run pytest                                            # unit tests (docker tests auto-skip)
```

## Authentication (use your subscription, not an API key)

`wfbench` drives Claude Code inside each task container, so it needs a credential. Two
forms are accepted, and the tool prefers the subscription:

1. Subscription token (recommended, no per-token charges):
   ```bash
   claude setup-token            # interactive OAuth; requires a Claude Pro/Max subscription
   export CLAUDE_CODE_OAUTH_TOKEN=<the-token-it-prints>     # sk-ant-oat01-...
   ```
   This token authenticates as your Claude subscription and counts against your
   subscription quota, the same as interactive Claude Code - it is NOT billed per-token.

2. API key (bills per-token via the Anthropic API):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-api03-...
   ```

How the tool protects your billing:

- It forwards ONLY the chosen credential into the sandbox, by variable name (the value
  is never placed in a command line or written to any artifact).
- If BOTH variables are set, the subscription token wins and the API key is ignored (with
  a warning). This matters because Claude Code otherwise prefers `ANTHROPIC_API_KEY` and
  would bill per-token. An API-key-only run prints a per-token billing warning.
- A run aborts before any container starts if no credential is present.

Caveat - subscription rate limits: the subscription quota has a rolling window plus a
weekly cap and is shared with your interactive Claude usage. Heavyweight workflows (for
example `/story-to-live`, which spawns sub-agents) consume a lot per task, so start with a
small `--n-tasks` and grow once you have a feel for the burn. A task that hits a rate
limit is recorded as `errored` and the batch continues (it is not a false pass).

Note: keep `ANTHROPIC_API_KEY` and any `apiKeyHelper` out of your `~/.claude/settings.json`
if you want to guarantee subscription billing, since settings can also supply a key.

## Pure-model baseline (reference run)

Pass `none` (or the aliases `model` / `baseline`) as the workflow to benchmark vanilla
Claude with no slash-command: the model receives only the task instruction. Everything else
is identical to a workflow run (same container, same `--model`, same grading, same sandbox
system-prompt), so the only varied factor is the slash-command wrapper. This is the control
that tells you whether a workflow actually beats raw Claude. Include it as one column of a
comparison:

```bash
uv run wfbench compare --command none --command /somecode --command /story-to-live \
  --model <m> --n-tasks 10 --seed 0
```

A real slash-command literally named `/none` must be written with its leading slash; the
bare words `none` / `model` / `baseline` are reserved for the baseline.

## `run` vs `compare`

- `run --command X` benchmarks ONE workflow and writes `report.md` + `run.json`. Passing
  `--command` more than once is an error (it points you to `compare`) - it does NOT compare.
- `compare --command X --command Y [--command Z ...]` benchmarks two or more workflows over
  the IDENTICAL subset with the same model, and writes `comparison.md` + `comparison.json`
  (per-workflow pass rates, a per-task outcome matrix, and a ranking over the tasks every
  workflow attempted). This is the only command that produces a comparison.
- Both share the same selection flags and require `--model`:
  `--task <id>` | `--tasks <id,id>` | `--n-tasks <N> --seed <S>`.
- `compare` reruns every workflow fresh over the whole subset (it does not reuse a prior
  `run`), so cost scales with `workflows x tasks`. A single task that all workflows pass is
  a tie and tells you nothing - use `--n-tasks` to find tasks where they diverge.

## Reading results

Every run is a directory under the gitignored `jobs/<run-id>/`:

- Top level: `report.md` + `run.json` (a `run`), or `comparison.md` + `comparison.json` (a `compare`).
- Per attempt, under `tasks/<task-id>/<workflow-slug>/` (the baseline slug is `baseline`):
  - `result.json` - outcome, reward, exit codes, durations, reason
  - `agent.json` - claude's JSON result: token `usage`, cost, and on failure `is_error` / `api_error_status`
  - `agent.err` - claude stderr (the FIRST place to look when a task fails)
  - `verifier.log` - the graded test run
  - `model.patch` - the code change the workflow produced (empty = it changed nothing)
  - `reward.txt` - raw verifier reward (`1` = pass)

## Outcomes

- `passed` - the verifier awarded a pass (reward 1).
- `failed` - the workflow ran and produced a change, but the tests did not pass (a genuine quality result).
- `errored` - the agent did not complete and left nothing gradeable (timeout, crash, or an auth/rate-limit error). This is an infra problem, NOT a quality signal - re-run it.
- `not_attempted` - the task's container could not be provisioned.

Headline pass rate is `passed / attempted`, where `attempted = passed + failed + errored`.

## Troubleshooting

When a task is `errored` (or `failed` unexpectedly), read `tasks/<id>/<slug>/agent.err`, then `agent.json`:

- `agent.json` shows `api_error_status: 401` -> the token is wrong or expired; re-run `claude setup-token` and re-export `CLAUDE_CODE_OAUTH_TOKEN`.
- `agent.json` shows `api_error_status: 429` -> subscription rate limit (shared with your interactive use); wait for the window to reset or lower `--n-tasks`.
- `agent.json` is empty and `agent.err` says "Input must be provided ..." -> stdin was not forwarded to the container (fixed; update to the latest build).
- `agent.err` says "cannot be used with root" -> the sandbox flag was missing (fixed; the harness sets `IS_SANDBOX=1`).
- `model.patch` is empty with `is_error: false` -> claude authenticated and ran but chose not to edit; that is a real (if poor) result for that workflow on that task.
