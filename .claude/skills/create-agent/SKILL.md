---
name: create-agent
description: >
  Guides correct creation of a Claude Code agent file for the Agentic-AutoML project.
  Use when: creating a new agent, adding a file to agents/, writing agent instructions,
  defining a subagent, designing an orchestrator agent, building an agent with tool
  restrictions. Covers: YAML frontmatter (name, description, tools, disallowedTools,
  model, maxTurns, permissionMode), DOs and DON'Ts, anti-patterns, composition patterns
  (agent+skill, agent+MCP, sequential, concurrent), and when to create vs. skip. Produces
  a YAML-frontmattered agent .md file ready for agents/. Trigger on full creation or
  major restructuring — not minor field edits. NOT for: creating skills, hooks, rules,
  or memory files — those have dedicated authoring skills.
version: 1.0.0
---

# Create Agent

When asked to create an agent file for this project, apply the following design rules consistently.

## Agent Anatomy

```yaml
---
name: code-reviewer
description: Reviews code changes for quality, security, and best practices.
  Use proactively after any significant code change.
tools: Read, Glob, Grep
model: sonnet
---

# Code Reviewer

[Instructions and context...]
```

**Required fields:**
- `name` — unique identifier (lowercase, hyphens only)
- `description` — what the agent does + when to use it + "use proactively" if should activate without explicit request

**Optional but useful:**
- `tools` — restrict to specific tools (default: all tools from parent)
- `disallowedTools` — explicitly block certain tools (even if listed in `tools`)
- `model` — route to specific model: `haiku`, `sonnet`, `opus`, full model ID, or `inherit`
- `maxTurns` — max agentic turns before stopping
- `permissionMode` — `default`, `acceptEdits`, `auto`, `dontAsk`, or `bypassPermissions`
- `skills` — skill names to inject into the subagent's context at startup
- `mcpServers` — MCP servers scoped to this subagent (inline definitions or server name references)
- `memory` — persistent memory scope: `user`, `project`, or `local`
- `isolation` — set to `worktree` to run in an isolated git worktree
- `background` — `true` to always run as a background task (default: false)
- `color` — display color: `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`
- `effort` — compute level: `low`, `medium`, `high`, or `max` (Opus only)
- `hooks` — lifecycle hooks scoped to this subagent only

## DOs

- **Write descriptions for delegation, not documentation.** Include what the agent does, when to use it, and trigger conditions for "use proactively."
- **Restrict tools to what the agent actually needs.** A read-only reviewer should not have Write or Bash access.
- **Use tool restriction for safety.** If an agent should never write files, set `disallowedTools: [Write, Edit]`.
- **Delegate parallel work.** When tasks are independent, launch multiple agents concurrently — one per focused task.
- **Compose agents with skills and MCP.** Agent orchestrates and decides; skill executes the specific task.
- **Set `maxTurns` for long-running agents.** Prevents accidental infinite loops. Pair with explicit stop conditions.
- **Use model routing intentionally.** Route deep analysis to Opus, routine checks to Sonnet, lightweight tasks to Haiku.

## DON'Ts

- **Don't create agents for one-off tasks.** Agents are for repeated, focused work.
- **Don't mix agent and skill responsibilities.** Agents = capacity and isolation. Skills = reusable workflow.
- **Don't over-grant permissions.** Restrict to minimum required tools.
- **Don't write vague descriptions.** "Helps with code" is useless. Be specific about scope and trigger conditions.
- **Don't use "use proactively" for every agent.** Reserve it for high-confidence, low-risk automation (read-only review). Never for destructive operations.

## Anti-Patterns

| Problem | What It Looks Like | Fix |
|---------|------------------|-----|
| **God agent** | One agent with all tools doing research, coding, deployment | Split into focused agents: researcher, coder, deployer |
| **Redundant agents** | Two agents with nearly identical descriptions and tools | Consolidate into one; if truly different, make differences explicit |
| **Vague scoping** | Description: "Helps with testing" | Rewrite: "Runs pytest on Python modules, parses failures, suggests fixes" |
| **Over-granted permissions** | Read-only reviewer with Write and Bash access | Set `disallowedTools: [Write, Edit, Bash]` or `tools: [Read, Glob, Grep]` |
| **Silent failures** | Agent runs but doesn't report what it did or why it stopped | Require explicit status: "✓ Review complete" or "✗ Cannot fix: reason" |
| **Proactive overuse** | Every agent has "use proactively" | Reserve for safe automation only |
| **Skill vs. agent confusion** | Agent encodes entire workflow instead of delegating to skills | Agent orchestrates and decides. Skill executes. |

## Composition Patterns

### Pattern 1: Agent + Skill
```
Main task → Delegate to agent → Agent invokes skill → Skill executes
```
Use when: Agent needs specialized tool access but delegates workflow to a skill.

### Pattern 2: Agent + MCP
```
Main task → Delegate to agent with MCP → Agent accesses external system
```
Use when: Agent needs API access (database, web APIs) not available via built-in tools.

### Pattern 3: Agent + Agent (Sequential)
```
Main task → Agent A (research) → Agent B (analysis) → Agent C (report)
```
Use when: Tasks are sequential and each requires focused expertise.

### Pattern 4: Agent + Subagent (Concurrent)
```
Main task → Launch Agent A, Agent B, Agent C in parallel → Gather results → Continue
```
Use when: Tasks are independent (e.g., fetch from 3 APIs in parallel).

## When to Create an Agent vs. When Not To

| Scenario | Decision | Rationale |
|----------|----------|-----------|
| "Review every PR before merge" | ✅ Create agent | Repeated, focused task with clear success criteria |
| "Research market trends" | ✅ Create agent | Needs web access; can run independently |
| "One-time data migration" | ❌ Don't create agent | Not repeated; overhead exceeds benefit |
| "Fix typos in README" | ❌ Don't create agent | Too simple; inline the work |
| "Coordinate multiple parallel tasks" | ✅ Create orchestrator agent | That's what agents excel at |

## Output

Place the completed agent file in `.claude/agents/<agent-name>.md` (project-scoped, commit to version control) or `~/.claude/agents/<agent-name>.md` (user-scoped, available across all projects). Confirm tool restrictions and description trigger conditions before finalising.

## Official References

- [Create custom subagents](https://code.claude.com/docs/en/sub-agents) — frontmatter fields, tool restrictions, model routing, memory, hooks, examples
