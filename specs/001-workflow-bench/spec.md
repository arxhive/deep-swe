# Feature Specification: Workflow Bench

**Feature Branch**: `feat/workflow-bench`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "Adopt the deep-swe coding-agents benchmarking corpus, but instead of benchmarking different frontier models, benchmark my personal Claude Code workflow expressed as skills and slash-commands (for example compare story-to-live.md and somecode.md). Keep deep-swe's tasks and evaluation mechanism, but make the CLI accept a skill or command that it must use for benchmarking, and let me compare two or more such workflows by pass rate."

## Overview

Workflow Bench is a lean standalone command-line tool that measures the code-producing quality of the repository owner's personal Claude Code workflows (slash-commands and skills, for example `/somecode` or `/story-to-live`) using the deep-swe task corpus and its held-out program-based verifiers as an objective, external grader. Instead of comparing frontier models, it treats a chosen workflow as the "agent under test", runs it against real software-engineering tasks inside each task's isolated sandbox, grades the produced code change with the task's own verifier, and reports pass rate. It can run one workflow over a deterministic task subset and can compare two or more workflows over the identical subset side-by-side, so the owner gets an apples-to-apples answer to "which of my workflows produces higher-quality code" from a held-out test suite rather than from self-assessment.

## Clarifications

### Session 2026-06-07

This session was resolved autonomously from the locked decisions, technical realities, and assumptions already captured in this spec (Constraints, Non-Functional Requirements, Assumptions) plus the corpus ground truth. Each decision is recorded here and applied to the affected requirements.

- Q: For pass rate, what is the denominator - tasks selected, tasks where the workflow actually ran, or both reported? → A: Report two denominators - `attempted` (workflow ran and was graded) drives the headline pass rate; `selected`, `errored`, and `not-attempted` (for example image unavailable) are also reported, so pass rate = passed / attempted with full reconciliation.
- Q: Which model do runs use when the owner does not specify one? → A: There is no built-in default; the owner MUST specify the model explicitly per run, and the tool refuses to start without it (keeps comparisons honest and reproducible).
- Q: Which credential forms are accepted for driving the workflow, and how is presence validated? → A: Accept exactly one of an API key or a mintable OAuth token (via the standard token-setup flow); presence is validated up front before any sandbox is provisioned, and the tool errors with how to obtain a token when neither is present.
- Q: How are distinct runs kept distinguishable under the version-control-excluded outputs directory? → A: Each run gets a unique run identifier (timestamp plus short random suffix) and its own subdirectory under the gitignored outputs location; per-task artifacts nest under the run, and nothing from a prior run is overwritten.
- Q: In a comparison, is each workflow scored over its own attempted set or over the set common to all workflows? → A: Report both - each workflow's own pass rate over its own attempted tasks, plus a "common attempted" pass rate computed over the intersection of tasks every workflow attempted, so head-to-head ranking is fair even when some tasks fail to provision for some runs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Benchmark one workflow against a deterministic task subset (Priority: P1)

The repository owner picks one of their Claude Code workflows (for example `/somecode`) and a reproducible slice of the corpus (for example "10 tasks, seed 0"). They run the tool, which for each selected task provisions the task's sandbox, drives the chosen workflow headlessly to implement the task in place, grades the resulting code change with the task's verifier, and records a pass or fail per task plus an overall pass rate. The owner ends up with a recorded run they can inspect and re-run reproducibly.

**Why this priority**: This is the core capability and the minimum viable product. Without the ability to run one workflow over a defined set of tasks and obtain a verifier-scored pass rate, nothing else (comparison, reporting) has meaning. It is the smallest slice that delivers standalone value: an objective score for a single workflow.

**Independent Test**: Can be fully tested by selecting one known task id and one workflow, running the tool, and confirming it produces a single recorded result containing the workflow identity, the task id, the captured code change, the verifier reward (pass or fail), and run metadata - without requiring any comparison feature to exist.

**Acceptance Scenarios**:

1. **Given** a valid workflow reference and a single valid task id, **When** the owner runs the tool for that task, **Then** the tool drives the workflow inside the task sandbox, grades the produced change with that task's verifier, and records exactly one result with a pass-or-fail outcome and the captured code change.
2. **Given** a workflow reference and a request for a deterministic subset of size N with seed S, **When** the owner runs the tool, **Then** the tool selects the same N tasks that the same (N, S) selection always yields, runs the workflow against each, and reports an overall pass rate (passed count over attempted count).
3. **Given** the same workflow, same N, and same seed are requested again, **When** the owner re-runs the tool, **Then** the identical set of task ids is selected for evaluation (subset selection is deterministic and repeatable).
4. **Given** one task in a subset fails to provision or the workflow errors on it, **When** the run continues, **Then** that task is recorded as a non-pass with a captured reason and the remaining tasks still run, and the final pass rate reflects all attempted tasks.

---

### User Story 2 - Compare two or more workflows over the same subset (Priority: P1)

The repository owner wants to know which of two (or more) of their workflows is better. They run a comparison over the identical deterministic task subset, and the tool runs every workflow against the exact same tasks and emits a side-by-side report of pass rate per workflow, plus a per-task breakdown showing which workflow passed which task.

**Why this priority**: Comparison is the headline reason the owner wants this tool ("compare the quality of two slash commands"). It depends on User Story 1 but is itself a primary deliverable rather than a nice-to-have, so it shares top priority. The comparison must be fair, which is why every workflow must run against the identical task set.

**Independent Test**: Can be tested by selecting a small deterministic subset and two workflows, running the comparison, and confirming the output contains a pass rate for each workflow computed over the same task ids and a per-task matrix of outcomes - verifiable even with a subset of size 1.

**Acceptance Scenarios**:

1. **Given** two or more workflow references and a deterministic subset (by N and seed, or by explicit task ids), **When** the owner runs a comparison, **Then** every workflow is evaluated against the identical set of task ids and the report shows each workflow's pass rate over that identical set.
2. **Given** a completed comparison, **When** the owner inspects the output, **Then** a per-task breakdown shows, for each task, the pass-or-fail outcome of each workflow, making it possible to see where workflows diverge.
3. **Given** a completed comparison, **When** the owner needs both quick human reading and downstream processing, **Then** the tool emits both a human-readable report and a machine-readable report describing the same results.

---

### User Story 3 - Inspect and trust a single task result (Priority: P2)

After a run, the repository owner opens the recorded artifacts for one task to understand and trust the outcome: what code change the workflow produced, what the verifier decided, how long it took, and any token or cost data the workflow run reported. This lets the owner audit a surprising pass or failure rather than taking the score on faith.

**Why this priority**: Trust and debuggability are essential for the score to be actionable, but they build on top of US1 and US2, so this is P2. A pass rate the owner cannot audit would undermine the tool's purpose of replacing self-assessment with objective evidence.

**Independent Test**: Can be tested by running a single task and confirming that the recorded artifacts for that task include the captured code change, the verifier outcome, the workflow and verifier logs, exit status, wall-clock duration, and any reported token or cost figures.

**Acceptance Scenarios**:

1. **Given** a completed single-task run, **When** the owner opens that task's recorded artifacts, **Then** they find the captured code change the workflow produced, the verifier reward value, and the logs from both the workflow run and the verifier run.
2. **Given** a completed single-task run, **When** the owner reviews the run metadata, **Then** it includes the workflow identity, the model used, the wall-clock duration, the exit status, and any token or cost figures reported by the workflow run.
3. **Given** a workflow run produced no usable code change (for example it errored before editing files), **When** the verifier runs, **Then** the result is recorded as a non-pass and the captured change is empty rather than the run aborting the whole batch.

---

### Edge Cases

- **Missing or invalid auth**: If no usable credential for running the workflow is present, the tool MUST refuse to start any run and explain, in one clear actionable message, which credential to provide and how to obtain it, rather than failing partway through after provisioning a sandbox.
- **Workflow performs out-of-scope sandbox actions**: The owner's real workflows attempt to create branches and worktrees, push to a remote, open pull requests, run additional review sub-commands, and monitor continuous integration. In an isolated offline sandbox with no remote and no forge credentials these steps are meaningless. The tool MUST neutralize them so the workflow implements the change in place and the run still yields a gradeable code change instead of stalling or erroring on a push or a pull-request step.
- **Subset larger than the corpus**: If the requested subset size exceeds the number of available tasks, the tool MUST cap at the full corpus and proceed (or report clearly) rather than failing.
- **Unknown task id**: If an explicitly requested task id does not exist in the corpus, the tool MUST report it clearly and either skip it or refuse the run, never silently substitute a different task.
- **Workflow exceeds its time budget**: If a workflow run does not finish within the task's allotted agent time, the tool MUST stop that run, record it as a non-pass with a timeout reason, capture whatever partial change exists, and continue with the next task.
- **Verifier cannot determine an outcome**: If the verifier does not produce a reward value (for example it crashes), the tool MUST record the task as a non-pass with the verifier failure captured, not as a pass and not as an aborted batch.
- **Prebuilt task image unavailable**: If a task's prebuilt environment cannot be obtained, the tool MUST record that task as not-attempted with a clear reason and continue with the rest of the subset.
- **Comparison with a partially failing workflow**: If one workflow in a comparison fails or errors on some tasks, the comparison MUST still complete and report each workflow's pass rate over the identical attempted task set.
- **Concurrent or repeated runs**: Re-running must not overwrite or corrupt a prior run's recorded artifacts; each run MUST be distinguishable.

## Requirements *(mandatory)*

### Functional Requirements

#### Task selection and corpus

- **FR-001**: The tool MUST run the existing deep-swe task corpus that lives under the repository's `tasks/` directory and MUST treat that corpus and its verifiers as read-only inputs, never modifying them.
- **FR-002**: The tool MUST support running a single task identified by its task id.
- **FR-003**: The tool MUST support running an explicit list of task ids provided by the owner.
- **FR-004**: The tool MUST support selecting a deterministic random subset of the corpus by a requested count and a seed, such that the same count and seed always select the same set of task ids, mirroring the corpus's established subset-selection semantics so results are reproducible and comparable.
- **FR-005**: The tool MUST make each task's instruction (the natural-language prompt) the task input given to the workflow under test, and MUST NOT expose the held-out hidden tests or the reference solution to the workflow.

#### The workflow under test

- **FR-006**: The tool MUST accept, as the "agent under test", a reference to one of the owner's Claude Code workflows expressed as a slash-command or a skill (for example `/somecode` or `/story-to-live`), and MUST drive that workflow as the implementer of each task.
- **FR-007**: The tool MUST drive the chosen workflow non-interactively (headlessly) so that it runs to completion without prompting a human, and MUST resolve the workflow by the same name the owner uses locally.
- **FR-008**: The tool MUST make the owner's workflow definitions (their slash-command and skill files) available to the workflow run even though those definitions are stored as symbolic links on the owner's machine, resolving the real file contents rather than relying on the links being valid inside the run environment.
- **FR-009**: The tool MUST neutralize the parts of the owner's workflows that assume a connected, authenticated development environment - specifically the creation of branches or worktrees, pushing to a remote, opening pull requests, and monitoring continuous integration - so that within the isolated offline grading environment the workflow implements the task in place and commits locally only, leaving a gradeable code change. The neutralization MUST NOT require editing the owner's original workflow files.
- **FR-010**: The tool MUST require the owner to specify, per run, which model the workflow uses; there is no built-in default model. The tool MUST refuse to start a run when no model is specified, and MUST record the model used for each task attempt. In a comparison, the same model specification applies to every workflow so the workflow is the only deliberately varied factor.

#### Execution and isolation

- **FR-011**: The tool MUST run each task in that task's own isolated prebuilt environment so the workflow has access to the task repository's toolchain, and MUST use the environment specified by the task metadata.
- **FR-012**: The tool MUST run the workflow against the task repository working copy and then capture the code change the workflow produced relative to the task's defined base state.
- **FR-013**: The tool MUST allow the workflow run the network access it needs to operate, while ensuring the grading step runs with no network access, consistent with the corpus's offline grading requirement; the workflow phase and the grading phase MUST be separable so that grading cannot reach the network.
- **FR-014**: The tool MUST enforce a per-task time budget for the workflow run and a per-task time budget for grading, using the budgets defined in the task metadata, and MUST treat exceeding a budget as a non-pass with a recorded timeout reason.
- **FR-015**: The tool MAY run tasks sequentially; parallel execution is not required for the first version.

#### Grading

- **FR-016**: The tool MUST grade each task using that task's own verifier entry point, unchanged, and MUST determine pass or fail from the reward the verifier produces (a reward of pass meaning the task's hidden tests succeeded on the workflow's change, anything else meaning fail).
- **FR-017**: The tool MUST treat the absence of a verifier reward, or a verifier that fails to run, as a non-pass with the failure captured, never as a pass.
- **FR-018**: The tool MUST grade the workflow's produced change against the task's held-out hidden tests exactly as the corpus's verifier does, without the workflow having had access to those hidden tests.

#### Recording and reporting

- **FR-019**: For each task attempt the tool MUST record: the workflow identity, the task id, the pass-or-fail outcome, the captured code change the workflow produced, the workflow run log, the verifier log, the workflow run exit status, the wall-clock duration, and any token or cost figures reported by the workflow run.
- **FR-020**: For a multi-task run the tool MUST classify every selected task into exactly one outcome state - `passed`, `failed` (workflow ran and was graded but the verifier did not award a pass), `errored` (the workflow run failed or timed out), or `not-attempted` (the task could not be provisioned, for example its environment was unavailable) - and MUST compute the headline pass rate as `passed` over `attempted`, where `attempted` = `passed` + `failed` + `errored`. The report MUST also include the counts of `selected`, `attempted`, and `not-attempted` so the figures reconcile.
- **FR-021**: For a comparison of two or more workflows, the tool MUST evaluate every workflow against the identical selected set of task ids and MUST report, for each workflow, both its own pass rate over the tasks it attempted and a "common attempted" pass rate computed over the intersection of tasks that every workflow attempted. The common-attempted set MUST be used for the head-to-head ranking so the comparison stays fair when some tasks fail to provision for some runs.
- **FR-022**: For a comparison, the tool MUST emit a per-task breakdown showing each workflow's outcome on each task.
- **FR-023**: The tool MUST emit results in both a human-readable form and a machine-readable form that describe the same run.
- **FR-024**: The tool MUST write all run artifacts and results under a directory that is excluded from version control. Each run MUST receive a unique run identifier (for example a timestamp plus a short random suffix) and its own subdirectory under that location, with per-task artifacts nested beneath the run, so that a new run never overwrites or corrupts a prior run's records and any run can be located by its identifier.

#### Preconditions and failure handling

- **FR-025**: Before starting any run, the tool MUST verify that a usable credential for driving the workflow is available - either an API key or a subscription OAuth-style token the owner can generate via the standard token-setup flow - and MUST refuse to start with a single clear actionable error (naming the accepted credential forms and how to obtain a token) when none is present. When both forms are present the tool MUST prefer the subscription token (so a stray API key never silently switches the run to per-token billing) and MUST forward only the chosen credential into the sandbox; an API-key-only run MUST warn that requests are billed per-token. This validation MUST happen before any sandbox is provisioned, so a missing credential never wastes provisioning work.
- **FR-026**: The tool MUST continue a multi-task run when an individual task fails to provision, errors, or times out, recording that task's failure reason and including it in the final tally as a non-pass or not-attempted as appropriate.
- **FR-027**: The tool MUST report a clear error for an unknown explicitly requested task id and MUST NOT silently substitute a different task.
- **FR-028**: The tool MUST surface, at the end of a run, a concise summary the owner can read at a glance (per-workflow pass rate and where to find the detailed artifacts).

### Key Entities *(include if feature involves data)*

- **Task**: A single benchmark item from the corpus. Key attributes: a stable task id, the implementation language, the natural-language instruction shown to the workflow, the isolated environment it runs in, the resource and time budgets, the offline-grading requirement, and the held-out verifier and hidden tests used only at grading time. Tasks are read-only inputs.
- **Workflow under test**: One of the owner's Claude Code slash-commands or skills, identified by name, that acts as the implementer of a task. It is the unit being benchmarked and compared.
- **Task subset**: A reproducible selection of tasks defined either by an explicit list of task ids or by a (count, seed) pair that deterministically yields the same task ids every time. The unit of fairness for comparison: every workflow in a comparison runs against the same subset.
- **Task attempt / result**: The outcome of running one workflow against one task. Key attributes: workflow identity, task id, pass-or-fail outcome, the captured code change, workflow and verifier logs, exit status, wall-clock duration, model used, any token or cost figures, and a failure reason when applicable.
- **Run**: One invocation of the tool covering one workflow over a subset (or one workflow over a single task). Produces a collection of task results and an overall pass rate, recorded as a distinguishable unit.
- **Comparison**: An evaluation of two or more workflows over one identical subset. Produces per-workflow pass rates and a per-task outcome breakdown, plus human-readable and machine-readable reports.

## Constraints

These are locked decisions and environmental realities that bound the solution. They are recorded here so the planning phase is grounded; the detailed implementation approach is deferred to the plan.

- **C-001 (New standalone tool)**: The solution MUST be a new, lean, standalone command-line tool built inside this repository. It MUST NOT depend on, fork, or require the upstream runner ("Pier").
- **C-002 (Agent runs inside the task environment)**: The workflow under test MUST be executed inside each task's own isolated environment (so it has the task repository's toolchain), not on the host against a checked-out copy.
- **C-003 (Delivered as a local feature branch)**: The tool's code lives in this repository's worktree (a dedicated top-level directory is acceptable, for example `bench/`) and is delivered as a local feature branch only. No pull request is opened against the corpus's upstream remote, which the owner does not control.
- **C-004 (Corpus is read-only)**: The task corpus and its verifiers MUST be consumed unchanged. No requirement may be satisfied by editing tasks, verifiers, or hidden tests.
- **C-005 (Claude-only)**: The "agent under test" is always a Claude Code workflow. Supporting other agents or benchmarking frontier models is out of scope.
- **C-006 (Explicit credential required)**: The host environment has no ambient credential usable inside an isolated environment. The tool MUST require an explicitly provided credential for driving the workflow, validate it up front, and make it available to the workflow run.
- **C-007 (Cross-architecture runtime)**: The host tooling that runs the workflow is built for the host's processor architecture and cannot run unchanged inside the task environments, which use a different architecture. A compatible way to run the workflow inside the task environment MUST be provided. (The specific mechanism is a planning detail.)
- **C-008 (Two-phase network separation)**: The workflow phase requires outbound access to the model service; the grading phase MUST run with no network. The design MUST keep these phases separate so grading is offline.
- **C-009 (Workflow files are symlinked)**: The owner's workflow definitions are stored as symbolic links into a dotfiles location. The tool MUST resolve and supply the real file contents to the workflow run rather than depending on the links resolving inside the run environment.
- **C-010 (Non-invasive neutralization)**: The neutralization of out-of-scope workflow steps (branch/worktree/push/pull-request/continuous-integration) MUST be achieved without modifying the owner's original workflow files.
- **C-011 (Results are gitignored)**: All run outputs and artifacts MUST be written under a version-control-excluded location. The repository already excludes a designated outputs directory for this purpose.

## Non-Functional Requirements

- **NFR-001 (Reproducibility)**: A given (subset count, seed) MUST select the same task ids on every run and every machine, so comparisons and re-runs are repeatable.
- **NFR-002 (Fair comparison)**: In a comparison, all workflows MUST be evaluated against the identical selected task set under the same per-task budgets and the same specified model, and ranking MUST use the common-attempted set, so the only deliberately varied factor is the workflow.
- **NFR-003 (Isolation and safety)**: Each task MUST run isolated from the host and from other tasks so a misbehaving workflow cannot affect the host or other results.
- **NFR-004 (Auditability)**: Every recorded outcome MUST be traceable to the captured code change, the verifier decision, and the logs that produced it, so the owner can independently verify any pass or fail.
- **NFR-005 (Resilience)**: A failure on one task MUST NOT abort the whole batch; the run MUST complete over the remaining tasks and report partial results.
- **NFR-006 (Clear preconditions)**: Misconfiguration (missing credential, unknown task id) MUST be reported clearly and early, before time-consuming work begins where feasible.
- **NFR-007 (Lean footprint)**: The tool MUST stay minimal in scope and dependencies, consistent with being a lean standalone harness rather than a full evaluation platform.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a single command, the owner can benchmark one chosen workflow over a deterministic subset and obtain an overall pass rate plus a per-task pass-or-fail outcome, with no manual steps between starting the run and reading the result.
- **SC-002**: Re-running the same workflow over the same subset specification selects the identical set of tasks every time (100% identical selection across repeated runs).
- **SC-003**: From a single command, the owner can compare two or more workflows and receive, per workflow, both its own pass rate and a common-attempted pass rate over the intersection of tasks every workflow attempted, plus a per-task outcome breakdown - all from the identical selected task set.
- **SC-004**: For every attempted task, the owner can open recorded artifacts and find the captured code change, the verifier outcome, both logs, the duration, the model used, and any token or cost figures - sufficient to audit the result without re-running it.
- **SC-005**: When neither accepted credential (API key or mintable token) is present, or when no model is specified, the tool refuses to start and tells the owner exactly what to provide and how to obtain it, with zero sandboxes provisioned.
- **SC-006**: A run over a multi-task subset in which at least one task fails, errors, times out, or cannot be provisioned still completes, reports a headline pass rate of `passed` over `attempted` with reconciling counts of `selected`, `attempted`, and `not-attempted`, and records a reason for each non-pass and each not-attempted task (no aborted batch).
- **SC-007**: Across a benchmarking run, the workflow under test never opens a pull request, pushes to a remote, or stalls waiting on continuous integration; each task run terminates in a captured local code change that the verifier grades.
- **SC-008**: The grading step for every task runs with no network access, consistent with the corpus's offline requirement, while the workflow step still completes its model interaction.
- **SC-009**: All run outputs land under the version-control-excluded outputs location and never appear as tracked changes in the repository.
- **SC-010**: Two different workflows benchmarked over the same non-trivial subset with the same specified model produce common-attempted pass rates that let the owner rank them, demonstrating the tool can distinguish workflow quality.

## Assumptions

- The corpus already present under `tasks/` in this worktree is the benchmark set to use, and its verifiers grade by producing a pass-or-fail reward per task.
- Each task ships a prebuilt isolated environment referenced by its metadata, with a reproducible fallback definition; obtaining that environment is a prerequisite the planning phase will detail.
- The owner runs the tool on their own machine where their Claude Code workflow definitions exist (as symlinked files) and where a container runtime is available.
- The workflows under test are the owner's existing slash-commands and skills (for example `somecode` and `story-to-live`); the tool benchmarks them as-is, only neutralizing the connected-environment steps for the duration of a benchmark run.
- "Quality" of a workflow is operationalized as verifier pass rate over the chosen task subset; the tool does not attempt any other quality measure in this version.
- Sequential execution is acceptable for the first version; throughput and parallelism are out of scope for now.
- Exactly one credential - an API key or a mintable token (see Clarifications, FR-025) - is required and sufficient to drive the workflow runs.
- The model is always specified explicitly by the owner per run; there is no default model (see Clarifications, FR-010).
- The owner accepts that running real model-driven workflows against many tasks incurs model usage cost and wall-clock time proportional to the subset size.

## Out of Scope (v1)

- Parallel or cloud-distributed execution.
- A web-based trajectory or results viewer.
- Benchmarking frontier models directly, or supporting non-Claude agents.
- Any modification to the task corpus, the verifiers, or the hidden tests.
- Defining new tasks or extending the corpus.
- Statistical-significance analysis beyond reporting pass rates and per-task outcomes.
