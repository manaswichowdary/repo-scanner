"""Build the text sent to the model, and count tokens."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .ast_outline import outline_python

README_CHARS = 5000
FILE_CHARS = 4000


def count_tokens(text: str) -> int:
    """Real count with tiktoken when installed, otherwise about 4 characters each."""
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return math.ceil(len(text) / 4)


@dataclass
class Context:
    text: str
    tokens_selected_raw: int
    tokens_sent: int
    tokens_no_ast: int = 0


def build_context(repo_line: str, files: list[tuple[str, str, str]]) -> Context:
    """files is a list of (path, reason, content)."""
    parts = [repo_line]
    plain = [repo_line]
    raw_total = 0
    for path, reason, content in files:
        raw_total += count_tokens(content)
        plain_limit = README_CHARS if reason == "readme" else FILE_CHARS
        plain.append(f"=== {path} ({reason}) ===\n{content[:plain_limit]}")
        if path.endswith(".py") and reason != "manifest":
            outline = outline_python(content)
            if outline is not None:
                body = f"[python outline]\n{outline[:FILE_CHARS]}"
            else:
                body = content[:FILE_CHARS]
        else:
            limit = README_CHARS if reason == "readme" else FILE_CHARS
            body = content[:limit]
        parts.append(f"=== {path} ({reason}) ===\n{body}")
    text = "\n\n".join(parts)
    return Context(text=text, tokens_selected_raw=raw_total, tokens_sent=count_tokens(text),
                   tokens_no_ast=count_tokens("\n\n".join(plain)))
