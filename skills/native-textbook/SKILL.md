---
name: native-textbook
description: Translate technical books or slide PDFs into native Chinese LaTeX PDFs with editable math and tables, vector figures, and rendered checks; preserve slide style when requested.
---

# 原生中文教材与课件工作流

这是 `office-files/native-textbook` 的直接调用入口。用于技术教材和课件的中文原生 PDF，不替换一般 PDF 阅读或 Word 转换。书籍引擎在 `E:\PDF\_ZH\native-forge`，可用 `NATIVE_FORGE_HOME` 指定迁移后的路径；入口是 [scripts/nf.cmd](scripts/nf.cmd)。

**"编译成功""检查通过""模型说看过"三者不能互相替代。** 本技能的所有门禁都建立在"每个检查证明什么、不证明什么"之上；越界引用检查结论视为造假。

## 文档地图

先读 [初稿规划与尾处理执行手册](references/first-draft-and-polish.md) 定位当前角色与阶段。其余按需读：

| 文件 | 什么时候读 |
|---|---|
| [first-draft-and-polish.md](references/first-draft-and-polish.md) | **总是**。角色分工、风险样张门槛、尾处理症状表、放行五阶段 |
| [source-preflight.md](references/source-preflight.md) | 新来源、异构书目、扫描件 |
| [scanned-source-repair.md](references/scanned-source-repair.md) | **扫描件（无文字层）总是**。标准修复流水线、症状→脚本判定表、worker 派单模板、两道内容损失门禁；脚本在 `scripts/scan_repair/` |
| [layout-and-polish.md](references/layout-and-polish.md) | 边注、宽版原稿、超宽对象、对已有稿做尾处理 |
| [chinese-typography.md](references/chinese-typography.md) | **总是**。字号模数、行距、留白下限、中文标点禁则、缩进、分页控制、中文学术语言精修 |
| [cover-and-geometry.md](references/cover-and-geometry.md) | 做封面、定页边距/版心/页脚保留区、核对字号实测值 |
| [figure-craft.md](references/figure-craft.md) | 任何绘图或图资产处理。语义合同、遮挡五类、连接拓扑、颜色线宽统一 |
| [visual-audit.md](references/visual-audit.md) | **交付前必须**。两级分辨率的纯视觉审核、逐对象清单、审查 JSON、双角色 |
| [slide-pitfalls.md](references/slide-pitfalls.md) | **slide 开工前 + 审核时必读**。症状→根因→判定→检查的排雷清单；含"交付后回写"流程 |
| [workflow-gates.md](references/workflow-gates.md) | 判断某个检查能证明什么、独立复编判据、缺陷四层归因、内存门槛 |
| [slide-native-pdf.md](references/slide-native-pdf.md) | **slide** 分支。页级几何、输出链选择、单位铁律、图裁切定位 |
| [slide-worker-contract.md](references/slide-worker-contract.md) | **slide** 分支的 worker 合同与自提示 |
| [worker-contract.md](references/worker-contract.md) | **book** 分支的 content.json 与对象合同 |

脚本：

| 脚本 | 用途 |
|---|---|
| [scripts/check_typography.py](scripts/check_typography.py) | 排版几何检查：越纸、文字重叠、文字被填充盖住（按对比度）、按字号的行距节奏、版心留白、行末填充率。`--mode book\|slide` |
| [scripts/compare_typography.py](scripts/compare_typography.py) | **字号/行距回抽比对**：源 vs 交付 PDF 逐级比字号与行距，报整体缩放比例（≈0.75 即 72/96 误缩）。自动识别外文源→中文 |
| [scripts/check_slide_spacing.py](scripts/check_slide_spacing.py) | **读 TeX 源**检查文本节点行盒冲突：长句折行后间距不够、残留空节点、节点超宽。为"折行压字"缺陷专门写的 |
| [scripts/check_slide_pdf.py](scripts/check_slide_pdf.py) | slide 技术检查：页数/尺寸/栅格图/字体嵌入/越界/必需字符 |
| [scripts/render_review_sheets.py](scripts/render_review_sheets.py) | 生成视觉审核用的接触表与高倍页图 + 绑定哈希的 manifest |
| [scripts/nf.cmd](scripts/nf.cmd) | book 引擎入口（build/qa/release 等） |

## 先锁定交付形态

- 用户要教材式连续阅读、章节重组或把课件扩写为教材：走 **book** 流程，使用 ElegantBook 和书籍引擎。
- 用户要保留 PPT 风味、近似原横版版式、按页中文课件 PDF：走 **slide** 流程，先读 [原生课件 PDF](references/slide-native-pdf.md) 和 [课件 worker 合同](references/slide-worker-contract.md)。保持页级结构，直接以 XeLaTeX 输出原生文本/数学与矢量图。
- 用户要创建、编辑或交付可编辑 `.pptx`：路由 `presentations`。**来源是 PPT 不等于必须交 PPTX**；按用户选定的最终产品决定路线。

把选择、来源范围和验收写入任务单；不凭文件名将课件套进书籍模板。无法从请求和证据确定形态时，先完成来源分析，再澄清这个差异。

现有 `nf.cmd build/qa/release` 是 **book** 后端，不支持本技能的直接 XeLaTeX **slide** 后端。slide 使用独立的构建、PDF 技术检查、逐页审查和发布清单；不得伪造 Native Forge `released` 状态。

## 三条最容易出错的铁律

1. **单位**：PDF 坐标与字号是 72 pt/in（`mm = pt × 25.4/72`）。**PDF 抽取的字号不乘 72/96**；CSS px 与 raster dpi 只在预览层换算。历史事故：乘了 72/96 让整册正文从 10.0 pt 缩到 7.5 pt。详见 [cover-and-geometry.md](references/cover-and-geometry.md) §5。
2. **声明值 ≠ 实测值**：模板里写的字号/行距与实际渲染不一致（实测封面声明 16 pt 实为 14.94，行距声明 13.3 实为 15.6–15.9）。**必须从交付 PDF 回抽实测并与源比对**；偏差 >±3% 先查因。见 [cover-and-geometry.md](references/cover-and-geometry.md) §4。
3. **看图是独立步骤**：自动检查查不到"挤不挤、空不空、齐不齐"。交付前必须按 [visual-audit.md](references/visual-audit.md) 做两级分辨率审核；没看图只能报 `not_performed`。

## 排雷清单：同类缺陷不许犯第二次

**同类排版缺陷在实测中连续出现三轮**（坐标方向反了、标签飘、度量线未落轴、长句折行重叠…），根因是当时把问题当"待修 bug"逐个修，**没有沉淀成规则**。

因此 slide 流程有三处**强制动作**，缺一即视为流程未走完：

1. **开工前**：读 [课件排雷清单](references/slide-pitfalls.md)。尤其 §A（坐标与几何）——那里的坐标系方向必须**先用 3 行实验确定**，禁止靠直觉。
2. **审核时**：逐条对照该清单 §A–§C 自查，**不许以"我逐页看过了"代替**。实测反例：15 页全部目检过，仍漏掉 4 处缺陷。
3. **交付后**：把本轮新缺陷按 [排雷清单 §D 沉淀流程](references/slide-pitfalls.md) 回写——能自动化的写成 `scripts/` 检查器，不能的写成清单条目。**回写是交付的一部分，不是可选项。**

> 判据：一条规则若不能在下一次**开工前**阻止同类缺陷，说明它写得还不够具体。
> 同样的判据用于检查器：一个只会在好稿上通过、在坏稿上也通过的检查器等于没有——
> 每次新增或修改检查器，都要跑一次**负向回归**（把修复前的输入喂进去，确认它报错）。

## book 执行

先读 [初稿规划与尾处理执行手册](references/first-draft-and-polish.md)。该手册按规划者、worker、尾处理者和发布者拆任务，给出证据到版式决策的顺序、风险样张门槛、最小 worker 上下文与排版故障索引。新文档必须先形成项目版式任务单并通过真实样张，再扩量；已有稿先诊断和精确修补，不整书重译。可用引擎 `scripts/plan_document.py` 建立/检查任务单；`plan_ready` 不等于内容或美观验收。

新来源或异构书目先读 [来源前检](references/source-preflight.md)，以只读观测和代表页看图区分扫描、文字层、代码、化学、课件及布局候选；用户仅授权分析的材料不得顺带翻译。

1. 读用户指定范围和原稿。先运行 `nf.cmd doctor`；使用 PDF 物理页码，明确章节边界。先核对纸张、正文栏、边注栏、最宽对象和最长注释，不能默认把所有书塞进 A4 等宽正文。遇到边注、宽版原稿、超宽对象，或对现有草稿做尾处理时，先读 [版式与尾处理](references/layout-and-polish.md)。排版参数按 [中文排版规范](references/chinese-typography.md) 的模数阶梯确定，不要逐处试字号。新书先用包含公式、表格与图形的实际小节校准，然后继续用户授权的完整范围。不要把校准小节当作全书完成。
2. `nf.cmd prepare --source "原稿.pdf" --pages 24-32 --project "项目目录" --title "书名"`。project.json 的来源哈希和页码是事实边界；只读原稿。packet 页面 PNG 仅供识别和核验，不作为出版正文。
   若扫描页没有文字块，先根据完整页面创建来源哈希绑定的 `source_inventory.json`：`schema_version:1,source_sha256:原稿哈希,pages:{"1":{objects:[{id:"p0001-s0000",page:1,bbox:[x0,y0,x1,y1],kind:"paragraph|equation|table|figure|heading|header_footer",text:"逐对象原文或描述"}]}}`。每个对象需真实区域和正确类别，之后回指其 ID 生成原生 TeX；仅确实空白的页可用 `blank:true,checked:true,reason`。空扫描页证据不能自动等同于“已完整还原”。
   可先用引擎目录的 `scripts/scaffold_inventory.py --project "项目目录"` 创建准确的空数组框架，再让 worker 填对象。objects 必须是数组，每个对象的 kind 是一个具体类别，不能写成竖线连接的字符串。该脚本不会覆盖已有人工清单。
3. 读 [worker-contract.md](references/worker-contract.md)，按语义小节写 content.json。把批量文字翻译、TeX 转写和机械比对交给受限 DeepSeek；监工负责范围、图片与重要符号判断。worker 只访问该项目，不能读密钥或不相关文件。若模型/工具失败，保持草稿与 unresolved，继续修可做部分，不把错误变成“完成”。中文语言修订按 [中文排版规范](references/chinese-typography.md) §9 的三层分流，语言补丁不得改动公式、数字、编号与技术结论。
4. 图形先查原 PDF 内部对象。`nf.cmd asset --project "项目目录" --page 24 --bbox x0 y0 x1 y1 --name f12` 保留矢量；认真看裁出资产，确认图例、刻度、反应条件和全部标签。需重绘的简单图可用 TikZ/PGFPlots/chemfig 或 Python 矢量 PDF；不捏造数据。PDF 中包装的位图仍按位图记录；真实照片可以保留。公式、表格必须原生 TeX，不能截图回退。绘图前先按 [绘图工艺](references/figure-craft.md) 写语义合同，线接命名锚点，并跑该页的遮挡与裁切自查。
   `nf.cmd redraw --project "项目目录" --spec "图形规范.json" --name f12-native` 支持 xy_plot、flowchart、tikz、chemfig，生成可编辑绘图 TeX、真矢量 PDF 与来源/代码指纹。数值图用原始数据或明示精度的数字化数据；必要时先读引擎 `engine/redraw.py` 的规范，禁止重绘时重采样未知随机数据。
5. `nf.cmd build --project "项目目录"`，再 `nf.cmd qa --project "项目目录"`。修复真实错误后重编译；只重做失败内容，复用未变证据与资产。不要用“XeLaTeX 编译成功”证明翻译准确。随后跑排版几何检查：
   ```powershell
   python scripts/check_typography.py --pdf "项目\build\main.pdf" --mode book --report "项目\qa\typo.md"
   ```
6. 对照全部授权源页，检查译文、公式条件/上下标/积分界限、表格每个单元格、图号及脚注。看全部实际输出页，核验字号、溢出、浮动体和留白。按照 QA 生成的 review 模板填写当前指纹、完整源页/输出页清单、实际完成的检查、reviewer 和 issues。范围内外混在一个抽取 block 时，复核 source_notes 的原文片段。
7. **纯视觉审核**（不通过不得交付）：按 [visual-audit.md](references/visual-audit.md) 生成接触表与高倍页图，逐对象核对，产出绑定当前 PDF 哈希的审查记录。
   ```powershell
   python scripts/render_review_sheets.py --pdf "项目\build\main.pdf" --out "项目\qa\review" `
     --hi-res-pages "<本次高风险页>" --hi-res-zoom 3 --poppler-dpi 144
   ```
8. `nf.cmd release --project "项目目录"`。有 unresolved、未覆盖来源、错误图形类型、编译/原生检查失败、缺页复核、缺视觉审核或过期指纹时均不得发布。交付 PDF、可编译 TeX 包及来源/质量报告，说明真实验证范围；不能承诺未测试的全书或任意扫描稿质量。放行判据与报告必备字段见 [门禁与证明边界](references/workflow-gates.md)。

## slide 执行

> **开工前必做**：读 [课件排雷清单](references/slide-pitfalls.md)；坐标系方向**先用 3 行实验确定**（画 y=10/50/90，看哪条在页顶），禁止靠直觉。

1. 先读 [slide-native-pdf.md](references/slide-native-pdf.md)（页级几何、输出链、单位铁律、失败定位表）与 [slide-worker-contract.md](references/slide-worker-contract.md)（worker 合同与自提示）。
2. 锁定 `slides_preserve`：保留源页序、比例、标题带、图文分组与课件式留白。一源页 = 一输出页，用 `\clearpage` 显式分页。几何与字号按 [cover-and-geometry.md](references/cover-and-geometry.md) §2 的毫米合同，**不要套教材流水版式**。
3. 数学直接走 XeLaTeX 原生数学 + TikZ 矢量图。**不要自写 LaTeX parser、字形盒或数学 SVG 排版器**；不要走"数学 → SVG → 逐字形重建 PPT → 另一渲染器"的链。需要 PPTX 时另行测试 presentation 引擎对公式的支持。
4. 保留课件外观时，反馈工具需先校准：整页出现同倍放大/裁切，先做无文字无公式的四边标记最小样张，对比真实导出的 PDF。已知工作绕过是 `PPTX convert → 实际 PDF → render PDF`（同 CLI 的 PDFium 分支正常），记录 `backend=pdfium`；**不要为迁就未校准的预览器缩放内容**。
5. 画图与摆标注时按 [figure-craft.md](references/figure-craft.md)：标注必须与所指对象建立可见联系（引线对准特征点 / 紧邻 / 跨距两端落在特征点）；表示宽高的虚线两端要落到基准轴。
6. 构建 → **三项检查** → 逐页视觉审核 → 独立包复编：
   ```powershell
   python scripts/check_slide_pdf.py     --pdf main.pdf --config slide-check.json --out qa/slide-check.json
   python scripts/check_typography.py    --pdf main.pdf --mode slide --report qa/typo.md
   python scripts/check_slide_spacing.py --tex main.tex --report qa/spacing.md   # 折行/间距/空节点
   ```
7. **拿排雷清单 §A–§C 逐条对照**全部输出页（不是只凭印象看图）；高风险页做 L2 高倍（3× PyMuPDF + Poppler 双渲染器）。坐标方向、标签净空、轴穿字、度量线落轴、折行间距这五类**必须逐页显式确认**。
8. 发布走独立 slide 清单，**不是** `nf.cmd release`，不得写 `nf released`。
9. **交付后回写**：本轮新缺陷按 [排雷清单 §D](references/slide-pitfalls.md) 沉淀——能自动化的写成 `scripts/` 检查器（并跑负向回归），不能的写成清单条目。**不回写等于这次白做。**

## 调用与维护

用户说“原生中文教材翻译”“原生中文课件”“保留PPT风味的PDF”“不要截图公式/表格”时按上面的交付形态选择流程。书籍完整本地说明与实际样例见 `NATIVE_FORGE_HOME/docs`、`projects`。本流程不要求 Qwen API，也不安装大模型。

资源约束按 [门禁与证明边界](references/workflow-gates.md) §6 执行：空闲物理内存低于 1 GiB 时暂停本地重活，只做非破坏性回收，保护 harness/编辑器/VPN/SSH/安全软件等白名单进程；不得为过 preflight 降低阈值，不得把降低后的阈值下发 worker。

长书按小节分派独立 chunks，监工按顺序使用引擎 `scripts/merge_chunks.py` 合并；执行前读 `docs/large-book.md`。共享 content.json、assets.json 与模板不能由多个 worker 同时改写。

覆盖检查只证明证据被分配，不能自动证明译文不遗漏。原生对象检查只证明 PDF/TeX 表示，不替代内容校对。保持 compiled、technical_pass、reviewed、released 的区别。完整证明边界见 [门禁与证明边界](references/workflow-gates.md) §1。

修改本技能时：新增规则要写成**可执行条款**（量、阈值、命令、判据），不要写"更仔细、更美观"这类无法验证的要求；把规则放在上表的对应文件里，并在本页文档地图中登记。
