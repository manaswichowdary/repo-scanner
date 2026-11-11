"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from rich.console import Console

from . import __version__
from .errors import ScannerError
from .formatter import FORMATS, render, render_text
from .github_client import GitHubClient
from .scanner import scan
from .summarizer import Summarizer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="repo-scanner",
        description="Summarize the architecture of any public GitHub repo.",
        epilog="Example: repo-scanner --repo https://github.com/pallets/flask --format markdown",
    )
    p.add_argument("--repo", "-r", required=True, help="GitHub URL or owner/repo")
    p.add_argument("--format", "-f", choices=FORMATS, default="text")
    p.add_argument("--depth", "-d", type=int, choices=range(1, 6), default=2,
                   help="extra source files to read, 1 to 5 (default 2)")
    p.add_argument("--output", "-o", help="save the result to this file")
    p.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    p.add_argument("--dry-run", action="store_true",
                   help="select files and count tokens without calling the model")
    p.add_argument("--version", action="version", version=f"repo-scanner {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(name)s: %(message)s", stream=sys.stderr)
    err = Console(stderr=True)
    out = Console()
    github = None
    try:
        summarizer = None if args.dry_run else Summarizer()
        github = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        with err.status("Starting...") as status:
            result = scan(args.repo, args.depth, github, summarizer,
                          progress=lambda m: status.update(m + "..."))
    except ScannerError as exc:
        err.print(f"[red]error:[/red] {exc}")
        return exc.exit_code
    finally:
        if github:
            github.close()

    if args.output:
        if args.format == "text":
            with open(args.output, "w", encoding="utf-8") as fh:
                render_text(result, Console(file=fh, width=100))
        else:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(render(result, args.format, out) or "")
        err.print(f"Saved to {args.output}")
        return 0

    text = render(result, args.format, out)
    if text is not None:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
