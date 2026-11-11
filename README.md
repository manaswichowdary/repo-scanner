# Repo Scanner

[![PyPI](https://img.shields.io/pypi/v/repoprobe)](https://pypi.org/project/repoprobe/)

Point it at a GitHub repo and get a short summary of what it does and how it is built.

```
pip install repoprobe
export OPENAI_API_KEY=...
repo-scanner --repo https://github.com/pallets/flask
```

It does not send the whole repo to the model. It picks a handful of files, turns Python files into
outlines of their classes and functions, and sends only that. This keeps it fast and cheap.

## Usage

```
repo-scanner --repo https://github.com/owner/repo [options]
```

| Flag | What it does |
|---|---|
| `--repo`, `-r` | GitHub URL or `owner/repo` (required) |
| `--format`, `-f` | `text` (Rich panels, default), `json` or `markdown` |
| `--depth`, `-d` | Extra source files to read, 1 to 5 (default 2) |
| `--output`, `-o` | Save the result to a file |
| `--verbose`, `-v` | Debug logging on stderr |
| `--dry-run` | Show the files it would read and the token count, with no model call and no OpenAI key |

Set `GITHUB_TOKEN` to raise the GitHub limit from 60 to 5,000 requests an hour. Set
`REPO_SCANNER_MODEL` to change the model (default `gpt-4o-mini`).

## How it picks files

1. Always the README.
2. One manifest: `pyproject.toml`, `package.json`, `go.mod` and similar.
3. One entry point: `main.py`, `app.py`, `cli.py`, `index.js` and similar.
4. Then `--depth` more source files, ranked by core sounding names (`core`, `api`, `model`,
   `service`, `client`), a useful size, and how close they are to the repo root.

It skips `node_modules`, virtual environments, build output, lock files, docs, migrations and
test files. Python files are parsed with the `ast` module and sent as an outline. A file that
does not parse is sent as raw text instead.

## Output

The same result in three formats: a Rich terminal panel, JSON for scripts, and Markdown for
saving. JSON has `summary`, `technologies`, `architecture` (3 bullets), `intended_users`,
`code_quality`, `files_read` and `stats` (tokens and seconds).

## When something goes wrong

Every failure has a plain message and its own exit code.

| Problem | Exit code | What you see |
|---|---|---|
| Not a GitHub URL | 2 | Tells you the expected format |
| Repo missing or private | 3 | Says it may not exist, or needs a `GITHUB_TOKEN` |
| GitHub rate limit | 4 | Says how many minutes to wait |
| Bad GitHub token | 5 | Asks you to check `GITHUB_TOKEN` |
| GitHub down or no network | 6 | Retries twice, then says it could not reach GitHub |
| Model call or reply failed | 7 | Says the model failed, or returned invalid JSON |
| Missing `OPENAI_API_KEY` | 8 | Says which variable to set |

## Web API

```
pip install "repoprobe[api]"
uvicorn repo_scanner.api:app
```

`POST /analyze` with `{"repo_url": "https://github.com/owner/repo", "depth": 2}` returns the JSON
result. `GET /` serves a small page with a box to paste a URL. Results are cached for 10 minutes
and each IP is limited to 20 requests a minute, to protect the OpenAI bill.

To deploy on Railway, connect the repo and set `OPENAI_API_KEY` (and `GITHUB_TOKEN`). The
`Procfile` and `requirements.txt` are already in place.

## Results

<!-- RESULTS:START -->
Measured on 10 public repos, depth 2, full run with gpt-4o-mini. Tokens are estimated at 4 characters each.

| Repo | Seconds | Files read | Tokens sent | Cut from AST outlines | Cut vs the same files raw | Cut vs every eligible file |
|---|---|---|---|---|---|---|
| pallets/flask | 5.8 | 5 | 2,368 | 47% | 92% | 98% |
| psf/requests | 4.7 | 4 | 2,231 | 39% | 84% | 100% |
| tiangolo/fastapi | 6.1 | 5 | 2,849 | 34% | 81% | 99% |
| Textualize/rich | 4.6 | 5 | 2,979 | 38% | 84% | 100% |
| encode/httpx | 5.9 | 4 | 3,551 | 16% | 83% | 96% |
| pallets/click | 4.7 | 4 | 2,426 | 31% | 85% | 98% |
| expressjs/express | 5.3 | 5 | 4,064 | 0% | 69% | 92% |
| tj/commander.js | 5.4 | 5 | 3,621 | 0% | 80% | 96% |
| axios/axios | 4.2 | 5 | 3,368 | 0% | 89% | 98% |
| gin-gonic/gin | 4.6 | 4 | 3,728 | 0% | 60% | 96% |

- Time: median 5.0 s, slowest 6.1 s. 10 of 10 finished under 15 s.
- Token cut from AST outlines alone, against the same files sent as truncated raw text (Python repos, 6 of them): median 36%. Against the same files in full: median 84%.
- Token cut against sending every eligible file: median 98% (an estimate, not a model count).
<!-- RESULTS:END -->

## Limits

- Outlines work for Python only. Other languages are sent as the first few thousand characters.
- It reads a few files, so it can miss parts of a large repo. A higher `--depth` helps.
- Files are ranked by name, size and location, not by how recently they changed.
- The summary comes from a language model and only sees the files listed in `files_read`.
- Private repos need a `GITHUB_TOKEN` that can read them.

## Development

```
git clone https://github.com/manaswichowdary/repo-scanner
cd repo-scanner
pip install -e ".[dev]"
pytest
```

The tests use a fake GitHub server and a fake model, so they need no keys and no network.

## License

MIT
