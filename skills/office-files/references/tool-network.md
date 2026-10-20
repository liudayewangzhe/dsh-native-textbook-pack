# Office Files Tool Network

Archive root: `C:\Users\ltllt\.agents\skill-archive\20260529-skill-consolidation`

## Tool Nodes

- `docx`: Word document creation, editing, comments, redlines, formatting.
- `pptx`: PowerPoint reading, editing, creation, splitting, combining.
- `pdf`: PDF extraction, OCR, merge, split, rotate, watermark, forms.
- `xlsx`: spreadsheet creation, cleaning, formulas, charts, conversion.
- `markitdown`: convert office/PDF/HTML/media files to Markdown.
- plugin `documents`: preferred for rich DOCX render-and-verify workflows.
- plugin `presentations`: preferred for PPTX deck generation.
- plugin `spreadsheets`: preferred for spreadsheet artifacts.
- `native-textbook`: native Chinese technical PDFs; book mode uses ElegantBook, slide mode preserves PPT page style with direct XeLaTeX; editable PPTX stays with `presentations`. Direct entry: `C:\Users\ltllt\.codex\skills\native-textbook\SKILL.md`.

## Flows

- `pdf-to-docx-report`: `pdf` -> `markitdown` -> `docx`.
- `spreadsheet-analysis-report`: `xlsx` -> analysis -> `docx` or `pptx`.
- `deck-from-paper`: `pdf` or `markitdown` -> outline -> `pptx`.
- `batch-conversion`: `markitdown` -> target format tool.
- `native-textbook`: PDF evidence -> DeepSeek semantic translation/TeX -> native/vector assets -> ElegantBook -> source and all-output-page QA -> release. Use the direct entry above for this specialized flow.
- `native-slide-pdf`: source slide evidence -> page/geometry contract -> bounded slide workers -> direct XeLaTeX -> actual PDF checks and all-page review -> independent release; use the same `native-textbook` entry.

## Loading Rule

Use plugin skills first when active. Use archived tool nodes for local implementation details or format-specific edge cases.
