#Requires -Version 5.1
<#
  按 MANIFEST.json 校验本包完整性（薄封装，实际逻辑在 verify_pack.py，跨平台）。

  用法:
      powershell -NoProfile -ExecutionPolicy Bypass -File .\verify-pack.ps1
      .\verify-pack.ps1 -PackRoot <包目录>

  退出码: 0 = 全部一致；1 = 有缺失/不符；2 = 找不到可用的 Python。
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
    Write-Host "verify_pack.py 不存在：$script" -ForegroundColor Red
    exit 1
}

# 依次尝试：环境变量 NF_PY → DSH 自带运行时 → PATH 里的 python / py -3
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

Write-Host "没有找到 Python 3.8+，无法校验。请安装 Python 或设置 NF_PY 指向 python.exe。" -ForegroundColor Yellow
exit 2
