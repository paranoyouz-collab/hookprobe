import json

from hookprobe.cli import main


def test_clean_config_exits_zero(one_hook, tmp_path, capsys):
    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    path = one_hook("PreToolUse", {"type": "command", "command": str(script), "timeout": 5})
    assert main([str(path)]) == 0
    assert "clean" in capsys.readouterr().out


def test_errors_exit_one(settings, capsys):
    path = settings({"NotAnEvent": [{"hooks": [{"type": "command", "command": "x"}]}]})
    assert main([str(path)]) == 1


def test_warnings_alone_pass_by_default(one_hook, capsys):
    path = one_hook("Stop", {"type": "command", "command": "x", "once": True})
    assert main([str(path)]) == 0


def test_fail_on_warn_catches_warnings(one_hook, capsys):
    path = one_hook("Stop", {"type": "command", "command": "x", "once": True})
    assert main([str(path), "--fail-on", "warn"]) == 1


def test_fail_on_never_always_passes(settings, capsys):
    path = settings({"NotAnEvent": [{"hooks": [{"type": "command", "command": "x"}]}]})
    assert main([str(path), "--fail-on", "never"]) == 0


def test_missing_path_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope.json")]) == 2
    assert "no such path" in capsys.readouterr().out


def test_directory_without_settings_is_not_an_error(tmp_path, capsys):
    assert main([str(tmp_path)]) == 0
    assert "no settings files found" in capsys.readouterr().out


def test_json_output_is_valid(one_hook, capsys):
    path = one_hook("PreToolUse", {"type": "command", "command": "x"}, matcher="bash")
    main([str(path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    entry = payload["files"][0]
    assert entry["hooks"][0]["event"] == "PreToolUse"
    assert "matcher-case" in {f["code"] for f in entry["hooks"][0]["findings"]}


def test_json_includes_file_level_findings(settings, capsys):
    path = settings({"Nope": [{"hooks": [{"type": "command", "command": "x"}]}]})
    main([str(path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert "unknown-event" in {f["code"] for f in payload["files"][0]["findings"]}


def test_project_dir_flag_resolves_placeholders(one_hook, tmp_path, capsys):
    script = tmp_path / "hook.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    path = one_hook(
        "PreToolUse",
        {"type": "command", "command": "${CLAUDE_PROJECT_DIR}/hook.sh", "timeout": 5},
    )
    assert main([str(path), "--project-dir", str(tmp_path)]) == 0
