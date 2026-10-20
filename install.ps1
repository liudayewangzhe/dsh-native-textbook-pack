#Requires -Version 5.1
<#
  原生中文教材转换 · 技能与引擎安装器

  作用：把本包里的 skills 装进 DSH 的技能目录，把 Native Forge 引擎装到固定位置，
        为引擎准备好 PyMuPDF，并生成可移植的 nf.cmd 启动器。

  用法（在解压后的包目录里）：
      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -WhatIfOnly
  双击 install.cmd 等价。
#>
[CmdletBinding()]
param(
    [string]$PackRoot,
    [string]$DshHome,
    [string]$EngineHome,
    [string]$SkillsRoot,
    [string]$PythonExe,
    [string]$WheelDir,
    [switch]$Force,
    [switch]$NoEnvVar,
    [switch]$SkipEngine,
    [switch]$SkipSkills,
    [switch]$WhatIfOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------- 基础工具
$script:StepNo = 0
function Say([string]$m)      { Write-Host $m }
function Head([string]$m) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
    Write-Host $m -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
}
function Ok([string]$m)   { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Info([string]$m) { Write-Host "  [..]   $m" -ForegroundColor Gray }
function Warn([string]$m) { Write-Host "  [警告] $m" -ForegroundColor Yellow }
function Bad([string]$m)  { Write-Host "  [失败] $m" -ForegroundColor Red }

function Get-FileHashSafe([string]$p) {
    try { return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash } catch { return $null }
}

function Copy-Tree([string]$src, [string]$dst) {
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    $exclude = @('.git', '__pycache__', '.github', 'node_modules')
    Get-ChildItem -LiteralPath $src -Force | ForEach-Object {
        if ($exclude -contains $_.Name) { return }
        $target = Join-Path $dst $_.Name
        if ($_.PSIsContainer) { Copy-Tree $_.FullName $target }
        else { Copy-Item -LiteralPath $_.FullName -Destination $target -Force }
    }
}

function Test-PythonModule([string]$py, [string[]]$modules) {
    $lines = @('import importlib')
    foreach ($m in $modules) { $lines += "importlib.import_module('$m')" }
    $lines += "print('PY_OK')"
    $code = ($lines -join "`n")
    try {
        $out = & $py -c $code 2>&1
        return ($LASTEXITCODE -eq 0 -and (($out | Out-String) -match 'PY_OK'))
    } catch { return $false }
}

function Resolve-PythonPath([string]$exe) {
    try {
        $p = & $exe -c "import sys;print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { return ($p | Select-Object -First 1).Trim() }
    } catch { }
    return $null
}

# ---------------------------------------------------------------- 参数落定
if (-not $PackRoot) { $PackRoot = $PSScriptRoot }
$PackRoot = (Resolve-Path -LiteralPath $PackRoot).Path

if (-not $DshHome) {
    if ($env:DSH_HOME) { $DshHome = $env:DSH_HOME }
    else { $DshHome = Join-Path $env:USERPROFILE '.dsh' }
}
if (-not $EngineHome)  { $EngineHome  = Join-Path $DshHome 'native-forge' }
if (-not $SkillsRoot)  { $SkillsRoot  = Join-Path $DshHome 'skills' }
if (-not $WheelDir)    { $WheelDir    = Join-Path $PackRoot 'wheels' }

Head "安装计划"
Write-Host "  包目录     : $PackRoot"
Write-Host "  DSH 家目录 : $DshHome"
Write-Host "  技能目录   : $SkillsRoot"
Write-Host "  引擎目录   : $EngineHome"
Write-Host "  轮子目录   : $WheelDir"

foreach ($need in @('skills', 'engine')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PackRoot $need))) {
        throw "包不完整：缺少 $need 目录（请在解压后的完整目录里运行）"
    }
}

# ---------------------------------------------------------------- 1. 找 Python
Head "1/7 选择 Python 解释器"
$candidates = New-Object System.Collections.Generic.List[string]

if ($PythonExe) { $candidates.Add($PythonExe) }
if ($env:NF_PY) { $candidates.Add($env:NF_PY) }

# DSH 自带运行时优先（目标机器一定有）
$rt = Join-Path $DshHome 'dsh-runtimes'
if (Test-Path -LiteralPath $rt) {
    Get-ChildItem -LiteralPath $rt -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $p = Join-Path $_.FullName 'dependencies\python\python.exe'
        if (Test-Path -LiteralPath $p) { $candidates.Add($p) }
    }
}
# 常见独立安装
foreach ($c in @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "C:\Python313\python.exe", "C:\Python312\python.exe", "C:\Python311\python.exe"
)) { if (Test-Path -LiteralPath $c) { $candidates.Add($c) } }
foreach ($n in @('python.exe', 'python3.exe')) {
    $g = Get-Command $n -ErrorAction SilentlyContinue
    if ($g) { $candidates.Add($g.Source) }
}
$pyLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue

$chosen = $null
$chosenHasFitz = $false
foreach ($c in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $c)) { continue }
    try {
        $ver = & $c -c "import sys;print('%d.%d.%d'%sys.version_info[:3])" 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
    } catch { continue }
    $parts = ($ver -split '\.') | ForEach-Object { [int]$_ }
    if ($parts[0] -lt 3 -or ($parts[0] -eq 3 -and $parts[1] -lt 10)) {
        Info "跳过 $c （Python $ver < 3.10）"; continue
    }
    $hasFitz = Test-PythonModule $c @('fitz')
    $hasCore = Test-PythonModule $c @('numpy', 'PIL')
    Info "$c  →  Python $ver   PyMuPDF=$(if($hasFitz){'有'}else{'无'})   numpy/Pillow=$(if($hasCore){'有'}else{'无'})"
    if (-not $chosen) { $chosen = $c; $chosenHasFitz = $hasFitz }
    elseif ($hasFitz -and -not $chosenHasFitz) { $chosen = $c; $chosenHasFitz = $hasFitz }
}
if (-not $chosen -and $pyLauncher) {
    # py.exe 必须带 -3，否则可能选到 Python 2
    $real = $null
    try {
        $real = (& $pyLauncher.Source -3 -c "import sys;print(sys.executable)" 2>$null |
                 Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) { $real = $null }
    } catch { $real = $null }
    if ($real) { $real = $real.Trim() }
    if ($real -and (Test-Path -LiteralPath $real)) {
        $chosen = $real
        $chosenHasFitz = Test-PythonModule $chosen @('fitz')
        Info "通过 py -3 解析到 Python：$chosen"
    }
}
if (-not $chosen) {
    Bad "没有找到 Python 3.10+。"
    Say  "  请先安装 Python 3.10 或更高版本（https://www.python.org/downloads/windows/ ），"
    Say  "  或安装/修复 DSH 桌面版（它自带运行时 Python），然后重新运行本安装器。"
    exit 2
}
Ok "解释器：$chosen"

# ---------------------------------------------------------------- 2. 装技能
Head "2/7 安装技能到 $SkillsRoot"
$installSkillNames = @()
if ($SkipSkills) { Warn "按参数跳过" }
else {
    if (-not $WhatIfOnly) { New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null }
    $srcSkills = Get-ChildItem -LiteralPath (Join-Path $PackRoot 'skills') -Directory |
                 Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') }
    foreach ($s in $srcSkills) {
        $dst = Join-Path $SkillsRoot $s.Name
        if (Test-Path -LiteralPath $dst) {
            $isLink = (Get-Item -LiteralPath $dst -Force).LinkType
            $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
            $bak = "$dst.bak-$stamp"
            if ($WhatIfOnly) {
                if ($Force) { Info "将会直接覆盖 $($s.Name)（-Force，不备份）" }
                else { Info "将会备份 $($s.Name) → $bak 并覆盖" }
            }
            else {
                try {
                    if ($Force) {
                        if ($isLink) { (Get-Item -LiteralPath $dst -Force).Delete() }
                        else { Remove-Item -LiteralPath $dst -Recurse -Force }
                        Info "已按 -Force 直接覆盖 $($s.Name)（未备份）"
                    }
                    elseif ($isLink) { (Get-Item -LiteralPath $dst -Force).Delete() }
                    else {
                        Move-Item -LiteralPath $dst -Destination $bak -Force
                        Info "已备份原有 $($s.Name) → $(Split-Path $bak -Leaf)"
                    }
                } catch { Warn "覆盖/备份 $($s.Name) 失败：$($_.Exception.Message)" }
            }
        }
        if (-not $WhatIfOnly) { Copy-Tree $s.FullName $dst }
        $installSkillNames += $s.Name
        Ok "技能 $($s.Name)"
    }
}

# 2b. 把技能文档里指向制作机的绝对技能路径改写成本机安装路径
#     （office-files / skill-network 之类的路由器里写着 C:\Users\ltllt\.codex\skills\...）
if (-not $SkipSkills -and -not $WhatIfOnly) {
    $deadPrefixes = @(
        'C:\Users\ltllt\.codex\skills\',
        'C:\Users\ltllt\.agents\skills\',
        'C:\Users\ltllt\.dsh\skills\'
    )
    $rewritten = 0
    foreach ($n in $installSkillNames) {
        $targets = Get-ChildItem -LiteralPath (Join-Path $SkillsRoot $n) -Recurse -File -Include *.md, *.yaml, *.yml, *.json -ErrorAction SilentlyContinue
        foreach ($t in $targets) {
            $enc = New-Object System.Text.UTF8Encoding($false)
            $text = [System.IO.File]::ReadAllText($t.FullName)
            $new = $text
            foreach ($pre in $deadPrefixes) {
                $new = $new.Replace($pre, $SkillsRoot + '\')
            }
            # 引擎默认路径（制作机 E:\PDF\_ZH\native-forge）也改写成本机安装目录
            $new = $new.Replace('E:\PDF\_ZH\native-forge', $EngineHome)
            if ($new -ne $text) {
                [System.IO.File]::WriteAllText($t.FullName, $new, $enc)
                $rewritten++
            }
        }
    }
    if ($rewritten -gt 0) { Ok "已把 $rewritten 个技能文档里的制作机路径改写为本机路径" }
    else { Info "技能文档里没有需要改写的绝对路径" }
}

# ---------------------------------------------------------------- 3. 装引擎
Head "3/7 安装 Native Forge 引擎到 $EngineHome"
if ($SkipEngine) { Warn "按参数跳过" }
else {
    $srcEngine = Join-Path $PackRoot 'engine\native-forge'
    if (-not (Test-Path -LiteralPath $srcEngine)) { throw "缺少 engine\native-forge" }
    if (-not $WhatIfOnly) {
        New-Item -ItemType Directory -Force -Path $EngineHome | Out-Null
        Copy-Tree $srcEngine $EngineHome
    }
    Ok "引擎文件已就位"
}

# ---------------------------------------------------------------- 4. PyMuPDF
Head "4/7 准备 PyMuPDF（引擎读 PDF 必需）"
$pylibs = Join-Path $EngineHome 'pylibs'
$fitzOk = $false
if (-not $SkipEngine -and $chosenHasFitz) {
    Ok "所选解释器已自带 PyMuPDF，无需安装"
    $fitzOk = $true
}
if (-not $SkipEngine -and -not $fitzOk) {
    $wheel = Get-ChildItem -LiteralPath $WheelDir -Filter 'pymupdf*.whl' -ErrorAction SilentlyContinue |
             Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $pylibs | Out-Null
    if ($WhatIfOnly) {
        Info "将会把 PyMuPDF 装到 $pylibs（离线优先：$($wheel.Name)）"
        $fitzOk = $true
    } else {
        $okInstall = $false
        if ($wheel) {
            Info "离线安装 $($wheel.Name) …"
            & $chosen -m pip install --quiet --disable-pip-version-check --no-index `
                --find-links $WheelDir --target $pylibs 'pymupdf==1.28.0' 2>&1 |
                ForEach-Object { Info $_ }
            $okInstall = ($LASTEXITCODE -eq 0)
        }
        if (-not $okInstall) {
            Warn "离线安装未成功，尝试联网 pip install …"
            & $chosen -m pip install --quiet --disable-pip-version-check --target $pylibs 'pymupdf>=1.24' 2>&1 |
                ForEach-Object { Info $_ }
            $okInstall = ($LASTEXITCODE -eq 0)
        }
        if ($okInstall) {
            $env:PYTHONPATH = "$pylibs;$env:PYTHONPATH"
            $fitzOk = Test-PythonModule $chosen @('fitz')
        }
        if ($fitzOk) { Ok "PyMuPDF 已装入 $pylibs" }
        else {
            Warn "PyMuPDF 未安装成功。引擎仍可运行，但读 PDF 的命令会报 'PyMuPDF (fitz) is required'。"
            Warn "手工修复：`"$chosen`" -m pip install --target `"$pylibs`" pymupdf"
        }
    }
}

# ---------------------------------------------------------------- 5. 生成 nf.cmd
Head "5/7 生成可移植启动器 nf.cmd"
if ($SkipEngine) { Warn "按参数跳过引擎，不生成 nf.cmd" }
else {
$nfCmd = Join-Path $EngineHome 'nf.cmd'
$stampNow = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$nfBody = @"
@echo off
rem ---------------------------------------------------------------
rem  Native Forge launcher, generated by install.ps1 on $stampNow
rem  To switch Python: set env var NF_PY to another python.exe,
rem  or delete this file and re-run install.ps1.
rem  NOTE: ASCII when the install path is ASCII; when the path contains
rem  non-ASCII characters this file is written in the system ANSI code page
rem  and starts with "chcp <cp>" so cmd.exe parses it in the same encoding.
rem ---------------------------------------------------------------
setlocal
set "NF_HOME=%~dp0"
set "NF_PY_BAK=$chosen"
if defined NF_PY if exist "%NF_PY%" goto :run
set "NF_PY=%NF_PY_BAK%"
:run
if not exist "%NF_PY%" (
  echo [Native Forge] Python not found: "%NF_PY%"  1>&2
  echo [Native Forge] Set NF_PY to a working python.exe, or re-run install.ps1.  1>&2
  exit /b 2
)
set "PYTHONPATH=%NF_HOME%pylibs;%PYTHONPATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%NF_PY%" "%NF_HOME%engine\native_forge.py" %*
exit /b %ERRORLEVEL%
"@
    # cmd.exe 对 LF-only / 混合行尾的批处理解析不可靠；统一成 CRLF
    $nfBody = $nfBody -replace "`r?`n", "`r`n"
    if ($WhatIfOnly) { Info "将会写入 $nfCmd" }
else {
    # cmd.exe 按当前代码页读取批处理：纯 ASCII 用 ASCII 写最安全；
    # 安装路径含非 ASCII（如中文用户名）时必须改用系统 ANSI 代码页（中文 Windows 为 GBK/936），
    # 否则解释器路径会被写成 "?"，启动器直接报 Python not found。
    $ansiCp = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
    if ($nfBody -match '[^\x00-\x7F]') {
        # cmd.exe 解析 .cmd 时用「当前控制台代码页」；DSH 的 shell 可能是 UTF-8(65001)，
        # 而文件按 ANSI(936) 写入。文件第一行必须把代码页切回写入时的代码页，否则中文路径变乱码。
        $nfBody = $nfBody.Replace("@echo off", "@echo off`r`nchcp $ansiCp >nul")
        Warn "安装路径含非 ASCII 字符，nf.cmd 将按系统 ANSI 代码页 $ansiCp 写入，并自带 chcp 切换。"
        [System.IO.File]::WriteAllText($nfCmd, $nfBody, [System.Text.Encoding]::GetEncoding($ansiCp))
    } else {
        [System.IO.File]::WriteAllText($nfCmd, $nfBody, [System.Text.Encoding]::ASCII)
    }
    Ok "已生成 $nfCmd"
}
}

# 让技能里的 nf.cmd 默认指向本机引擎
$skillNf = Join-Path $SkillsRoot 'native-textbook\scripts\nf.cmd'
if ((Test-Path -LiteralPath $skillNf) -and -not $WhatIfOnly) {
    $txt = Get-Content -LiteralPath $skillNf -Raw
    $txt = [regex]::Replace($txt, 'set "NATIVE_FORGE_HOME=.*"',
                            "set `"NATIVE_FORGE_HOME=$EngineHome`"")
    $txt = $txt -replace "`r?`n", "`r`n"
    $ansiCp = [System.Globalization.CultureInfo]::CurrentCulture.TextInfo.ANSICodePage
    if ($txt -match '[^\x00-\x7F]') {
        # 同 nf.cmd：按 ANSI 代码页写入时，文件开头补 chcp，避免 UTF-8 控制台下解析错乱
        $txt = [regex]::Replace($txt, '(?m)^@echo off\r?\n',
                                "@echo off`r`nchcp $ansiCp >nul`r`n")
        [System.IO.File]::WriteAllText($skillNf, $txt, [System.Text.Encoding]::GetEncoding($ansiCp))
    } else {
        [System.IO.File]::WriteAllText($skillNf, $txt, [System.Text.Encoding]::ASCII)
    }
    Ok "技能内 nf.cmd 默认引擎 → $EngineHome"
}

# ---------------------------------------------------------------- 6. 环境变量
Head "6/7 设置环境变量（用户级）"
if ($NoEnvVar) { Warn "按参数跳过" }
elseif ($WhatIfOnly) { Info "将会把 NATIVE_FORGE_HOME 设为 $EngineHome" }
else {
    try {
        [Environment]::SetEnvironmentVariable('NATIVE_FORGE_HOME', $EngineHome, 'User')
        $env:NATIVE_FORGE_HOME = $EngineHome
        Ok "NATIVE_FORGE_HOME=$EngineHome"
    } catch { Warn "设置 NATIVE_FORGE_HOME 失败：$($_.Exception.Message)" }
}

# ---------------------------------------------------------------- 7. 验证
Head "7/7 自检"
$problems = @()

# 7.1 技能结构
if ($SkipSkills) { Info "跳过技能结构检查" }
elseif ($WhatIfOnly) { Info "演练模式：跳过技能结构检查（文件尚未复制）" }
else {
    foreach ($n in $installSkillNames) {
        $sk = Join-Path $SkillsRoot "$n\SKILL.md"
        if (-not (Test-Path -LiteralPath $sk)) { $problems += "技能 $n 缺 SKILL.md"; continue }
        $head = Get-Content -LiteralPath $sk -TotalCount 12 -Encoding UTF8
        $hasName = ($head | Where-Object { $_ -match '^\s*name\s*:' }).Count -gt 0
        $hasDesc = ($head | Where-Object { $_ -match '^\s*description\s*:' }).Count -gt 0
        if (-not ($hasName -and $hasDesc)) { $problems += "技能 $n 的 frontmatter 缺 name/description" }
    }
    if (-not $problems) { Ok "$($installSkillNames.Count) 个技能结构检查通过" }
}

# 7.2 Python 依赖
if (-not $SkipEngine) {
    $env:PYTHONPATH = "$pylibs;$env:PYTHONPATH"
    if (Test-PythonModule $chosen @('fitz')) { Ok "PyMuPDF 可导入" }
    else { $problems += "PyMuPDF 不可导入" }
    if (Test-PythonModule $chosen @('numpy', 'PIL')) { Ok "numpy / Pillow 可导入" }
    else { $problems += "numpy 或 Pillow 不可导入（扫描件修复脚本需要）" }
}

# 7.3 引擎 doctor
if (-not $SkipEngine -and -not $WhatIfOnly) {
    Info "运行 nf.cmd doctor …"
    $doc = & $nfCmd doctor 2>&1
    $docText = ($doc | Out-String)
    $doc | Select-Object -First 40 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    $parsed = $null
    try { $parsed = $docText | ConvertFrom-Json } catch { }
    if ($parsed) {
        $pymupdfOk  = [bool]$parsed.pymupdf.available
        $templatesOk = [bool]$parsed.templates.ok
        $xelatexOk  = [bool]$parsed.xelatex.found
        if ($pymupdfOk)  { Ok "doctor: PyMuPDF $($parsed.pymupdf.version)" }  else { $problems += "doctor: PyMuPDF 不可用" }
        if ($templatesOk) { Ok "doctor: 模板完整" } else { $problems += "doctor: 模板缺失" }
        if ($xelatexOk)  { Ok "doctor: 找到 xelatex" } else { Warn "doctor: 没找到 xelatex（编译阶段会失败，先装 TeX Live）" }
        if (-not [bool]$parsed.ok -and $pymupdfOk -and $templatesOk) {
            $freeMB = [math]::Round([double]$parsed.memory.available_bytes / 1MB)
            Warn "doctor 报内存门禁未过：当前空闲物理内存约 $freeMB MB，低于 1 GiB 阈值。"
            Warn "这是工作流的规定动作（低内存时暂停本地重活），不是安装失败；腾出内存后重跑 nf.cmd doctor 即可。"
        }
    } elseif ($LASTEXITCODE -eq 0) {
        Ok "引擎 doctor 通过"
    } else {
        $problems += "引擎 doctor 返回码 $LASTEXITCODE（无法解析输出，请手工跑一次 nf.cmd doctor）"
    }
}

# 7.4 XeLaTeX
$xelatex = (Get-Command 'xelatex.exe' -ErrorAction SilentlyContinue).Source
if (-not $xelatex) {
    foreach ($p in @('D:\texlive\2024\bin\windows\xelatex.exe', 'C:\texlive\2024\bin\windows\xelatex.exe',
                     'C:\texlive\2023\bin\windows\xelatex.exe')) {
        if (Test-Path -LiteralPath $p) { $xelatex = $p; break }
    }
}
if ($xelatex) { Ok "XeLaTeX: $xelatex" }
else {
    Warn "没有找到 xelatex。book/slide 交付的编译阶段需要 TeX Live。"
    Warn "安装 TeX Live 后确认 xelatex 在 PATH 上（引擎用 shutil.which('xelatex') 解析）。"
}

Write-Host ""
Write-Host ("=" * 72) -ForegroundColor DarkCyan
if ($problems.Count -eq 0) {
    Write-Host "安装完成，全部自检通过。" -ForegroundColor Green
} else {
    Write-Host "安装完成，但有 $($problems.Count) 项需要处理：" -ForegroundColor Yellow
    $problems | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
}
Write-Host ("=" * 72) -ForegroundColor DarkCyan
Say ""
Say "下一步："
Say "  1. 完全退出并重开 DSH（技能目录在会话启动时扫描）。"
Say "  2. 在 DSH 里让它读：$SkillsRoot\native-textbook\SKILL.md"
Say "  3. 复现一次真实任务，例如："
Say "     `$NF = '$nfCmd'"
Say "     & `$NF doctor"
Say "     & `$NF prepare --source '原稿.pdf' --pages 24-32 --project 'D:\proj\demo' --title '书名'"
Say "  4. 经验手册在包内 playbook\ 目录；历史会话在 sessions\ 目录。"
