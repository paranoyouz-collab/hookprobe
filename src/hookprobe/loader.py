"""Finding settings files and walking the hooks structure out of them."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from hookprobe.model import Finding, Hook, Severity
from hookprobe.spec import EVENTS, suggest_event

# Where Claude Code looks, in the order it merges them.
SETTINGS_NAMES = ("settings.json", "settings.local.json")


@dataclass
class Config:
    """One settings file: the hooks in it, plus anything wrong with the file."""

    source: Path
    hooks: list[Hook] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def discover(root: Path) -> list[Path]:
    """Settings files under ``root``, or ``root`` itself when it is a file."""
    if root.is_file():
        return [root]

    found = [root / name for name in SETTINGS_NAMES if (root / name).is_file()]
    claude = root / ".claude"
    if claude.is_dir():
        found += [claude / name for name in SETTINGS_NAMES if (claude / name).is_file()]
    return sorted(set(found))


def load(path: Path) -> Config:
    """Read one settings file and pull every hook handler out of it.

    Structural problems become findings on the Config rather than exceptions:
    the point of the tool is to report on files that are wrong.
    """
    config = Config(source=path)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        config.findings.append(Finding("unreadable", Severity.ERROR, str(exc)))
        return config
    except json.JSONDecodeError as exc:
        config.findings.append(
            Finding("invalid-json", Severity.ERROR, f"line {exc.lineno}: {exc.msg}")
        )
        return config

    if not isinstance(raw, dict):
        config.findings.append(
            Finding("not-an-object", Severity.ERROR, "settings is not an object")
        )
        return config

    hooks_block = raw.get("hooks")
    if hooks_block is None:
        return config
    if not isinstance(hooks_block, dict):
        config.findings.append(
            Finding("hooks-not-an-object", Severity.ERROR, "`hooks` must be an object of events")
        )
        return config

    for event, entries in hooks_block.items():
        _load_event(config, event, entries)

    return config


def _load_event(config: Config, event: str, entries: object) -> None:
    if event not in EVENTS:
        suggestion = suggest_event(event)
        hint = f" — did you mean `{suggestion}`?" if suggestion else ""
        config.findings.append(
            Finding(
                "unknown-event",
                Severity.ERROR,
                f"`{event}` is not a hook event, so nothing here ever runs{hint}",
            )
        )
        return

    if not isinstance(entries, list):
        config.findings.append(
            Finding("event-not-a-list", Severity.ERROR, f"`{event}` must be a list of matchers")
        )
        return

    position = 0
    for entry in entries:
        if not isinstance(entry, dict):
            config.findings.append(
                Finding("entry-not-an-object", Severity.ERROR, f"`{event}` entry is not an object")
            )
            continue

        matcher = entry.get("matcher")
        handlers = entry.get("hooks")
        if handlers is None:
            config.findings.append(
                Finding(
                    "no-handlers",
                    Severity.ERROR,
                    f"`{event}` entry has no `hooks` array, so it does nothing",
                )
            )
            continue
        if not isinstance(handlers, list):
            config.findings.append(
                Finding("handlers-not-a-list", Severity.ERROR, f"`{event}` `hooks` must be a list")
            )
            continue

        for handler in handlers:
            if not isinstance(handler, dict):
                config.findings.append(
                    Finding(
                        "handler-not-an-object", Severity.ERROR, f"`{event}` hook is not an object"
                    )
                )
                continue
            config.hooks.append(
                Hook(
                    source=config.source,
                    event=event,
                    index=position,
                    config=handler,
                    matcher=matcher if isinstance(matcher, str) else None,
                )
            )
            position += 1
