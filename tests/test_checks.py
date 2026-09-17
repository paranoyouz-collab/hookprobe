"""Checks, and the real-world cases that corrected them.

The four regressions at the bottom all came from running this against genuine
settings.json files pulled from public repositories (dart, claudekit,
logging-operator, dbatools). None of them would have surfaced from fixtures
written against my own reading of the schema.
"""

from hookprobe.checks import analyze, check_config
from hookprobe.loader import load
from tests.conftest import codes


def run(path, project_dir=None):
    config = load(path)
    check_config(config, project_dir)
    return config


def hook_codes(config) -> set[str]:
    return {f.code for hook in config.hooks for f in hook.findings}


# ---------------------------------------------------------------------------
# Handler shape
# ---------------------------------------------------------------------------


def test_missing_type_is_an_error(one_hook):
    assert "no-type" in hook_codes(run(one_hook("Stop", {"command": "x"})))


def test_unknown_type_is_an_error(one_hook):
    assert "unknown-type" in hook_codes(run(one_hook("Stop", {"type": "wizard"})))


def test_command_hook_needs_a_command(one_hook):
    assert "missing-field" in hook_codes(run(one_hook("Stop", {"type": "command"})))


def test_http_hook_needs_a_url(one_hook):
    assert "missing-field" in hook_codes(run(one_hook("Stop", {"type": "http"})))


def test_mcp_tool_hook_needs_server_and_tool(one_hook):
    config = run(one_hook("Stop", {"type": "mcp_tool", "server": "s"}))
    assert "missing-field" in hook_codes(config)


def test_a_valid_hook_is_clean(one_hook, tmp_path):
    script = tmp_path / "hook.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    config = run(one_hook("PreToolUse", {"type": "command", "command": str(script), "timeout": 10}))
    assert hook_codes(config) == set()


# ---------------------------------------------------------------------------
# Matchers
# ---------------------------------------------------------------------------


def test_matcher_on_an_event_that_ignores_it(one_hook):
    config = run(one_hook("Stop", {"type": "command", "command": "x"}, matcher="Edit"))
    assert "matcher-ignored" in hook_codes(config)


def test_wildcard_matcher_is_not_flagged(one_hook):
    config = run(one_hook("Stop", {"type": "command", "command": "x"}, matcher="*"))
    assert "matcher-ignored" not in hook_codes(config)


def test_lowercase_tool_name_never_matches(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x"}, matcher="bash"))
    assert "matcher-case" in hook_codes(config)


def test_correct_tool_name_is_accepted(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x"}, matcher="Bash|Edit"))
    assert "matcher-case" not in hook_codes(config)


def test_invalid_regex_matcher_is_an_error(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x"}, matcher="(unclosed"))
    assert "bad-regex" in hook_codes(config)


def test_valid_regex_matcher_is_accepted(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x"}, matcher="mcp__.*"))
    assert hook_codes(config) == set()


def test_enum_matcher_outside_the_allowed_set(one_hook):
    config = run(one_hook("SessionStart", {"type": "command", "command": "x"}, matcher="launch"))
    assert "matcher-never-matches" in hook_codes(config)


def test_enum_matcher_inside_the_allowed_set(one_hook):
    config = run(one_hook("SessionStart", {"type": "command", "command": "x"}, matcher="resume"))
    assert "matcher-never-matches" not in hook_codes(config)


# ---------------------------------------------------------------------------
# Semantics that fail silently
# ---------------------------------------------------------------------------


def test_if_outside_tool_events_is_flagged(one_hook):
    config = run(one_hook("Stop", {"type": "command", "command": "x", "if": "Bash(git *)"}))
    assert "if-ignored" in hook_codes(config)


def test_if_on_a_tool_event_is_fine(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x", "if": "Bash(git *)"}))
    assert "if-ignored" not in hook_codes(config)


def test_http_header_env_without_allowlist(one_hook):
    config = run(
        one_hook("Stop", {"type": "http", "url": "http://x", "headers": {"A": "Bearer $TOK"}})
    )
    assert "env-not-allowed" in hook_codes(config)


def test_http_header_env_with_allowlist_is_fine(one_hook):
    config = run(
        one_hook(
            "Stop",
            {
                "type": "http",
                "url": "http://x",
                "headers": {"A": "Bearer $TOK"},
                "allowedEnvVars": ["TOK"],
            },
        )
    )
    assert "env-not-allowed" not in hook_codes(config)


def test_once_outside_a_skill_is_flagged(one_hook):
    config = run(one_hook("Stop", {"type": "command", "command": "x", "once": True}))
    assert "once-outside-skill" in hook_codes(config)


def test_prompt_hook_on_an_event_that_discards_output(one_hook):
    config = run(one_hook("SessionEnd", {"type": "prompt", "prompt": "check"}))
    assert "output-discarded" in hook_codes(config)


def test_shell_with_args_is_noted(one_hook):
    config = run(one_hook("Stop", {"type": "command", "command": "x", "args": [], "shell": "bash"}))
    assert "shell-ignored" in hook_codes(config)


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------


def test_explicit_long_timeout_on_a_blocking_event_warns(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x", "timeout": 900}))
    assert "slow-blocking" in hook_codes(config)


def test_short_timeout_is_fine(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x", "timeout": 10}))
    assert "slow-blocking" not in hook_codes(config)


def test_negative_timeout_is_an_error(one_hook):
    config = run(one_hook("PreToolUse", {"type": "command", "command": "x", "timeout": -1}))
    assert "bad-timeout" in hook_codes(config)


def test_default_timeout_is_summarised_once_per_file_not_per_hook(settings):
    # Regression: flagging every hook that omits `timeout` fired on all four
    # real configs tested, drowning the findings that mattered.
    entries = [{"hooks": [{"type": "command", "command": f"cmd{n}"}]} for n in range(5)]
    config = run(settings({"PreToolUse": entries}))
    assert [f.code for f in config.findings].count("default-timeout") == 1
    assert "slow-blocking" not in hook_codes(config)


def test_async_hooks_do_not_count_toward_the_timeout_note(settings):
    entries = [{"hooks": [{"type": "command", "command": "x", "async": True}]}]
    config = run(settings({"PreToolUse": entries}))
    assert "default-timeout" not in codes(config.findings)


# ---------------------------------------------------------------------------
# Command resolution — regressions from real configs
# ---------------------------------------------------------------------------


def test_quoted_path_resolves(one_hook, tmp_path):
    # Regression (dart): the command is `"${CLAUDE_PROJECT_DIR}/.../guard.sh"`,
    # quotes included, and stripping only the ends left a stray quote.
    script = tmp_path / "guard.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    path = one_hook(
        "PreToolUse",
        {"type": "command", "command": '"${CLAUDE_PROJECT_DIR}/guard.sh"', "timeout": 5},
    )
    assert hook_codes(run(path, tmp_path)) == set()


def test_quote_inside_the_token_resolves(one_hook, tmp_path):
    # Regression (dbatools): `bash "$CLAUDE_PROJECT_DIR"/.claude/hooks/x.sh`
    # puts the closing quote mid-token.
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    path = one_hook(
        "PreToolUse",
        {"type": "command", "command": 'bash "$CLAUDE_PROJECT_DIR"/x.sh', "timeout": 5},
    )
    assert hook_codes(run(path, tmp_path)) == set()


def test_unbraced_placeholder_resolves(one_hook, tmp_path):
    # Regression (logging-operator): real configs write $CLAUDE_PROJECT_DIR as
    # often as ${CLAUDE_PROJECT_DIR}.
    script = tmp_path / "sec.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    path = one_hook(
        "PreToolUse", {"type": "command", "command": "$CLAUDE_PROJECT_DIR/sec.sh", "timeout": 5}
    )
    assert hook_codes(run(path, tmp_path)) == set()


def test_missing_script_is_an_error(one_hook, tmp_path):
    path = one_hook(
        "PreToolUse", {"type": "command", "command": "${CLAUDE_PROJECT_DIR}/gone.sh", "timeout": 5}
    )
    assert "missing-script" in hook_codes(run(path, tmp_path))


def test_non_executable_script_is_an_error(one_hook, tmp_path):
    script = tmp_path / "plain.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o644)
    path = one_hook(
        "PreToolUse", {"type": "command", "command": "${CLAUDE_PROJECT_DIR}/plain.sh", "timeout": 5}
    )
    assert "not-executable" in hook_codes(run(path, tmp_path))


def test_a_shell_pipeline_is_not_treated_as_a_path(one_hook, tmp_path):
    # Guessing at a path inside a pipeline would produce confident nonsense.
    path = one_hook(
        "PreToolUse", {"type": "command", "command": "cat a/b.txt | grep x", "timeout": 5}
    )
    assert "missing-script" not in hook_codes(run(path, tmp_path))


def test_a_bare_executable_name_is_not_treated_as_a_path(one_hook, tmp_path):
    # Regression (claudekit): `claudekit-hooks run file-guard` is on PATH, not
    # a file beside the settings.
    path = one_hook(
        "PreToolUse", {"type": "command", "command": "claudekit-hooks run file-guard", "timeout": 5}
    )
    assert "missing-script" not in hook_codes(run(path, tmp_path))


def test_unknown_placeholder_is_flagged(one_hook, tmp_path):
    path = one_hook(
        "PreToolUse", {"type": "command", "command": "${NOT_A_THING}/x.sh", "timeout": 5}
    )
    assert "unknown-placeholder" in hook_codes(run(path, tmp_path))


def test_environment_variables_that_exist_are_not_flagged(one_hook, tmp_path, monkeypatch):
    monkeypatch.setenv("MY_HOOK_DIR", str(tmp_path))
    path = one_hook("PreToolUse", {"type": "command", "command": "$MY_HOOK_DIR/x.sh", "timeout": 5})
    assert "unknown-placeholder" not in hook_codes(run(path, tmp_path))


def test_analyze_walks_a_directory(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        '{"hooks":{"Nope":[{"hooks":[{"type":"command","command":"x"}]}]}}', encoding="utf-8"
    )
    configs = analyze(tmp_path)
    assert len(configs) == 1
    assert "unknown-event" in codes(configs[0].findings)
