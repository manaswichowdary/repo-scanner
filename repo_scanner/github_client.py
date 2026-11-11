"""Small GitHub REST client with clear errors for every failure case."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

from .errors import (
    AuthError,
    GitHubUnavailableError,
    InvalidRepoURLError,
    RateLimitError,
    RepositoryNotFoundError,
)

log = logging.getLogger("repo_scanner.github")

API = "https://api.github.com"
_URL = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$"
)
_SHORT = re.compile(r"^([\w.-]+)/([\w.-]+)$")


def parse_repo_url(value: str) -> tuple[str, str]:
    """Accept https://github.com/o/r, github.com/o/r(.git) or o/r."""
    value = (value or "").strip()
    match = _URL.match(value) or _SHORT.match(value)
    if not match:
        raise InvalidRepoURLError(
            f"'{value}' is not a GitHub repo. Use https://github.com/owner/repo"
        )
    return match.group(1), match.group(2)


@dataclass
class RepoInfo:
    owner: str
    name: str
    description: str
    default_branch: str
    language: str
    stars: int


@dataclass
class TreeEntry:
    path: str
    size: int


class GitHubClient:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None,
                 retries: int = 2, timeout: float = 15.0):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "repo-scanner",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.has_token = bool(token)
        self.retries = retries
        self.calls = 0
        self._http = httpx.Client(base_url=API, headers=headers, timeout=timeout,
                                  transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, **kwargs) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            self.calls += 1
            try:
                resp = self._http.get(path, **kwargs)
            except httpx.TransportError as exc:
                last = exc
                log.debug("network error on %s (attempt %d): %s", path, attempt + 1, exc)
                time.sleep(0.2 * (attempt + 1))
                continue
            if resp.status_code >= 500:
                last = GitHubUnavailableError(f"GitHub returned {resp.status_code}")
                log.debug("GitHub %s on %s (attempt %d)", resp.status_code, path, attempt + 1)
                time.sleep(0.2 * (attempt + 1))
                continue
            return self._check(resp)
        raise GitHubUnavailableError(
            "Could not reach GitHub. Check your connection and try again."
        ) from last

    def _check(self, resp: httpx.Response) -> httpx.Response:
        code = resp.status_code
        if code < 300:
            return resp
        if code < 400:
            raise GitHubUnavailableError(f"GitHub sent an unexpected redirect ({code}).")
        if code == 401:
            raise AuthError("GitHub rejected the token. Check GITHUB_TOKEN.")
        if code in (403, 429):
            remaining = resp.headers.get("x-ratelimit-remaining")
            if remaining == "0" or code == 429 or "rate limit" in resp.text.lower():
                reset = resp.headers.get("x-ratelimit-reset")
                retry = resp.headers.get("retry-after")
                wait = None
                if retry and retry.isdigit():
                    wait = int(retry)
                elif reset and reset.isdigit():
                    wait = max(0, int(reset) - int(time.time()))
                hint = f" Try again in about {wait // 60 + 1} min." if wait is not None else ""
                tip = "" if self.has_token else " Set GITHUB_TOKEN to raise the limit."
                raise RateLimitError(f"GitHub rate limit reached.{hint}{tip}", retry_after=wait)
            raise RepositoryNotFoundError(
                "GitHub denied access. The repo may be private or blocked."
            )
        if code == 404:
            raise RepositoryNotFoundError(
                "Repo not found. It may not exist, or it is private "
                "(private repos need a GITHUB_TOKEN with access)."
            )
        raise GitHubUnavailableError(f"GitHub returned an unexpected {code}.")

    def get_repo(self, owner: str, name: str) -> RepoInfo:
        data = self._get(f"/repos/{owner}/{name}").json()
        return RepoInfo(
            owner=owner,
            name=data.get("name", name),
            description=data.get("description") or "",
            default_branch=data.get("default_branch") or "main",
            language=data.get("language") or "",
            stars=int(data.get("stargazers_count") or 0),
        )

    def get_tree(self, owner: str, name: str, branch: str) -> list[TreeEntry]:
        data = self._get(f"/repos/{owner}/{name}/git/trees/{branch}",
                         params={"recursive": "1"}).json()
        entries = [
            TreeEntry(path=item["path"], size=int(item.get("size") or 0))
            for item in data.get("tree", [])
            if item.get("type") == "blob"
        ]
        if data.get("truncated"):
            log.debug("tree for %s/%s was truncated, reading the root and source dirs", owner, name)
            entries = self._fill_truncated(owner, name, branch, entries)
        return entries

    def _fill_truncated(self, owner: str, name: str, branch: str,
                        entries: list[TreeEntry]) -> list[TreeEntry]:
        """Huge repos get a cut off listing. Read the root, then the likely source dirs."""
        have = {e.path for e in entries}
        root = self._get(f"/repos/{owner}/{name}/git/trees/{branch}").json().get("tree", [])
        for item in root:
            if item.get("type") == "blob" and item["path"] not in have:
                entries.append(TreeEntry(item["path"], int(item.get("size") or 0)))
                have.add(item["path"])
        wanted = {name.lower().replace("-", "_"), name.lower(), "src", "lib", "app", "packages"}
        dirs = [i for i in root if i.get("type") == "tree" and i["path"].lower() in wanted][:3]
        for d in dirs:
            sub = self._get(f"/repos/{owner}/{name}/git/trees/{d['sha']}",
                            params={"recursive": "1"}).json().get("tree", [])
            for item in sub:
                path = f"{d['path']}/{item['path']}"
                if item.get("type") == "blob" and path not in have:
                    entries.append(TreeEntry(path, int(item.get("size") or 0)))
                    have.add(path)
        return entries

    def get_file(self, owner: str, name: str, path: str, ref: str) -> str:
        resp = self._get(
            f"/repos/{owner}/{name}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        return resp.content.decode("utf-8", errors="replace")
