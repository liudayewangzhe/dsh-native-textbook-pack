---
name: office-files
description: Consolidated office-file skill. Use when working with DOCX, PPTX, PDF, XLSX, CSV, TSV, markdown conversion, document extraction, document editing, spreadsheet manipulation, slide decks, or file-format conversion.
---

# Office Files

Route by primary file type and desired output:

- Word or `.docx`: create, read, edit, redline, comment, or format documents.
- PowerPoint or `.pptx`: create, inspect, edit, split, combine, or export slide decks.
- Spreadsheet or `.xlsx` / `.csv` / `.tsv`: clean data, add formulas, format tables, chart, or export workbooks.
- PDF: extract text/tables/images, OCR, merge, split, rotate, watermark, encrypt, or create PDFs.
- Native Chinese technical book or slide PDF: route to `native-textbook` at `C:\Users\ltllt\.codex\skills\native-textbook\SKILL.md`; continuous textbooks use book mode, preserving PPT style in PDF uses slide mode, and editable PPTX stays with `presentations`.
- Conversion: use structured converters before ad hoc parsing.

Prefer official plugin skills when available in the current session for rich rendering and verification. Use archived source skills only for implementation details not covered by active plugins.

## Tool Network

Read `references/tool-network.md` when the user names a specific file-format tool node, asks for conversion, or needs a multi-file workflow.

## Source Map

Archived source skills:

- `docx`
- `pptx`
- `pdf`
- `xlsx`
- `markitdown`
