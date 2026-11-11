"""Pick the few files that explain a repo, and skip everything else."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .github_client import TreeEntry

EXCLUDED_DIRS = {
    "node_modules", "venv", ".venv", "env", ".git", "dist", "build", "__pycache__",
    ".next", "vendor", "target", ".tox", ".idea", ".vscode", "site-packages",
    ".mypy_cache", ".pytest_cache", "coverage", ".github", "migrations", "docs",
}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}
LOCKFILES = {
    "package-lock.json", "yarn.lock", "poetry.lock", "pnpm-lock.yaml", "cargo.lock",
    "pipfile.lock", "uv.lock", "composer.lock", "gemfile.lock",
}
MANIFESTS = [
    "pyproject.toml", "package.json", "setup.py", "go.mod", "cargo.toml",
    "pom.xml", "build.gradle", "requirements.txt",
]
ENTRY_POINTS = [
    "main.py", "app.py", "__main__.py", "cli.py", "manage.py", "server.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "app.js",
    "main.go", "main.rs", "main.java", "application.java",
]
SOURCE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
    ".php", ".c", ".cpp", ".cs", ".swift",
}
HINTS = ("core", "app", "api", "model", "service", "route", "client", "engine", "server")
MAX_FILE_BYTES = 100_000


@dataclass
class Selected:
    path: str
    reason: str


def _parts(path: str) -> list[str]:
    return [p.lower() for p in PurePosixPath(path).parts]


def is_excluded(path: str) -> bool:
    parts = _parts(path)
    return any(p in EXCLUDED_DIRS for p in parts[:-1])


def is_test(path: str) -> bool:
    parts = _parts(path)
    name = parts[-1]
    if any(p in TEST_DIRS for p in parts[:-1]):
        return True
    return (name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.ts",
            ".spec.js", ".spec.ts", "_test.go")))


def eligible(entries: list[TreeEntry]) -> list[TreeEntry]:
    """Files that could ever be useful: not excluded, not tests, not locks."""
    out = []
    for e in entries:
        name = PurePosixPath(e.path).name.lower()
        if is_excluded(e.path) or is_test(e.path) or name in LOCKFILES:
            continue
        out.append(e)
    return out


def _is_source(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in SOURCE_EXT


def select_files(entries: list[TreeEntry], depth: int = 2) -> list[Selected]:
    """README, one manifest, one entry point, then `depth` more source files."""
    files = eligible(entries)
    chosen: list[Selected] = []
    seen: set[str] = set()

    def add(path: str, reason: str) -> None:
        if path not in seen:
            seen.add(path)
            chosen.append(Selected(path, reason))

    root = [e for e in files if "/" not in e.path]

    readmes = sorted((e for e in root if e.path.lower().startswith("readme")),
                     key=lambda e: e.path.lower())
    if readmes:
        add(readmes[0].path, "readme")

    names = {e.path.lower(): e.path for e in root}
    for manifest in MANIFESTS:
        if manifest in names:
            add(names[manifest], "manifest")
            break

    entries_sorted = sorted(files, key=lambda e: (e.path.count("/"), e.path))
    for want in ENTRY_POINTS:
        match = next((e for e in entries_sorted
                      if PurePosixPath(e.path).name.lower() == want
                      and 0 < e.size <= MAX_FILE_BYTES), None)
        if match:
            add(match.path, "entry point")
            break

    def score(e: TreeEntry) -> tuple:
        name = PurePosixPath(e.path).name.lower()
        hint = any(h in name for h in HINTS)
        good_size = 500 <= e.size <= 30_000
        return (-int(hint), -int(good_size), e.path.count("/"), -e.size, e.path)

    candidates = [e for e in files
                  if _is_source(e.path) and 0 < e.size <= MAX_FILE_BYTES
                  and e.path not in seen]
    for e in sorted(candidates, key=score)[:depth]:
        add(e.path, "core source")
    return chosen
