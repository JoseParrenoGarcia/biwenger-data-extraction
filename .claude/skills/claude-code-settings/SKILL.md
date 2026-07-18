---
name: claude-code-settings
description: >
  Use this skill when the user asks to configure, review, tune, or explain Claude
  Code settings, settings.json, settings.local.json, environment variables, MCP
  loading, context/token controls, terminal ergonomics, skill-listing overhead,
  or repo-local Claude defaults. Trigger on phrases like Claude settings, Claude
  Code config, MCP loading, auto compact, mouse clicks, respectGitignore,
  settings tips, and .claude/settings.json. NOT for creating skills, hooks,
  agents, rules, or editing CLAUDE.md content itself; use the dedicated create*
  skills or create-claude-md for those workflows.
version: 1.0.0
---

# Claude Code Settings

Use this workflow to help configure Claude Code settings for this repository or
to explain the impact of a proposed setting.

## Workflow

1. Identify the target scope:
   - user-wide: `~/.claude/settings.json`;
   - shared repo setting: `.claude/settings.json`;
   - personal repo override: `.claude/settings.local.json`;
   - preferences outside settings files, when Claude stores them elsewhere.
2. Decide whether the setting is a preference, a repo convention, or a control:
   - preferences usually belong in local or user settings;
   - repo conventions may belong in tracked project settings;
   - controls that must be enforced should use hooks, permissions, CI, or branch
     protection rather than prose alone.
3. Prefer small settings changes and document why they are useful.
4. Keep sensitive paths such as `secrets/` out of tool suggestions and agent
   workflows. Settings can reduce risk, but should not be treated as the only
   secrets boundary.
5. Verify JSON syntax after editing settings files.

## High-Value Settings Patterns

Use these patterns as defaults when they match the user's intent.

### Context And Compaction

Tune compaction earlier for long sessions in large repos:

```json
{
  "env": {
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "500000"
  }
}
```

Keep this as a performance and reliability preference, not a correctness
guarantee.

### MCP Loading

Use deferred MCP loading when many servers or tools exist:

```json
{
  "env": {
    "ENABLE_TOOL_SEARCH": "true"
  }
}
```

Load tools eagerly only when predictability matters more than startup/context
cost. Disable noisy optional servers with `disabledMcpjsonServers`, and reserve
`alwaysLoad: true` for important servers that should block startup until ready.

### Gitignore-Aware File Suggestions

Preserve or add this when the user wants safer `@` file suggestions:

```json
{
  "respectGitignore": true
}
```

This reduces accidental references to ignored files, but it does not replace
secrets hooks or filesystem permissions.

### Terminal Ergonomics

For users worried about accidental terminal UI clicks:

```json
{
  "env": {
    "CLAUDE_CODE_DISABLE_MOUSE_CLICKS": "1"
  }
}
```

Explain that Claude Code must be restarted for startup-read environment
variables to take effect.

### Skill Listing Overhead

In skill-heavy workspaces, reduce listing overhead with:

```json
{
  "skillListingBudgetFraction": 0.005,
  "skillListingMaxDescChars": 512
}
```

Use this only when the workspace has enough skills for listing size to matter.

## Repo Defaults

For this Biwenger extractor repo:

- Keep real files under `secrets/` ignored and inaccessible to agent workflows.
- Prefer project settings only for shared, low-surprise defaults.
- Prefer `.claude/settings.local.json` for personal terminal or token-cost
  preferences.
- Do not introduce LLM/news-related Claude settings as part of normal cleanup;
  this repo is now Biwenger-focused.

## Review Checklist

Before finishing a settings change, confirm:

- the chosen settings file matches the intended scope;
- JSON is valid;
- the change does not reveal private paths, tokens, or credentials;
- any security-sensitive behavior has an enforcement mechanism when needed;
- the final response names the setting changed and how it was verified.

## Source Notes

This skill was synthesized for this repository from internal Skyscanner Claude
Code settings guidance and reviewed to avoid committing private source prose or
sensitive operational details.
