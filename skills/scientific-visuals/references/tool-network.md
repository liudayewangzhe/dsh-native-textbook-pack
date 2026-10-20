# Scientific Visuals Tool Network

Archive root: `C:\Users\ltllt\.agents\skill-archive\20260529-skill-consolidation`

## Tool Nodes

- `matplotlib`: precise low-level plotting and publication exports.
- `seaborn`: fast statistical plots and exploratory visuals.
- `scientific-figure-making`: publication-ready figure conventions.
- `scientific-visualization`: meta-skill for journal multi-panel figures.
- `scientific-schematics`: scientific diagrams and mechanism schematics.
- `tech-graph`: architecture/UML/technical diagrams.
- `markdown-mermaid-writing`: Markdown and Mermaid diagrams.
- `generate-image`: AI image generation assets.
- system `imagegen`: Codex bitmap generation/editing.
- `infographics`: research/data infographics.
- `scientific-slides`: research talk decks.
- `latex-posters`: LaTeX academic posters.
- `pptx-posters`: PowerPoint poster format.

## Flows

- `journal-figure`: `scientific-visualization` -> `matplotlib` -> export QA.
- `quick-eda`: `seaborn` -> `matplotlib` polish if needed.
- `paper-schematic`: `scientific-schematics` -> visual QA.
- `architecture-doc`: `tech-graph` -> `markdown-mermaid-writing`.
- `research-poster`: `scientific-visualization` -> `latex-posters` or `pptx-posters`.
- `infographic`: `research-web` -> `infographics` -> image QA.

## Loading Rule

Read the tool node whose output format matches the deliverable. Do not load plotting, poster, and image-generation references together unless the task truly combines them.
