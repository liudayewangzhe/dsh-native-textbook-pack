param(
    [string]$Prompt,

    [string]$PromptFile,

    [string]$Model = "deepseek-flash[1m]",

    [string[]]$AllowedTools = @(),

    [string[]]$Tools = @(),

    [string[]]$AddDir = @(),

    [string]$AddDirList,

    [ValidateSet("text", "json", "stream-json")]
    [string]$OutputFormat = "text",

    [ValidateSet("acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan")]
    [string]$PermissionMode = "dontAsk",

    [string]$AppendSystemPrompt,

    [string]$DebugFile,

    [decimal]$MaxBudgetUsd,

    [switch]$PersistSession,

    [switch]$DangerouslySkipPermissions
)

$ErrorActionPreference = "Stop"

if ($PromptFile) {
    if (-not (Test-Path -LiteralPath $PromptFile)) {
        throw "PromptFile not found: $PromptFile"
    }
    $Prompt = Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8
}

if ([string]::IsNullOrWhiteSpace($Prompt)) {
    throw "Provide -Prompt or -PromptFile."
}

if ($AddDirList) {
    $AddDir += ($AddDirList -split ";" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

$extensionRoot = Join-Path $env:USERPROFILE ".vscode\extensions"
$claudeExe = Get-ChildItem -LiteralPath $extensionRoot -Directory -Filter "anthropic.claude-code-*-win32-x64" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    ForEach-Object { Join-Path $_.FullName "resources\native-binary\claude.exe" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1

if (-not $claudeExe) {
    throw "Could not find VS Code Claude Code native binary under $extensionRoot."
}

$claudeArgs = @("-p")

if ($AddDir.Count -gt 0) {
    $claudeArgs += "--add-dir"
    $claudeArgs += $AddDir
}

if ($AllowedTools.Count -gt 0) {
    $claudeArgs += "--allowedTools"
    $claudeArgs += ($AllowedTools -join ",")
} elseif ($Tools.Count -gt 0) {
    $claudeArgs += "--tools"
    $claudeArgs += ($Tools -join ",")
} else {
    $claudeArgs += "--tools"
    $claudeArgs += ""
}

if ($DangerouslySkipPermissions) {
    $claudeArgs += "--dangerously-skip-permissions"
}

$claudeArgs += @(
    "--model", $Model,
    "--output-format", $OutputFormat,
    "--permission-mode", $PermissionMode
)

if ($AppendSystemPrompt) {
    $claudeArgs += "--append-system-prompt"
    $claudeArgs += $AppendSystemPrompt
}

if ($DebugFile) {
    $claudeArgs += "--debug-file"
    $claudeArgs += $DebugFile
}

if ($MaxBudgetUsd -gt 0) {
    $claudeArgs += "--max-budget-usd"
    $claudeArgs += $MaxBudgetUsd.ToString([Globalization.CultureInfo]::InvariantCulture)
}

if (-not $PersistSession) {
    $claudeArgs += "--no-session-persistence"
}

$claudeArgs += $Prompt

& $claudeExe @claudeArgs
