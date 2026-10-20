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
- `native-textbook`: [native Chinese document workflow](../../native-textbook/SKILL.md); semantic work packages, scoped terms and resumable state; book mode uses ElegantBook, slide mode preserves PPT page style with direct XeLaTeX; native figures/covers and rendered-page review remain required; editable PPTX stays with `presentations`.

## Flows

- `pdf-to-docx-report`: `pdf` -> `markitdown` -> `docx`.
- `spreadsheet-analysis-report`: `xlsx` -> analysis -> `docx` or `pptx`.
- `deck-from-paper`: `pdf` or `markitdown` -> outline -> `pptx`.
- `batch-conversion`: `markitdown` -> target format tool.
- `native-textbook`: source evidence -> risk sample -> semantic packages / terminology / state -> bounded DeepSeek semantic translation/TeX -> verified draft integration -> native/vector figures and cover -> ElegantBook -> source, typography and all-output-page QA -> independent rebuild and release.
- `native-slide-pdf`: source slide evidence -> page/geometry contract -> bounded slide workers -> direct XeLaTeX -> actual PDF checks and all-page review -> independent release; use the same `native-textbook` entry.

## Loading Rule

Use plugin skills first when active. Use archived tool nodes for local implementation details or format-specific edge cases.
