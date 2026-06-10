# [DeepSWE](https://deepswe.datacurve.ai/) task corpus

DeepSWE is a benchmark for measuring frontier coding agents on original, long-horizon software engineering tasks drawn from active open-source repositories. The benchmark includes 113 tasks across TypeScript, Go, Python, JavaScript, and Rust, with isolated environments and program-based verifiers.

This directory holds those 113 tasks. They are consumed read-only by the `wfbench` harness in [`../bench/`](../bench/) (see the repository [README](../README.md)); this fork does not modify the tasks or their verifiers.

## Task format

DeepSWE tasks use the [Harbor](https://www.harborframework.com/docs/tasks) task format:

```text
task.toml         Metadata: repository, base commit, language, prebuilt image, resource limits
instruction.md    The prompt the agent sees
environment/      Dockerfile that reproduces the prebuilt image (fallback if the image is unavailable)
tests/            Verifier: test.sh (entry point) + test.patch (test additions, applied at grading time)
solution/         Reference solution (held out from the agent; for human and AI reviewers)
```

The verifier exercises the behavior the prompt describes. It accepts any solution whose observable behavior is correct, regardless of internal symbol names or structure.
The reference patch in `solution/` is never used at grading time; it exists so reviewers can spot-check correctness offline.

## Running the upstream benchmark (frontier models)

The original DeepSWE benchmark is run with [Pier](https://github.com/datacurve-ai/pier), a [Harbor](https://www.harborframework.com/docs/tasks)-compatible framework for sandboxed coding-agent evals:

```bash
uv tool install datacurve-pier

export ANTHROPIC_API_KEY=...
pier run -p tasks --agent mini-swe-agent --model anthropic/claude-opus-4-7

# deterministic subset / single task
pier run -p tasks --agent mini-swe-agent --n-tasks 10 --sample-seed 0
pier run -p tasks/<task-id> --agent mini-swe-agent
```

To benchmark your own Claude Code workflows against this corpus instead of frontier models, use `wfbench` (see the repository [README](../README.md)).
