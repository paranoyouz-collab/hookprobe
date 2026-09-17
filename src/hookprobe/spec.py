"""The hook schema, as data.

Everything here is transcribed from the Claude Code hooks reference. It lives in
one module so that when the schema moves, exactly one file changes — and so the
checks read as questions about the spec rather than as hardcoded trivia.
"""

# Every valid event name. A typo here is the single most common hook bug and the
# most invisible: the config loads fine and the hook simply never fires.
EVENTS: frozenset[str] = frozenset(
    [
        "SessionStart",
        "Setup",
        "UserPromptSubmit",
        "UserPromptExpansion",
        "PreToolUse",
        "PermissionRequest",
        "PermissionDenied",
        "PostToolUse",
        "PostToolUseFailure",
        "PostToolBatch",
        "Notification",
        "MessageDisplay",
        "SubagentStart",
        "SubagentStop",
        "TaskCreated",
        "TaskCompleted",
        "Stop",
        "StopFailure",
        "TeammateIdle",
        "InstructionsLoaded",
        "ConfigChange",
        "CwdChanged",
        "DirectoryAdded",
        "FileChanged",
        "WorktreeCreate",
        "WorktreeRemove",
        "PreCompact",
        "PostCompact",
        "PreModelSwitch",
        "PostModelSwitch",
        "Elicitation",
        "ElicitationResult",
        "SessionEnd",
    ]
)

# Events that ignore `matcher` entirely. Setting one here is not an error the
# config will report — the hook just fires on everything, which is rarely what
# the author meant when they bothered to write a filter.
NO_MATCHER: frozenset[str] = frozenset(
    [
        "UserPromptSubmit",
        "PostToolBatch",
        "Stop",
        "CwdChanged",
        "TeammateIdle",
        "TaskCreated",
        "TaskCompleted",
        "WorktreeCreate",
        "WorktreeRemove",
        "MessageDisplay",
    ]
)

# Events whose matcher is a tool name, so a lowercase `bash` silently matches
# nothing.
TOOL_MATCHER_EVENTS: frozenset[str] = frozenset(
    ["PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest", "PermissionDenied"]
)

# Matchers for these events come from a closed set; anything else never fires.
ENUM_MATCHERS: dict[str, frozenset[str]] = {
    "SessionStart": frozenset(["startup", "resume", "clear", "compact", "fork"]),
    "Setup": frozenset(["init", "maintenance"]),
    "SessionEnd": frozenset(["clear", "resume", "logout", "prompt_input_exit", "other"]),
    "PreCompact": frozenset(["manual", "auto"]),
    "PostCompact": frozenset(["manual", "auto"]),
    "ConfigChange": frozenset(["user_settings", "project_settings", "policy_settings"]),
    "DirectoryAdded": frozenset(["slash_command", "register_repo_root"]),
    "InstructionsLoaded": frozenset(["session_start", "nested_traversal", "include", "compact"]),
}

HANDLER_TYPES: frozenset[str] = frozenset(["command", "http", "mcp_tool", "prompt", "agent"])

# Fields each handler type cannot work without.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "command": ("command",),
    "http": ("url",),
    "mcp_tool": ("server", "tool"),
    "prompt": ("prompt",),
    "agent": ("prompt",),
}

# Default timeout in seconds when none is given. The command default is ten
# minutes, which is a very long time to block a tool call on a hung script.
DEFAULT_TIMEOUT: dict[str, int] = {
    "command": 600,
    "http": 600,
    "mcp_tool": 600,
    "prompt": 30,
    "agent": 60,
}

# Events where a hook exiting 2 actually blocks. Anywhere else, a script written
# to veto something is writing into the void.
BLOCKING_EVENTS: frozenset[str] = frozenset(
    ["PreToolUse", "UserPromptSubmit", "UserPromptExpansion", "Stop", "WorktreeCreate"]
)

# Events that discard hook output altogether.
OUTPUT_DISCARDED: frozenset[str] = frozenset(["SessionEnd", "StopFailure"])

# Events carrying the standard decision model, so permissionDecision applies.
DECISION_EVENTS: frozenset[str] = frozenset(
    [
        "PreToolUse",
        "UserPromptSubmit",
        "UserPromptExpansion",
        "PostToolUse",
        "PostToolUseFailure",
        "PostToolBatch",
        "Stop",
    ]
)

# `if` is a permission rule, and only means anything on tool events.
IF_EVENTS: frozenset[str] = TOOL_MATCHER_EVENTS

# Substituted in command/args before execution.
PLACEHOLDERS: frozenset[str] = frozenset(
    ["CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA"]
)

# A matcher made only of these characters is compared literally; anything else
# is treated as an unanchored JavaScript regex.
LITERAL_MATCHER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ,|")


def is_literal_matcher(matcher: str) -> bool:
    """True when the matcher is compared as a literal rather than as a regex."""
    return all(character in LITERAL_MATCHER_CHARS for character in matcher)


def suggest_event(name: str) -> str | None:
    """Closest valid event name, for a probable typo."""
    import difflib

    # 0.6, not the more usual 0.7: `PreToolCall` -> `PreToolUse` scores 0.67,
    # and that is exactly the typo most worth catching.
    matches = difflib.get_close_matches(name, sorted(EVENTS), n=1, cutoff=0.6)
    return matches[0] if matches else None
