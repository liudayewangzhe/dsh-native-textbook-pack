#Requires -Version 5.1
<#
  Verify this pack against MANIFEST.json (thin wrapper around verify_pack.py).

  This script is intentionally ASCII-only: Windows PowerShell 5.1 reads BOM-less
  scripts in the system ANSI code page, so non-ASCII text here can break parsing
  on non-English Windows.  All user-facing detail comes from verify_pack.py.

  Usage:
      powershell -NoProfile -ExecutionPolicy Bypass -File .\verify-pack.ps1
      .\verify-pack.ps1 -PackRoot <dir> [-Strict]

  Exit codes: 0 = all files match; 1 = missing/mismatched files;
              2 = no usable Python 3.8+ found.
#>
[CmdletBinding()]
param(
    [string]$PackRoot,
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'
if (-not $PackRoot) { $PackRoot = $PSScriptRoot }
$PackRoot = (Resolve-Path -LiteralPath $PackRoot).Path
$script = Join-Path $PackRoot 'verify_pack.py'
if (-not (Test-Path -LiteralPath $script)) {
    Write-Host "verify_pack.py not found: $script" -ForegroundColor Red
    exit 1
}

# Try in order: NF_PY -> DSH bundled runtime -> python on PATH -> py -3
$candidates = New-Object System.Collections.Generic.List[string]
if ($env:NF_PY) { $candidates.Add($env:NF_PY) }
$rt = Join-Path $env:USERPROFILE '.dsh\dsh-runtimes'
if (Test-Path -LiteralPath $rt) {
    Get-ChildItem -LiteralPath $rt -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Join-Path $_.FullName 'dependencies\python\python.exe'
        if (Test-Path -LiteralPath $p) { $candidates.Add($p) }
    }
}
foreach ($n in @('python.exe', 'python3.exe')) {
    $g = Get-Command $n -ErrorAction SilentlyContinue
    if ($g) { $candidates.Add($g.Source) }
}

$argList = @($script, '--pack', $PackRoot)
if ($Strict) { $argList += '--strict' }

foreach ($py in ($candidates | Select-Object -Unique)) {
    if (-not $py -or -not (Test-Path -LiteralPath $py)) { continue }
    & $py @argList
    if ($LASTEXITCODE -ne 2) { exit $LASTEXITCODE }
}

$pyLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
if ($pyLauncher) {
    & $pyLauncher.Source -3 @argList
    if ($LASTEXITCODE -ne 2) { exit $LASTEXITCODE }
}

Write-Host "No Python 3.8+ found. Install Python, or set NF_PY to python.exe, then retry." -ForegroundColor Yellow
exit 2
