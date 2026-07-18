---
name: create-claude-md
description: >
  Use this skill when creating, reviewing, or refactoring a CLAUDE.md file for
  Claude Code. Covers what belongs in CLAUDE.md, how to keep it concise,
  choosing between CLAUDE.md, .claude/rules, hooks, settings, skills, README, and
  AGENTS.md, and writing completion criteria the agent can verify. Trigger on
  phrases like write CLAUDE.md, improve Claude instructions, repo memory,
  Claude context, project instructions, agent operating contract, or CLAUDE.md
  review. NOT for tuning Claude Code settings, authoring hooks, creating skills,
  or writing general documentation.
version: 1.0.0
---

# Create CLAUDE.md

Use this workflow to create or improve a repository `CLAUDE.md` file.

## Purpose

Treat `CLAUDE.md` as persistent operating context for Claude Code, not as a
replacement for documentation. It should help the agent answer:

- what this repository is for;
- how work should be done here;
- what rules apply across the repository;
- when to pause and ask;
- how to verify that a task is complete.

## What Belongs In CLAUDE.md

Prefer concise, stable guidance:

- repository purpose and non-goals;
- common commands for install, test, lint, typecheck, and local runs;
- repo-wide conventions that materially affect edits;
- risk and approval boundaries;
- pointers to deeper instructions;
- completion criteria and expected evidence.

Avoid:

- long copied README/wiki material;
- generic advice such as "write clean code";
- temporary task lists;
- architecture history that does not affect current work;
- secrets, credentials, or sensitive operational details;
- rules that must be enforced by hooks, permissions, CI, or branch protection.

## Placement Decisions

Use the right Claude Code mechanism:

- `CLAUDE.md`: concise repo-wide operating contract.
- `.claude/rules`: modular repo-wide or path-scoped guidance.
- Skills: repeatable task workflows loaded on demand.
- Hooks, permissions, CI, branch protection: controls that must actually be
  enforced.
- `AGENTS.md`: cross-agent or agent-neutral repository instructions.
- README/docs: human-facing product, setup, or architecture documentation.

If guidance only applies to a folder, prefer a scoped rule. If guidance is a
procedure, prefer a skill. If a rule must not be bypassed, enforce it with a
system control.

## Writing Rules

- Keep the file high-signal; target roughly under 200 lines when practical.
- Use concrete commands and file paths.
- Pair prohibitions with the correct alternative.
- Name canonical source-of-truth files when they exist.
- Remove text that could be pasted unchanged into any repository.
- Make completion criteria observable.

## Practical Template

```markdown
# Claude Instructions

## What This Repo Is
- <short repo purpose and non-goals>

## Common Commands
- Install: `<command>`
- Test: `<command>`
- Lint/typecheck: `<command>`
- Run locally: `<command>`

## Repository Rules
- <specific, stable, verifiable rule>
- <specific, stable, verifiable rule>

## Risk Boundaries
- Ask before <high-risk change>.
- Do not modify <sensitive area> without approval.

## More Specific Guidance
- For <topic>, read `<path>`.

## Completion Criteria
- Run the narrowest relevant checks.
- Report commands run and results.
- State assumptions and remaining risks.
```

## Review Checklist

Before finishing a `CLAUDE.md` change, confirm:

- it explains the repository clearly;
- rules are concrete and verifiable;
- narrow guidance is not forced into global context;
- stop-and-ask boundaries are explicit;
- verification expectations are clear;
- sensitive or private details were not introduced.

## Source Notes

This skill was synthesized for this repository from internal Skyscanner guidance
on writing effective Claude Code memory files and reviewed to avoid committing
private source prose or sensitive operational details.
