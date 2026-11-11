import json

import httpx
import pytest

from repo_scanner import cli
from repo_scanner.github_client import GitHubClient
from tests.conftest import FakeOpenAI, make_handler


@pytest.fixture
def wired(monkeypatch):
    def install(handler=None, openai=None):
        handler = handler or make_handler()
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setattr(cli, "GitHubClient",
                            lambda token=None: GitHubClient(transport=httpx.MockTransport(handler), retries=0))
        monkeypatch.setattr(cli, "Summarizer", lambda: __import__(
            "repo_scanner.summarizer", fromlist=["Summarizer"]).Summarizer(client=openai or FakeOpenAI()))
    return install


def test_json_output(wired, capsys):
    wired()
    assert cli.main(["--repo", "o/r", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["repo"] == "o/r"


def test_markdown_to_file(wired, tmp_path, capsys):
    wired()
    out = tmp_path / "r.md"
    assert cli.main(["-r", "o/r", "-f", "markdown", "-o", str(out)]) == 0
    assert out.read_text().startswith("# o/r")


def test_text_output_prints_panel(wired, capsys):
    wired()
    assert cli.main(["-r", "o/r"]) == 0
    assert "A tiny demo app." in capsys.readouterr().out


def test_dry_run_needs_no_key(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "GitHubClient",
                        lambda token=None: GitHubClient(transport=httpx.MockTransport(make_handler()), retries=0))
    assert cli.main(["-r", "o/r", "--dry-run", "-f", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"] is None


@pytest.mark.parametrize("args,code,text", [
    (["-r", "nonsense"], 2, "not a GitHub repo"),
])
def test_bad_url_exit_code(wired, capsys, args, code, text):
    wired()
    assert cli.main(args) == code
    assert text in capsys.readouterr().err


def test_not_found_exit_code(wired, capsys):
    wired(handler=make_handler(status=404))
    assert cli.main(["-r", "o/r"]) == 3
    assert "not found" in capsys.readouterr().err.lower()


def test_rate_limit_exit_code(wired, capsys):
    wired(handler=make_handler(status=429))
    assert cli.main(["-r", "o/r"]) == 4


def test_model_failure_exit_code(wired, capsys):
    wired(openai=FakeOpenAI(exc=RuntimeError("x")))
    assert cli.main(["-r", "o/r"]) == 7


def test_missing_openai_key_exit_code(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(["-r", "o/r"]) == 8


def test_depth_flag_rejects_out_of_range():
    with pytest.raises(SystemExit):
        cli.main(["-r", "o/r", "-d", "9"])
