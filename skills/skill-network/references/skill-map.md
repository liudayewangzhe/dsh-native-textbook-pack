# Skill Map

Archive roots:

- Agent tool archive: `C:\Users\ltllt\.agents\skill-archive\20260529-skill-consolidation`
- Codex tool archive: `C:\Users\ltllt\.codex\skill-archive\20260529-skill-consolidation`

## Category Skills

### `dev-workflow`

Purpose: software engineering process, from intent to verification.

Tool nodes:

- `brainstorming`
- `writing-plans`
- `executing-plans`
- `using-git-worktrees`
- `systematic-debugging`
- `test-driven-development`
- `verification-before-completion`
- `requesting-code-review`
- `receiving-code-review`
- `dispatching-parallel-agents`
- `subagent-driven-development`
- `finishing-a-development-branch`
- `context-save`
- `using-superpowers`

Common flows:

- `feature-build`: brainstorming -> writing-plans -> implementation -> verification-before-completion
- `bug-fix`: systematic-debugging -> test-driven-development -> implementation -> verification-before-completion
- `large-refactor`: using-git-worktrees -> writing-plans -> subagent-driven-development -> requesting-code-review
- `large-context-dev`: agent-delegation/deepseek-claude-subagent -> dev-workflow verification

### `agent-delegation`

Purpose: external/subagent work delegation, especially DeepSeek.

Agent nodes:

- `deepseek-claude-subagent`
- `dispatching-parallel-agents`
- `subagent-driven-development`
- `requesting-code-review`

Common flows:

- `bulk-read`: define scope -> DeepSeek reads/extracts -> Codex verifies
- `repo-scan`: DeepSeek broad search -> Codex targeted inspection
- `mechanical-edits`: DeepSeek repetitive edits in a bounded trusted directory -> Codex reviews diff
- `second-opinion`: Codex solution -> DeepSeek review -> Codex decision
- `sticky-deepseek`: DeepSeek requested or used -> subsequent turns keep the DeepSeek continuation check active -> explicit stop ends it

### `office-files`

Purpose: office/document file work.

Tool nodes:

- `docx`
- `pptx`
- `pdf`
- `xlsx`
- `markitdown`
- plugin `documents`
- plugin `presentations`
- plugin `spreadsheets`
- `native-textbook`: direct Codex entry at `C:\Users\ltllt\.codex\skills\native-textbook\SKILL.md`; book mode for continuous textbooks, slide mode for native PDFs preserving PPT style; editable PPTX stays with `presentations`.

Common flows:

- `pdf-to-report`: pdf -> markitdown -> docx
- `data-to-deck`: xlsx -> chart/table analysis -> pptx
- `doc-redline`: docx -> render/verify -> comment or tracked changes
- `native-textbook`: source PDF evidence -> bounded DeepSeek translation/TeX -> vector/native assets -> ElegantBook -> semantic/visual review -> release
- `native-slide-pdf`: source slide evidence -> page/geometry contract -> bounded DeepSeek slide workers -> direct XeLaTeX -> actual PDF and all-page review -> independent release

### `scientific-visuals`

Purpose: figures, diagrams, infographics, slides, posters, and visual assets.

Tool nodes:

- `matplotlib`
- `seaborn`
- `scientific-figure-making`
- `scientific-visualization`
- `scientific-schematics`
- `tech-graph`
- `markdown-mermaid-writing`
- `generate-image`
- `imagegen`
- `infographics`
- `scientific-slides`
- `latex-posters`
- `pptx-posters`

Common flows:

- `journal-figure`: scientific-visualization -> matplotlib -> export verification
- `technical-diagram`: tech-graph or scientific-schematics -> Mermaid/SVG/PNG verification
- `poster`: scientific-visuals -> latex-posters or pptx-posters -> render verification

### `academic-writing`

Purpose: research prose, manuscript adaptation, and long-form research reports.

Tool nodes:

- `nature-polishing`
- `journal-adapt`
- `market-research-reports`

Common flows:

- `paper-polish`: nature-polishing -> section consistency review
- `journal-fit`: journal-adapt -> reference-corpus checks -> revision
- `consulting-report`: research-web -> market-research-reports -> visual synthesis

### `research-web`

Purpose: search, current information, academic lookup, URL extraction, and enrichment.

Tool nodes:

- `parallel-web`
- `paper-search` (Microsoft ResearchStudio-Idea; multi-index academic retrieval)
- `scoop-check` (Microsoft ResearchStudio-Idea; claim-specific prior-art collision audit)
- `idea-spark` (Microsoft ResearchStudio-Idea; evidence-grounded single-idea pipeline)
- web search
- official-document lookup
- academic literature retrieval

Common flows:

- `current-answer`: search -> source triage -> cited summary
- `literature-review`: academic search -> paper extraction -> synthesis
- `evidence-grounded-ideation`: paper-search -> idea-spark -> scoop-check -> ccf-idea-optimizer/ccf-experiment-designer
- `dataset-enrichment`: schema -> web lookup -> provenance table

### `obsidian-wiki`

Purpose: local Obsidian personal knowledge-base setup, ingestion, querying, maintenance, and export.

Category node:

- `llm-wiki`

Tool nodes:

- `wiki-setup`
- `wiki-ingest`
- `ingest-url`
- `data-ingest`
- `obsidian-wiki-ingest`
- `wiki-query`
- `wiki-update`
- `wiki-capture`
- `wiki-quick-chat-capture`
- `wiki-status`
- `wiki-lint`
- `wiki-dedup`
- `wiki-rebuild`
- `cross-linker`
- `tag-taxonomy`
- `wiki-export`
- `wiki-import`
- `graph-colorize`
- `wiki-dashboard`
- `wiki-research`
- `wiki-synthesize`
- `wiki-digest`
- `wiki-history-ingest`
- `codex-history-ingest`
- `claude-history-ingest`
- `hermes-history-ingest`
- `openclaw-history-ingest`
- `copilot-history-ingest`
- `pi-history-ingest`
- `memory-bridge`
- `daily-update`
- `impl-validator`

Common flows:

- `vault-setup`: obsidian-wiki/wiki-setup -> AGENTS.md protocol -> git init -> plugin bridge configuration
- `source-ingest`: raw source -> obsidian-wiki/wiki-ingest or obsidian-wiki/ingest-url -> cross-linker -> wiki-lint
- `project-sync`: dev-workflow context -> obsidian-wiki/wiki-update -> index/log/hot/manifest refresh
- `query`: obsidian-wiki/wiki-query -> cheapest retrieval primitive -> cited answer
- `document-to-knowledge-skill`: skill-authoring/document-to-skill -> book-to-skill -> obsidian-wiki/wiki-update

### `compute-gpu`

Purpose: resource inspection, local GPU acceleration, and cloud GPU work.

Tool nodes:

- `get-available-resources`
- `optimize-for-gpu`
- `modal`

Common flows:

- `heavy-local-run`: get-available-resources -> algorithm choice -> run/monitor
- `gpu-port`: profile CPU bottleneck -> optimize-for-gpu -> verify equivalence
- `cloud-gpu`: package workload -> modal -> deploy/run

### `metaphysics`

Purpose: Chinese metaphysics routing.

Tool nodes:

- `bazi`
- `liuyao`
- `metaphysics-pipeline`
- `horosa-bazi`
- `horosa-liuyao`
- `horosa-ziwei`
- `horosa-agent`

Common flows:

- `bazi-reading`: bazi or horosa-bazi -> timing/life-area analysis
- `liuyao-decision`: liuyao or horosa-liuyao -> concrete decision answer
- `cross-technique`: metaphysics-pipeline -> compare agreement/divergence

### `vedic-astrology`

Purpose: Vedic/Jyotish chart reading and reporting.

Tool nodes:

- `vedic-calculator`
- `vedic-reader`
- `vedic-rectifier`
- `vedic-core`
- `vedic-career`
- `vedic-love`
- `vedic-synastry`
- `vedic-prashna`

Common flows:

- `calculator-first`: vedic-calculator -> vedic-reader validation -> structured data -> core audit
- `read-chart`: vedic-calculator or vedic-reader -> structured data -> core audit
- `career`: vedic-calculator or vedic-reader -> vedic-core -> vedic-career
- `career-d1-quick`: vedic-reader -> career methodology D1-only review
- `relationship-timing`: vedic-calculator or vedic-reader -> vedic-core -> vedic-love
- `synastry`: two calculator-backed charts -> vedic-synastry -> compatibility matrix and timing
- `prashna`: one concrete question + exact question time/place -> vedic-prashna -> isolated structured_prashna.md judgment
- `report-build`: existing Vedic markdown outputs -> vedic-core report_builder -> HTML report

### `skill-authoring`

Purpose: create, clean, package, and improve skills.

Tool nodes:

- `skill-creator`
- `writing-skills`
- `skill-cleaner`
- `book-to-skill`
- system `skill-creator`
- system `skill-installer`
- system `plugin-creator`

Common flows:

- `new-skill`: capture intent -> draft -> eval prompts -> package
- `document-to-skill`: source documents -> skill-authoring/book-to-skill -> generated skill -> skill-cleaner verification
- `skill-cleanup`: inventory -> duplicates -> category merge -> budget verification
- `description-optimization`: trigger evals -> description rewrite -> re-scan

## Extension Protocol

When adding future skills, follow `references/extension-protocol.md`:

1. Classify as category, tool node, flow, specialist, or agent node.
2. Add overlapping capabilities under the closest existing category.
3. Preserve old skills in archive and route old names to new category/tool nodes.
4. Re-run skill-cleaner after structural changes.

### Standalone Specialists

Keep visible because they are narrow but independent:

- `frontend-design`
- `humanizer`
- `humanizer-zh`
- `dhdna-profiler`
- `iso-13485-certification`

Plugin/system specialists remain platform-managed:

- `browser`
- `chrome`
- `github`
- `gh-fix-ci`
- `gh-address-comments`
- `yeet`
- `openai-docs`
