"""Three ways to show a result: Rich terminal, JSON, Markdown."""

from __future__ import annotations

import json

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

from .scanner import ScanResult

FORMATS = ("text", "json", "markdown")


def render_json(result: ScanResult) -> str:
    return json.dumps(result.to_dict(), indent=2)


def render_markdown(result: ScanResult) -> str:
    a = result.analysis
    if a is None:
        return (f"# {result.repo}\n\nDry run. Files that would be read:\n\n"
                + "\n".join(f"- `{p}`" for p in result.files_read) + "\n")
    lines = [f"# {result.repo}", "", f"> {a.summary}", "", "## Technologies", ""]
    lines += [f"- {t}" for t in a.technologies] or ["- none found"]
    lines += ["", "## Architecture", ""] + [f"- {b}" for b in a.architecture]
    lines += ["", "## Intended users", ""] + [f"- {u}" for u in a.intended_users]
    lines += ["", "## Code quality", "", a.code_quality, "", "## Files read", ""]
    lines += [f"- `{p}`" for p in result.files_read]
    return "\n".join(lines) + "\n"


def render_text(result: ScanResult, console: Console) -> None:
    a = result.analysis
    if a is None:
        table = Table(title=f"Dry run: {result.repo}")
        table.add_column("File to read")
        for p in result.files_read:
            table.add_row(p)
        console.print(table)
        console.print(f"Tokens that would be sent: {result.stats['tokens_sent']}")
        return
    tech = Table(show_header=False, box=None)
    tech.add_row("Technologies", ", ".join(a.technologies) or "none found")
    tech.add_row("Intended users", ", ".join(a.intended_users) or "unknown")
    arch = "\n".join(f"- {b}" for b in a.architecture)
    console.print(Panel(Group(a.summary, "", tech, "", "[bold]Architecture[/bold]", arch,
                              "", "[bold]Code quality[/bold]", a.code_quality),
                        title=f"[bold cyan]{result.repo}[/bold cyan]", border_style="cyan"))
    s = result.stats
    console.print(f"[dim]{s['files_read']} files read, {s['tokens_sent']} tokens sent, "
                  f"{s['seconds']} s[/dim]")


def render(result: ScanResult, fmt: str, console: Console) -> str | None:
    """Return a string for json/markdown. For text, print and return None."""
    if fmt == "json":
        return render_json(result)
    if fmt == "markdown":
        return render_markdown(result)
    render_text(result, console)
    return None
