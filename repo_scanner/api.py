"""FastAPI wrapper: POST /analyze with a GitHub URL, get the same JSON back."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .errors import (
    AuthError, ConfigError, EmptyRepoError, GitHubUnavailableError, InvalidRepoURLError, RateLimitError,
    RepositoryNotFoundError, ScannerError, SummarizerError,
)
from .github_client import GitHubClient, parse_repo_url
from .scanner import scan
from .summarizer import Summarizer

app = FastAPI(title="Repo Scanner", version="0.1.0")
STATIC = Path(__file__).parent / "static"

CACHE_SECONDS = 600
LIMIT_PER_MINUTE = int(os.getenv("REPO_SCANNER_LIMIT", "20"))
_cache: dict[tuple[str, int], tuple[float, dict]] = {}
_hits: dict[str, deque] = defaultdict(deque)

STATUS = {
    InvalidRepoURLError: 400,
    EmptyRepoError: 422,
    RepositoryNotFoundError: 404,
    RateLimitError: 429,
    AuthError: 502,
    GitHubUnavailableError: 502,
    SummarizerError: 502,
    ConfigError: 500,
}


class AnalyzeRequest(BaseModel):
    repo_url: str
    depth: int = 2


def _limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= LIMIT_PER_MINUTE:
        return True
    q.append(now)
    return False


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/analyze")
def analyze(body: AnalyzeRequest, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    if _limited(ip):
        raise HTTPException(429, "Too many requests. Wait a minute and try again.")
    depth = max(1, min(5, body.depth))
    try:
        owner, name = parse_repo_url(body.repo_url)
        key = (f"{owner}/{name}".lower(), depth)
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return {**hit[1], "cached": True}
        github = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        try:
            result = scan(body.repo_url, depth, github, Summarizer()).to_dict()
        finally:
            github.close()
    except ScannerError as exc:
        status = STATUS.get(type(exc), 500)
        # Server side config problems should not leak details to visitors.
        hidden = isinstance(exc, (AuthError, ConfigError))
        detail = "The service is not available right now." if hidden else str(exc)
        raise HTTPException(status, detail) from exc
    _cache[key] = (time.time(), result)
    return {**result, "cached": False}
