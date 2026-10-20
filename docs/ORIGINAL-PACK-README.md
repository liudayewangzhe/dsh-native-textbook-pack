# 原生中文教材转换 · 移植包

> **归档说明**：这是原始 zip 包（`dsh-native-textbook-pack`）的 README，保留作历史参考。
> 本 GitHub 仓库已做如下改动：`examples/project-skeleton/` 换成合成样张；历史路径 `out\main.pdf`
> 统一修正为 `build\main.pdf`；`XELATEX_LEGACY` 改为可选环境变量 `NF_XELATEX_LEGACY`；补充了
> 官方 DSH 下载地址与第三方许可声明。安装与使用请以根目录 [README.md](../README.md) 和
> `docs/` 下的四篇文档为准。

把本机 DSH 上跑通的「原生中文教材转换」工作流整体搬到另一台机器：
**技能 + 引擎 + 经验手册 + 真实会话记录 + 示例用法**，解压后一条命令装好，重开 DSH 即可上手同类任务。

> 目标机器前提：已经装好 **DeepSeek Harness 桌面版**，但没有任何自定义 skill。
> 本包不需要 Codex，也不需要联网（PyMuPDF 的 wheel 已随包）。

---

## 三步上手

```text
1) 把 zip 解压到任意目录（路径尽量短、别放 OneDrive 同步目录里跑重活）
2) 双击 install.cmd
3) 完全退出并重开 DSH
```

安装器会自动：

- 找一台机器上可用的 Python 3.10+（**优先用 DSH 自带的运行时 Python**，没有才退到系统 Python）；
- 把 `skills\*` 装到 `%USERPROFILE%\.dsh\skills`（DSH 的用户技能根，rank 400），同名旧技能先备份成 `*.bak-<时间戳>`；
- 把 Native Forge 引擎装到 `%USERPROFILE%\.dsh\native-forge`；
- 用随包 wheel 离线把 **PyMuPDF** 装进 `…\native-forge\pylibs`（引擎读 PDF 必需）；
- 生成**可移植的 `nf.cmd`**（原引擎里写死了本机的 Codex Python 路径，这一步把它换成目标机器上真实可用的解释器）；
- 设置用户级环境变量 `NATIVE_FORGE_HOME`；
- 自检：技能 frontmatter、`import fitz / numpy / PIL`、`nf.cmd doctor`、XeLaTeX 是否存在。

想先看会做什么、不动文件：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -WhatIfOnly
```

常用开关：`-PythonExe <path>`、`-EngineHome <dir>`、`-SkillsRoot <dir>`、`-SkipEngine`、`-SkipSkills`、`-NoEnvVar`。

---

## 重开 DSH 之后怎么开始

DSH 只在会话启动时扫描技能目录，所以**必须重开会话**。然后对它说一句就能落地：

> 用 native-textbook 技能，把 `D:\书\原稿.pdf` 的第 3 章译排成原生中文教材。
> 公式、表格要可编辑，图形按内容保留矢量或重绘，做完内容和全部输出页复核后交付 PDF 与 TeX 包。

如果它没自动加载技能，直接让它读：

```text
%USERPROFILE%\.dsh\skills\native-textbook\SKILL.md
```

**30 秒自检**（确认引擎真的能跑）：

```powershell
$NF = "$env:USERPROFILE\.dsh\native-forge\nf.cmd"
& $NF doctor
```

### 完整冒烟验证（建议装完就做一次）

拿任意一个小 PDF（两三页就够）跑一遍真实的 `prepare`，确认"读 PDF → 抽页面对象 → 生成证据包"这条链路是通的：

```powershell
$NF = "$env:USERPROFILE\.dsh\native-forge\nf.cmd"
& $NF prepare --source 'D:\tmp\小样本.pdf' --pages 1-2 --project 'D:\tmp\smoke' --title '冒烟测试'
```

成功时返回 JSON（`"command": "prepare"`, `"content": "created"`），并在 `D:\tmp\smoke\packet\pages\` 下生成每页的 `pNNNN.json` 与 `pNNNN.png`。

> 如果报 `available physical RAM ... is below the required 1024 MiB; halting`：
> 这是工作流的**内存门禁**（低内存时暂停本地重活，见 `playbook\04-踩坑与注意点.md`），不是安装坏了。
> 腾出内存后再跑；仅当"总内存充足但空闲读数贴着阈值"时，可以用引擎自带的运算符开关
> `$env:NF_RAM_FLOOR_MIB = 768`（引擎只允许在 512 MiB–1 GiB 之间放宽，且不会杀任何进程）。
>
> ⚠️ **只在你自己的构建命令上临时设**。技能正文明确禁止把降低后的阈值**下发给 worker**——
> 历史事故正是 `NF_RAM_FLOOR_MIB=560` 被写进 worker 任务单，导致低内存下照跑重活。
> 安装器不设这个变量，也不建议写进系统环境变量。

---

## 还需要你自己准备的东西

| 依赖 | 是否随包 | 说明 |
|---|---|---|
| DeepSeek Harness | 目标机器已装 | 技能宿主 |
| Python 3.10+ | 优先用 DSH 自带运行时 | 本包的 wheel 是 `cp310-abi3`，3.10 及以上通用 |
| PyMuPDF | ✅ 随包（`wheels\`） | 引擎读 PDF、抽矢量、渲染校对图 |
| numpy / Pillow | ✅ DSH 运行时自带 | 扫描件修复与校对图脚本 |
| **TeX Live（XeLaTeX）** | ❌ 需自装 | 最终 PDF 编译。装完确认 `xelatex` 在 PATH 上（引擎用 `shutil.which('xelatex')` 解析）。中文字体也要装（思源宋体/黑体一类） |
| LibreOffice | ❌ DSH 自带 CLI | 仅 `.pptx` 预览/转换时需要，用 DSH 随包的那套，不要另装 |
| DeepSeek API key | ❌ | 仅当要用 `deepseek-claude-subagent` 把大批量文字工作外包时 |

---

## 目录结构

```text
dsh-native-textbook-pack\
├── install.cmd / install.ps1     一键安装与自检（幂等，可重复运行）
├── README.md                     本文件
├── skills\                       装进 %USERPROFILE%\.dsh\skills 的技能
│   ├── native-textbook\          ★ 核心技能（SKILL.md + references\ + scripts\）
│   ├── office-files\ scientific-visuals\ skill-authoring\ skill-network\ skill-creator\
│   ├── deepseek-claude-subagent\ humanizer-zh\ humanizer\
│   ├── diagnose-windows-sandbox-acl\
│   └── README-SKILLS.md          清单、为什么某些技能故意没装、卸载回滚
├── engine\native-forge\          精简后的 Native Forge 引擎（不含 5GB 的项目产物）
│   ├── nf.cmd                    ※ 安装器会用目标机器的 Python 重新生成
│   ├── engine\ scripts\ templates\ tests\ third_party\ docs\
├── wheels\pymupdf-1.28.0-cp310-abi3-win_amd64.whl
├── playbook\                     ★ 经验手册（先读这个）
│   ├── 01-总览与取舍.md
│   ├── 02-环境与依赖.md
│   ├── 03-命令速查.md
│   ├── 04-踩坑与注意点.md
│   ├── 05-会话复盘.md
│   └── 06-示例用法.md
├── sessions\                     ★ 12 个真实会话的可读记录 + index.md + SKILL-使用统计.md
├── examples\                     ★ 照抄即用的派单模板、命令脚本、真实项目骨架
│   ├── commands.ps1              从 doctor 到 release 的一串命令
│   ├── worker-brief-template.md  4 种 worker 任务书模板（book / 扫描件 / 独立审查 / 单人版）
│   ├── smoke-test.md             装完机器 5 分钟验收流程
│   └── project-skeleton\         一次真实 prepare 之后的项目结构样例
├── build\                        本包的制作脚本（刷新会话记录 / 重建清单与分卷）
├── verify-pack.ps1               按 MANIFEST.json 校验文件完整性
└── MANIFEST.json                 文件清单与 SHA256（校验完整性；含分卷方案）
```

## 分卷说明

单个 zip 控制在 500 MB 以内。本包（含 12 份会话记录、约 6 MB 文本）压缩后远小于该上限，**只需一个压缩包**。
若日后追加样本 PDF/成书成品导致超限，按 `…-part1.zip`、`…-part2.zip` 分卷，
解压时**全部解压到同一个目录**后再运行 `install.cmd`；`MANIFEST.json` 里带各分卷的文件表，安装器不区分分卷。

---

## 出问题时

| 现象 | 处理 |
|---|---|
| `无法加载文件 …install.ps1，因为在此系统上禁止运行脚本` | 用 `install.cmd`（它带 `-ExecutionPolicy Bypass`），或按 README 里的命令行显式加 `-ExecutionPolicy Bypass` |
| 装完 DSH 里看不到技能 | 技能目录只在会话启动时扫描：完全退出 DSH 再重开 |
| 引擎报 `PyMuPDF (fitz) is required` | `& $python -m pip install --target "$env:USERPROFILE\.dsh\native-forge\pylibs" pymupdf` |
| 引擎报找不到 Python | 设 `NF_PY` 环境变量指向可用的 `python.exe`，或删掉 `nf.cmd` 重跑 `install.ps1` |
| 编译阶段报 `xelatex` 找不到 | 装 TeX Live 并把 `…\texlive\<年>\bin\windows` 加进 PATH |
| 文件写入被 Windows 沙箱拒绝 | 见 `playbook\04-踩坑与注意点.md` 的"Windows 沙箱权限"一节；技能 `diagnose-windows-sandbox-acl` 里有诊断修复脚本 |

---

## 来源说明

- 技能取自本机 `C:\Users\ltllt\.codex\skills\`（原为 Codex 技能，通过 junction 接进 DSH）。
- 引擎取自 `E:\PDF\_ZH\native-forge`，**只复制代码与模板**（`engine/ scripts/ templates/ tests/ third_party/ docs/` 与根级说明文件），
  不含 5.2 GB 的 `projects/`、`audit/`、`reports/` 成果目录。
- 会话记录由 `session.v4.jsonl.zstd` 自动转换成 Markdown：保留用户消息、助手正文、工具调用参数与实际返回，全部截断，推理过程未导出。
- 引擎内的 `docs/`、`README.md` 等仍含原作者机器上的绝对路径（`C:\Users\ltllt`、`E:\PDF\_ZH`），那是**历史记录**不是配置；
  真正生效的路径由 `install.ps1` 生成与设置。
