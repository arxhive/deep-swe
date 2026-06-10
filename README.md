# Workflow Bench

A fork of [DeepSWE](https://deepswe.datacurve.ai/) ([datacurve-ai/deep-swe](https://github.com/datacurve-ai/deep-swe)) adapted to benchmark **your own Claude Code workflows** - slash-commands and skills such as `/somecode` or `/story-to-live` - instead of frontier models.

It reuses DeepSWE's 113-task corpus and its held-out, program-based verifiers as an objective grader: it runs a workflow you choose as the "agent under test" inside each task's sandbox, grades the code change the workflow produces with the task's own verifier, and reports pass rate, duration, and token usage. You can benchmark one workflow, or compare several head-to-head over the identical task subset.

The runner is **`wfbench`**, a lean standalone Python CLI in [`bench/`](bench/). The 113-task corpus lives in [`tasks/`](tasks/) ([tasks/README.md](tasks/README.md)); design docs are in [`specs/`](specs/).

## Why

DeepSWE measures frontier models. This fork answers a different question: **does my personal workflow actually produce better code than raw Claude, and which of my workflows is best?** It swaps the "model under test" for a "workflow under test" and adds a pure-model baseline as the control.

## Capabilities

- **Benchmark one workflow** over a single task or a deterministic subset; get a pass rate plus per-task outcomes.
- **Compare two or more workflows** over the identical subset with the same model: per-workflow pass rates, a per-task outcome matrix, a ranking, and per-task duration + token totals.
- **Pure-model baseline** (`--command none`): vanilla Claude with no slash-command, as the control to measure a workflow's lift.
- **Faithful, isolated grading**: each task runs in its own air-gapped `linux/amd64` container; the workflow runs with network, then the network is cut and the task's own verifier grades the diff offline. Held-out tests are injected only at grading time, so the workflow can never see them.
- **Subscription billing**: authenticates with your Claude Pro/Max subscription, so there are no per-token API charges.
- **Auditable artifacts**: every attempt records the produced diff, both logs, reward, duration, and token/cost under a gitignored `jobs/<run-id>/` tree, as JSON and Markdown.

## How it works

```text
for each task:  pull image -> run your workflow headless in the container (claude -p)
                -> capture the diff -> disconnect network -> inject held-out tests
                -> run the task's verifier -> reward 1/0 -> classify outcome
```

Outcomes: `passed` (verifier reward 1), `failed` (ran, tests did not pass), `errored` (agent crash/timeout/rate-limit - an infra problem, not a quality signal), `not_attempted` (could not provision). Headline pass rate is `passed / attempted`.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/)
- Docker, running. Images are `linux/amd64`; on Apple Silicon the harness passes `--platform linux/amd64` automatically.
- A Claude Pro/Max subscription, and your Claude Code workflows in `~/.claude/commands` and `~/.claude/skills`.

## Install

```bash
cd bench
uv sync
```

## Authenticate (use your subscription, not an API key)

```bash
claude setup-token                 # interactive; requires a Claude Pro/Max subscription
export CLAUDE_CODE_OAUTH_TOKEN=<the-token-it-prints>   # sk-ant-oat01-...
```

This bills against your subscription, not per-token. An `ANTHROPIC_API_KEY` also works but bills per-token via the Anthropic API; if both are set, the subscription token wins and the key is ignored. Full details in [bench/README.md](bench/README.md).

## Usage

All commands run from `bench/`; `--model` is required.

```bash
cd bench

# one-time: build the cached Claude runtime (needs Docker, not a credential)
uv run wfbench prepare-runtime

# benchmark ONE workflow on a single task
uv run wfbench run --command /somecode --model opus --task abs-module-cache-flags

# the pure-model baseline (raw Claude, no slash-command) - the control
uv run wfbench run --command none --model opus --task abs-module-cache-flags

# benchmark ONE workflow over a deterministic subset (same tasks every time for a seed)
uv run wfbench run --command /somecode --model opus --n-tasks 5 --seed 0

# COMPARE workflows over the identical subset (this is what writes comparison.md)
uv run wfbench compare --command none --command /somecode --command /story-to-live \
  --model opus --n-tasks 5 --seed 0
```

### Picking the workflow: `--command`

- `--command /somecode` - one of your slash-commands or skills (the leading slash is optional).
- `--command none` - the pure-model baseline (aliases: `model`, `baseline`). A real command literally named `/none` must keep its slash.
- `run` takes exactly **one** `--command`; `compare` takes **two or more** (repeat the flag). Only `compare` produces a comparison report.

### Picking tasks (both `run` and `compare`)

- `--task <id>` - a single task by id.
- `--tasks <id,id,...>` - an explicit list.
- `--n-tasks <N> --seed <S>` - a deterministic random subset; the same `N` and `seed` always select the same tasks.

## Results

Outputs land under the gitignored `jobs/<run-id>/`:

- Top level: `report.md` + `run.json` (a `run`), or `comparison.md` + `comparison.json` (a `compare`, including per-task duration and token totals with per-workflow totals).
- Per attempt, under `tasks/<task-id>/<workflow>/`: `result.json`, `agent.json` (token usage / cost), `agent.err`, `verifier.log`, `model.patch`, `reward.txt`.

For reading results, the outcome states, troubleshooting (auth `401`, rate-limit `429`, empty patch), and cost/time guidance, see [bench/README.md](bench/README.md).

## Cost and time

Runs use your subscription, so there is no per-token charge - but the subscription has rate limits (rolling plus weekly) shared with your interactive use, and heavyweight workflows (for example `/story-to-live`) are slow and quota-hungry (~15-20 min per task). A full 113-task sweep for one command is roughly 40 hours of agent time, so start with a small `--n-tasks`. For reference, the API-pricing equivalent (recorded as `cost_usd`) has been ~$4-17 per task on the tasks sampled so far.

## Layout

```text
bench/    the wfbench CLI (uv package), its tests, and the full tool README
tasks/    the 113-task DeepSWE corpus (read-only inputs; see tasks/README.md)
specs/    design docs (spec, plan, tasks, research, quickstart)
jobs/     run outputs (gitignored)
```

## Credits

The task corpus and verifiers are from [DeepSWE](https://github.com/datacurve-ai/deep-swe) by Datacurve. This fork adds the `wfbench` workflow-benchmarking harness and does not modify the tasks or verifiers.
