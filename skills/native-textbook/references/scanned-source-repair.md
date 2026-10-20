# 扫描版书源的修复流水线（book 分支）

**什么时候读**：源 PDF 是**扫描件**（无文字层）时，**总是**。扫描件的每一个"内容丢失"都不是排版问题，而是数据问题；这一页就是"报错 → 该跑哪个脚本"的判定表。

一句话结论：**扫描件的失败几乎从不出现在 LaTeX 里，而出现在 `inbox/*.json` 分片的数据形状里。** 引擎报的错名（`content.json invalid`、`source_inventory page N`）只是症状，根因在分片。

## 1. 标准序列

每一步都是幂等的，可以整段重复执行。**顺序不可换**：数据形状类修复必须在 `merge` 之前，因为 `merge` 会把分片物化成 `source_inventory.json` 与 `content.json`。

```powershell
$py = "<python>"            # 需要 PyMuPDF(fitz) 与 numpy
$S  = "<skill>/scripts/scan_repair"

# --- A. 数据形状修复（幂等，可反复跑）---
& $py $S/fix_bad_json.py           # 分片 JSON 非法转义
& $py $S/fix_object_kind.py        # 证据对象的 kind 越界
& $py $S/fix_figure_tex.py         # 自写 \includegraphics
& $py $S/fix_literal_blocks.py     # code/console 块的多余字段
& $py $S/fix_empty_text.py         # text 为空的证据对象
& $py $S/fix_excluded_fields.py    # excluded 条目缺 id/page/kind/text
& $py $S/fix_glyphs.py             # 字体没有字形的字符
& $py $S/fix_cdots.py              # 文本模式里的 \cdots
& $py $S/clamp_bbox.py             # bbox 越界/退化
& $py $S/fix_array_cols.py         # 矩阵/表格声明列数不足
& $py $S/auto_continues.py         # 跨页标记只标单侧

# --- B. 引擎流程（prepare 必须在 merge 之前，它才生成 packet）---
$pages = & $py $S/gen_pages.py     # 已转写页的紧凑范围串
& $NF prepare --source <src.pdf> --pages $pages --project <proj>
& $py <proj>/tools/merge_workers.py --pages $pages
& $py $S/make_assets.py --pages $pages     # 裁图并改写 figure 块
& $py $S/merge_workers.py --pages $pages   # 第二次：把 asset 纳进来
& $NF build --project <proj>

# --- C. 门禁（每批必跑）---
& $py $S/audit_coverage.py --pages $pages   # 墨迹行覆盖
& $py $S/check_numbering.py                 # 公式/图/表编号连续性
& $NF qa --project <proj>
```

`prepare → merge → make_assets → merge → build` 里的**两次 merge 是必需的**：`make_assets` 读的是上一次 merge 产出的 `work/figure_requests.json`，新页的插图当轮还没进那个文件。

## 2. 症状 → 根因 → 处置

| 引擎报的错 | 真实根因 | 处置 |
|---|---|---|
| `content.json invalid: literal block has unsupported fields: tex` | worker 给 code/console 块写了 `tex`（或 `continues_*`） | `fix_literal_blocks.py` |
| `content.json invalid: figure must not carry tex` / `forbidden macro '\includegraphics'` | worker 自己写了图形宏；图形宏只能由引擎生成 | `fix_figure_tex.py` |
| `source_inventory page N: every object needs id/page/kind/text` | 对象的 `kind` 越界（几乎总是 worker 写了 `code`） | `fix_object_kind.py`，然后 `merge` |
| 同上，但字段看着全对 | `excluded_objects` 条目缺 `page/kind/text` | `fix_excluded_fields.py` |
| `source page N has zero text evidence` | `pages` 范围与分片不一致（把没转写的页纳进来了） | 用 `gen_pages.py` 统一 `prepare`/`merge` 的范围 |
| `FileNotFoundError: packet/pages/pNNNN.json` | 新完成的页还没生成 packet | **先 `prepare` 再 `merge`**（每次合并前都跑） |
| `xelatex failed`: `! Missing $ inserted` | 替换 ⋯ 时把 `\cdots` 放进了文本模式 | `fix_cdots.py`（跨行状态机，只包文本模式处） |
| `log.missing_character`（罗马数字 Ⅰ Ⅱ Ⅲ） | 正文字体无 U+2160–217F 字形 | preamble 加 `\xeCJKDeclareCharClass{CJK}{"2160 -> "217F}` |
| `log.missing_character`（𝜇 U+1D707） | `\mathrm{\mu}` 把 μ 交给正文字体 | 改写成 `\mu\mathrm{m}` |
| `log.overfull` 单点很大 | 单个长公式或矩阵超版心 | `locate_overfull.py` 定位来源块 → 换 `split` / 收紧 `\arraycolsep` / 缩小 TikZ `scale` |
| `expectations.required_strings_missing` 带 `$...$` | 生成 required_strings 时没剥 LaTeX | 生成前 `re.sub(r"\$[^$]*\$", "", s)` |
| 分片 `json.load` 失败 | notes 里的 LaTeX 只写了单反斜杠 | `fix_bad_json.py`（逐字符扫描，勿用简单正则，会破坏合法 `\\`） |

## 3. 三条铁律

1. **`inbox/*.json` 分片是唯一事实源。** 直接改 `source_inventory.json` 会被下一次 `merge` 覆盖——修复必须落在分片上。多个 worker 因此白干过一轮。
2. **证据 bbox 一律用整页归一化坐标**（像素 y ÷ 整页高度）。worker 若用"带内相对坐标"，同一条行会偏 0.02–0.05 页高，覆盖审计会整片报未覆盖。判断方法：对象 bbox 的跨度与墨迹行跨度之比明显不是 1。
3. **一个池子里不要同时写同一页。** 曾出现两个 worker 领到同一页，后者覆盖前者，内容静默丢失。

## 4. worker 派单模板（扫描件专用）

单个 worker 处理 **3 页**为宜（5 页时长与上下文都逼近上限，失败率显著上升）。派单里必须写死这几条：

- 只看本页分带图；一屏看不清就用 Pillow 裁该带局部放大再看，**不得据一屏不清就判定内容不存在**（曾因此整页上半部漏读）。
- 不要把相邻页内容收进本页（曾因此两页内容整体串位）。
- bbox 用整页归一化坐标。
- 证据对象的 kind 只能是 `paragraph/equation/table/figure/heading/header_footer`。
- 页眉页脚只作 object + `excluded_objects`，不写 block。
- 程序清单用 block 的 `kind="code"` + `text`，不写 `tex`。
- figure 块不要自己写 `tex`。
- 矩阵列数声明与内容一致。
- notes 里写 LaTeX 片段时反斜杠写成双反斜杠。
- **每写完一页立刻落盘并 `json.load` 验证**（一批 5 页的末尾失败会让整批白干）。

## 5. 几条只有踩过才知道的契约细节

- **`kind="table"` 的 block 必须自带编号与表题**：引擎对 table 块**原样输出**它的 tex，不会替你写 `\renewcommand{\thetable}{...}` 与 `\caption{...}`。少了这两样，表格在成品里既没有表号也没有表题（表体还在，所以很难一眼看出）。表格本体建议用 `longtable`（跨页自动重复表头），另把契约要求的 `tabular` 形态存进 `tables[].tex`。
- **`kind="figure"` 的 block 不要写 tex**：图形宏由引擎生成；worker 自写 `\includegraphics` 会被判 `forbidden macro`。矢量重绘才用 `figure_native` 自带 TikZ/pgfplots。
- **红底白字页面要换掩码**：常规「RGB 三通道 < 150」判墨对白字是漏检，会把标题整片判成"无墨迹"；红底白字用「R>100 且 G>100」定位。
- **`\tag` 与环境的嵌套是 LaTeX 最脆弱的一环**：`\begin{equation}\begin{equation*}`、`\end{equation*}\tag{...}\end{equation}`、`\begin{equation*}\begin{equation*}` 三种畸形都会让编译崩掉。修结构后**必须立即重编译验证**，不能只看脚本报告——我自己写的第一版清理脚本方向选反，把编译从 36 页推到 26 页。
- **自动补 `\tag` 的脚本必须能识别"这不是编号公式"**：判据是块内已有 `\text{(n)}` / `（Ⅰ）` 这类手写序号，或内容属于习题列表。宁可漏补（由编号门禁报出来），也不要乱补——乱补会污染编号序列并让 `content.json` 判非法。
- **`numbered: false` 与 `\tag` 互斥**：带 `\tag` 就是编号公式（`numbered: true`）；不编号的块要用 starred 环境。

## 6. 换一个项目时改什么

脚本自带两份常量，在文件顶部，迁移时改这两处即可（其余逻辑与项目无关）：

```python
INBOX   = Path(r"D:\native-forge-work\inbox")          # worker 分片目录
PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\<名>")  # 项目根
```

`make_assets.py` 与 `merge_workers.py` 另外需要 `assets.json` / `project.json` 的路径，同样在顶部；`fix_glyphs.py` 与 `fix_cdots.py` 的替换表按目标书的正文字体调整（正文字体缺哪些字形，看 `build/main.log` 的 `missing_character`）。

脚本不依赖本项目特有的目录名，但**依赖分片格式**：`inbox/pNNNN.json` 含 `objects`（id/page/kind/text/bbox）与 `blocks`（id/kind/source_ids/…）。换书时先按 `worker-contract.md` 让 worker 产出这个格式。

## 6. 两道真正能抓出内容损失的机械门禁

排版类检查抓不到"少了半页"，只有这两道能：

- **墨迹行覆盖审计**（`audit_coverage.py`）：把源页渲染成像素，逐行取墨迹，检查每一条文字行是否落在某个对象 bbox 内。抓到过：整页上半部漏读、相邻页串位、bbox 大面积错位。
- **编号连续性**（`check_numbering.py`）：按章统计公式/图/表编号，报缺口。抓到过：页底三个公式连同整个例题框整段漏读。

两者都只证明"没有未覆盖的行/没有编号缺口"，**不证明文字转写正确**——逐字正确性仍要靠视觉审核与独立复核。
