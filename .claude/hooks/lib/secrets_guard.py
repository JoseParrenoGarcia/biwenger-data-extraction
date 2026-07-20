"""Deterministic matcher used by the block-secrets-access PreToolUse hook.

Detects attempts to access real files under secrets/ (via file-path style
tool inputs or shell commands) while allowing the committed *.example.toml
templates. Kept dependency-free (stdlib only) so it can run inside the hook
wrapper without installing anything.
"""

import re

BLOCK_MESSAGE = (
    "Blocked: real files under secrets/ are off-limits. "
    "Use secrets/*.example.toml or ask the user to provide non-secret structure instead."
)

_SECRETS_SEGMENT_RE = re.compile(r"secrets/([^\s'\"]*)")


def _is_allowed_path(secrets_relative_path: str) -> bool:
    basename = secrets_relative_path.rsplit("/", 1)[-1]
    return basename.endswith(".example.toml")


def _candidate_strings(payload: dict) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    candidates = []
    for key in ("file_path", "path", "notebook_path", "command"):
        value = tool_input.get(key)
        if isinstance(value, str):
            candidates.append(value)
    return candidates


def is_blocked(payload: dict) -> str | None:
    """Return a block reason if payload touches a real secrets/ file, else None."""
    for candidate in _candidate_strings(payload):
        for match in _SECRETS_SEGMENT_RE.finditer(candidate):
            relative_path = match.group(1)
            if not _is_allowed_path(relative_path):
                return BLOCK_MESSAGE
    return None
