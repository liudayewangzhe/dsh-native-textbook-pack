---
name: skill-network
description: Skill routing and composition map. Use when organizing, auditing, selecting, combining, or restoring skills; when the user asks for skill categories, tool nodes, workflows, or skill collaboration.
---

# Skill Network

Use this as the map of the local skill system. It keeps the global skill list small while preserving small tools as addressable nodes inside larger task skills.

## Model

- **Category skill**: visible top-level skill for a broad task family.
- **Tool node**: a small archived skill or focused capability addressable by name inside a category.
- **Flow**: an ordered composition of tool nodes for a repeatable job.
- **Agent node**: an external or subagent worker that can be composed with category skills for volume-heavy work.

When the user names an old small skill, route to the category that owns that tool node and read that category's `references/tool-network.md`.

## Categories

Read `references/skill-map.md` for the full map, aliases, archive paths, and common flows.

Read `references/extension-protocol.md` before adding, merging, restoring, or redesigning skills.
