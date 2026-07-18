---
name: create-hook
description: >
  Guides correct creation of Claude Code hooks in settings.json for the Agentic-AutoML
  project. Use when: adding a hook, automating an action on tool use or task completion,
  setting up file-change or subagent-lifecycle automation, creating formatting or linting
  triggers. Covers: correct event names (PreToolUse, PostToolUse, Stop, SubagentStart,
  SessionStart, etc.), hook types (command, prompt, agent, http), correct settings.json
  structure (event-keyed arrays of hook groups), exit codes (0=proceed, 2=block), the
  `if` field for fine-grained filtering, hook location scoping. Produces a settings.json
  hook block
  ready to add to .claude/settings.json. NOT for: creating skill, agent, or rule files —
  those have dedicated authoring skills.
version: 1.0.0
---

# Create Hook

When asked to create a Claude Code hook, apply the following design rules consistently.

## Hook Events

| Event | Fires When | Matcher Filters On |
|-------|-----------|-------------------|
| `PreToolUse` | Before a tool call — can block it | tool name: `Bash`, `Edit\|Write` |
| `PostToolUse` | After a tool call succeeds | tool name |
| `PostToolUseFailure` | After a tool call fails | tool name |
| `PermissionRequest` | Permission dialog is about to appear | tool name |
| `PermissionDenied` | Tool call denied by auto-mode classifier | tool name |
| `Stop` | Claude finishes responding | no matcher |
| `StopFailure` | Turn ends due to API error | no matcher |
| `SessionStart` | Session begins, resumes, or compacts | `startup`, `resume`, `clear`, `compact` |
| `SessionEnd` | Session terminates | `clear`, `resume`, `logout`, etc. |
| `UserPromptSubmit` | Prompt submitted, before Claude processes it | no matcher |
| `Notification` | Claude needs input | `permission_prompt`, `idle_prompt` |
| `SubagentStart` | Subagent spawned | agent type name |
| `SubagentStop` | Subagent finishes | agent type name |
| `ConfigChange` | Config or skills file changes during session | `project_settings`, `user_settings`, `skills` |
| `FileChanged` | Watched file changes on disk | filename (basename) |
| `CwdChanged` | Working directory changes | no matcher |
| `PreCompact` / `PostCompact` | Before/after context compaction | `manual`, `auto` |

## settings.json Structure

```json
{
  "hooks": {
    "EventName": [
      {
        "matcher": "ToolName|OtherTool",
        "hooks": [
          {
            "type": "command",
            "command": "shell command to run",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

**Structure rules:**
- Top-level key is the **event name** (e.g., `PostToolUse`), not a custom hook name
- Value is an **array** of hook groups
- Each group has optional `matcher` (regex on the column above) and a `hooks` array
- Each hook entry has `type` and `command`; optional `timeout` (seconds), `async` (bool), `if`

## Hook Types

| Type | Description | Use When |
|------|-------------|----------|
| `command` | Runs a shell command | Deterministic: formatting, validation, logging |
| `prompt` | Single-turn LLM call (Haiku by default) | Decisions requiring judgment, no file access needed |
| `agent` | Multi-turn subagent with tool access (up to 50 turns) | Verify against actual codebase state |
| `http` | POST event data to a URL | External services, shared audit logging |

## Exit Codes (for `type: command`)

| Exit Code | Behavior |
|-----------|---------|
| `0` | Action proceeds. For `UserPromptSubmit`/`SessionStart`, stdout is added to Claude's context |
| `2` | Action **blocked**. Write reason to stderr — Claude receives it as feedback to adjust |
| Other | Action proceeds; one-line notice in transcript, full stderr in debug log |

For structured decisions (exit 0 + JSON to stdout):
- `PreToolUse`: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "reason"}}`
- `Stop` / `PostToolUse`: `{"decision": "block"}`

**Do not mix exit 2 and JSON output.** Use exit 2 for simple blocking only.

## The `if` Field (v2.1.85+)

Filters by tool name AND arguments — more precise than `matcher` alone:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(git *)",
            "command": "./.claude/hooks/check-git-policy.sh"
          }
        ]
      }
    ]
  }
}
```

Only works on tool events: `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionRequest`, `PermissionDenied`.

## DOs

- **Use correct event names.** `PostToolUse` not `on-tool-use-Edit`. `SubagentStart` not `on-subagent-spawn`. `Stop` not `on-task-completed`.
- **Keep hooks lightweight.** Target <5s. Longer hooks block all work on every turn.
- **Use hooks for deterministic operations.** Linting, formatting, validation, logging — not interactive decisions.
- **Log hook execution.** Add `echo "[HOOK] ..."` so you can audit what ran.
- **Fail loudly.** Exit 2 to block with a stderr reason. Don't swallow errors with `|| true`.
- **Gate with `matcher` and `if`.** Avoid spawning on every tool call when only some matter.
- **Document hooks in CLAUDE.md.** List active hooks with one-line descriptions. Surprises break workflows.

## DON'Ts

- **Don't use wrong event names.** This is the most common error — check the event table above.
- **Don't use flat hook objects.** `"my-hook-name": {"command": "..."}` is invalid; use event-keyed arrays of hook groups.
- **Don't create slow hooks.** A 2s hook on every turn adds 2s to all work.
- **Don't create cascading hooks.** Hook A → B → C is hard to debug. Keep dependencies shallow.
- **Don't silence errors.** `command || true` hides problems. Let failures surface.
- **Don't automate destructive operations.** Never auto-push, auto-delete, or auto-deploy without confirmation.
- **Don't create Stop hook loops.** If your Stop hook triggers Claude to keep working, check `stop_hook_active` in stdin and exit 0 if `true`.

## Anti-Patterns

| Problem | What It Looks Like | Fix |
|---------|------------------|-----|
| **Wrong event names** | `on-tool-use-Edit`, `on-subagent-spawn`, `on-error` | Use `PostToolUse`, `SubagentStart`, `StopFailure` |
| **Wrong structure** | `"my-hook": {"command": "..."}` flat object | Event name as key → array of hook groups |
| **Slow hooks** | Every tool use triggers a 3s script | Gate with `matcher` or `if` field |
| **Silent failures** | Hook exits non-zero but execution continues | Use exit 2 for blocking; don't use `\|\| true` |
| **Stop hook loop** | Claude keeps working indefinitely | Parse `stop_hook_active` from stdin; exit 0 if `true` |
| **Destructive automation** | Hook auto-pushes on `Stop` | Never auto-push; require explicit confirmation |
| **Undocumented automation** | Hooks run but aren't listed anywhere | Add "Active Hooks:" section to CLAUDE.md |

## Examples

### Auto-format Python after Edit
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "FILE=$(jq -r '.tool_input.file_path'); if [[ \"$FILE\" == *.py ]]; then echo '[HOOK] Formatting...'; black \"$FILE\" --quiet; fi"
          }
        ]
      }
    ]
  }
}
```

### Validate JSON on Write
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "FILE=$(jq -r '.tool_input.file_path'); if [[ \"$FILE\" == *.json ]]; then jq empty \"$FILE\" || (echo 'Invalid JSON' >&2 && exit 2); fi"
          }
        ]
      }
    ]
  }
}
```

### Log Subagent Activation
```json
{
  "hooks": {
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo \"[HOOK] Subagent spawned at $(date)\" >> .claude/subagent-log.txt"
          }
        ]
      }
    ]
  }
}
```

### Notify when Claude needs input (macOS)
```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "idle_prompt|permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "osascript -e 'display notification \"Claude Code needs your attention\" with title \"Claude Code\"'"
          }
        ]
      }
    ]
  }
}
```

## Hook Location

| Settings File | Scope | Committable |
|---------------|-------|-------------|
| `~/.claude/settings.json` | All projects | No (local to machine) |
| `.claude/settings.json` | Single project | Yes |
| `.claude/settings.local.json` | Single project | No (gitignored) |
| Skill or agent frontmatter | While that skill/agent is active | Yes |

Run `/hooks` in Claude Code to browse all configured hooks grouped by event.

## When to Use a Hook vs. When Not To

| Scenario | Decision | Rationale |
|----------|----------|-----------|
| "Run linter after every code edit" | ✅ Hook | Deterministic, fast, always valuable |
| "Format code before commit" | ✅ Hook | Consistent; good hygiene |
| "Decide whether to auto-push" | ❌ Don't hook | Requires judgment; not deterministic |
| "Ask user for approval" | ❌ Don't hook | Hooks are non-interactive; use rules instead |
| "Run full test suite on every edit" | ⚠️ Maybe with gating | Gate to specific files; depends on duration |

## Output

Add the hook block to `.claude/settings.json` under `hooks`. Document in `.claude/CLAUDE.md` under "Active Hooks" with one-line descriptions. If the hook calls a script, store it in `.claude/hooks/` and make it executable: `chmod +x .claude/hooks/your-script.sh`.

## Official References

- [Automate workflows with hooks](https://code.claude.com/docs/en/hooks-guide) — common use cases, examples, troubleshooting
- [Hooks reference](https://code.claude.com/docs/en/hooks) — complete event schemas, JSON output, async hooks, HTTP hooks
