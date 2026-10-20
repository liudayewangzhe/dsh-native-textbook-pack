# Skill Network Extension Protocol

Use this protocol whenever adding, merging, restoring, or redesigning skills.

## Skill Types

- **Category skill**: globally visible router for a broad task family.
- **Tool node**: focused capability, often archived, referenced from a category.
- **Flow**: ordered composition of tool nodes.
- **Specialist**: narrow skill that remains globally visible because independent triggering is valuable.
- **Agent node**: external or subagent worker such as DeepSeek.

## Add A New Skill

1. Decide whether it is a new category, tool node, flow, specialist, or agent node.
2. If it overlaps an existing category, add it under that category's `references/tool-network.md`.
3. Keep it globally visible only when independent automatic triggering is important.
4. Add aliases and common flows to `skill-network/references/skill-map.md`.
5. If the original skill is archived, keep archive path and restore instructions.
6. Re-run skill-cleaner and keep descriptions under budget.

## Merge Skills

Merge when skills share trigger phrases, tools, source files, output formats, or appear together in workflows.

Preserve:

- Unique scripts and assets.
- Exact old wording in the archive.
- A route from old skill name to new category/tool node.

Avoid:

- Giant SKILL.md files.
- Multi-level hidden references.
- Duplicating archived skill bodies in category skills.

## Compose Flows

Use this syntax in docs and prompts:

- `category/tool-node`
- `category/flow-name`
- `category/tool-a + category/tool-b`

Examples:

- `office-files/pdf`
- `scientific-visuals/journal-figure`
- `agent-delegation/bulk-read + academic-writing/journal-submission`

## Promotion And Demotion

Promote a tool node to visible specialist when:

- It is frequently requested directly.
- Misrouting is costly.
- It has unique safety or setup rules.

Demote a visible skill to tool node when:

- It is rarely used.
- It mostly participates in larger flows.
- Its description overlaps a category.

## Verification

After any structural change:

```powershell
node --experimental-strip-types D:\Temp\agent-scripts\skills\skill-cleaner\scripts\skill-cleaner.ts --months 6 --deep-logs --context-tokens 272000 --budget-percent 2 --root C:\Users\ltllt\.agents\skills
```

Pass criteria:

- No unintended duplicate names.
- No description truncation.
- Budget use stays comfortably below 100% of the 2% skill budget.
- Every archived skill has a route from `skill-map.md`.
