import httpx
import pytest
from fastapi.testclient import TestClient

from repo_scanner import api
from repo_scanner.github_client import GitHubClient
from repo_scanner.summarizer import Summarizer
from tests.conftest import FakeOpenAI, make_handler


@pytest.fixture
def client(monkeypatch):
    api._cache.clear()
    api._hits.clear()
    state = {"handler": make_handler(), "openai": FakeOpenAI()}
    monkeypatch.setattr(api, "GitHubClient",
                        lambda token=None: GitHubClient(transport=httpx.MockTransport(state["handler"]), retries=0))
    monkeypatch.setattr(api, "Summarizer", lambda: Summarizer(client=state["openai"]))
    c = TestClient(api.app)
    c.state = state
    return c


def test_health_and_home(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "Repo Scanner" in client.get("/").text


def test_analyze_ok_then_cached(client):
    r = client.post("/analyze", json={"repo_url": "https://github.com/o/r"})
    assert r.status_code == 200 and r.json()["cached"] is False
    assert client.post("/analyze", json={"repo_url": "o/r"}).json()["cached"] is True
    assert client.state["openai"].chat.completions.calls == 1


def test_bad_url_is_400(client):
    assert client.post("/analyze", json={"repo_url": "nope"}).status_code == 400


def test_missing_repo_is_404(client):
    client.state["handler"] = make_handler(status=404)
    assert client.post("/analyze", json={"repo_url": "o/r"}).status_code == 404


def test_github_rate_limit_is_429(client):
    client.state["handler"] = make_handler(status=429)
    assert client.post("/analyze", json={"repo_url": "o/r"}).status_code == 429


def test_model_failure_is_502(client):
    client.state["openai"] = FakeOpenAI(exc=RuntimeError("x"))
    assert client.post("/analyze", json={"repo_url": "o/r"}).status_code == 502


def test_per_ip_limit(client, monkeypatch):
    monkeypatch.setattr(api, "LIMIT_PER_MINUTE", 2)
    codes = [client.post("/analyze", json={"repo_url": "o/r"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
