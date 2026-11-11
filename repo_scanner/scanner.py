"""The scan pipeline shared by the CLI and the API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from .context import build_context
from .errors import EmptyRepoError
from .file_selector import eligible, select_files
from .github_client import GitHubClient, parse_repo_url
from .summarizer import Analysis, Summarizer

log = logging.getLogger("repo_scanner.scanner")


@dataclass
class ScanResult:
    repo: str
    url: str
    analysis: Analysis | None
    files_read: list[str]
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        a = self.analysis
        return {
            "repo": self.repo,
            "url": self.url,
            "summary": a.summary if a else None,
            "technologies": a.technologies if a else [],
            "architecture": a.architecture if a else [],
            "intended_users": a.intended_users if a else [],
            "code_quality": a.code_quality if a else None,
            "files_read": self.files_read,
            "stats": self.stats,
        }


def scan(repo_url: str, depth: int, github: GitHubClient,
         summarizer: Summarizer | None, progress: Callable[[str], None] | None = None
         ) -> ScanResult:
    """Fetch, select, build context, summarize. summarizer=None is a dry run."""
    say = progress or (lambda _msg: None)
    started = time.perf_counter()
    owner, name = parse_repo_url(repo_url)

    say("Fetching repo")
    info = github.get_repo(owner, name)
    entries = github.get_tree(owner, name, info.default_branch)

    say("Selecting files")
    pool = eligible(entries)
    chosen = select_files(entries, depth)
    if not chosen:
        raise EmptyRepoError("No readable files found in this repo, so there is nothing to summarize.")
    contents = [(s.path, s.reason, github.get_file(owner, name, s.path, info.default_branch))
                for s in chosen]

    line = (f"Repo: {owner}/{name}. Description: {info.description or 'none'}. "
            f"Main language: {info.language or 'unknown'}.")
    ctx = build_context(line, contents)

    # Rough size of everything a naive tool would send: all eligible files, 4 chars a token.
    tokens_all_files_est = sum(e.size for e in pool) // 4

    analysis = None
    if summarizer is not None:
        say("Analyzing")
        analysis = summarizer.summarize(ctx.text)
    say("Done")

    stats = {
        "files_in_repo": len(entries),
        "files_eligible": len(pool),
        "files_read": len(chosen),
        "github_calls": github.calls,
        "tokens_all_files_est": tokens_all_files_est,
        "tokens_selected_raw": ctx.tokens_selected_raw,
        "tokens_no_ast": ctx.tokens_no_ast,
        "tokens_sent": ctx.tokens_sent,
        "seconds": round(time.perf_counter() - started, 2),
    }
    return ScanResult(
        repo=f"{owner}/{name}",
        url=f"https://github.com/{owner}/{name}",
        analysis=analysis,
        files_read=[s.path for s in chosen],
        stats=stats,
    )
