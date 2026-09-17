import json

from hookprobe.loader import discover, load
from tests.conftest import codes


def test_reads_a_hook(one_hook):
    config = load(one_hook("PreToolUse", {"type": "command", "command": "echo hi"}))
    assert len(config.hooks) == 1
    assert config.hooks[0].event == "PreToolUse"
    assert config.hooks[0].kind == "command"


def test_invalid_json_is_a_finding_not_a_crash(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert "invalid-json" in codes(load(path).findings)


def test_missing_file_is_a_finding(tmp_path):
    assert "unreadable" in codes(load(tmp_path / "nope.json").findings)


def test_settings_without_hooks_is_fine(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    config = load(path)
    assert config.hooks == []
    assert config.findings == []


def test_unknown_event_is_reported_with_a_suggestion(settings):
    config = load(settings({"PreToolCall": [{"hooks": [{"type": "command", "command": "x"}]}]}))
    assert "unknown-event" in codes(config.findings)
    assert "PreToolUse" in config.findings[0].message


def test_event_must_be_a_list(settings):
    assert "event-not-a-list" in codes(load(settings({"Stop": {}})).findings)


def test_entry_without_handlers_is_reported(settings):
    assert "no-handlers" in codes(load(settings({"Stop": [{"matcher": "x"}]})).findings)


def test_handlers_must_be_a_list(settings):
    assert "handlers-not-a-list" in codes(load(settings({"Stop": [{"hooks": {}}]})).findings)


def test_hooks_must_be_an_object(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hooks": []}), encoding="utf-8")
    assert "hooks-not-an-object" in codes(load(path).findings)


def test_handlers_are_numbered_across_entries(settings):
    config = load(
        settings(
            {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "a"}]},
                    {"matcher": "Edit", "hooks": [{"type": "command", "command": "b"}]},
                ]
            }
        )
    )
    assert [hook.index for hook in config.hooks] == [0, 1]


def test_discover_finds_dot_claude_settings(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}", encoding="utf-8")
    (claude / "settings.local.json").write_text("{}", encoding="utf-8")
    assert len(discover(tmp_path)) == 2


def test_discover_accepts_a_file(one_hook):
    path = one_hook("Stop", {"type": "command", "command": "x"})
    assert discover(path) == [path]
