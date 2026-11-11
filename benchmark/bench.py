"""Measure speed and token savings on real public repos.

Needs OPENAI_API_KEY (unless --dry-run) and, ideally, GITHUB_TOKEN.
    python benchmark/bench.py
    python benchmark/bench.py --write-readme
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_scanner.errors import ScannerError  # noqa: E402
from repo_scanner.github_client import GitHubClient  # noqa: E402
from repo_scanner.scanner import scan  # noqa: E402
from repo_scanner.summarizer import Summarizer  # noqa: E402

REPOS = [
    ("pallets/flask", "py"), ("psf/requests", "py"), ("tiangolo/fastapi", "py"),
    ("Textualize/rich", "py"), ("encode/httpx", "py"), ("pallets/click", "py"),
    ("expressjs/express", "js"), ("tj/commander.js", "js"),
    ("axios/axios", "js"), ("gin-gonic/gin", "go"),
]
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="skip the model call")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--write-readme", action="store_true")
    args = ap.parse_args()

    summarizer = None if args.dry_run else Summarizer()
    rows = []
    for repo, lang in REPOS:
        github = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        t0 = time.perf_counter()
        try:
            r = scan(repo, args.depth, github, summarizer)
        except ScannerError as exc:
            print(f"{repo}: FAILED {exc}")
            continue
        finally:
            github.close()
        wall = time.perf_counter() - t0
        s = r.stats
        if s["files_read"] == 0:
            print(f"{repo}: FAILED read no files")
            continue
        row = {
            "repo": repo, "lang": lang, "seconds": round(wall, 1),
            "files_read": s["files_read"], "tokens_all": s["tokens_all_files_est"],
            "tokens_selected_raw": s["tokens_selected_raw"], "tokens_no_ast": s["tokens_no_ast"],
            "cut_from_ast": round(100 * (1 - s["tokens_sent"] / max(1, s["tokens_no_ast"]))), "tokens_sent": s["tokens_sent"],
            "cut_vs_selected_raw": round(100 * (1 - s["tokens_sent"] / max(1, s["tokens_selected_raw"]))),
            "cut_vs_all": round(100 * (1 - s["tokens_sent"] / max(1, s["tokens_all_files_est"]))),
        }
        rows.append(row)
        print(f"{repo:22} {row['seconds']:>5}s  sent {row['tokens_sent']:>6}  "
              f"cut vs selected {row['cut_vs_selected_raw']}%  vs all {row['cut_vs_all']}%")

    if not rows:
        print("No successful runs.")
        return 1
    Path(__file__).with_name("results.json").write_text(json.dumps(rows, indent=2))

    secs = [r["seconds"] for r in rows]
    py = [r["cut_from_ast"] for r in rows if r["lang"] == "py"]
    py_all = [r["cut_vs_selected_raw"] for r in rows if r["lang"] == "py"]
    lines = [
        f"Measured on {len(rows)} public repos, depth {args.depth}, "
        f"{'dry run (no model call)' if args.dry_run else 'full run with ' + summarizer.model}. "
        "Tokens are estimated at 4 characters each.",
        "",
        "| Repo | Seconds | Files read | Tokens sent | Cut from AST outlines | Cut vs the same files raw | Cut vs every eligible file |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['repo']} | {r['seconds']} | {r['files_read']} | {r['tokens_sent']:,} | "
                     f"{r['cut_from_ast']}% | {r['cut_vs_selected_raw']}% | {r['cut_vs_all']}% |")
    lines += [
        "",
        f"- Time: median {statistics.median(secs):.1f} s, slowest {max(secs):.1f} s. "
        f"{sum(1 for x in secs if x < 15)} of {len(secs)} finished under 15 s.",
        (f"- Token cut from AST outlines alone, against the same files sent as truncated raw text "
         f"(Python repos, {len(py)} of them): median {statistics.median(py):.0f}%. "
         f"Against the same files in full: median {statistics.median(py_all):.0f}%.") if py else "",
        f"- Token cut against sending every eligible file: median "
        f"{statistics.median(r['cut_vs_all'] for r in rows):.0f}% (an estimate, not a model count).",
    ]
    block = "\n".join(l for l in lines if l is not None)
    print("\n" + block)

    if args.write_readme:
        readme = Path(__file__).resolve().parent.parent / "README.md"
        text = readme.read_text()
        if START not in text:
            print("README markers missing")
            return 1
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        readme.write_text(f"{head}{START}\n{block}\n{END}{tail}")
        print("README updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
