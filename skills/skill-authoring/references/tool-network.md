# Skill Authoring Tool Network

Agent archive root: `C:\Users\ltllt\.agents\skill-archive\20260529-skill-consolidation`

## Tool Nodes

- `skill-creator`: create, evaluate, and package skills.
- `writing-skills`: skill writing discipline and test-driven skill development.
- `skill-cleaner`: audit budget, duplicates, unused skills, and descriptions.
- Codex `book-to-skill`: convert books and documents into reusable generated skills.
- system `skill-creator`: current Codex canonical skill authoring guide.
- system `skill-installer`: install curated or GitHub skills.
- system `plugin-creator`: create Codex plugins.

## Flows

- `new-skill`: capture intent -> draft SKILL.md -> eval prompts -> package.
- `cleanup`: inventory -> duplicate scan -> consolidation plan -> archive -> re-scan.
- `network-design`: categories -> tool nodes -> flows -> aliases -> budget verification.
- `description-trim`: long descriptions -> trigger-safe rewrite -> skill-cleaner verification.
- `document-to-skill`: source document(s) -> book-to-skill extraction/preflight -> generated skill -> skill-cleaner verification.

## Loading Rule

Use Codex `book-to-skill` when a user wants to turn books, PDFs, EPUBs, DOCX, HTML, Markdown, text, RTF, or Calibre-supported ebook files into reusable skills. Use system `skill-creator` for canonical structure. Use `skill-cleaner` for budget evidence before and after changes.
