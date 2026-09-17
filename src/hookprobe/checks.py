"""The checks.

The failure mode worth caring about is the silent one. A hook with a mistyped
event name, a matcher on an event that ignores matchers, or a script that exits
2 where nothing blocks will all load without complaint and simply never do what
the author meant. Those are the findings this tool exists for.
"""

import os
import re
from pathlib import Path

from hookprobe.loader import Config
from hookprobe.model import Finding, Hook, Severity
from hookprobe.spec import (
    BLOCKING_EVENTS,
    DEFAULT_TIMEOUT,
    ENUM_MATCHERS,
    HANDLER_TYPES,
    IF_EVENTS,
    NO_MATCHER,
    OUTPUT_DISCARDED,
    PLACEHOLDERS,
    REQUIRED_FIELDS,
    TOOL_MATCHER_EVENTS,
    is_literal_matcher,
)

# Blocking hooks run in the path of a tool call, so a long default timeout is a
# long stall. Warn past this when the event can block.
SLOW_BLOCKING_TIMEOUT = 60

# Used ONLY to catch casing mistakes, which silently match nothing. This list
# cannot be authoritative — tools come and go, and MCP and plugin tools are
# unbounded — so an unrecognised name is never itself reported. Running against
# real configs flagged `MultiEdit` as unknown, which was noise, not a finding.
KNOWN_TOOLS = frozenset(
    [
        "Bash",
        "Read",
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "NotebookRead",
        "Glob",
        "Grep",
        "LS",
        "Task",
        "Agent",
        "WebFetch",
        "WebSearch",
        "TodoWrite",
        "TodoRead",
        "ExitPlanMode",
        "SlashCommand",
        "BashOutput",
        "KillBash",
        "KillShell",
    ]
)

_ENV_IN_HEADER = re.compile(r"\$(\w+)")
_PLACEHOLDER = re.compile(r"\$\{(\w+)\}|\$([A-Z_][A-Z0-9_]*)")


def check_config(config: Config, project_dir: Path | None = None) -> None:
    """Run every check over one loaded settings file."""
    for hook in config.hooks:
        check_hook(hook, project_dir or config.source.parent)
    _check_default_timeouts(config)


def _check_default_timeouts(config: Config) -> None:
    """Note, once, how many blocking hooks run on the long default timeout.

    Almost no real config sets `timeout`, so this is context rather than a
    fault — but the default for a command hook is ten minutes, and people are
    generally surprised by that.
    """
    exposed = [
        hook
        for hook in config.hooks
        if hook.event in BLOCKING_EVENTS
        and hook.config.get("timeout") is None
        and not hook.config.get("async")
        and (DEFAULT_TIMEOUT.get(hook.kind, 0) > SLOW_BLOCKING_TIMEOUT)
    ]
    if not exposed:
        return

    events = ", ".join(sorted({hook.event for hook in exposed}))
    config.findings.append(
        Finding(
            "default-timeout",
            Severity.INFO,
            f"{len(exposed)} blocking hook(s) on {events} set no `timeout`, so a hung one "
            f"stalls for the default {DEFAULT_TIMEOUT['command']}s",
        )
    )


def check_hook(hook: Hook, project_dir: Path) -> None:
    _check_type(hook)
    _check_matcher(hook)
    _check_if(hook)
    _check_timeout(hook)
    _check_command(hook, project_dir)
    _check_http(hook)
    _check_once(hook)
    _check_output_expectations(hook)


def _check_type(hook: Hook) -> None:
    kind = hook.config.get("type")
    if kind is None:
        hook.findings.append(Finding("no-type", Severity.ERROR, "hook has no `type`"))
        return
    if kind not in HANDLER_TYPES:
        valid = ", ".join(sorted(HANDLER_TYPES))
        hook.findings.append(
            Finding(
                "unknown-type", Severity.ERROR, f"`{kind}` is not a hook type; expected {valid}"
            )
        )
        return

    for required in REQUIRED_FIELDS[kind]:
        if not hook.config.get(required):
            hook.findings.append(
                Finding("missing-field", Severity.ERROR, f"`{kind}` hook needs `{required}`")
            )


def _check_matcher(hook: Hook) -> None:
    matcher = hook.matcher
    if matcher is None or matcher in ("", "*"):
        return

    if hook.event in NO_MATCHER:
        hook.findings.append(
            Finding(
                "matcher-ignored",
                Severity.WARN,
                f"`{hook.event}` ignores `matcher`, so this fires on everything anyway",
            )
        )
        return

    if hook.event in ENUM_MATCHERS:
        allowed = ENUM_MATCHERS[hook.event]
        values = [v.strip() for v in re.split(r"[|,]", matcher) if v.strip()]
        unknown = [v for v in values if v not in allowed and is_literal_matcher(v)]
        if unknown:
            hook.findings.append(
                Finding(
                    "matcher-never-matches",
                    Severity.ERROR,
                    f"`{', '.join(unknown)}` is not a {hook.event} value; expected one of "
                    + ", ".join(sorted(allowed)),
                )
            )
        return

    if not is_literal_matcher(matcher):
        try:
            re.compile(matcher)
        except re.error as exc:
            hook.findings.append(
                Finding("bad-regex", Severity.ERROR, f"matcher is not a valid regex: {exc}")
            )
        return

    if hook.event in TOOL_MATCHER_EVENTS:
        names = [v.strip() for v in re.split(r"[|,]", matcher) if v.strip()]
        for name in names:
            if name in KNOWN_TOOLS or name.startswith("mcp__"):
                continue
            correct = next((t for t in KNOWN_TOOLS if t.lower() == name.lower()), None)
            if correct:
                hook.findings.append(
                    Finding(
                        "matcher-case",
                        Severity.ERROR,
                        f"tool names are case-sensitive: `{name}` never matches, use `{correct}`",
                    )
                )


def _check_if(hook: Hook) -> None:
    if hook.config.get("if") and hook.event not in IF_EVENTS:
        hook.findings.append(
            Finding(
                "if-ignored",
                Severity.WARN,
                f"`if` is a permission rule and only applies to tool events, not `{hook.event}`",
            )
        )


def _check_timeout(hook: Hook) -> None:
    timeout = hook.config.get("timeout")

    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        hook.findings.append(
            Finding(
                "bad-timeout",
                Severity.ERROR,
                f"`timeout` must be a positive number, got {timeout!r}",
            )
        )
        return

    if hook.event not in BLOCKING_EVENTS or hook.config.get("async"):
        return

    # Omitting `timeout` is the overwhelming default in real configs, so
    # flagging each one individually buries the findings that matter. It is
    # summarised once per file instead (see _check_default_timeouts).
    if timeout is None:
        return

    if timeout > SLOW_BLOCKING_TIMEOUT:
        hook.findings.append(
            Finding(
                "slow-blocking",
                Severity.WARN,
                f"`timeout` of {timeout:g}s blocks `{hook.event}` for that long if it hangs",
            )
        )


def _check_command(hook: Hook, project_dir: Path) -> None:
    if hook.kind != "command":
        return

    command = hook.config.get("command")
    if not isinstance(command, str) or not command.strip():
        return

    for braced, bare in _PLACEHOLDER.findall(command):
        name = braced or bare
        if name not in PLACEHOLDERS and name not in os.environ:
            hook.findings.append(
                Finding(
                    "unknown-placeholder",
                    Severity.WARN,
                    f"`${{{name}}}` is not a hook placeholder and is not set in the environment",
                )
            )

    if hook.config.get("shell") and hook.config.get("args") is not None:
        hook.findings.append(
            Finding(
                "shell-ignored",
                Severity.INFO,
                "`shell` is ignored when `args` is set, since that runs without a shell",
            )
        )

    resolved = _resolve(command, project_dir)
    if resolved is None:
        return
    if not resolved.exists():
        hook.findings.append(
            Finding("missing-script", Severity.ERROR, f"`{resolved}` does not exist")
        )
    elif not os.access(resolved, os.X_OK):
        hook.findings.append(
            Finding("not-executable", Severity.ERROR, f"`{resolved}` is not executable (chmod +x)")
        )


def _resolve(command: str, project_dir: Path) -> Path | None:
    """The script path a command runs, when it plainly is one.

    Only the unambiguous case is resolved: a single token that looks like a path.
    A shell pipeline or a bare executable name is left alone rather than guessed
    at — a wrong "missing script" error is worse than no check.
    """
    text = command.strip()
    if not text or any(character in text for character in "|&;><("):
        return None

    tokens = text.split()
    # `bash path/to/hook.sh` and `python3 hook.py` are as common as a bare path.
    if tokens[0] in ("bash", "sh", "zsh", "python", "python3", "node", "uv", "npx"):
        tokens = tokens[1:]
    if not tokens:
        return None

    # Real configs quote the path because it interpolates a directory, and the
    # quotes are not always around the whole token — `"$CLAUDE_PROJECT_DIR"/x`
    # puts one in the middle, so strip them throughout rather than at the ends.
    first = tokens[0].replace('"', "").replace("'", "")
    if "/" not in first:
        return None

    expanded = first
    for form in ("${CLAUDE_PROJECT_DIR}", "$CLAUDE_PROJECT_DIR"):
        expanded = expanded.replace(form, str(project_dir))
    # Anything still unresolved cannot be checked without guessing.
    if "$" in expanded:
        return None
    return Path(expanded).expanduser()


def _check_http(hook: Hook) -> None:
    if hook.kind != "http":
        return

    headers = hook.config.get("headers")
    if not isinstance(headers, dict):
        return

    allowed = hook.config.get("allowedEnvVars")
    allowed_names = set(allowed) if isinstance(allowed, list) else set()

    for value in headers.values():
        if not isinstance(value, str):
            continue
        for name in _ENV_IN_HEADER.findall(value):
            if name not in allowed_names:
                hook.findings.append(
                    Finding(
                        "env-not-allowed",
                        Severity.ERROR,
                        f"header uses `${name}` but it is not in `allowedEnvVars`, "
                        "so it is sent uninterpolated",
                    )
                )


def _check_once(hook: Hook) -> None:
    if hook.config.get("once"):
        hook.findings.append(
            Finding("once-outside-skill", Severity.WARN, "`once` only applies to skill hooks")
        )


def _check_output_expectations(hook: Hook) -> None:
    """Flag hooks wired to events that throw their output away."""
    if hook.event in OUTPUT_DISCARDED and hook.kind in ("prompt", "agent"):
        hook.findings.append(
            Finding(
                "output-discarded",
                Severity.WARN,
                f"`{hook.event}` discards hook output, so this {hook.kind} hook's result is unused",
            )
        )


def analyze(root: Path, project_dir: Path | None = None) -> list[Config]:
    """Load and check every settings file under ``root``."""
    from hookprobe.loader import discover, load

    configs = [load(path) for path in discover(root)]
    for config in configs:
        check_config(config, project_dir)
    return configs
