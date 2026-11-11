import time

import httpx
import pytest

from repo_scanner.errors import (
    AuthError, GitHubUnavailableError, RateLimitError, RepositoryNotFoundError,
)
from tests.conftest import client_for, make_handler


def test_reads_repo_tree_and_file(gh):
    info = gh.get_repo("o", "r")
    assert info.default_branch == "main" and info.stars == 3
    tree = gh.get_tree("o", "r", "main")
    assert "app.py" in [t.path for t in tree]
    assert gh.get_file("o", "r", "app.py", "main").startswith('"""Demo')


def test_404_is_repository_not_found():
    c = client_for(make_handler(status=404))
    with pytest.raises(RepositoryNotFoundError, match="private"):
        c.get_repo("o", "r")


def test_bad_token_is_auth_error():
    c = client_for(make_handler(status=401))
    with pytest.raises(AuthError):
        c.get_repo("o", "r")


def test_rate_limit_reports_wait_time():
    reset = str(int(time.time()) + 600)
    c = client_for(make_handler(status=403, headers={
        "x-ratelimit-remaining": "0", "x-ratelimit-reset": reset}))
    with pytest.raises(RateLimitError) as e:
        c.get_repo("o", "r")
    assert "Try again in about" in str(e.value)
    assert "GITHUB_TOKEN" in str(e.value)
    assert 590 <= e.value.retry_after <= 600


def test_403_without_rate_limit_is_access_denied():
    c = client_for(make_handler(status=403, body="Repository access blocked"))
    with pytest.raises(RepositoryNotFoundError, match="denied"):
        c.get_repo("o", "r")


def test_server_errors_retry_then_fail():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    c = client_for(handler, retries=2)
    with pytest.raises(GitHubUnavailableError):
        c.get_repo("o", "r")
    assert len(calls) == 3


def test_recovers_after_one_server_error():
    state = {"n": 0}
    good = make_handler()

    def handler(request):
        state["n"] += 1
        return httpx.Response(502) if state["n"] == 1 else good(request)

    c = client_for(handler, retries=2)
    assert c.get_repo("o", "r").name == "r"


def test_network_down_is_github_unavailable():
    def handler(request):
        raise httpx.ConnectError("no route")

    c = client_for(handler, retries=1)
    with pytest.raises(GitHubUnavailableError, match="Could not reach GitHub"):
        c.get_repo("o", "r")


def test_truncated_tree_still_finds_root_and_source_files():
    def handler(request):
        path = request.url.path
        recursive = request.url.params.get("recursive")
        if path == "/repos/o/r/git/trees/main" and recursive:
            return httpx.Response(200, json={"truncated": True, "tree": [
                {"path": "docs/a.md", "type": "blob", "size": 5}]})
        if path == "/repos/o/r/git/trees/main":
            return httpx.Response(200, json={"tree": [
                {"path": "README.md", "type": "blob", "size": 100},
                {"path": "r", "type": "tree", "sha": "abc"},
                {"path": "docs", "type": "tree", "sha": "def"}]})
        if path == "/repos/o/r/git/trees/abc":
            return httpx.Response(200, json={"tree": [
                {"path": "core.py", "type": "blob", "size": 900}]})
        return httpx.Response(404)

    paths = [e.path for e in client_for(handler).get_tree("o", "r", "main")]
    assert "README.md" in paths and "r/core.py" in paths and "docs/a.md" in paths


def test_renamed_repo_redirect_is_followed():
    good = make_handler()

    def handler(request):
        if request.url.path == "/repos/old/r":
            return httpx.Response(301, headers={"location": "https://api.github.com/repos/o/r"})
        return good(request)

    assert client_for(handler).get_repo("old", "r").name == "r"


def test_unfollowed_redirect_is_an_error_not_an_empty_repo():
    c = client_for(make_handler(status=302))
    c._http.follow_redirects = False
    with pytest.raises(GitHubUnavailableError, match="redirect"):
        c.get_repo("o", "r")
