import json

import pytest


@pytest.fixture
def settings(tmp_path):
    """Write a settings.json containing the given hooks block."""

    def _write(hooks: dict, name: str = "settings.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def one_hook(settings):
    """A settings file with a single handler under one event."""

    def _write(event: str, handler: dict, matcher: str | None = None):
        entry: dict = {"hooks": [handler]}
        if matcher is not None:
            entry["matcher"] = matcher
        return settings({event: [entry]})

    return _write


def codes(items) -> set[str]:
    return {f.code for f in items}
