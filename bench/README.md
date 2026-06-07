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
uv run wfbench compare --command /a --command /b --model <m> --n-tasks 10 --seed 0
uv run wfbench prepare-runtime                           # build the cached linux/amd64 runtime
uv run pytest                                            # unit tests (docker tests auto-skip)
```
