# Worker 任务书模板（照抄即用）

这些模板不是编出来的，是从真实会话里抽出来的、当时**真的跑通**的任务书
（`..\sessions\05-经典力学-主控.md`、`..\sessions\10-计算物理-扫描件主控.md`、
`..\sessions\11-计算物理-独立视觉审查.md`、`..\sessions\08-worker加监工模式.md`）。
把 `$PROJ` 换成你的项目目录、`$NF` 换成引擎入口即可。

派单原则（踩出来的）：
- **一个 worker 只给一个可写的窄范围**（一个 chunk 文件 / 3 页 inbox JSON），其余全部只读。
- **合同先行**：worker 第一步必须完整读 `WORKER_CONTRACT.md` / `WORKER_BRIEF.md` + 术语表 + 版式规则。
- **把踩过的坑直接写进任务书**（下面 B 模板就是范例），比让 worker 自己撞便宜得多。
- **要求它自己看图**，不允许只抄抽取文本；不允许把"抽取不到"当作"原书没有"。
- **要求返回 ≤120 字的自述**，不要它写"已通过审校"这种没有证据的结论。

---

## A. book 分支：分块译排 worker

```text
你是《<书名>》中文原生重建项目的翻译 worker。任务：把 chunk `<0004>`（PDF 页 <16–21>，第 <1> 章
「<Bird's-Eye View of Classical Mechanics>」）译排成中文，写成一个 JSON 文件。

## 只读
- 证据简报：`$PROJ\briefs\0004.json`（含每页的 body/margin/mixed 文本块与 packet id、图框、页面 PNG 路径）
- 术语表（强制）：`$PROJ\GLOSSARY.md`
- 版式与硬规则：`$PROJ\LAYOUT_TASK.md`（重点读 §2、§3、§5）

## 只写
`$PROJ\chunks\0004.json`

## 输出结构
{
 "title": "<章标题中文>",
 "blocks": [ ... ],
 "exclusions": [{"source_id":"p0016-b0000","category":"header_footer","reason":"running head"}],
 "source_notes": [{"note":"..."}],
 "unresolved": [],
 "expectations": {"equation_tags": [], "table_count": 0, "figure_count": 0, "required_strings": []}
}
block 形如 {"id":"...","kind":"...","source_ids":[...],"tex":"..."}。kind 只能是
chapter / section / subsection / paragraph / equation / table / figure / figure_native / note。

## 必须遵守（引擎会直接拒绝）
1. **覆盖**：该 chunk 涉及的每个 packet block id 必须出现在某个 block 的 source_ids 里，
   或出现在 exclusions 里（二选一，不能既引用又排除）。header/footer 用 header_footer 排除。
2. **段落 vs 公式**：paragraph.tex 不得含显示公式环境（equation/align/\[/$$）或表格环境；
   显示公式必须独立成 equation 块。行内 $...$ 可以。
3. **公式编号**：原书编号形如 (1.5)。用 {"kind":"equation","numbered":false,"tex":"... \\tag*{(1.5)}"}。
   正文引用照抄原号。
4. **标题块** tex 只写标题文字，不要写 \section{}，也不要手写编号（LaTeX 自动编号）。
5. **边注**：{"kind":"note","number":"1","placement":"margin","tex":"...","source_ids":[...]}；
   正文该处写 \nfnotemark{该 note 的 id}{1}。若边注文本被抽进混合块、无法与正文段分离，
   给该 note 加 "anchor":"position"，此时正文不必写标记。
6. 转义 %→\%、#→\#、&→\&、_→\_（数学模式内不变）。
7. 禁止 \usepackage \includegraphics \input \include \documentclass \usetikzlibrary \begin{document}。
8. 数学用原生 TeX，不要用 \text 拼希腊字母。

## 翻译风格
读起来像中文老师写的专业书，不是逐词机翻。忠实：数字、上下标、积分限、条件、符号、单位、
公式号与原页一致。术语首次出现「中文（English）」，此后只用中文。原书笔误照原意保留并在
source_notes 说明。

## 数学注意
本 chunk 若出现公式，**必须自己看页面图片**（`packet\pages\p00NN.png`）确认符号与上下标，
**不要**直接抄简报里可能错乱的提取文本。

## 完成前自检
运行 lint（存在的话）：必须 "status": "pass"（warnings 可接受）。
写 JSON 到 E: 等 exFAT 盘时用：
  [System.IO.File]::WriteAllText('路径', $json, (New-Object System.Text.UTF8Encoding($false)))
（exFAT 不支持 link / 原子替换式写入。）

## 返回
≤120 字：block 数（各 kind 几个）、实际看过的页、图形 keep/redraw 数、未解决项、lint 结果。
不要声称"通过审校"。
```

---

## B. 扫描件分支：分带转写 worker（把坑直接写进任务书）

```text
转写「<项目名>」项目的源扫描页 **p0155、p0156、p0157**（3 页）。

先读合同 `$PROJ\WORKER_CONTRACT.md`，按它执行。分带图在 `work\slices\`
（`p0155_b0.png` 等 6 张），像素范围看同目录 `slice_index.json`。

关键约束（都是踩过的坑）：
- 只看本页分带图；一屏看不清就用 Pillow 裁该带局部放大再看，**别因为看不清就判定内容不存在**。
- bbox 用**整页归一化坐标**（y ÷ 整页高），不是带内坐标。
- 证据 object 的 kind 只能用 paragraph/equation/table/figure/heading/header_footer（**不要用 code**），
  text 不能空。
- 页眉页脚只作 object + excluded_objects，不写 block。
- 程序清单用 block 的 `kind="code"` + `text`，不要写 tex。
- figure 块不要自己写 tex。
- 矩阵列数声明要和内容一致。
- notes 里写 LaTeX 片段时反斜杠要写成双反斜杠。

输出：`$INBOX\p0155.json`、`p0156.json`、`p0157.json`，**每写完一页立刻落盘并用 json.load 验证**。
汇报中文 4 行内。
```

> 这条流水线后来出过的最大事故是"**只读了上半页**"：worker 的 objects 的 y 上界明显小于页面实际墨迹。
> 监工侧的几何检测 + 原书裁图复核是必需的，见 `..\playbook\04-踩坑与注意点.md`。

---

## C. 独立视觉审查者（不参与制作）

```text
你是「<项目名>」原生中文 PDF 重建项目的**独立视觉审查者**（不参与制作，独立出结论）。
审查对象是**样张**（<第一章 + 第二章开头，PDF 物理页 23–45>）。

## 交付物
- 待审 PDF：`$PROJ\build\main.pdf`（<25> 页）
- 已生成的审核图（PyMuPDF 3× 高倍 + Poppler 144dpi 第二渲染器）：`$PROJ\...`
- 你要写的：`$PROJ\qa\review-<你的标识>.json`（绑定当前 PDF 的 SHA256）

## 要求
- 逐页、逐对象核对，不许用"我整体看过了"代替清单式确认。
- 五类必须逐页显式确认：坐标方向、标签净空、轴穿字、度量线落轴、长句折行间距。
- 每个问题给出：页码、对象、现象、证据（截图坐标或 bbox）、判定（缺陷 / 可接受 / 需人工确认）。
- 不通过就明确写"不得交付"，不要给面子分。

## 返回
≤200 字结论 + 问题清单条数；不要复述流程。
```

---

## D. 小项目单人版：worker + 监工

```text
你是 native-textbook 工作流的「翻译/重建 worker + 监工」，任务范围严格限定在一个已初始化好的
Native Forge 项目里。

## 项目与事实边界
- 引擎：`$NF`（用 `& $NF <子命令> --project "$PROJ"` 调用）
- 项目目录（**你唯一可写的目录**）：`$PROJ`
- 原稿只读，project.json 里的来源哈希与页码是事实边界，不得超出。

## 你要做的
1. 读 `$NF` 对应技能的 SKILL.md 与 `references\first-draft-and-polish.md`，确认当前阶段。
2. 按 `references\worker-contract.md` 写 content.json；图形按 `references\figure-craft.md`
   写语义合同后再重绘；简单图用 TikZ/PGFPlots/chemfig。
3. build → qa → 排版几何检查 → **纯视觉审核**（`references\visual-audit.md`，未做只能报 not_performed）→ release。
4. 任何 unresolved / 未覆盖来源 / 过期指纹都要留在报告里，不许用"编译成功"顶替。

## 返回
≤200 字：阶段、已完成的对象数、qa 结果、视觉审核范围、未解决项。
```

---

## 关于 subagent 的返回通道

DSH 的 `subagent` / `spawn_teammate` 派单时，父会话**不会**自动看到子会话的记录，必须显式要求它回消息。
真实用过的写法（自动附加在子会话末尾）：

```text
Your parent agent id is "<parent-session-id>". Before you finish, send your result to that agent with
send_message({ agent_id: "<parent-session-id>", message: "<self-contained result>" }).
The parent shares your workspace but does not automatically receive your transcript, tool output, or reasoning.
```

并发写盘纪律：**共享的 `content.json` / `assets.json` / 模板不能由多个 worker 同时改写**，
每个 worker 只写自己的 chunk 文件，最后统一合并（引擎 `scripts\merge_chunks.py`，长书流程见 `docs\large-book.md`）。
