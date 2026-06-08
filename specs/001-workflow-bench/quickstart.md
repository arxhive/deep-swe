# Quickstart: Workflow Bench

A runnable walkthrough of the `wfbench` CLI once implemented. All commands run from the repository root unless noted; the package lives in `bench/`.

## Prerequisites

- `uv` installed (verified present: 0.8.22).
- Docker Desktop running (verified: Docker 29.4.0). Images are `linux/amd64`; the host is arm64 macOS - the harness passes `--platform linux/amd64` automatically.
- A Claude credential exported. Use your subscription (no per-token charges):
  ```bash
  claude setup-token            # interactive; requires a Claude Pro/Max subscription
  export CLAUDE_CODE_OAUTH_TOKEN=<the-token-it-prints>   # sk-ant-oat01-...
  ```
  An `ANTHROPIC_API_KEY` also works but bills per-token via the Anthropic API. If both
  are set the subscription token wins and the API key is ignored (only the chosen
  credential is forwarded to the sandbox, so no accidental API charges). See
  "Authentication" in `bench/README.md`.
- The owner's `~/.claude` with `commands/` and `skills/` (resolved automatically even though they are symlinks into dotfiles).

## Install / sync

```bash
cd bench
uv sync            # creates the venv and installs pytest (no runtime deps)
```

## One-time: warm the Claude runtime (optional)

Builds the cached `linux/amd64` Claude runtime once; `run`/`compare` do this lazily on first use anyway.

```bash
uv run wfbench prepare-runtime
# -> prints the runtime cache path under jobs/.runtime-cache/runtime
```

## User Story 1 - benchmark one workflow

Single task:

```bash
uv run wfbench run --command /somecode --model <model> --task abs-module-cache-flags
```

Deterministic subset (same ids every time for a given seed):

```bash
uv run wfbench run --command /somecode --model <model> --n-tasks 10 --seed 0
```

What happens: preflight validates credential + model + docker (aborts with a clear message and zero containers if anything is missing) -> the deterministic subset is selected -> for each task the workflow runs headlessly inside the task's `linux/amd64` container with the network ON, then the network is disconnected and the task's own verifier grades the change -> results land under `jobs/<run-id>/`.

Read the result:

```bash
cat jobs/<run-id>/report.md                 # human-readable: pass rate + per-task outcomes
jq . jobs/<run-id>/run.json                  # machine-readable
```

## User Story 2 - compare two or more workflows

```bash
uv run wfbench compare \
  --command /somecode \
  --command /story-to-live \
  --model <model> \
  --n-tasks 10 --seed 0
```

Both workflows run over the IDENTICAL 10-task subset with the SAME model. Output:

```bash
cat jobs/<run-id>/comparison.md             # per-task outcome matrix + per-workflow pass rates + ranking
jq . jobs/<run-id>/comparison.json
```

The ranking uses the common-attempted set (tasks every workflow attempted), so it stays fair even if some tasks fail to provision for one workflow.

## User Story 3 - inspect and trust a single task result

```bash
ls jobs/<run-id>/tasks/abs-module-cache-flags/somecode/
# result.json  model.patch  agent.json  agent.err  verifier.log  reward.txt

cat jobs/<run-id>/tasks/abs-module-cache-flags/somecode/model.patch   # the code change the workflow produced
cat jobs/<run-id>/tasks/abs-module-cache-flags/somecode/reward.txt    # 1 = pass, else non-pass
jq '{outcome, reward, duration_sec, tokens, cost_usd, reason}' \
   jobs/<run-id>/tasks/abs-module-cache-flags/somecode/result.json
```

## Expected behaviors to verify (acceptance)

- Re-running the same `--n-tasks N --seed S` selects the identical task ids (SC-002).
- Missing credential or missing `--model` aborts before any container starts (SC-005).
- A subset where some tasks fail/timeout/cannot provision still completes and reports `passed/attempted` with reconciling `selected/attempted/not_attempted` counts (SC-006).
- No run opens a PR, pushes, or waits on CI; each task ends in a captured local change the verifier grades (SC-007).
- Grading runs with no network while the agent phase still reached the model (SC-008).
- Everything lands under `jobs/` and never shows up as a tracked git change (SC-009).

## Running the tests

```bash
cd bench
uv run pytest                       # unit tests only (docker/network tests auto-skip)
uv run pytest -m integration        # docker smoke test (requires docker + a credential)
uv run pylint src/wfbench           # lint
uv run python -m py_compile src/wfbench/*.py
```
