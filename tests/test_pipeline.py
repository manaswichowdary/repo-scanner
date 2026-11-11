import json

import pytest

from repo_scanner.context import build_context
from repo_scanner.errors import ConfigError, SummarizerError
from repo_scanner.formatter import render_json, render_markdown
from repo_scanner.scanner import scan
from repo_scanner.summarizer import Summarizer, parse_analysis
from tests.conftest import FILES, FakeOpenAI, GOOD_JSON


def test_python_files_are_sent_as_outlines_and_cut_tokens():
    big = "".join(
        f"def handler_{i}(request, user):\n"
        + "    value = request.get('field')\n    if value is None:\n        return None\n"
        + "    total = 0\n    for item in value:\n        total += item * user\n    return total\n\n"
        for i in range(40)
    )
    ctx = build_context("repo", [("a.py", "core source", big)])
    assert "[python outline]" in ctx.text
    assert ctx.tokens_sent < ctx.tokens_selected_raw * 0.5


def test_broken_python_falls_back_to_raw_text():
    ctx = build_context("repo", [("a.py", "core source", "def broken(:\n")])
    assert "def broken(:" in ctx.text and "[python outline]" not in ctx.text


def test_summarizer_parses_and_trims_architecture_to_three():
    a = parse_analysis(GOOD_JSON)
    assert a.summary and len(a.architecture) == 3


@pytest.mark.parametrize("raw", ["not json", "[]", json.dumps({"technologies": []}), None])
def test_bad_model_replies_raise_summarizer_error(raw):
    with pytest.raises(SummarizerError):
        parse_analysis(raw)


def test_model_failure_becomes_summarizer_error():
    s = Summarizer(client=FakeOpenAI(exc=RuntimeError("boom")))
    with pytest.raises(SummarizerError, match="RuntimeError"):
        s.summarize("ctx")


def test_missing_key_is_config_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        Summarizer()


def test_full_scan_with_fakes(gh):
    result = scan("https://github.com/o/r", 2, gh, Summarizer(client=FakeOpenAI()))
    assert result.repo == "o/r"
    assert result.files_read[:3] == ["README.md", "pyproject.toml", "app.py"]
    assert result.stats["tokens_sent"] < result.stats["tokens_all_files_est"]
    assert result.analysis.summary == "A tiny demo app."
    assert "node_modules/lib/index.js" not in result.files_read


def test_dry_run_makes_no_model_call(gh):
    result = scan("o/r", 1, gh, None)
    assert result.analysis is None and result.stats["files_read"] == 4


def test_json_and_markdown_outputs(gh):
    result = scan("o/r", 1, gh, Summarizer(client=FakeOpenAI()))
    data = json.loads(render_json(result))
    assert data["summary"] == "A tiny demo app." and "stats" in data
    md = render_markdown(result)
    assert md.startswith("# o/r") and "## Architecture" in md and "- `app.py`" in md


def test_repo_with_no_readable_files_is_an_error_not_an_empty_summary():
    import httpx
    from repo_scanner.errors import EmptyRepoError
    from tests.conftest import client_for, make_handler
    gh = client_for(make_handler(files={"logo.png": "x", "node_modules/a.js": "y"}))
    with pytest.raises(EmptyRepoError):
        scan("o/r", 2, gh, Summarizer(client=FakeOpenAI()))


def test_ast_outline_cut_is_measured_against_plain_truncated_text():
    big = "".join(
        f"def handler_{i}(request, user):\n"
        + "    value = request.get('field')\n    if value is None:\n        return None\n"
        + "    total = 0\n    for item in value:\n        total += item * user\n    return total\n\n"
        for i in range(60)
    )
    ctx = build_context("repo", [("a.py", "core source", big)])
    assert 0 < ctx.tokens_sent < ctx.tokens_no_ast <= ctx.tokens_selected_raw


def test_outline_of_a_huge_file_is_capped():
    big = "".join(f"def handler_number_{i}(request):\n    return 1\n" for i in range(2000))
    ctx = build_context("repo", [("a.py", "core source", big)])
    assert ctx.tokens_sent < 1500
