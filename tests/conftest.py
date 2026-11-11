import base64
import json

import httpx
import pytest

from repo_scanner.github_client import GitHubClient

FILES = {
    "README.md": "# Demo\nA tiny demo app.\n" * 20,
    "pyproject.toml": "[project]\nname='demo'\n",
    "app.py": '"""Demo app."""\nclass Server:\n    def run(self, port):\n        pass\n\ndef main():\n    pass\n',
    "demo/core.py": "def work(a, b):\n    return a + b\n" * 40,
    "demo/api.py": "async def handler(req):\n    return 1\n" * 40,
    "demo/util.py": "def u():\n    return 1\n" * 30,
    "tests/test_demo.py": "def test_x():\n    assert True\n",
    "node_modules/lib/index.js": "x" * 5000,
    "package-lock.json": "{}" * 3000,
    "logo.png": "binary",
}

GOOD_JSON = json.dumps({
    "summary": "A tiny demo app.",
    "technologies": ["Python"],
    "architecture": ["a", "b", "c", "d"],
    "intended_users": ["Developers"],
    "code_quality": "Small and tidy. No tests shown.",
})


def make_handler(files=None, status=None, headers=None, body=None, branch="main"):
    files = FILES if files is None else files

    def handler(request: httpx.Request) -> httpx.Response:
        if status:
            return httpx.Response(status, headers=headers or {}, text=body or "")
        path = request.url.path
        if path == "/repos/o/r":
            return httpx.Response(200, json={
                "name": "r", "description": "demo", "default_branch": branch,
                "language": "Python", "stargazers_count": 3})
        if path.startswith("/repos/o/r/git/trees/"):
            tree = [{"path": p, "type": "blob", "size": len(c)} for p, c in files.items()]
            return httpx.Response(200, json={"tree": tree, "truncated": False})
        if path.startswith("/repos/o/r/contents/"):
            name = path[len("/repos/o/r/contents/"):]
            if name in files:
                return httpx.Response(200, content=files[name].encode())
        return httpx.Response(404, json={"message": "Not Found"})

    return handler


@pytest.fixture
def gh():
    client = GitHubClient(transport=httpx.MockTransport(make_handler()), retries=1)
    yield client
    client.close()


def client_for(handler, retries=1):
    return GitHubClient(transport=httpx.MockTransport(handler), retries=retries)


class FakeCompletions:
    def __init__(self, reply=GOOD_JSON, exc=None):
        self.reply, self.exc, self.calls = reply, exc, 0

    def create(self, **kwargs):
        self.calls += 1
        if self.exc:
            raise self.exc
        msg = type("M", (), {"content": self.reply})
        return type("R", (), {"choices": [type("C", (), {"message": msg})]})


class FakeOpenAI:
    def __init__(self, reply=GOOD_JSON, exc=None):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(reply, exc)
