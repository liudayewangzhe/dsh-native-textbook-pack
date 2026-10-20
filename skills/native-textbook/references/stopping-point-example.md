# 计算物理 原生重排 · 收工状态（2026-10-15）

> 与 `RUNBOOK.md`、`RUNBOOK-ADDENDUM.md`、`WORKER_CONTRACT.md`、`DISPATCH-LEDGER.md`、
> skill 的 `native-textbook/scripts/scan_repair/`（31 个脚本）一起构成完整续接包。

## 一、当前成品

| 项 | 数值 |
|---|---|
| 文件 | `E:\PDF\_ZH\native-forge\projects\cpp-zh\build\main.pdf`（桌面副本 `计算物理_原生重排_进展.pdf`） |
| 页数 | **306** |
| 可选中文字 | **283,148** 字符 |
| LaTeX 错误 | **0** |
| Overfull \hbox | **3** |
| content 块 / 公式 | **3271 / 1197** |
| 表格 / 图 | **6 / 73**（其中 8 幅关键线条/坐标图已矢量重绘） |
| 转写覆盖 | `1-10, 13-221, 224-253, 257-280` ≈ **278 / 638 物理页（44%）** |

## 二、门禁状态（全绿或已知可接受）

| 门禁 | 脚本 | 结果 |
|---|---|---|
| 半页漏读（只读 band0） | `detect_partial_pages.py` | **0 页** ✓ |
| 公式编号连续性 | `check_numbering.py` | **§8.3 已闭合（missing=∅）**；§8.4 缺 (8.4.1)–(8.4.19) → **属未转写页 PDF 222/223** |
| 墨迹覆盖审计 | `audit_coverage.py` | 少数页未覆盖行为框线/装饰，或图框偏窄（p0221 图 8.3.3） |
| 排版几何 | `check_typography.py` | error×1（图 1.1.1 斜排标注，已知误报）、warn×1（7.6pt 小字 4 处） |
| 构建 | `run_build_loop.py` | 通过（闭环重试至 merge 无 unresolved） |

## 三、未完成部分（下一会话入口）

### 1. 未转写页（360 页）
- **11, 12**（前言残余）
- **222, 223**（第八章末：(8.3.63)–(8.3.66) 与 (8.4.1)–(8.4.19)，含算法 8.4/8.5/8.6）
- **254, 255, 256**（第九章末：本章要点总结 + 图 9.5.4）
- **281–638**（第十一章中后段至全书末）

### 2. 已知待修（非阻塞）
- `p0218-b007` 段落截断：原书 p0218 的 0.517–0.719 约 11 行正文（「第一，算法要简单……都满足这样的要求」）未转写
- p0217/0218/0219 部分旧对象 bbox 有 band1 折算压缩（如 p0219 的 (8.3.30) 记 0.222、实测 0.103）
- p0221 图 8.3.3 的 figure bbox 偏小（图下半未覆盖）
- 图 1.1.1 斜排标注的 `text_overlap` 误报（字形已目视确认分离）

## 四、续接方式（一句话）

> 继续「计算物理」原生重排：先读本文件与 `D:\nf-stage\DISPATCH-LEDGER.md`，
> 按 3 页/worker 并发派单转写 PDF **281–638**（顺带 11/12/222/223/254-256），
> 每批后跑 `python D:\nf-stage\run_build_loop.py --rounds 3` 出数，
> 门禁用 `detect_partial_pages.py` + `check_numbering.py` + `audit_coverage.py`。

## 五、铁律（59 轮总结，务必遵守）

1. **`inbox\pNNNN.json` 分片是唯一真源**：改 `source_inventory.json` 会被 merge 覆盖。
2. **每页必须读完 band0 + band1 到页脚**：本项目 8 次证实「只读 band0」丢失下半页整段（p0193/p0215/p0220/p0230/p0007/p0251/p0263/p0217）。汇报必须**分别**给出「正文对象 y 上界」与「含页脚 y 上界」。
3. **一页只派一个 worker**：已发生 6 次重复派单导致的覆盖冲突。
4. **`\tag` 三铁律**：每 equation 块恰好一个 `\tag`；带 `\tag` 必 `numbered:true`；**原书无编号的显示式不加 `\tag`**。环境**绝不嵌套**（`\begin{equation}\begin{equation*}` 与 `\end{equation*}\tag{...}\end{equation}` 都会让编译崩）。
5. **页脚只作 object + `excluded_objects`**，绝不建 block（`header_footer` 不是合法 block kind）。
6. **`kind=table` 的 block 必须自带 `\renewcommand{\thetable}` + `\caption`**，否则印不出表号表题。
7. **红底白字换掩码**（R>100 且 G>100）；红底页不能用灰度阈值判墨（会整页误报"漏读"）。
8. **b1 偏移必须用两带重叠区逐像素比对确认**（各页在 726–739 之间，非固定值；用二值掩码 IoU 判定最硬）。
9. **修结构的脚本极易引入新畸形**：每次改后立即重编译验证，不能只看脚本报告。
