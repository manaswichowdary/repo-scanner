"""Ask the model for a structured summary and validate what comes back."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from .errors import ConfigError, SummarizerError

log = logging.getLogger("repo_scanner.summarizer")

DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM = (
    "You analyze GitHub repositories. Reply with one JSON object and nothing else. "
    "Keys: summary (one sentence on what the project does), technologies (list of "
    "strings), architecture (exactly 3 short strings on how the code is organized), "
    "intended_users (list of strings), code_quality (2 sentences, honest, based only "
    "on the files shown). Do not invent files or features that are not in the context."
)


@dataclass
class Analysis:
    summary: str
    technologies: list[str] = field(default_factory=list)
    architecture: list[str] = field(default_factory=list)
    intended_users: list[str] = field(default_factory=list)
    code_quality: str = ""


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def parse_analysis(raw: str) -> Analysis:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SummarizerError("The model returned invalid JSON. Try again.") from exc
    if not isinstance(data, dict) or not str(data.get("summary", "")).strip():
        raise SummarizerError("The model reply was missing a summary. Try again.")
    return Analysis(
        summary=str(data["summary"]).strip(),
        technologies=_strings(data.get("technologies")),
        architecture=_strings(data.get("architecture"))[:3],
        intended_users=_strings(data.get("intended_users")),
        code_quality=str(data.get("code_quality", "")).strip(),
    )


class Summarizer:
    def __init__(self, api_key: str | None = None, model: str | None = None, client=None):
        self.model = model or os.getenv("REPO_SCANNER_MODEL") or DEFAULT_MODEL
        if client is not None:
            self._client = client
            return
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigError("OPENAI_API_KEY is not set. Add it to your environment.")
        from openai import OpenAI

        self._client = OpenAI(api_key=key, timeout=60, max_retries=2)

    def summarize(self, context: str) -> Analysis:
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": context},
                ],
            )
            raw = resp.choices[0].message.content
        except SummarizerError:
            raise
        except Exception as exc:  # network, auth, rate limit, anything from the SDK
            log.debug("model call failed: %r", exc)
            raise SummarizerError(f"The model call failed: {type(exc).__name__}.") from exc
        return parse_analysis(raw)
