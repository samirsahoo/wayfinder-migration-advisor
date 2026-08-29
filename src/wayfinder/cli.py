"""Command-line entry point.

    wayfinder run examples/legacy_trading_platform.yaml
    wayfinder run examples/legacy_trading_platform.yaml --auto-approve
    wayfinder run examples/legacy_trading_platform.yaml --out report.md

Runs the full agent graph against a SystemProfile YAML file, prints a live
trace of each agent as it completes, pauses at the governance gate for a
human decision (unless ``--auto-approve``/``--reject`` is passed, which is
what makes this scriptable/testable), then writes the final Markdown report.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel

from .graph import Command, build_graph
from .models import SystemProfile
from .report import render_markdown

console = Console()


def load_profile(path: Path) -> SystemProfile:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SystemProfile.model_validate(data)


def _prompt_for_decision(payload: dict) -> dict:
    console.print(Panel.fit(
        f"[bold]{payload['system_name']}[/bold]\n"
        f"Readiness: {payload['readiness_score']}/100  |  "
        f"Pattern: {payload['migration_pattern']}  |  "
        f"Cost tier: {payload['cost_tier']}  |  "
        f"Escalated: {payload['escalated']}\n"
        + (f"[red]Critical risks: {'; '.join(payload['critical_risks'])}[/red]\n" if payload["critical_risks"] else "")
        + "\n" + payload["prompt"],
        title="Governance gate -- human approval required",
        border_style="yellow",
    ))
    raw = console.input("[bold]approve / reject[/bold] > ").strip().lower()
    status = "approved" if raw.startswith("a") else "changes_requested"
    note = "" if status == "approved" else console.input("Reviewer note > ").strip()
    return {"status": status, "note": note}


def run_command(args: argparse.Namespace) -> int:
    profile = load_profile(Path(args.profile))
    app = build_graph()
    thread_id = args.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    console.rule(f"[bold blue]Wayfinder[/bold blue] -- assessing {profile.name}")

    state = app.invoke({"profile": profile, "escalated": False}, config=config)

    for label in ("discovery", "architecture", "risk", "cost"):
        if label in state:
            console.print(f"  [green]done[/green] {label}")

    if "__interrupt__" not in state:
        console.print("[red]Graph finished without reaching the governance gate -- unexpected.[/red]")
        return 1

    if args.auto_approve:
        decision = {"status": "approved", "note": ""}
    elif args.reject:
        decision = {"status": "changes_requested", "note": args.reject}
    else:
        payload = state["__interrupt__"][0].value
        decision = _prompt_for_decision(payload)

    final_state = app.invoke(Command(resume=decision), config=config)
    report = final_state["report"]

    markdown = render_markdown(
        profile=profile,
        discovery=final_state["discovery"],
        architecture=final_state["architecture"],
        risk=final_state["risk"],
        cost=final_state["cost"],
        report=report,
    )

    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        console.print(f"\n[bold green]Report written to {args.out}[/bold green]")
    else:
        console.print()
        console.print(markdown)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wayfinder", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run the advisory graph against a SystemProfile YAML file")
    run_parser.add_argument("profile", help="Path to a SystemProfile YAML file")
    run_parser.add_argument("--out", help="Write the Markdown report to this path instead of stdout")
    run_parser.add_argument("--auto-approve", action="store_true", help="Skip the interactive gate; approve automatically")
    run_parser.add_argument("--reject", metavar="NOTE", help="Skip the interactive gate; request changes with NOTE")
    run_parser.add_argument("--thread-id", help="Reuse a specific LangGraph thread id (advanced)")
    run_parser.set_defaults(func=run_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
