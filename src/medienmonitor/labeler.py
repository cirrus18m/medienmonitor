"""Language-model backends that answer one prompt with JSON matching a schema.

Chosen with the environment variable ``MM_LABELER`` (default ``claude_cli``):

* ``claude_cli``: Claude Code in print mode (``claude -p``). Authenticates with the
  Claude subscription via ``CLAUDE_CODE_OAUTH_TOKEN`` (``claude setup-token``) or a
  local login. No tools, no session files. Model from ``MM_MODEL`` (default ``sonnet``).

Further backends (Claude API, DeepSeek) implement the same ``Labeler`` protocol.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Protocol

TIMEOUT_S = 600


class LabelerError(RuntimeError):
    pass


class Labeler(Protocol):
    def complete_json(self, system: str, prompt: str, schema: dict) -> dict: ...


class ClaudeCli:
    def __init__(self, model: str | None = None, effort: str | None = None) -> None:
        self.model = model or os.environ.get("MM_MODEL", "sonnet")
        self.effort = effort or os.environ.get("MM_EFFORT", "low")
        self.binary = shutil.which("claude")
        if not self.binary:
            raise LabelerError("Claude Code (Befehl „claude“) ist nicht installiert.")
        self.last_cost_usd = 0.0

    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        command = [
            self.binary,
            "-p",
            "--system-prompt", system,
            "--tools", "",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--model", self.model,
            "--effort", self.effort,
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
        ]  # fmt: skip
        try:
            done = subprocess.run(
                command, input=prompt, capture_output=True, text=True, timeout=TIMEOUT_S
            )
        except subprocess.TimeoutExpired as exc:
            raise LabelerError(f"Claude Code antwortet nicht ({TIMEOUT_S} s)") from exc
        if done.returncode != 0 and not done.stdout.strip():
            raise LabelerError(f"Claude Code Fehler {done.returncode}: {done.stderr[-500:]}")
        try:
            result = json.loads(done.stdout)
        except json.JSONDecodeError as exc:
            raise LabelerError(f"Antwort ist kein JSON: {done.stdout[-300:]}") from exc
        if result.get("is_error") or "structured_output" not in result:
            detail = result.get("result") or result.get("subtype") or "ohne Ergebnis"
            raise LabelerError(f"Claude Code: {str(detail)[:300]}")
        self.last_cost_usd = float(result.get("total_cost_usd") or 0.0)
        return result["structured_output"]


def from_env() -> Labeler:
    name = os.environ.get("MM_LABELER", "claude_cli")
    if name == "claude_cli":
        return ClaudeCli()
    raise LabelerError(f"Unbekanntes Backend MM_LABELER={name!r}")
