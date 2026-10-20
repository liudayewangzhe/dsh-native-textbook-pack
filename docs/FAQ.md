# 常见问题

排错顺序建议：**先 `nf.cmd doctor`，再看本页，最后查 `playbook/04-踩坑与注意点.md`。**

> 约定：`$NF` = 引擎目录（`%USERPROFILE%\.dsh\native-forge`）；`$SK` = 技能目录（`%USERPROFILE%\.dsh\skills\native-textbook`）；`$PY` = 带 PyMuPDF 的 `python.exe`。

---

## 脚本执行策略：提示"在此系统上禁止运行脚本"

**现象**：运行 `install.ps1` 或其它 `.ps1` 时报"无法加载文件……因为在此系统上禁止运行脚本"。

**原因**：Windows 默认 PowerShell 执行策略（Execution Policy），与 DSH 文件沙箱无关。

**处理**：

```powershell
# 方式 1：用 install.cmd（它已经带 -ExecutionPolicy Bypass）
.\install.cmd

# 方式 2：显式绕过
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

# 方式 3：只在当前进程临时放行（关窗口即失效）
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
```

不要为了这个提示去改机器级的执行策略，也不要提权。

---

## 装完 DSH 里看不到技能

**现象**：安装成功，但 DSH 的技能列表里没有 `native-textbook`。

**原因**（按概率排序）：

1. **没有完全重启 DSH**——DSH 只在会话启动时扫描技能目录；
2. 技能目录不是 `<name>/SKILL.md` 顶层结构（嵌套目录不会被发现）；
3. 安装到了错误的 DSH 家目录（例如实际用的是 `DSH_HOME` 指定的目录，而不是 `%USERPROFILE%\.dsh`）；
4. `SKILL.md` 的 YAML frontmatter 缺 `name` 或 `description`。

**处理**：

```powershell
# 1) 完全退出 DSH 再重开，然后确认布局
Get-ChildItem "$env:USERPROFILE\.dsh\skills" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } |
  Select-Object -ExpandProperty Name

# 期望 10 个：
# native-textbook, office-files, scientific-visuals, skill-authoring, skill-creator,
# skill-network, deepseek-claude-subagent, humanizer, humanizer-zh, diagnose-windows-sandbox-acl
```

如果目录对但仍不出现，直接在会话里让 agent 读绝对路径：

```text
%USERPROFILE%\.dsh\skills\native-textbook\SKILL.md
```

---

## PyMuPDF 缺失（`PyMuPDF (fitz) is required`）

**现象**：`nf.cmd doctor` 里 `pymupdf.available:false`，或 `prepare` 直接报缺 fitz。

**原因**：解释器里没有 PyMuPDF，或 `pylibs` 没进 `PYTHONPATH`。

**处理**：

```powershell
# 让安装器重装（推荐）：重跑 install.cmd 即可离线装 wheel
.\install.cmd

# 或手工装到引擎的 pylibs
$PY = '<可用的 python.exe>'
& $PY -m pip install --no-index --find-links "$PWD\wheels" `
  --target "$env:USERPROFILE\.dsh\native-forge\pylibs" pymupdf==1.28.0

# 验证
& "$env:USERPROFILE\.dsh\native-forge\nf.cmd" doctor
```

手工调用技能脚本时，记得：

```powershell
$env:PYTHONPATH = "$env:USERPROFILE\.dsh\native-forge\pylibs;$env:PYTHONPATH"
```

**版本注意**：仓库锁定 1.28.0；PyPI 最新已到 2.x（要求 Python ≥3.11），不要在生产项目里随意升主版本。

---

## 找不到 xelatex

**现象**：`doctor` 里 `xelatex.found:false`；`build` 报 `xelatex not found on PATH`。

**原因**：没装 TeX Live，或 `xelatex.exe` 不在 `PATH` 上。引擎用 `shutil.which("xelatex")` 解析，只认 `PATH`；找不到时可以用环境变量 `NF_XELATEX_LEGACY` 显式指定一个 `xelatex.exe` 作为兜底。

**处理**：

1. 按 [DEPENDENCIES.md](DEPENDENCIES.md) §4 安装 TeX Live（推荐 `scheme-full`）；
2. 把 `...\texlive\<年>\bin\windows` 加进 `PATH`；
3. 新开终端验证：

```powershell
xelatex --version
& "$env:USERPROFILE\.dsh\native-forge\nf.cmd" doctor
```

4. 如果暂时不想改 `PATH`，可只对当前会话指定兜底路径（后续命令在同一会话里生效）：

```powershell
$env:NF_XELATEX_LEGACY = 'D:\texlive\2024\bin\windows\xelatex.exe'
& "$env:USERPROFILE\.dsh\native-forge\nf.cmd" doctor
```

`doctor` 的 `xelatex.legacy_path` 默认是 `null`；只有设置了 `NF_XELATEX_LEGACY` 时才会显示该路径。它只是兜底，不是"已安装"的证明——`xelatex.found:true` 才算通过。

---

## 缺字 / 缺字形（`Missing character`）

**现象**：编译日志出现 `Missing character: There is no Ⅰ (U+2160) ...`，成品里字符消失或变方框。

**原因**：当前字体没有该字形（罗马数字、特殊希腊字母、数学符号、生僻汉字都可能）。

**处理**：

1. 确认 Fandol 或中文字体已安装：

```powershell
kpsewhich FandolSong-Regular.otf
```

2. 换字体：在模板/项目样式里指定已装的中文字体（如 Noto Serif CJK SC / 思源宋体）；
3. 针对罗马数字，可在 preamble 加：

```tex
\xeCJKDeclareCharClass{CJK}{"2160 -> "217F}
```

4. 数学符号优先用数学字体（如 `\mu\mathrm{m}` 而不是把 μ 交给正文字体）；
5. 改完必须重新编译并**回抽实测**，不要只看源码里"写对了"。

更多细节见 `playbook/04-踩坑与注意点.md` §A2、§F。

---

## 内存门禁

**现象**：`doctor` 里 `memory.ok:false`，或命令报 `available physical RAM ... is below the required 1024 MiB; halting`。

**原因**：这是工作流的**规定动作**——空闲物理内存低于 1 GiB 时暂停本地重活，避免构建/前检中途失败或产物不一致。**不是安装坏了。**

**处理**：

1. 先腾内存（关掉不需要的应用），复测：

```powershell
$os = Get-CimInstance Win32_OperatingSystem
[math]::Round($os.FreePhysicalMemory / 1MB, 3)   # 单位 GiB
```

2. 只做**非破坏性回收**：不要把 harness/编辑器/VPN/SSH/安全软件/输入法强杀掉；
3. 仅当"总内存充足、空闲读数贴着阈值"时，才可在**你自己的重活命令上临时**放宽：

```powershell
$env:NF_RAM_FLOOR_MIB = "768"    # 允许范围 512–1024 MiB，超出会被夹取
& $NF\nf.cmd doctor
```

**红线**：不得为通过检查而改阈值；**不得把放宽后的阈值下发给 worker**（历史事故正是把 `NF_RAM_FLOOR_MIB=560` 写进 worker 任务单）。

---

## Windows 沙箱权限报错

**现象**：任何 shell 命令都返回类似：

```text
Error: sandbox-local windows-acl temp grant materialization failed and its cleanup also failed
```

读文件正常，只有 shell 挂。

**原因**：DSH 的 Windows 沙箱无法在工作区建立临时授权。**不是脚本或内容的问题**，也不是执行策略问题。

**处理**：

1. 安装/写文件建议在**普通 PowerShell 终端**里做，不要放在受限沙箱 shell 里；
2. 若在 DSH 会话中遇到，加载并执行技能 `diagnose-windows-sandbox-acl`——它用一条命令同时诊断并修复（检查路径及每个上级目录，补当前用户缺少的完全控制项，并清理外来的应用包权限项）；
3. 判据看脚本最后输出的 `RECAP` 与 `details.nextAction`：
   - `verify_original_confined_operation` → 修好了，去重跑原操作；
   - `stop` → 没修任何东西，如实报告并停手。

**不要做**：不要手工改 ACL、不要提权（UAC/`runas`）、不要反复执行被拒绝的命令。

---

## 编码 / BOM / 中文乱码

**现象 A**：`preflight_pdf.py` 读 `inputs.json` 报 JSON 解析错误。  
**现象 B**：控制台中文输出乱码，看不出真实报错。  
**现象 C**：`install.ps1` 解析失败，报一堆奇怪的语法错误。

**原因与处理**：

| 现象 | 原因 | 处理 |
|---|---|---|
| A | Windows PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写 BOM | 用 Python 写 JSON：`Path(...).write_text(json.dumps(...), encoding='utf-8')`；或用不带 BOM 的写入方式 |
| B | 控制台代码页与 UTF-8 不一致 | 运行前设 `$env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"`；必要时 `[Console]::OutputEncoding=[Text.Encoding]::UTF8` |
| C | `install.ps1` 必须是 UTF-8 **带 BOM**（含大量中文），否则 5.1 按 ANSI/GBK 解码 | 直接用 `install.cmd`（它会自动补 BOM），不要手工另存 |

`nf.cmd` 也是特殊文件：纯 ASCII 路径时按 ASCII 写；**安装路径含中文时按系统 ANSI 代码页（中文 Windows=936）写**。看到相关警告是正常的，不要用编辑器把它改成 UTF-8。

---

## 加密 PDF

**现象**：前检报 `encrypted PDF needs an authorized password`，或 `prepare` 读不了页面。

**原因**：原稿带打开密码/权限密码；本工作流**不内置解密**，也不支持带密码自动打开。

**处理**：先用你有权限的工具解密出一份副本（保留原件的只读与哈希记录），再对副本跑 preflight / prepare。不要把"能打开"当成"已授权"——版权与授权由使用者负责。

---

## 扫描件质量与"只读了半页"

**现象**：成品正文缺了一段、半页或某个例题，但 PDF 看起来是连续的，编译也不报错。

**原因**：扫描件没有文字层，内容靠 worker 按分带图逐对象转写；常见根因是只读了上半页（`b0`）就停、把页首当上一页续文跳过、或把相邻页内容收进本页。

**处理**：

1. 扫描件项目必须建 `source_inventory.json`（逐对象区域与类别），不要靠空文本抽取"证明"页面已还原；
2. 每批 **3 页**，任务书写死"读完 `b1` 到页脚"；
3. 每批跑机械门禁：

```powershell
& $PY "$SK\scripts\scan_repair\audit_coverage.py" --pages "<范围>"
& $PY "$SK\scripts\scan_repair\check_numbering.py"
& $PY "$SK\scripts\scan_repair\detect_partial_pages.py" --threshold 0.12
```

4. 这些脚本只证明"没有未覆盖的行/没有编号缺口"，**不证明转写正确**；必须配合原页看图复核。

完整流程见 `skills/native-textbook/references/scanned-source-repair.md`。

> 扫描件识别质量决定成品上限。不要在未验证识别与复核方法的整本书上直接扩量；先做含密集公式与图表的真实小节样张。

---

## 只装技能、不装引擎（`-SkipEngine`）

可以，行为如下（已实测）：

```powershell
# 只安装/更新技能：不复制引擎、不装 PyMuPDF、不生成 nf.cmd（已有引擎保持不动）
.\install.cmd -SkipEngine

# 反过来：只装引擎、不装技能
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SkipSkills
```

后果：

- `-SkipEngine`：10 个技能会装好；若这台机器从未装过引擎，则 **`nf.cmd` 不存在**，`prepare/build/qa/release` 全都跑不了；
- `-SkipSkills`：引擎与 `nf.cmd` 可用，但 DSH 里没有 `native-textbook` 技能，需要手工读 `SKILL.md` 或自己派单。

装错了直接重跑 `install.cmd` 补装即可（幂等，会备份同名旧技能）。

> 小提示：`-SkipEngine` 时安装器结尾的「下一步」提示里 `$NF` 会是空串，这是提示文案的已知小瑕疵，不影响安装结果。

---

## 行尾 / 换行（CRLF vs LF）

**现象**：`python verify_pack.py` 在 Windows 上通过、换到别的平台或换 `core.autocrlf` 后哈希对不上；或 PowerShell 脚本在 Git 检出后执行异常。

**原因**：不同平台换行不同；仓库已用 `.gitattributes` 固定策略，`verify_pack.py` 在校验前统一做 `CRLF → LF` 归一化。

**处理**：

- 不要手工改 `.gitattributes` 或批量转换换行；
- Windows 脚本（`*.ps1`/`*.cmd`/`*.bat`）必须保留 CRLF，文本/源码按仓库策略走 LF；
- 校验失败时先确认是不是自己改过文件，再排查换行。

---

## `nf.cmd` 报 Python not found

**现象**：运行 `nf.cmd` 直接报：

```text
[Native Forge] Python not found: "..."
```

**原因**：生成 `nf.cmd` 时选的解释器后来被卸载/移动；或安装路径含中文但文件被另存成了不匹配的编码。

**处理**：

```powershell
# 方式 1：用环境变量临时指定可用解释器
$env:NF_PY = 'C:\Python312\python.exe'
& "$env:USERPROFILE\.dsh\native-forge\nf.cmd" doctor

# 方式 2：删掉启动器重跑安装器（推荐，会重新探测）
Remove-Item "$env:USERPROFILE\.dsh\native-forge\nf.cmd"
.\install.cmd
```

---

## `build` 报 `blocks must contain native content`

**现象**：刚 `prepare` 完就 `build`，报：

```text
content.json invalid: blocks must contain native content; empty content cannot be built or published
```

**原因**：这是**设计**。`prepare` 只产出证据包和空的 `content.json` 骨架；正文要由 worker（或你自己）按合同写进去。

**处理**：先完成起草与合并（见 [WORKFLOW.md](WORKFLOW.md) §5–§6），再 build。引擎会拒绝把空内容送进构建/发布链，这不是故障。

---

## `release` 说复核指纹过期 / 不让发布

**现象**：

```text
release blocked (project stays draft):
- review is bound to a different build fingerprint; the project was rebuilt, so a fresh human review is required
```

**原因**：`review.json` 绑定的是**构建指纹**，不是"我做过复核"这句话。内容、资产、模板、原稿或 PDF 任何一项变化，都会让旧复核失效。

**处理**：

1. 重新 `build` → `qa`，生成新的 `review-template.json`；
2. **重新看图**（不能沿用旧结论），再更新 `review.json` 的 `build_fingerprint`、页清单与 `issues`；
3. 再 `release`。也可以先用只读方式核对门禁字段，避免反复触发打包。

其余被拒原因：存在 `unresolved`、有未覆盖来源页、图形类型错误、编译/原生检查失败、`pending_pages` 非空。

---

## 看到 `out\main.pdf`，但实际找不到

**原因**：极早期的引擎版本把产物写在 `$PROJ\out\main.pdf`。本仓库里的 `playbook/03`、`examples/commands.ps1`、
`skills/native-textbook/SKILL.md` 与 references 已全部按当前引擎修正为：

```text
$PROJ\build\main.pdf
```

排版检查、字号回抽、视觉审核图都应指向 `build\main.pdf`；发布后的成品在 `deliverable\main.pdf`。
如果你照抄了外部旧教程或旧会话里的命令，把 `out\` 换成 `build\` 即可。

---

## 中文 / 空格安装路径

安装器**支持**中文与空格路径，但要注意：

- 含非 ASCII 时 `nf.cmd` 按系统 ANSI 代码页写入（中文 Windows 为 936）并在首行加 `chcp 936`，这是为了 `cmd.exe` 能正确读取；
- 不要用编辑器把它另存为 UTF-8/BOM；
- 命令行参数中的路径整体加引号：

```powershell
& $NF\nf.cmd prepare --source "$env:USERPROFILE\Desktop\我的书.pdf" `
  --pages 1-2 --project "$env:USERPROFILE\Desktop\我的项目" --title '我的书'
```

---

## Linux / macOS 支持吗

**Windows 是唯一实测平台**：

- `install.cmd` / `install.ps1` 仅 Windows；
- Linux/macOS 需要手工复制技能与引擎、`pip install pymupdf`（仓库 wheel 是 Windows x64，不能用）、自行生成 `nf.sh`；
- 引擎本身是 Python + XeLaTeX，理论上跨平台，但**本仓库未在 Linux/macOS 上实测**。

手工程序见 [INSTALL.md](INSTALL.md) §7。

---

## 不用 DeepSeek API key 能跑吗

**能。** 主流程的必需依赖只有 DSH、Python、PyMuPDF、TeX Live 与中文字体。DeepSeek API key 只影响你是否使用 `deepseek-claude-subagent` 把大批量机械工作外包；不用它时，起草由 DSH 会话里的模型完成，只是并行方式与消耗不同。

---

## 还有问题

按这个顺序找：

1. `nf.cmd doctor` 的 JSON 里哪一项不对；
2. 本页对应条目；
3. [playbook/04-踩坑与注意点.md](../playbook/04-踩坑与注意点.md)（症状 → 根因 → 判据 → 避免）；
4. `sessions/` 里 12 份真实会话记录（含当时怎么修好的），从 `sessions/index.md` 开始；
5. 仓库 Issue（附上 `doctor` 输出、命令、完整报错与最小复现材料；**不要贴密钥或整本原稿**）。
