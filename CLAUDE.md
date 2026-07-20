# Claude Instructions

Read the repo context and working rules in @AGENTS.md before making changes.

## Active Hooks

- `block-secrets-access` (`PreToolUse`, matches `Bash|Read|Edit|Write|NotebookEdit`, script at `.claude/hooks/block-secrets-access.sh`): blocks any tool call whose file path or shell command touches a real file under `secrets/`. Only `secrets/*.example.toml` templates are allowed through. Real credentials must never be printed, summarized, or otherwise exposed — if you need secret structure, ask the user instead of opening the real file. See the matcher logic in `.claude/hooks/lib/secrets_guard.py` and tests in `tests/test_secrets_guard_hook.py`.

