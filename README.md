# 原生中文教材转换工具包

> 把技术书、教材、扫描件与课件 PDF 重建为**原生中文 LaTeX PDF**：公式与表格可编辑、图形保留矢量或原生重绘、逐页渲染与视觉复核，最终交付 PDF 与可编译 TeX 源码。

这是一个面向 **DeepSeek Harness（DSH）** 的技能包 + 转换引擎 + 经验手册。陌生人 `git clone` 后按本文操作即可开始工作。

![原生中文课件复核对照：左为失败稿，右为通过稿](skills/native-textbook/assets/review-examples/compare-p03-matrix.png)

> 对照示例来自本仓库真实复核材料。左：矩阵上下标错位、条目断行；右：公式为可编辑原生数学、中文标点与行距统一。

---

## 这是什么

- **一条有门禁的工作流**，不是"PDF 翻译器"：原稿只读 → 证据包（packet）→ 语义 TeX → 构建 → 技术检查 → 排版/字号检查 → 视觉复核 → 发布打包。
- **原生中文版**：正文、公式、表格都是可编辑的 LaTeX；公式/表格**禁止截图回退**；图形按来源选择"保留矢量 / 原生重绘 / 如实保留位图"。
- **DSH 技能**：`native-textbook` 定义角色分工、worker 合同与放行判据，配套 9 个辅助技能（见下文「技能分工」）。
- **Native Forge 引擎**：`nf.cmd doctor / prepare / asset / redraw / build / qa / release`，负责证据抽取、编译、技术检查与发布拦截。
- **可追溯**：来源 SHA-256、构建指纹、review 记录、`deliverable.zip` 内逐文件哈希；原稿与证据包只读保留。

### 不是什么

- 不是 OCR 工具，也不承诺"扫描件自动识别无需人工校对"；
- 不是"一键整本书全自动"，仍需要监工看图、核对公式与术语；
- 不是通用 PDF 阅读/转换器（那类需求请用 `office-files` 等技能）。

### 适用人群

| 适合 | 不适合 |
|---|---|
| 要把外文技术书/教材/讲义译成中文并**重排出版**的教师、研究生、技术作者、编辑 | 只想要一份机翻文本或可搜索 PDF 的人 |
| 需要公式、表格、图形在成品里仍可编辑/矢量的人 | 扫描质量极差且不愿做人工校对的人 |
| 愿意按流程做样张、逐页复核的人 | 期望完全无人值守、任意书一次跑完的人 |

---

## 30 秒上手（Windows）

**前提**：Windows 10/11 或 macOS 13+（Apple 芯片），已安装 **DSH 桌面版**（官方下载页 <https://www.deepseek.com/download/>；Windows 直达 <https://download.deepseek.com/desktop/dsh-latest-windows-x64.exe>，macOS 直达 <https://download.deepseek.com/desktop/dsh-latest-macos-arm64.dmg>）。TeX Live 可以先不装，但**没有它最终编译不出 PDF**。

```powershell
git clone https://github.com/liudayewangzhe/dsh-native-textbook-pack.git
cd dsh-native-textbook-pack
.\install.cmd
```

1. 安装器把 **10 个技能**装到 `%USERPROFILE%\.dsh\skills`、把引擎装到 `%USERPROFILE%\.dsh\native-forge`，并离线装好 PyMuPDF、生成 `nf.cmd`、设置 `NATIVE_FORGE_HOME`、做自检。
2. **完全退出 DSH，再重新打开**（技能只在会话启动时扫描）。
3. 在 DSH 里说一句：

> 用 native-textbook 技能，把 `D:\书\原稿.pdf` 的第 3 章译排成原生中文教材。公式、表格要可编辑，图形按内容保留矢量或重绘，做完内容与全部输出页复核后交付 PDF 与 TeX 包。

如果技能没有自动加载，直接让它读：

```text
%USERPROFILE%\.dsh\skills\native-textbook\SKILL.md
```

**Linux / macOS 没有一键脚本**：按 [docs/INSTALL.md](docs/INSTALL.md) §7 手工安装（仓库里的 PyMuPDF wheel 是 Windows x64，其它平台需 `pip install pymupdf`）。

> 不用 Git 也可以：GitHub 页面 **Code → Download ZIP**，解压后运行 `install.cmd`。

---

## 装完自检

### 1. 技能是否可见

```powershell
Get-ChildItem "$env:USERPROFILE\.dsh\skills" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } |
  Select-Object -ExpandProperty Name
```

应看到 10 个：`native-textbook`、`office-files`、`scientific-visuals`、`skill-authoring`、`skill-creator`、`skill-network`、`deepseek-claude-subagent`、`humanizer`、`humanizer-zh`、`diagnose-windows-sandbox-acl`。

### 2. 引擎 `doctor`

```powershell
$NF = "$env:USERPROFILE\.dsh\native-forge"
& "$NF\nf.cmd" doctor
```

期望输出（本机实测形态，路径与内存数值会不同）：

```json
{
  "command": "doctor",
  "ok": true,
  "python":   { "version": "3.12.14", "executable": "...python.exe" },
  "pymupdf":  { "available": true, "version": "1.28.0" },
  "templates":{ "ok": true, "directory": "...\\native-forge\\templates" },
  "xelatex":  { "found": true, "command": ["D:\\texlive\\2024\\bin\\windows\\xelatex.EXE"] },
  "memory":   { "ok": true, "required_bytes": 1073741824, "available_bytes": 2206154752 }
}
```

- `pymupdf.available` / `templates.ok` 必须为 `true`；
- `xelatex.found` 为 `false` 表示还没装 TeX Live 或没进 `PATH`（此时技能可用，但 `build` 会失败）；
- `memory.ok:false` 是**内存门禁**，不是安装失败（见 [FAQ](docs/FAQ.md#内存门禁)）。

### 3. 真实 `prepare` 冒烟

拿任意一个两三页的 PDF（没有就用 Office 导一份），跑一次真实的证据抽取：

```powershell
& "$NF\nf.cmd" prepare --source 'D:\tmp\小样本.pdf' --pages 1-2 `
  --project 'D:\tmp\smoke' --title '冒烟测试'
```

期望返回：

```json
{
  "cached": false,
  "command": "prepare",
  "content": "created",
  "pages": [1, 2],
  "project": "D:\\tmp\\smoke",
  "source": "D:\\tmp\\小样本.pdf",
  "source_sha256": "<64位十六进制>"
}
```

并在 `D:\tmp\smoke\` 下生成：

```text
project.json   content.json   assets.json
packet\packet.json
packet\pages\p0001.json  p0001.png
packet\pages\p0002.json  p0002.png
```

产物形状可对照 [`examples/project-skeleton/`](examples/project-skeleton/README.md)：合成样张的 `prepare` 输出（含 `source.pdf` 与页面渲染图；仅示结构，**不可直接 build**）。

> **注意**：`prepare` 只抽证据包，`content.json` 还是空骨架。此时直接 `build` 会报 `blocks must contain native content`——这是设计，不是故障。完整的 5 分钟验收流程见 [`examples/smoke-test.md`](examples/smoke-test.md)。

---

## 依赖清单（摘要）

| 依赖 | 必需性 | 随仓库 | 获取 | 验证 |
|---|---|---|---|---|
| DSH 桌面版 | 必需 | 否 | [deepseek.com/download](https://www.deepseek.com/download/) | 能正常开会话 |
| Python 3.10+ | 必需 | 否（DSH 自带即可） | [python.org](https://www.python.org/downloads/windows/) / [阿里云镜像](https://mirrors.aliyun.com/python-release/windows/) | `python -V` |
| PyMuPDF 1.28.0 | 必需 | ✅ `wheels/` | 安装器离线装，或 `pip` | `nf.cmd doctor` |
| numpy / Pillow | 必需 | 否（DSH 运行时自带） | 随 DSH | `python -c "import numpy, PIL"` |
| TeX Live（XeLaTeX + ctex + 字体） | 必需 | 否 | [TUNA](https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/Images/) / [USTC](https://mirrors.ustc.edu.cn/CTAN/systems/texlive/Images/) / [阿里云](https://mirrors.aliyun.com/CTAN/systems/texlive/Images/) | `xelatex --version` |
| 中文字体 | 必需 | TeX Live 自带 Fandol | Fandol（随 TeX Live）/ [Noto CJK Releases](https://github.com/notofonts/noto-cjk/releases) | `kpsewhich FandolSong-Regular.otf` |
| DeepSeek API key | 可选 | 否 | [platform.deepseek.com](https://platform.deepseek.com/) | 调用 `deepseek-claude-subagent` 成功 |
| LibreOffice | 可选 | DSH 自带 | 用 DSH 自带，不要另装 | 需要时走 `office-*` 技能 |

完整下载地址、国内镜像与逐项验证命令见 **[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)**。

---

## 工作流一图流

```text
原稿 PDF（只读）
   │
   ├─ preflight   只读前检：哈希 / 逐页观测 / 风险候选
   ├─ plan        版式计划：几何 / 内容路线 / 风险样张
   ├─ prepare     证据包 packet（project.json 锁定来源哈希与物理页码）
   ├─ draft       worker 分块起草 → chunks/*.json（只写自己的块）
   ├─ merge       按阅读顺序合并 → content.json
   ├─ build       XeLaTeX → build/main.pdf + 构建指纹        [compiled]
   ├─ qa          技术检查 → qa/qa_report.json               [technical_pass]
   ├─ 排版/视觉   几何检查 + 字号回抽 + 接触表/高倍页
   ├─ 复核        全部输出页看图 + 独立审查 → review.json    [reviewed]
   └─ release     重跑 qa、校验 review、打包 → deliverable.zip [released]
```

**阶段验收门（任一不过就停）：**

| 阶段 | 必须通过 |
|---|---|
| prepare | 来源哈希与页码锁定；证据包结构完整 |
| draft / merge | 每个来源 ID 被引用或显式排除；无截图公式/表格；合并校验通过 |
| build | 退出码 0、`build/main.pdf` 存在、指纹生成 |
| qa | `status: pass`、`findings: []`、review 指纹与当前构建一致 |
| 排版 | `check_typography --fail-on error` 通过；`body_scale_ratio ≈ 1.0` |
| 视觉复核 | **全部**输出页看过；高风险页高倍；记录绑定当前指纹 |
| release | 无 unresolved / 未覆盖页 / 过期指纹 / pending_pages |

详细的每阶段命令、产物路径、失败原因见 **[docs/WORKFLOW.md](docs/WORKFLOW.md)**。

---

## 技能分工

| 技能 | 作用 |
|---|---|
| **native-textbook** | 核心：book / slide 两条分支、角色分工、worker 合同、门禁与放行判据 |
| office-files | 文档类技能路由器，`native-textbook` 登记为其子路由 |
| scientific-visuals | 出版级图表、matplotlib、可视化与图 QA |
| deepseek-claude-subagent | 把批量翻译/TeX 转写外包给受限 DeepSeek（可选，需 API key） |
| humanizer-zh | 中文去 AI 味、语言层精修 |
| humanizer | 英文去 AI 味 |
| skill-creator | 创建/修改/评测技能 |
| skill-authoring | 技能编写规范与路由 |
| skill-network | 技能之间的路由与组合图 |
| diagnose-windows-sandbox-acl | Windows 沙箱 ACL 报错的诊断与修复 |

清单与"为什么某些技能故意没装"见 [`skills/README-SKILLS.md`](skills/README-SKILLS.md)。

---

## 仓库目录结构

```text
dsh-native-textbook-pack\
├── README.md / README.en.md           ← 你在这里（英文版见 README.en.md）
├── install.cmd / install.ps1          Windows 一键安装与自检（幂等）
├── verify_pack.py / verify-pack.ps1   按 MANIFEST.json 校验完整性（跨平台）
├── MANIFEST.json                      文件清单 + SHA256
├── LICENSE / NOTICE.md / LICENSES/    MIT + 第三方许可（含 PyMuPDF AGPL 说明）
├── ci\github-actions-verify.yml       可选 CI 模板（复制到 .github\workflows\ 启用）
├── skills\                            10 个 DSH 技能（native-textbook 是核心）
├── engine\native-forge\               Native Forge 引擎（代码/模板/测试/文档）
├── wheels\                            pymupdf-1.28.0-cp310-abi3-win_amd64.whl
├── playbook\                          6 篇中文经验手册（01 总览 … 06 示例）
├── sessions\                          12 份真实会话记录 + index.md + 使用统计
├── examples\                          commands.ps1 / worker 任务书模板 / smoke-test / 项目骨架
├── docs\                              DEPENDENCIES / INSTALL / WORKFLOW / FAQ / 原包 README
└── build\                             本包的制作脚本（日常使用可忽略）
```

---

## 典型命令速查

```powershell
$NF   = "$env:USERPROFILE\.dsh\native-forge"   # 引擎目录
$SRC  = 'D:\书\原稿.pdf'
$PROJ = 'D:\work\mybook'

# 环境
& "$NF\nf.cmd" doctor

# 建项目（--pages 是 PDF 物理页码；支持 "1,13-65,69-89"）
& "$NF\nf.cmd" prepare --source $SRC --pages 24-32 --project $PROJ --title '书名'

# 登记图资产 / 原生重绘（可选）
& "$NF\nf.cmd" asset  --project $PROJ --page 29 --bbox 316.69 207.98 548.84 355.26 --name f0029-1.1.2
& "$NF\nf.cmd" redraw --project $PROJ --spec "$PROJ\figures\f12.json" --name f12-native

# 编译 → 技术检查 → 发布
& "$NF\nf.cmd" build   --project $PROJ        # 产物：$PROJ\build\main.pdf
& "$NF\nf.cmd" qa      --project $PROJ        # 产物：$PROJ\qa\qa_report.json
& "$NF\nf.cmd" release --project $PROJ        # 产物：$PROJ\deliverable.zip

# 排版几何 / 字号回抽 / 视觉审核图（注意 PDF 是 build\main.pdf）
$SK = "$env:USERPROFILE\.dsh\skills\native-textbook"
$PY = '<带 PyMuPDF 的 python.exe>'
& $PY "$SK\scripts\check_typography.py" --pdf "$PROJ\build\main.pdf" --mode book --fail-on error
& $PY "$SK\scripts\compare_typography.py" --source $SRC --target "$PROJ\build\main.pdf" --mode book
& $PY "$SK\scripts\render_review_sheets.py" --pdf "$PROJ\build\main.pdf" --out "$PROJ\qa\review" --hi-res-pages "1,3,5" --hi-res-zoom 3

# 分块合并（文件顺序 = 阅读顺序）
& $PY "$env:USERPROFILE\.dsh\native-forge\scripts\merge_chunks.py" --project $PROJ `
  --chunks "$PROJ\chunks\0000.json" "$PROJ\chunks\0001.json"
```

> 说明：`playbook/03` 与 `examples/commands.ps1` 已按当前引擎统一为 `$PROJ\build\main.pdf`；若你在其他历史材料里仍看到 `out\main.pdf`，那是旧版本路径，一律以本文与 [docs/WORKFLOW.md](docs/WORKFLOW.md) 为准。

可直接复制的一整串命令在 [`examples/commands.ps1`](examples/commands.ps1)；派单模板在 [`examples/worker-brief-template.md`](examples/worker-brief-template.md)。

---

## 常见问题（摘要）

| 问题 | 一句话处理 |
|---|---|
| 提示"禁止运行脚本" | 用 `.\install.cmd`，或显式 `-ExecutionPolicy Bypass` |
| 装完 DSH 里看不到技能 | **完全退出并重开 DSH**；确认是 `<name>\SKILL.md` 顶层结构 |
| `PyMuPDF (fitz) is required` | 重跑 `install.cmd`，或把 wheel 装进 `...\native-forge\pylibs` |
| 找不到 `xelatex` | 装 TeX Live 并把 `...\bin\windows` 加进 `PATH` |
| 编译报 `Missing character` | 字体缺字形：换 Fandol / Noto CJK 或按文档处理特殊字符 |
| `memory.ok:false` / RAM 不足中止 | 内存门禁：腾内存后再跑；不要下发降低后的阈值给 worker |
| Windows 沙箱 ACL 报错 | 用 `diagnose-windows-sandbox-acl` 技能诊断修复；不要手工改 ACL |
| `release` 说指纹过期 | PDF 变了旧复核失效：重新 build → qa → 重新看图 → 更新 review.json |

更多条目（含空 `content.json` 不能 build、加密 PDF、行尾、中文路径等）见 **[docs/FAQ.md](docs/FAQ.md)**。

---

## 局限与边界

- **Windows 优先**：一键脚本仅 Windows；Linux/macOS 为手工路径，**未在本仓库实测**。
- **必须自装 TeX Live**：仓库不分发 TeX Live 与字体（体积/许可），没有 `xelatex` 就无法编译。
- **内存门禁**：空闲物理内存低于 1 GiB 时暂停本地重活；这是保护动作，不是故障。`NF_RAM_FLOOR_MIB` 只能在 512–1024 MiB 之间放宽，且**不得下发给 worker**。
- **扫描件质量决定上限**：不做"自动 OCR 免校对"的承诺；半页漏读、串页是已知高频缺陷，必须建逐对象清单并跑机械门禁 + 看图复核。
- **版权与合规由使用者负责**：只处理你有权翻译/使用的原稿；成品的使用、分发与署名责任在你自己。
- **不承诺任意整书质量**：仓库内验证的是引擎能力与多组真实选段（见 [`engine/native-forge/README.md`](engine/native-forge/README.md)）；整本书的交付仍需按流程逐页复核。
- **会话记录含历史绝对路径**：`sessions/`、`playbook/`、`engine/` 文档里的 `C:\Users\ltllt`、`E:\PDF\_ZH` 是制作机历史记录，不是配置；安装器会改写技能文档里的路径，引擎文档中的历史路径不影响运行。
- **PyMuPDF 是 AGPL-3.0**：随仓库 wheel 为原样分发；不接受 AGPL 时请自行购买商业许可或不用 PyMuPDF（见 [NOTICE.md](NOTICE.md)）。

---

## 校验完整性

```powershell
# Windows：自动找 Python（优先 DSH 运行时），推荐
.\verify-pack.ps1

# 任意平台：需要 PATH 上有 Python 3.8+
python verify_pack.py
python verify_pack.py --strict   # 清单之外的多余文件也算失败
python verify_pack.py -q         # 只输出结论
```

退出码：`0` = 全部一致；`1` = 缺失/哈希不符/（strict 下）多余文件；`2` = 没找到可用 Python。

CI 是**可选**的：仓库里提供了 [`ci/github-actions-verify.yml`](ci/github-actions-verify.yml) 模板，把它复制到 `.github/workflows/verify.yml` 并让推送凭据具备 `workflow` scope，之后每次 push/PR 会自动跑 `python verify_pack.py --strict`。

---

## 许可与第三方

- **原创内容**（文档、脚本、技能正文等）：[MIT](LICENSE)。
- **第三方组件**：各自的许可证保留，优先于 MIT 适用于对应组件。清单、版权与许可证全文见 [NOTICE.md](NOTICE.md) 与 [`LICENSES/`](LICENSES/)。
- 需要特别注意：[PyMuPDF](https://github.com/pymupdf/PyMuPDF) 采用 **AGPL-3.0 或 Artifex 商业许可**双许可；`wheels/` 里的 wheel 是原样分发的 AGPL 组件。
- 本仓库**不包含**完整原书、扫描件样本或 API 凭据；`sessions/` 是作者的历史工作记录，只含零散片段。

---

## 经验手册与真实会话

| 内容 | 位置 |
|---|---|
| 6 篇中文手册：总览/环境/命令/踩坑/会话复盘/示例 | [`playbook/`](playbook/01-总览与取舍.md) |
| 12 份真实会话记录（含失败与续跑） | [`sessions/index.md`](sessions/index.md) |
| 技能使用统计 | [`sessions/SKILL-使用统计.md`](sessions/SKILL-使用统计.md) |
| 原 zip 包说明（历史） | [`docs/ORIGINAL-PACK-README.md`](docs/ORIGINAL-PACK-README.md) |
| 引擎设计与验收合同 | [`engine/native-forge/docs/design.md`](engine/native-forge/docs/design.md) |
| 长书并行/合并/恢复 | [`engine/native-forge/docs/large-book.md`](engine/native-forge/docs/large-book.md) |
| 本包怎么重新打包 | [`build/README.md`](build/README.md) |

---

## 文档地图

| 你想做的事 | 读 |
|---|---|
| 5 分钟装好并验证 | 本文「30 秒上手」+ [docs/INSTALL.md](docs/INSTALL.md) |
| 搞清楚每一阶段怎么跑、门禁是什么 | [docs/WORKFLOW.md](docs/WORKFLOW.md) |
| 找下载地址、镜像、装完怎么验证 | [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) |
| 报错怎么修 | [docs/FAQ.md](docs/FAQ.md) |
| 直接抄命令/派单模板 | [`examples/`](examples/README.md) |
| 理解取舍与历史缺陷 | [`playbook/`](playbook/01-总览与取舍.md) |
