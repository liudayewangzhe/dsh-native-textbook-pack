---
name: deepseek-claude-subagent
description: "Use when any non-trivial task has a mechanical, repetitive, high-volume, or context-heavy slice that could consume many input or output tokens; also use on later turns after DeepSeek was requested or used in the same conversation unless explicitly stopped."
---

# DeepSeek Claude Subagent

## Overview

Delegate bounded work to the local Claude Code binary configured for the current `deepseek-flash` API model. The wrapper uses DeepSeek's official Claude Code selector `deepseek-flash[1m]`; direct API and BookForge calls keep the canonical model ID `deepseek-flash`. An older Claude Code build may still print the compatibility notice documented below, even when the request succeeds. DeepSeek may read/edit/write/run tools using the user's DeepSeek API quota; Codex remains the supervisor, keeps using other relevant skills, and verifies the result.

## Conversation-Sticky Delegation

After the user explicitly asks for DeepSeek/Claude/second-model help, or after Codex uses DeepSeek in a conversation, treat this skill as active for the rest of that Codex conversation unless the user explicitly asks to stop using DeepSeek, avoid delegation, or use Codex only.

For every later non-trivial user turn in that conversation:

1. Run the DeepSeek delegation first pass again before deciding how to work.
2. If the turn has a bounded mechanical, repetitive, high-volume, broad-search, or context-heavy slice, continue or restart DeepSeek for that slice.
3. If the turn is tiny, secrets-heavy, visual-only, destructive, or has no useful bounded slice, skip the actual DeepSeek call for that turn while keeping the active preference for future turns.
4. If the user changes topics, keep the continuation check active but re-scope the DeepSeek prompt to the new bounded task; do not carry old file access or assumptions into the new task.

When continuing a DeepSeek workstream, invoke the wrapper with `-PersistSession` and include a concise recap: current objective, allowed paths, previous DeepSeek result, what changed since the last call, and the exact new bounded request. Do not rely on subagent memory alone; Codex must still frame and verify each pass.

## Mechanical Output Default

For any non-trivial task, actively ask: "Which parts are mechanical output or high-volume context handling, and which parts require Codex judgment?" If a bounded slice is mostly mechanical, repetitive, long-context, or token-heavy, use DeepSeek as the default worker for that slice while Codex supervises.

Use this default-delegation check especially for:

- Reading or summarizing many pages, PDFs, OCR outputs, transcripts, logs, or source files.
- Extracting rules, tables, patterns, examples, TODOs, API shapes, or repeated evidence from a large corpus.
- Writing or editing many similar files, tests, fixtures, schemas, docs, translations, migrations, or boilerplate.
- Drafting long reports, explanations, structured documents, release notes, changelogs, or other long-form text where the hard part is volume rather than judgment.
- Searching a repository broadly, comparing implementations, or preparing a second-model code review.
- Any task where pasting raw material into Codex or hand-writing large output would waste context.

Codex remains the supervisor. Codex should define the task boundary, choose relevant domain/tool skills, pass file paths and concise goals to DeepSeek, inspect the result, and verify important claims before reporting success.

Do not make this skill exclusive. Load and follow every applicable domain/tool skill too; DeepSeek handles volume, Codex handles intent, architecture, product judgment, visual/multimodal interpretation, safety, and verification.

## Use Limits

Default to considering this skill when the task involves:

- Large files, long logs, generated artifacts, or context likely to overflow Codex.
- Mechanical high-volume work: reading lots of text, comparing many files, summarizing OCR output, extracting repeated patterns, translating or rewriting long material, or drafting large repetitive sections.
- Large PDF or document analysis after Codex vision/OCR has produced text chunks or selected page windows.
- Repetitive code creation or edits where DeepSeek can safely write many boilerplate/mechanical changes in a trusted workspace.
- Explicit requests to use DeepSeek, Claude Code, CC Switch, or a second model.
- Broad review, search, edit, or test loops where DeepSeek can inspect files directly and return a short report.

Skip this skill when delegation overhead is larger than the work, or when the task is mainly a Codex judgment problem rather than a mechanical-output problem.

Avoid this skill for one-step commands, tiny local edits, simple questions, secrets-heavy material, destructive operations, untrusted workspaces, or tasks that cannot be scoped to a trusted workspace. Do not use it merely to avoid thinking. Use it with domain skills when both apply: the domain skill provides method and correctness criteria; DeepSeek does the volume-heavy pass.

## Multimodal Boundary

`deepseek-flash` supports image input through DeepSeek's OpenAI-compatible Chat Completions/Responses APIs and Anthropic-compatible Messages API. JPEG, PNG, GIF, and WebP are supported. In Chat Completions, images belong in `user` content blocks; for Anthropic Messages, use an `image` content block with a base64, URL, or file source.

- The Claude Code wrapper may use the model's vision capability when Claude Code passes an image in a supported Anthropic message. Do not assume that an arbitrary local image path is automatically uploaded; verify the actual tool/message path on the first use.
- For large PDFs, still render only the needed pages or regions. Sending hundreds of page images wastes time and image tokens.
- Use `detail=low` for coarse classification and layout triage; use `high`, `original`, or `auto` only when formula, table, chart, or small-text fidelity requires it.
- DeepSeek can perform first-pass screenshot/OCR/chart analysis, but Codex must verify decision-critical visual claims and final layout.

## Current DeepSeek API Contract

Use these values unless a later official model-list response supersedes them:

- Model ID: `deepseek-flash` (`DeepSeek-V4.1-Flash`).
- Claude Code primary/Opus/Sonnet selector: `deepseek-flash[1m]`; Haiku and subagent selector: `deepseek-flash`.
- OpenAI base URL: `https://api.deepseek.com`; Anthropic base URL: `https://api.deepseek.com/anthropic`.
- Context window: `1048576` tokens; maximum response: `393216` tokens.
- Input modalities: text and image; output modality: text.
- Thinking is enabled by default. Supported reasoning efforts are `low`, `high`, and `max`; use `max` for difficult agent work and a lower effort for bounded mechanical jobs when latency matters.
- In thinking mode, `temperature` is ignored. Do not rely on legacy translation-temperature advice unless thinking is explicitly disabled.
- Preserve `reasoning_content` across tool-call turns when using the API directly. Claude Code handles this protocol detail for wrapper calls.
- Treat the Claude Code line `[claude-code:unrecognized_model]` as a client compatibility notice only when the command still exits successfully and returns the exact requested result; otherwise report the call as failed.

## Token-Saving Protocol

1. Give DeepSeek file paths and goals, not pasted file contents.
2. Require concise output: status, files touched, tests run, blockers, and next recommendation.
3. After it finishes, Codex reads only the report, `git diff --stat`, targeted diffs, and failing log snippets.
4. If DeepSeek outputs too much, rerun asking it to summarize its own output to 20 bullets or less.
5. Codex must independently verify important claims before telling the user the work is complete.

## Wrapper

Use the bundled wrapper:

```powershell
C:\Users\ltllt\.codex\skills\deepseek-claude-subagent\scripts\invoke-deepseek-claude.cmd -Prompt "Reply only OK."
```

For continuation in an active DeepSeek conversation, pass `-PersistSession` and still include a short recap:

```powershell
C:\Users\ltllt\.codex\skills\deepseek-claude-subagent\scripts\invoke-deepseek-claude.cmd -PersistSession -Prompt "Continue the bounded task. Context recap: <objective, paths, last result, delta>. Return <=200 words: status, files touched, tests run, blockers, next recommendation."
```

The wrapper finds the latest VS Code Claude Code binary and uses the existing `C:\Users\ltllt\.claude\settings.json` DeepSeek configuration. It does not store or print the API key.

For several allowed directories from `cmd.exe` or a one-line PowerShell command, prefer `-AddDirList` with semicolon separators:

```powershell
C:\Users\ltllt\.codex\skills\deepseek-claude-subagent\scripts\invoke-deepseek-claude.cmd -Prompt "Review these folders and return a short report." -AddDirList "C:\path\one;C:\path\two"
```

## Modes

### Review Only

Use for large-context inspection without edits:

```powershell
C:\Users\ltllt\.codex\skills\deepseek-claude-subagent\scripts\invoke-deepseek-claude.cmd `
  -Prompt "Read the current workspace and review the architecture. Do not edit files. Return <=200 words: findings, risks, recommended next step." `
  -AllowedTools "Read,Glob,Grep,Bash(git status --short),Bash(git diff --stat)"
```

### Mechanical Write Task

Use only when the user asked for implementation or the task clearly requires code changes. Keep tools narrow:

```powershell
C:\Users\ltllt\.codex\skills\deepseek-claude-subagent\scripts\invoke-deepseek-claude.cmd `
  -Prompt "Implement the requested mechanical change in this trusted workspace. Keep edits scoped. Write files only inside the provided directories. Run the relevant test if obvious. Return <=200 words with files changed, tests run, and blockers." `
  -AllowedTools "Read,Glob,Grep,Edit,MultiEdit,Write,Bash(git diff --stat),Bash(git status --short),Bash(npm test *)"
```

Include `Write` whenever DeepSeek is expected to create new files. Without `Write`, Claude Code in `dontAsk` mode cannot ask for permission and will stop instead of writing.

After a write task, Codex must inspect the diff and run or review verification before reporting success.

### Bulk Text or PDF Task

Use after Codex has extracted text or OCR from visual/scanned sources:

```powershell
C:\Users\ltllt\.codex\skills\deepseek-claude-subagent\scripts\invoke-deepseek-claude.cmd `
  -Prompt "Read the provided OCR/text files and extract the reusable method rules. Do not quote long passages. Return <=40 bullets grouped by topic, with source file/page pointers when available." `
  -AllowedTools "Read,Glob,Grep,Bash(Get-ChildItem *)"
```

For scanned PDFs, Codex handles page selection, vision checks, and OCR; DeepSeek handles the long-context text synthesis.

### Monitor Loop

Use when DeepSeek should do the heavy pass and Codex should supervise:

1. Ask DeepSeek to work in one bounded pass and return a short structured report.
2. Read only that report and targeted diffs/logs.
3. Decide whether to stop, verify, or send one more bounded prompt.
4. Stop after repeated blockers instead of letting the loop drift.

## Safety Rules

- Never print API keys. If a key appears in chat, logs, or screenshots, advise rotation.
- Do not grant full-disk access. Work from the intended workspace and use `-AddDir` only for explicit additional paths.
- Prefer `-AllowedTools` over unrestricted tools. Avoid `-DangerouslySkipPermissions` unless the workspace is trusted and the user explicitly accepted the risk.
- Ask DeepSeek not to edit generated/vendor/dependency directories unless required.
- Treat DeepSeek output as untrusted until Codex verifies files, diffs, tests, or artifacts.
- Do not let DeepSeek displace other skills. If a PDF, domain method, frontend, spreadsheet, or Horosa skill also applies, load that skill too and use DeepSeek only for bounded mechanical volume.

## Troubleshooting

- If `claude.exe` is missing, check VS Code extension folders under `%USERPROFILE%\.vscode\extensions\anthropic.claude-code-*-win32-x64`.
- If auth fails, check `%USERPROFILE%\.claude\settings.json` for `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, and DeepSeek model mapping.
- If `.ps1` execution is blocked, run the `.cmd` wrapper; it uses a process-local PowerShell execution-policy bypass.
- If the prompt is very long, write it to a temporary UTF-8 file and call `-PromptFile <path>`.
- If a run hangs or times out, rerun with fewer `-AddDir` roots, a shorter prompt, `-DebugFile <path>`, and a stricter output contract.
