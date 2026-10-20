---
name: skill-authoring
description: Skill authoring router. Use for skill-creator, writing-skills, skill-cleaner, creating, editing, testing, packaging, consolidating, deduplicating, or optimizing skills.
---

# Skill Authoring

Use this for skill lifecycle work: create, improve, evaluate, package, clean, merge, and archive skills.

## Workflow

1. Identify whether the user wants a new skill, a revision, or a cleanup.
2. Preserve source material before editing or moving existing skills.
3. Keep the visible `description` short, trigger-focused, and specific.
4. Prefer one routing skill over many overlapping micro-skills when the workflows are naturally sequential or share tools.
5. Archive superseded skills outside loaded skill roots so they stop appearing in the available-skills list.
6. Keep a manifest of moved skills and the consolidation rationale.
7. Verify with a skill inventory scan after changes.

## Tool Network

Read `references/tool-network.md` for the local skill-cleaning, skill-creation, packaging, and network-design tool nodes.

## Source Map

Archived source skills:

- `skill-creator`
- `writing-skills`

Codex also has a system `skill-creator`; prefer the system skill for formal eval harnesses and this skill for local cleanup/refactoring.
