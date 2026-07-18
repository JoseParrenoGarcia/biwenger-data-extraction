---
name: create-rule
description: >
  Guides correct creation of a Claude Code rule file for the Agentic-AutoML project.
  Use when: creating a new rule, adding a .md file to .claude/rules/, writing
  unconditional or path-scoped behavioral rules, encoding operational constraints
  (idempotency, schema safety, audit requirements, data privacy), configuring
  path-scoped rules with YAML paths: frontmatter. Covers: hierarchical rule loading
  (unconditional vs. path-scoped), keeping rules focused (one file per topic), encoding
  risk profiles explicitly, rule anti-patterns (bloat, confusing scoping, silent
  failures, dead rules), rule vs. memory distinction. Produces a focused rule .md file
  with optional paths: frontmatter, ready for .claude/rules/. NOT for: creating agents,
  skills, hooks, or managing memory files — those have dedicated authoring skills.
version: 1.0.0
---

# Create Rule

When asked to create a rule file for this project, apply the following design rules consistently.

## Rule Types

**Unconditional rules** — always loaded in every session. Use for project-wide constraints.

**Path-scoped rules** — only loaded when editing files matching a pattern. Use YAML frontmatter:

```yaml
---
paths:
  - "notebooks/**/*.ipynb"
  - "src/pipelines/**"
---

# Notebook Rule

[Instructions only relevant when working in notebooks]
```

## DOs

- **Load rules hierarchically.** Unconditional rules for project-wide constraints. Path-scoped rules for specialized contexts (notebooks, production code, data-sensitive areas).
- **Keep rules focused.** One rule file = one coherent topic: `python-style.md`, `data-privacy.md`, `notebooks.md`.
- **Encode risk profiles explicitly.** State directly: "This is production-critical code. Data quality errors have business impact."
- **Elevate invariants to rules.** Idempotency, schema stability, audit trails — first-class constraints, not implementation details.
- **Keep rule files under 1KB each.** Focused, easy to audit. When a rule grows beyond that, split it.
- **Bury critical safety constraints prominently.** State operational safety rules explicitly: "Stop and ask before X," "Never Y without approval."

## DON'Ts

- **Don't mix levels.** Path-scoped rules in `.claude/rules/` are different from project-level CLAUDE.md constraints. Keep them separate.
- **Don't create rule bloat.** More than 8-10 rule files suggests you're encoding implementation details that belong in code comments.
- **Don't rely on rule scoping for security.** Path-scoped rules are a convenience, not an access-control boundary.
- **Don't create silent failures.** If a rule creates conditions where Claude might silently skip important checks, make the failure loud.
- **Don't duplicate linter rules.** "Sort imports alphabetically" → put in isort config, not a Claude rule.

## Anti-Patterns

| Problem | What It Looks Like | Fix |
|---------|------------------|-----|
| **Rule bloat** | 15+ rule files, many overlapping | Consolidate by topic. Merge `testing.md` and `test-utils.md`. |
| **Confusing scoping** | Rules mixed with imports in CLAUDE.md, unclear which applies where | Make scoping explicit. Use `paths:` frontmatter for conditional rules. |
| **Silent failures** | Rule says "do X" but no alarm if X doesn't happen | Reframe: "Always verify X happened. Flag if not." |
| **Dead rules** | Rule file hasn't been touched in months, path pattern matches nothing | Audit quarterly. Delete unused rules. |

## Repo Layout Reference

```
.claude/
  rules/
    python-style.md     ← unconditional (all Python work)
    data-privacy.md     ← unconditional (data handling everywhere)
    production-ml.md    ← path-scoped to src/models/** and src/pipelines/**
    notebooks.md        ← path-scoped to notebooks/**/*.ipynb
    frontend/           ← subdirectories are discovered recursively
      react.md
```

**Path patterns support brace expansion:**
```yaml
---
paths:
  - "src/**/*.{ts,tsx}"
  - "{src,lib}/**/*.ts"
---
```

**User-level rules** (`~/.claude/rules/`) apply across all projects — personal defaults that any project can override. Project rules take higher priority.

**Subdirectory support** — all `.md` files in `.claude/rules/` are discovered recursively. Use subdirectories to group related rules without losing discoverability.

## Priority Insight

Rules load with the **same high priority as CLAUDE.md**. This is powerful, but:

> High priority everywhere = priority nowhere. When everything competes for attention with equal weight, Claude struggles to determine what's actually relevant to the current task.

Use `paths:` frontmatter to scope rules to the files where they matter. An API rule only loads when working on API files. A notebooks rule only loads when editing notebooks. This keeps instructions authoritative without saturating context with irrelevant guidance.

## When to Create a Rule vs. When Not To

| Scenario | Decision | Rationale |
|----------|----------|-----------|
| "Never modify schemas without a migration file" | ✅ Create a rule | First-class operational constraint |
| "Use type hints in function signatures" | ✅ In `python-style.md` | Affects all code, reduces ambiguity |
| "Always call `set_random_seed()` at notebook start" | ✅ Path-scoped to notebooks/ | Reproducibility is non-negotiable |
| "Sort imports alphabetically" | ❌ Put in linter config | Don't duplicate linter rules in Claude rules |
| "Use descriptive variable names" | ❌ Code comment is enough | Too obvious; clutters rules |

## Output

Place the rule at `.claude/rules/<topic>.md`. If path-scoped, add `paths:` frontmatter. List the new rule in `.claude/CLAUDE.md` under the Rules section with a one-line description.

## Official References

- [Claude Code rules documentation](https://code.claude.com/docs/en/rules) — loading hierarchy, path-scoped rules, format
- [Rules directory deep-dive](https://claudefa.st/blog/guide/mechanics/rules-directory) — priority mechanics, brace expansion, user-level rules, subdirectory discovery
