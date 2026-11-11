import pytest

from repo_scanner.errors import InvalidRepoURLError
from repo_scanner.github_client import parse_repo_url


@pytest.mark.parametrize("value", [
    "https://github.com/pallets/flask",
    "http://github.com/pallets/flask/",
    "github.com/pallets/flask.git",
    "https://www.github.com/pallets/flask/tree/main/src",
    "pallets/flask",
])
def test_valid_urls(value):
    assert parse_repo_url(value) == ("pallets", "flask")


@pytest.mark.parametrize("value", ["", "not a url", "https://gitlab.com/a/b", "https://github.com/onlyowner"])
def test_invalid_urls(value):
    with pytest.raises(InvalidRepoURLError):
        parse_repo_url(value)
