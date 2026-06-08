"""Command-line interface for wfbench: ``run``, ``compare``, and ``prepare-runtime``.

Exit codes (CLI contract): 0 success (even if some tasks failed), 2 usage/precondition
error (aborts before provisioning), 1 unexpected internal error. Progress logs to
stderr; the at-a-glance summary prints to stdout.
"""

import argparse
import logging
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

from . import config, report
from .corpus import discover_tasks
from .docker_cli import DockerCli
from .errors import CorpusError, PreflightError, SelectionError, WfbenchError
from .logging_setup import configure_logging
from .preflight import check_docker, preflight_run
from .prompt import parse_workflow_ref
from .runner import RunConfig, run_comparison, run_workflow
from .runtime import ensure_runtime
from .claude_config import materialize_config
from .selection import Selection, resolve_explicit, resolve_sample

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2


def _generate_run_id() -> str:
    """Return a unique run id: ``<UTC timestamp>-<short random hex>`` (FR-024)."""
    stamp = datetime.now(timezone.utc).strftime(config.RUN_ID_TIMESTAMP_FORMAT)
    suffix = secrets.token_hex(config.RUN_ID_SUFFIX_BYTES)
    return f"{stamp}-{suffix}"


def _anchor_dir() -> Path:
    """Locate the repo root holding the task corpus so defaults work from any CWD.

    The corpus lives at ``<repo>/tasks`` while ``uv run`` may execute from ``bench/``.
    Prefer the current directory, then its parent (running inside ``bench/``), then the
    package-relative repo root; fall back to the current directory so the standard
    not-found error still fires when no corpus exists anywhere.
    """
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        Path(__file__).resolve().parents[3],
    ]
    for base in candidates:
        if (base / config.DEFAULT_CORPUS).is_dir():
            return base
    return Path.cwd()


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add the flags shared by ``run`` and ``compare`` to ``parser``."""
    parser.add_argument("--model", required=True, help="Model id passed to claude --model.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--task", help="Single task id.")
    selection.add_argument("--tasks", help="Comma-separated explicit task ids.")
    selection.add_argument("--n-tasks", type=int, dest="n_tasks", help="Deterministic sample size.")
    parser.add_argument("--seed", type=int, default=0, help="Seed for --n-tasks (default 0).")
    anchor = _anchor_dir()
    parser.add_argument("--corpus", default=str(anchor / config.DEFAULT_CORPUS),
                        help="Corpus root (default: the repo's tasks/ dir).")
    parser.add_argument("--jobs-dir", dest="jobs_dir", default=str(anchor / config.DEFAULT_JOBS),
                        help="Gitignored output root (default: the repo's jobs/ dir).")
    parser.add_argument("--runtime-cache", dest="runtime_cache", default=None,
                        help="Cached Claude runtime location (default <jobs>/.runtime-cache).")
    parser.add_argument("--claude-config", dest="claude_config",
                        default=config.DEFAULT_CLAUDE_CONFIG,
                        help="Owner Claude config to resolve and copy.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="wfbench", description="Benchmark Claude Code workflows.")
    # dest="subcommand" avoids colliding with the run/compare ``--command`` flag (dest "command").
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_parser = subparsers.add_parser("run", help="Benchmark one workflow over a subset.")
    run_parser.add_argument("--command", required=True,
                            help="The workflow under test (e.g. /somecode), or "
                                 "'none' for the pure-model baseline (no slash-command).")
    _add_common_args(run_parser)

    compare_parser = subparsers.add_parser("compare", help="Compare two-plus workflows.")
    compare_parser.add_argument("--command", action="append", default=[], dest="commands",
                                help="A workflow under test; repeat at least twice. Use "
                                     "'none' as one entry for the pure-model baseline.")
    _add_common_args(compare_parser)

    prep_parser = subparsers.add_parser("prepare-runtime", help="Build the cached Claude runtime.")
    prep_parser.add_argument("--runtime-cache", dest="runtime_cache", default=None,
                             help="Cached Claude runtime location.")
    prep_parser.add_argument("--jobs-dir", dest="jobs_dir", default=config.DEFAULT_JOBS,
                             help="Output root (for the default runtime cache).")
    prep_parser.add_argument("--force", action="store_true", help="Rebuild even if cached.")
    prep_parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    return parser


def _resolve_runtime_cache(args: argparse.Namespace) -> Path:
    """Return the runtime cache dir, defaulting to ``<jobs>/.runtime-cache``."""
    if args.runtime_cache:
        return Path(args.runtime_cache)
    return Path(args.jobs_dir) / config.RUNTIME_CACHE_SUBDIR


def _resolve_selection(args: argparse.Namespace, available_ids: Sequence[str]) -> Selection:
    """Resolve the task selection from the parsed args (explicit or sampled)."""
    if args.task:
        return resolve_explicit([args.task], available_ids)
    if args.tasks:
        return resolve_explicit(args.tasks.split(","), available_ids)
    return resolve_sample(args.n_tasks, args.seed, available_ids)


def _build_run_config(args: argparse.Namespace, workflows: list, selection: Selection,
                      credential, model: str) -> RunConfig:
    """Assemble the immutable ``RunConfig`` for this invocation."""
    run_id = _generate_run_id()
    jobs_root = Path(args.jobs_dir)
    return RunConfig(
        workflows=workflows,
        selection=selection,
        model=model,
        credential=credential,
        corpus_root=Path(args.corpus),
        jobs_root=jobs_root,
        runtime_cache=_resolve_runtime_cache(args),
        run_id=run_id,
        run_dir=jobs_root / run_id,
    )


def _provision(cfg: RunConfig, args: argparse.Namespace, docker: DockerCli) -> tuple[Path, Path]:
    """Ensure the runtime and a per-run config copy exist; return their dirs."""
    runtime_dir = ensure_runtime(cfg.runtime_cache, docker)
    config_dir = materialize_config(Path(args.claude_config), cfg.run_dir / ".claude-config")
    return runtime_dir, config_dir


def _cmd_run(args: argparse.Namespace, docker: DockerCli) -> int:
    """Execute the ``run`` subcommand end-to-end."""
    ref = parse_workflow_ref(args.command)
    credential, model = preflight_run(_env(), args.model, docker)
    tasks = discover_tasks(Path(args.corpus))
    selection = _resolve_selection(args, list(tasks))
    cfg = _build_run_config(args, [ref], selection, credential, model)
    logger.info(
        "run: workflow=%s model=%s tasks=%d run_id=%s",
        ref.token, model, len(selection.task_ids), cfg.run_id,
    )
    runtime_dir, config_dir = _provision(cfg, args, docker)
    run = run_workflow(cfg, ref, tasks, runtime_dir, config_dir, docker)
    report.write_run(run, cfg.run_dir)
    report.print_summary(run, cfg.run_dir)
    return EXIT_OK


def _cmd_compare(args: argparse.Namespace, docker: DockerCli) -> int:
    """Execute the ``compare`` subcommand end-to-end."""
    if len(args.commands) < 2:
        raise SelectionError("compare requires at least two --command workflows.")
    refs = [parse_workflow_ref(raw) for raw in args.commands]
    credential, model = preflight_run(_env(), args.model, docker)
    tasks = discover_tasks(Path(args.corpus))
    selection = _resolve_selection(args, list(tasks))
    cfg = _build_run_config(args, refs, selection, credential, model)
    logger.info(
        "compare: workflows=%s model=%s tasks=%d run_id=%s",
        [r.token for r in refs], model, len(selection.task_ids), cfg.run_id,
    )
    runtime_dir, config_dir = _provision(cfg, args, docker)
    comparison = run_comparison(cfg, tasks, runtime_dir, config_dir, docker)
    report.write_comparison(comparison, cfg.run_dir)
    report.print_summary(comparison, cfg.run_dir)
    return EXIT_OK


def _cmd_prepare_runtime(args: argparse.Namespace, docker: DockerCli) -> int:
    """Execute the ``prepare-runtime`` subcommand (docker only, no credential)."""
    check_docker(docker)
    cache = _resolve_runtime_cache(args)
    runtime_dir = ensure_runtime(cache, docker, force=getattr(args, "force", False))
    print(f"Claude runtime ready at: {runtime_dir}")
    return EXIT_OK


def _env() -> Mapping[str, str]:
    """Return the current process environment (the credential is read from here)."""
    return os.environ


_DISPATCH = {
    "run": _cmd_run,
    "compare": _cmd_compare,
    "prepare-runtime": _cmd_prepare_runtime,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments, dispatch the subcommand, and map errors to exit codes."""
    parser = build_parser()
    # prepare-runtime registers --force lazily so it does not appear on run/compare.
    args = parser.parse_args(argv)
    configure_logging(getattr(args, "verbose", False))

    docker = DockerCli()
    handler = _DISPATCH[args.subcommand]
    try:
        return handler(args, docker)
    except (PreflightError, SelectionError, CorpusError) as exc:
        logger.error("%s", exc)
        return EXIT_USAGE
    except WfbenchError as exc:
        logger.error("Internal error: %s", exc)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
