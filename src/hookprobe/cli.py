"""Command line entry point."""

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text

from hookprobe.loader import Config
from hookprobe.model import Severity

_SEVERITY_STYLE = {Severity.ERROR: "bold red", Severity.WARN: "yellow", Severity.INFO: "dim"}
_SEVERITY_MARK = {Severity.ERROR: "x", Severity.WARN: "!", Severity.INFO: "-"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hookprobe",
        description=(
            "Lint Claude Code hooks: wrong event names, dead matchers, "
            "hooks that silently never fire."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="a settings.json, or a directory to search (default: the current directory)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="what ${CLAUDE_PROJECT_DIR} resolves to (default: the settings file's directory)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warn", "never"),
        default="error",
        help="exit non-zero at this severity or worse (default: error)",
    )
    return parser


def _payload(configs: list[Config]) -> dict:
    return {
        "files": [
            {
                "path": str(config.source),
                "findings": [
                    {"code": f.code, "severity": f.severity.value, "message": f.message}
                    for f in config.findings
                ],
                "hooks": [
                    {
                        "event": hook.event,
                        "type": hook.kind,
                        "matcher": hook.matcher,
                        "findings": [
                            {"code": f.code, "severity": f.severity.value, "message": f.message}
                            for f in hook.findings
                        ],
                    }
                    for hook in config.hooks
                ],
            }
            for config in configs
        ]
    }


def render(console: Console, configs: list[Config]) -> None:
    total_hooks = 0
    total_findings = 0

    for config in configs:
        console.print(Text(str(config.source), style="bold"))

        for finding in config.findings:
            total_findings += 1
            console.print(
                Text(
                    f"  {_SEVERITY_MARK[finding.severity]} ",
                    style=_SEVERITY_STYLE[finding.severity],
                )
                + Text(finding.message)
            )

        for hook in config.hooks:
            total_hooks += 1
            if not hook.findings:
                continue
            console.print(Text(f"  {hook.label}", style="cyan"))
            for finding in sorted(hook.findings, key=lambda f: -f.severity.rank):
                total_findings += 1
                console.print(
                    Text(
                        f"    {_SEVERITY_MARK[finding.severity]} ",
                        style=_SEVERITY_STYLE[finding.severity],
                    )
                    + Text(finding.message)
                )

        if not config.findings and not any(h.findings for h in config.hooks):
            console.print(Text("  clean", style="dim green"))
        console.print()

    summary = Text()
    summary.append(f"{total_hooks} hooks", style="bold")
    summary.append(f" across {len(configs)} file(s), ", style="dim")
    summary.append(
        f"{total_findings} finding(s)", style="bold red" if total_findings else "bold green"
    )
    console.print(summary)


def main(argv: list[str] | None = None) -> int:
    from hookprobe.checks import analyze

    args = build_parser().parse_args(argv)
    console = Console()

    if not args.path.exists():
        console.print(f"[bold red]no such path:[/] {args.path}", highlight=False)
        return 2

    configs = analyze(args.path, args.project_dir)
    if not configs:
        console.print(f"[yellow]no settings files found under[/] {args.path}", highlight=False)
        return 0

    if args.json:
        print(json.dumps(_payload(configs), indent=2))
    else:
        render(console, configs)

    if args.fail_on == "never":
        return 0
    threshold = Severity.ERROR if args.fail_on == "error" else Severity.WARN
    hit = any(
        f.severity.rank >= threshold.rank
        for config in configs
        for f in list(config.findings) + [x for h in config.hooks for x in h.findings]
    )
    return 1 if hit else 0


if __name__ == "__main__":
    sys.exit(main())
