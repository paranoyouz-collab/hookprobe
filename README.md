# hookprobe

Lint Claude Code hooks. The failure that matters is the silent one: a hook with
a mistyped event name, a matcher on an event that ignores matchers, or a
lowercase tool name loads without complaint and simply never runs.

```
$ hookprobe .claude/settings.json

.claude/settings.json
  x `PreToolCall` is not a hook event, so nothing here ever runs — did you mean `PreToolUse`?
  - 1 blocking hook(s) on Stop set no `timeout`, so a hung one stalls for the default 600s
  PreToolUse[0] echo hi
    x tool names are case-sensitive: `bash` never matches, use `Bash`
    ! `timeout` of 900s blocks `PreToolUse` for that long if it hangs
  Stop[0] http://x
    x header uses `$TOK` but it is not in `allowedEnvVars`, so it is sent uninterpolated
    ! `Stop` ignores `matcher`, so this fires on everything anyway
  SessionStart[0]
    x `mcp_tool` hook needs `tool`
    x `launch` is not a SessionStart value; expected one of clear, compact, fork, resume, startup
  UserPromptSubmit[0] x
    x `wizard` is not a hook type; expected agent, command, http, mcp_tool, prompt

4 hooks across 1 file(s), 9 finding(s)
```

Every one of those loads fine today and tells you nothing.

## Install

```bash
uv tool install hookprobe     # or: pipx install hookprobe
```

No key, no network, no config. It reads JSON and prints what will not work.

## Usage

```bash
hookprobe                          # searches ./ and ./.claude
hookprobe path/to/settings.json    # one file
hookprobe --json                   # machine-readable
hookprobe --fail-on warn           # stricter gate
hookprobe --project-dir /repo      # what ${CLAUDE_PROJECT_DIR} resolves to
```

Exit codes: `0` clean, `1` findings at or above `--fail-on` (default `error`),
`2` bad invocation.

## What it catches

**Hooks that never fire**

- An event name that is not one of the 33 real ones, with a spelling suggestion
- A tool matcher whose casing is wrong — `bash` never matches `Bash`
- A matcher outside the closed set an event accepts, like `launch` for
  `SessionStart`
- A matcher regex that will not compile

**Hooks that fire but do nothing you intended**

- A `matcher` on one of the ten events that ignore matchers entirely
- An `if` permission rule on a non-tool event, where it means nothing
- `once` outside a skill hook
- A `prompt` or `agent` hook on `SessionEnd` or `StopFailure`, which discard
  hook output

**Hooks that are wired wrong**

- Missing the field its type requires — `command`, `url`, `server`+`tool`,
  `prompt`
- A `type` that is not one of the five
- A script path that does not exist, or exists but is not executable
- `${PLACEHOLDER}` that is neither a hook placeholder nor set in the environment
- An HTTP header interpolating `$VAR` that is missing from `allowedEnvVars`, so
  it is transmitted uninterpolated

**Hooks that will cost you time**

- An explicit `timeout` long enough to stall a blocking event
- A per-file note of how many blocking hooks run on the default timeout, which
  for a command hook is **600 seconds**

## Why per-file for the timeout note

Almost nobody sets `timeout`. Flagging each hook individually fired on every
real-world config tested and buried the findings that mattered, so it is
summarised once per file instead. A linter everyone ignores is a linter that
does not work.

## Built against real configs

The checks were corrected by running them against genuine `settings.json` files
from public repositories rather than only against fixtures. Four bugs came out
of that and are now regression tests:

| Found in | Bug |
|---|---|
| `dartsim/dart` | `"${CLAUDE_PROJECT_DIR}/x.sh"` — quoted path left a stray quote |
| `dataplat/dbatools` | `bash "$CLAUDE_PROJECT_DIR"/x.sh` — quote mid-token |
| `kube-logging/logging-operator` | `$VAR` unbraced was never resolved |
| `carlrannaberg/claudekit` | `MultiEdit` reported as an unknown tool — it isn't |

The tool-name list is now used **only** to catch casing mistakes. An
unrecognised name is never itself a finding, because that list can never be
authoritative.

## Companion

[skillprobe](https://github.com/paranoyouz-collab/skillprobe) does the same job
for agent skills — whether they trigger, what they cost per turn, and whether
they collide.

## Development

```bash
uv sync
pytest
ruff check . && ruff format --check .
```

## License

MIT
