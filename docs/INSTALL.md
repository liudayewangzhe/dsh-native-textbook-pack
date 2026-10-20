# 安装、升级与卸载

本文覆盖：Windows 一键安装、手动安装、离线安装、升级/重装、卸载回滚、校验完整性，以及 Linux/macOS 的手工步骤。

> 一句话结论：**Windows 上只有一件事要做——在解压/克隆后的仓库根目录双击（或运行）`install.cmd`，然后完全退出并重开 DSH。** Linux/macOS 没有一键脚本，按 §7 手工安装。

---

## 1. 前置条件

| 条件 | 说明 |
|---|---|
| 操作系统 | Windows 10/11（一键脚本仅在 Windows 上提供与实测） |
| PowerShell | `install.cmd` 会优先用 `pwsh.exe`，没有则用系统自带的 `powershell.exe`（要求 5.1+） |
| DSH 桌面版 | 已安装并能正常开会话（官方下载 <https://www.deepseek.com/download/>）；安装器优先使用 DSH 自带 Python 运行时 |
| Python | 3.10+；若 DSH 运行时可用，通常无需单独安装 |
| TeX Live | 可以装完本包再装；但**没有 xelatex 就无法编译出 PDF** |
| 磁盘 | 仓库工作区约 29 MB（其中 PyMuPDF wheel 约 19 MB）；TeX Live full 需数 GB |
| 网络 | 安装本包不需要联网（PyMuPDF wheel 随仓库）；装 TeX Live 需要 |

---

## 2. 获取仓库

```powershell
git clone https://github.com/liudayewangzhe/dsh-native-textbook-pack.git
cd dsh-native-textbook-pack
```

不用 Git 也可以：在 GitHub 页面选择 **Code → Download ZIP**，解压后进入解压出的目录。

> 路径建议短、纯英文，例如 `C:\dsh-native-textbook-pack`。安装器**支持**中文/空格路径（见 §5），但短路径能少踩历史工具链的坑。  
> 不要把仓库放在 OneDrive 等同步目录里跑重活。

---

## 3. Windows 一键安装

```powershell
.\install.cmd
```

等价于：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

> `install.ps1` 含大量中文，必须保持 **UTF-8 带 BOM**（Windows PowerShell 5.1 缺 BOM 会按 GBK 解码而报语法错误）。`install.cmd` 会在运行前检查并补 BOM；如果直接用 `powershell -File .\install.ps1` 报一堆 `Unexpected token`，先改用 `install.cmd`。

`install.cmd` 做了三件事：临时恢复 `install.ps1` 的 UTF-8 BOM（Windows PowerShell 5.1 需要）、选择 `pwsh`/`powershell`、以 `-ExecutionPolicy Bypass` 运行安装器。

### 3.1 安装器做了什么（7 步）

1. **选择 Python**：按 `-PythonExe` → `NF_PY` → DSH 运行时 → 常见安装路径 → `PATH`/`py -3` 的顺序探测，要求 3.10+，优先选已带 PyMuPDF 的解释器；
2. **安装技能并改写路径**：把 `skills\` 下带 `SKILL.md` 的顶层目录复制到 `%USERPROFILE%\.dsh\skills`；同名旧技能先改名为 `<name>.bak-<时间戳>`。随后把技能文档里制作机的绝对路径（`E:\PDF\_ZH\native-forge`、`C:\Users\ltllt\.codex\skills\...` 等）改写成本机真实安装路径，**新用户不需要手工改路径**；
3. **安装引擎**：把 `engine\native-forge\*` 复制到 `%USERPROFILE%\.dsh\native-forge`；
4. **准备 PyMuPDF**：优先用 `wheels\` 里的 wheel 离线装到 `<引擎目录>\pylibs`；失败才联网 `pip install "pymupdf>=1.24"`；
5. **生成 `nf.cmd` 启动器**：写入目标机器上真实可用的 Python 路径，并设置 `PYTHONPATH` / `PYTHONUTF8`；统一 CRLF；若路径含非 ASCII 字符，按系统 ANSI 代码页写入并在首行加 `chcp` 切回同一代码页。同时把技能侧 `native-textbook\scripts\nf.cmd` 的默认引擎路径指向本机；
6. **设置环境变量**：用户级 `NATIVE_FORGE_HOME` 指向引擎目录（`-NoEnvVar` 可跳过）；
7. **自检**：技能 frontmatter、`import fitz / numpy / PIL`、`nf.cmd doctor`、XeLaTeX 是否存在。有问题的项会列在最后的「需要处理」里。

最后一行提示 `安装完成，全部自检通过`（或有 N 项需要处理）。**`xelatex` 未找到只是警告**：可以稍后装 TeX Live，不影响技能与引擎就位。

### 3.2 装完必须做的一步

**完全退出 DSH，再重新打开。** DSH 只在会话启动时扫描技能目录；不重开就看不到新技能。

### 3.3 安装参数

| 参数 | 作用 | 默认值 |
|---|---|---|
| `-PackRoot <dir>` | 包根目录 | 脚本所在目录 |
| `-DshHome <dir>` | DSH 用户目录 | `$env:DSH_HOME`，否则 `%USERPROFILE%\.dsh` |
| `-SkillsRoot <dir>` | 技能安装目录 | `<DshHome>\skills` |
| `-EngineHome <dir>` | 引擎安装目录 | `<DshHome>\native-forge` |
| `-PythonExe <path>` | 指定 Python 解释器（优先于自动探测） | 自动探测 |
| `-WheelDir <dir>` | 离线 wheel 目录 | `<PackRoot>\wheels` |
| `-NoEnvVar` | 不设置用户级 `NATIVE_FORGE_HOME` | 设置 |
| `-SkipSkills` | 只装引擎，不装技能 | 否 |
| `-SkipEngine` | 跳过引擎复制、PyMuPDF 与 `nf.cmd` 生成（只安装/更新技能；已有引擎保持不动） | 否 |
| `-WhatIfOnly` | 演练：只打印计划，不写入技能/引擎文件（可能创建空目录） | 否 |
| `-Force` | **直接覆盖同名技能，不生成 `*.bak` 备份**；重装时想保留旧版就不要用它 | 否 |

示例（没有 `pwsh` 时把命令里的 `pwsh` 换成 `powershell`）：

```powershell
# 先看会做什么，不写入实际文件
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -WhatIfOnly

# 指定解释器与安装位置
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -PythonExe 'C:\Python312\python.exe' `
  -EngineHome 'D:\tools\native-forge'
```

> 在受限沙箱（例如某些 agent 提供的 shell）里运行安装脚本，写 `%USERPROFILE%` 可能被拒绝。建议在**普通 PowerShell 终端**里运行安装器；被沙箱拒绝的排错见 [FAQ.md](FAQ.md#windows-沙箱权限报错)。

---

## 4. 安装后的目录

| 内容 | 位置 | 说明 |
|---|---|---|
| 技能 | `%USERPROFILE%\.dsh\skills\<name>\SKILL.md` | DSH 用户技能根（扫描优先级 400） |
| 引擎 | `%USERPROFILE%\.dsh\native-forge\` | `nf.cmd`、`engine\`、`scripts\`、`templates\`、`pylibs\` |
| PyMuPDF | `%USERPROFILE%\.dsh\native-forge\pylibs\` | 由生成的 `nf.cmd` 加进 `PYTHONPATH` |
| 环境变量 | `NATIVE_FORGE_HOME`（用户级） | 指向引擎目录 |
| 旧技能备份 | `%USERPROFILE%\.dsh\skills\<name>.bak-<时间戳>` | 重装时自动生成 |

**项目数据不在这里**：`prepare --project <目录>` 的项目由你自己指定，升级/重装引擎不会动它们。

---

## 5. 中文/空格安装路径

安装器支持类似 `C:\Users\张三\.dsh` 的路径。要点：

- 含非 ASCII 字符时，生成的 `nf.cmd` 按系统 ANSI 代码页写入（中文 Windows 为 936），并在首行加 `chcp 936` 把控制台代码页切回同一编码；否则 `cmd.exe` 会把路径读成 `?` 并报 `Python not found`；
- 看到 `安装路径含非 ASCII 字符，nf.cmd 将按系统 ANSI 代码页 936 写入，并自带 chcp 切换` 属于正常提示，**不要用编辑器把该文件另存为 UTF-8**；
- 仓库本身可以放在中文路径，但命令行参数里的路径要用引号整体包住。

---

## 6. Windows 手动安装（不运行一键脚本）

只有在安装器跑不通、或你需要把技能/引擎装到非默认位置时才需要这一节。**一键安装能跑就别手工装**——安装器还会做路径改写与自检。

> 手工安装**不会**改写技能文档里的历史绝对路径。若之后技能路由报"路径不存在"，按安装器的替换规则批量替换（`E:\PDF\_ZH\native-forge` → 你的引擎目录；`C:\Users\ltllt\.codex\skills\`、`C:\Users\ltllt\.dsh\skills\` → 你的技能目录），或干脆改用 `install.cmd`。

### 6.1 复制技能与引擎

```powershell
$PACK = 'C:\dsh-native-textbook-pack'      # 解压/克隆后的仓库
$DSH  = "$env:USERPROFILE\.dsh"
$SK   = "$DSH\skills"
$NF   = "$DSH\native-forge"

New-Item -ItemType Directory -Force -Path $SK, $NF, "$NF\pylibs" | Out-Null

# 只复制含 SKILL.md 的顶层技能目录（与 DSH 的发现规则一致）
Get-ChildItem "$PACK\skills" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } |
  ForEach-Object { Copy-Item $_.FullName $SK -Recurse -Force }

# 引擎
Copy-Item "$PACK\engine\native-forge\*" $NF -Recurse -Force
```

### 6.2 安装 PyMuPDF

```powershell
$PY = 'C:\Python312\python.exe'    # 3.10+，带 pip；也可以是 DSH 运行时 Python
& $PY -m pip install --no-index --find-links "$PACK\wheels" --target "$NF\pylibs" pymupdf==1.28.0
```

### 6.3 生成 `nf.cmd`

```powershell
$nf = @"
@echo off
setlocal
set "NF_HOME=%~dp0"
set "NF_PY=$PY"
set "PYTHONPATH=%NF_HOME%pylibs;%PYTHONPATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%NF_PY%" "%NF_HOME%engine\native_forge.py" %*
exit /b %ERRORLEVEL%
"@
# 路径全 ASCII 时用 ASCII 写；若安装路径含中文，请改用 install.cmd（它会按 ANSI 代码页写）
[System.IO.File]::WriteAllText("$NF\nf.cmd", $nf, [System.Text.Encoding]::ASCII)
```

### 6.4 设置环境变量与技能侧默认引擎

```powershell
[Environment]::SetEnvironmentVariable('NATIVE_FORGE_HOME', $NF, 'User')
$env:NATIVE_FORGE_HOME = $NF

# 让技能里的 nf.cmd 也指向本机引擎
# 注意：下面按 ASCII 写；若 $NF 或 $SK 含中文，请改用 install.cmd，否则中文路径会变成 "?"
$skillNf = "$SK\native-textbook\scripts\nf.cmd"
$txt = Get-Content $skillNf -Raw
$txt = [regex]::Replace($txt, 'set "NATIVE_FORGE_HOME=.*"', "set `"NATIVE_FORGE_HOME=$NF`"")
Set-Content -LiteralPath $skillNf -Value $txt -Encoding ASCII -NoNewline
```

### 6.5 验证

```powershell
& "$NF\nf.cmd" doctor
```

完全退出并重开 DSH 后，再按 [README.md](../README.md) 的「装完自检」验证技能与 `prepare`。

---

## 7. Linux / macOS 手工安装（无一键脚本）

> 本仓库的 `install.cmd` / `install.ps1` **只适用于 Windows**。Linux/macOS 没有一键脚本，以下是手工路径；引擎是 Python 程序、XeLaTeX 跨平台，但**本仓库未在 Linux/macOS 上实测**，遇到问题按 [FAQ.md](FAQ.md) 的通用条目排查。

### 7.1 复制技能与引擎

```bash
git clone https://github.com/liudayewangzhe/dsh-native-textbook-pack.git
cd dsh-native-textbook-pack
PACK="$PWD"

mkdir -p "$HOME/.dsh/skills" "$HOME/.dsh/native-forge"
cp -R skills/* "$HOME/.dsh/skills/"
cp -R engine/native-forge/* "$HOME/.dsh/native-forge/"
```

### 7.2 安装 PyMuPDF

**注意**：仓库里的 wheel 是 **Windows x64**（`win_amd64`），Linux/macOS 不能用，必须联网 `pip`：

```bash
python3 -m pip install --user pymupdf
python3 -c "import fitz; print(fitz.__doc__)"
```

### 7.3 生成启动器 `nf.sh`

```bash
cat > "$HOME/.dsh/native-forge/nf.sh" <<'EOF'
#!/usr/bin/env bash
NF_HOME="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$NF_HOME/pylibs:${PYTHONPATH:-}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
exec python3 "$NF_HOME/engine/native_forge.py" "$@"
EOF
chmod +x "$HOME/.dsh/native-forge/nf.sh"
```

设置环境变量（写进 `~/.bashrc` / `~/.zshrc`）：

```bash
export NATIVE_FORGE_HOME="$HOME/.dsh/native-forge"
```

同时把 `<技能目录>/native-textbook/scripts/nf.cmd` 里的 `NATIVE_FORGE_HOME` 默认值改成你的引擎目录，或确保 shell 里已导出该变量。

### 7.4 TeX Live 与字体

- macOS：安装 MacTeX（TeX Live 的 macOS 发行版），`which xelatex` 应能解析；
- Linux：用发行版包管理器安装 TeX Live，或按 [DEPENDENCIES.md](DEPENDENCIES.md) §4 的 ISO/在线安装器；
- 字体：TeX Live 自带 Fandol 通常够用；正式出版建议装 Noto CJK（见 [DEPENDENCIES.md](DEPENDENCIES.md) §4.4）。

### 7.5 验证

```bash
"$HOME/.dsh/native-forge/nf.sh" doctor
xelatex --version
kpsewhich FandolSong-Regular.otf
```

`doctor` 输出 `ok:true` 即环境可用。如果 DSH 侧仍然找不到技能，确认技能布局是 `~/.dsh/skills/native-textbook/SKILL.md`（顶层目录，不能嵌套），并重启 DSH。

---

## 8. 离线安装

可以离线完成的部分：

- 技能与引擎：直接复制，无需网络；
- PyMuPDF：`wheels\pymupdf-1.28.0-cp310-abi3-win_amd64.whl` 随仓库；
- 中文字体：Fandol 随 TeX Live ISO。

需要提前准备好的离线材料：

- TeX Live ISO（约 6.3 GiB，见 [DEPENDENCIES.md](DEPENDENCIES.md) §4）；
- DSH 安装包（从你的获取渠道拿）。

`install.ps1` 没有独立的 `-Offline` 开关：只要 wheel 安装成功就不会联网。若 wheel 因 Python 版本/架构不匹配失败，它会回退到联网 `pip`；纯离线机器上请先确认 Python 版本与 wheel 匹配（3.10+，Windows x64）。

---

## 9. 升级 / 重装

```powershell
cd <仓库目录>
git pull            # 或重新下载 ZIP
.\install.cmd
```

- 技能：同名旧目录会先备份成 `<name>.bak-<时间戳>` 再覆盖；加 `-Force` 则**直接覆盖、不备份**；
- 引擎：`%USERPROFILE%\.dsh\native-forge` 内容被覆盖（`Copy-Tree -Force`）。如果你手工改过引擎，先自行备份；
- `nf.cmd` 与技能侧默认引擎路径会重新生成；
- 环境变量已存在时重复设置无副作用；
- 装完仍需**完全退出并重开 DSH**。

---

## 10. 卸载 / 回滚

### 10.1 回滚到旧技能

```powershell
$S = "$env:USERPROFILE\.dsh\skills"
Remove-Item "$S\native-textbook" -Recurse -Force
Rename-Item "$S\native-textbook.bak-20261015-120000" "native-textbook"
```

### 10.2 完全卸载

```powershell
# 1) 删除本包安装的技能（只会删这 10 个；装之前请确认没有同名自建技能）
$S = "$env:USERPROFILE\.dsh\skills"
$names = @(
  'native-textbook','office-files','scientific-visuals','skill-authoring','skill-creator',
  'skill-network','deepseek-claude-subagent','humanizer','humanizer-zh','diagnose-windows-sandbox-acl'
)
$names | ForEach-Object { Remove-Item (Join-Path $S $_) -Recurse -Force -ErrorAction SilentlyContinue }

# 2) 删除引擎
Remove-Item "$env:USERPROFILE\.dsh\native-forge" -Recurse -Force -ErrorAction SilentlyContinue

# 3) 清除用户级环境变量
[Environment]::SetEnvironmentVariable('NATIVE_FORGE_HOME', $null, 'User')
```

然后完全退出并重开 DSH。项目目录、原稿、交付产物都不在上述删除范围内，需要你自己保留或清理。

---

## 11. 校验仓库完整性

仓库带 `MANIFEST.json`（文件清单 + SHA256），并附跨平台校验脚本：

```powershell
python verify_pack.py          # 在仓库根目录；0 = 全部一致
python verify_pack.py --strict # 清单之外的多余文件也算失败
python verify_pack.py -q       # 只输出结论
```

Windows 也可以用薄封装（自动找 Python，包括 DSH 自带运行时；PATH 上没有 `python` 时用它）：

```powershell
.\verify-pack.ps1
```

退出码：`0` = 全部一致；`1` = 有缺失/哈希不符/（strict 下）多余文件；`2` = 没找到可用 Python。

> 校验按 `CRLF → LF` 归一化后计算哈希，因此 Windows（CRLF 检出）与 Linux/macOS（LF 检出）结果一致；`.gitattributes` 已固定脚本/文本的换行策略。  
> 如果你本地修改过文件，校验失败是预期行为。

---

## 12. 安装完成后做什么

1. 打开 [README.md](../README.md) 的「装完自检」，跑技能列表、`nf.cmd doctor` 和一次真实 `prepare`；
2. 想直接看任务怎么派：读 [WORKFLOW.md](WORKFLOW.md) 与 `examples/worker-brief-template.md`；
3. 遇到报错：先查 [FAQ.md](FAQ.md)，再查 `playbook/04-踩坑与注意点.md`。
