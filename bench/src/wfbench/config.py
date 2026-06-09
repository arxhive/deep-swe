"""Module-level constants for wfbench. No logic lives here.

Centralizes all paths, pinned versions, mount points, env var names, and the
benchmark neutralization directive so there are no magic strings elsewhere.
"""

# --- Default host-side paths (relative to the repository root) ---
DEFAULT_CORPUS = "tasks"
DEFAULT_JOBS = "jobs"
# Cached Claude runtime lives under the gitignored jobs tree by default.
RUNTIME_CACHE_SUBDIR = ".runtime-cache"
RUNTIME_DIR_NAME = "runtime"
DEFAULT_CLAUDE_CONFIG = "~/.claude"

# --- Container mount points and working dirs ---
MOUNT_RUNTIME = "/opt/wfbench"
MOUNT_TESTS = "/tests"
MOUNT_LOGS = "/logs"
MOUNT_WORK = "/work"
CONTAINER_APP_DIR = "/app"
# Most swe-bench task images run as root; the config mounts at the root HOME.
CONTAINER_HOME = "/root"
PROMPT_FILENAME = "prompt.txt"

# --- Log subdirectories the harness owns (test.sh only creates artifacts) ---
LOGS_VERIFIER_SUBDIR = "verifier"
LOGS_ARTIFACTS_SUBDIR = "artifacts"
REWARD_FILENAME = "reward.txt"
MODEL_PATCH_FILENAME = "model.patch"

# --- Runtime build pins (reproducibility, NFR-001 spirit) ---
NODE_IMAGE = "node:20-bookworm-slim"
# Pinned Claude Code npm version installed into the linux/amd64 runtime.
CLAUDE_CODE_VERSION = "2.1.168"
CLAUDE_CODE_PACKAGE = "@anthropic-ai/claude-code"

# --- Docker platform (the host zsh docker() function is bypassed by subprocess) ---
DOCKER_PLATFORM = "linux/amd64"
DOCKER_DEFAULT_PLATFORM_ENV = "DOCKER_DEFAULT_PLATFORM"
DEFAULT_DOCKER_BIN = "docker"
DEFAULT_BRIDGE_NETWORK = "bridge"

# --- Credential env var names (value never serialized or logged) ---
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_CLAUDE_CODE_OAUTH_TOKEN = "CLAUDE_CODE_OAUTH_TOKEN"

# Claude Code refuses --dangerously-skip-permissions/bypassPermissions as root unless
# IS_SANDBOX=1 (verified in the claude binary: getuid()===0 && IS_SANDBOX!=="1" -> abort).
# The task containers run as root, so the agent exec sets this.
ENV_IS_SANDBOX = "IS_SANDBOX"
IS_SANDBOX_VALUE = "1"

# --- Run identity ---
RUN_ID_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_SUFFIX_BYTES = 3  # 3 bytes -> 6 hex chars

# --- Output artifact file names ---
RUN_JSON = "run.json"
REPORT_MD = "report.md"
COMPARISON_JSON = "comparison.json"
COMPARISON_MD = "comparison.md"
RESULT_JSON = "result.json"
AGENT_JSON = "agent.json"
AGENT_ERR = "agent.err"
VERIFIER_LOG = "verifier.log"

# --- Owner ~/.claude entries to copy (resolved) and to exclude (secrets/large) ---
CONFIG_INCLUDE = ("commands", "skills", "scripts", "settings.json", "CLAUDE.md")
CONFIG_REQUIRED = ("commands", "skills")
CONFIG_EXCLUDE = (
    "projects",
    "file-history",
    "history.jsonl",
    "sessions",
    "session-env",
    "security",
    "telemetry",
    "shell-snapshots",
    "tasks",
    "backups",
    "plugins",
    "paste-cache",
    "stats-cache.json",
    "stats-cache",
    "debug",
    "ide",
    "mcp-needs-auth-cache.json",
)

# Settings keys stripped from the sandbox copy of settings.json: they invoke host
# commands or host-only state that breaks or pollutes a headless container run, and
# they are interactive-environment config, not workflow logic. apiKeyHelper/proxyAuthHelper
# are dropped so they cannot override the forwarded subscription credential.
SETTINGS_NAME = "settings.json"
SETTINGS_SANDBOX_DROP_KEYS = (
    "hooks",
    "statusLine",
    "enabledPlugins",
    "enableAllProjectMcpServers",
    "mcpServers",
    "apiKeyHelper",
    "proxyAuthHelper",
    "awsAuthRefresh",
)

# Required files for a directory to count as a valid corpus task.
TASK_TOML = "task.toml"
INSTRUCTION_MD = "instruction.md"
TESTS_DIRNAME = "tests"
TEST_SH = "test.sh"

# --- Neutralization directive appended to the workflow's system prompt (R6) ---
# Defense-in-depth only: physical test isolation (R8) is the integrity mechanism.
# The held-out tests do not exist in the container during the agent phase.
BENCHMARK_DIRECTIVE = (
    "You are running inside an isolated OFFLINE benchmark sandbox, solving exactly "
    "ONE task whose repository is checked out at /app. There is NO git remote, NO "
    "GitHub, NO CI system, and NO human available to answer questions. Implement the "
    "requested change directly in the working tree at /app and finish as soon as the "
    "implementation is complete.\n"
    "You MUST NOT: create git worktrees or branches, push to any remote, open or "
    "manage pull requests, run or wait on CI, spawn sub-agents for PR/CI/review/QA "
    "phases, or perform any specify/clarify/PR/CI/QA step that assumes a connected "
    "environment. You MAY commit locally if your workflow does so, but a commit is "
    "optional - the change in the /app working tree is what is graded.\n"
    "Work solely from /app and the task instruction. Do NOT search for, read, or rely "
    "on any held-out grading tests; grading happens after you finish, in a separate "
    "offline phase you cannot observe."
)
