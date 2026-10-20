# 位图公式来源（文字层正常，但公式与图全是截图）

本页处理一类**很容易被误判为"普通可抽取 PDF"**的来源：文字层完好、目录完好、页码正常，但**所有行间公式、行内数学符号和插图都是嵌入位图**。典型是 Calibre 从 EPUB 生成的 PDF、部分出版社的纯图片排版书。

误判的代价很大：你会以为"有文字层就能抽"，于是安排翻译 worker 拿抽取文本干活，结果交付稿里公式全缺，或者被迫截图回退——而这正是本工作流明令禁止的。

## 1. 先用三个可复算的数字确认来源类型

在引擎目录用带 PyMuPDF 的 Python 跑（只读）：

```python
import fitz
from collections import Counter
d = fitz.open(path)                       # 1) 页数
cnt = Counter()                            # 2) 字体名直方图
for p in d:
    for f in p.get_fonts(full=True):
        cnt[f[3]] += 1
bands = Counter(); uniq = set()            # 3) 图像面积分布
for p in d:
    for it in p.get_image_info(xrefs=True):
        uniq.add(it.get("xref")); n = it["width"] * it["height"]
        bands["<2k" if n < 2000 else "2k-10k" if n < 10000 else
              "10k-50k" if n < 50000 else "50k-200k" if n < 200000 else ">=200k"] += 1
```

判定（三个同时成立即属本类）：

| 证据 | 本类来源的表现 | 对照：正常矢量书 |
|---|---|---|
| 字体名 | 只有正文衬线/无衬线（如 `ACaslonPro-*`），**没有任何数学字体**（无 `CMMI`/`CMSY`/`NewCM*`/`STIX*`） | 有数学字体，且数学字符占比可观 |
| 图像面积分布 | **大量小图**：`<2k` 与 `2k-10k` 桶几百到几千个 | 图像少，且集中在 `>=200k`（整幅插图/照片） |
| 抽取文本 | 句子通顺，但公式位置**是空的**（`...does not work if  . (Can you...)`） | 公式位置有字符或乱码 |

实测一例（Griffiths《量子力学概论》三版，644 页 A4）：唯一图像 7046 个，其中 `<2k` 4975、`2k-10k` 1756、`>=200k` 仅 19；字体只有 5 个 ACaslonPro 变体；文字层 708,296 字符完全可用。

> 判据：**"有文字层"不等于"内容可抽取"**。本类的文字层只覆盖散文，数学与图必须逐个对象看图重建。

## 2. 确定性对象抽取：三类对象、三条判定

不要靠"看图猜哪个是公式"。位置关系足以稳定分类，写成脚本一次跑完全书（参考实现：`tools/extract_math_objects.py`）。

三类对象与判定：

1. **行内符号**：位图 bbox 与某条文本行的纵向重叠 ≥ 自身高度的 60% → 它嵌在这句话里。
2. **行间公式**：不与任何正文文本行重叠，且（常）右侧有独立的 `(N.M)` 文本行。同一纵向带内相距 ≤6 pt 的多块图合并为一个对象（多行推导常被切成数块图）。
3. **插图**：对象下方 4–34 pt 内有一条以 `Figure N.M` 开头的文本行（图题）。

同时产出两样东西，缺一不可：

- **每个对象一张 600 dpi 精确裁切 PNG**（按 bbox + 3 pt 余量，`clip` 到页内）。裁切只含对象本身，**不含任何上下文文字**——这是"截图准确性"的机械保证，而不是靠人眼把关。
- **每页一份"回填阅读文本"**：把该页文本按阅读顺序输出，行内符号与行间公式换成 `[[p0051-i002]]` / `[[EQ:p0051-d002#2.33]]` / `[[FIG:p0051-f000#2.2]]` 占位符，图题原文保留。这是 worker 唯一的文本输入，比原始抽取干净得多。

### 已知陷阱（都实际踩过）

| 症状 | 根因 | 修法 |
|---|---|---|
| 行内符号错位、跑到句首 | PyMuPDF 把**被图打断的同一行拆成多个 line**，按 line 原样处理会丢顺序 | 按**基线 y** 合并同一行的碎片（容差 1.6 pt）+ 按每个 span 的 x 排序 |
| 有编号的行间公式被归成"行内" | 判定时把 `(1.10)` 这种**公式编号行**当成了宿主文本行 | 行内判定**排除**匹配 `^\(\d+\.\d+\)$` 的文本行 |
| 正文句 "Figure 1.7 shows the graph of…" 被当成图题 | 图题正则只匹配 `Figure N.M` | 要求号后紧跟**冒号或左括号**：`^\s*Figure\s*\d+\.\d+\s*(?::|\(|$)`。注意有出版社用 `Figure 2.23 (a) …` 这种无冒号式样，所以不能只收冒号 |
| 图在页底、图题在下一页 | 图题距离超过窗口 | 机械规则抓不到，**必须**由 worker 在读到"如图 N.M 所示"却找不到 `[[FIG:...]]` 时补报 |
| 图片对象页被当成"整页公式" | 封面/整页图占满页面 | 面积占比 >80% 的整页图单独标记，不参与公式统计 |
| 章节首页装饰符号（如 ◈）进正文 | 装饰字形被算作文本 | 列入 `exclusions`，category 用 `extraction_artifact` |

## 3. 用"联络表"把看图成本压下来

本书 1987 个行间公式 + 6383 个行内符号。逐个 `read_image` 是 O(8000) 次读图，transcription 一定成为瓶颈。

做法：把小对象拼成**带 id 标签的联络表**（参考实现：`tools/make_contact_sheets.py`）。

- 行间公式：每张纵向堆 4 个，每个左侧印 `p0044-d003` 这样的 id；
- 行内符号：每张排 24 格网格，每格下方印 id；
- 输出 `sheets/manifest.json` 记录"哪张 sheet 含哪些 id"，worker 先查 manifest 再定向读图。

实测第 1 章（27 页 / 70 个公式 / 206 个符号）压缩成 **50 张 sheet**，一个 chunk 的读图次数从 276 降到 50 量级。

**联络表不能取代单图**：合同里必须写明"格子看不清时改读 `evidence/objects/<id>.png` 单图"，否则小符号会被猜错。

## 4. 引擎硬约束（踩过才写得出来）

这些是 `nf.cmd` 的真实行为，不是建议：

| 约束 | 表现 | 应对 |
|---|---|---|
| `build` 要求**来源全覆盖** | 任一 packet 块既未引用也未排除即报错 | **试排必须把项目范围缩到该章**（`prepare --pages 15-41`），过样张后再扩到全书。否则你永远编译不出第一章 |
| `source_ids` 只认 packet 与 `source_inventory` 的 id | 自造 id 报 "is not a packet block id" | 行内符号不建独立对象；行间公式/图用 `source_inventory` 登记，id 沿用抽取器 id |
| 编号公式必须**恰好一个** `\tag{}` | 多一个或没有都报错 | 多行推导用 `align` + 在该行 `\tag{}` |
| `numbered:false` **不得**带 `\tag` | 报错 | 无编号式用 `equation*`/`align*` |
| `expectations.equation_tags` 必须是 `\tag` 的**精确多重集** | 多一个少一个都拦 | 从抽取到的原书编号自动生成，不要手抄 |
| `exclusions.category` 只有三个枚举：`header_footer` / `out_of_scope` / `extraction_artifact` | 自造 `page_number` 直接报错 | 页码→`header_footer`；空白页→`out_of_scope` |
| `figure_native` 必须非空 tex，且**不得**带 `caption`/`width`/`asset` | 图题要写进 tex 里的 `\caption{}` | 照片例外改走 `figure` + `source_raster` 资产 |
| 模板 `nativeforge.sty` **不加载 pgfplots** | 图里写 `\pgfplotsset` 直接 `Undefined control sequence` | 图一律纯 TikZ：`\draw plot[domain=...,samples=...] (\x,{f(\x)})`。block 内禁 `\usepackage`，加包不是选项 |
| 模板是 `11pt` 文档类，实测正文 **10.9 pt**、行距比 1.616 | 与"10.5 pt"的规格差 +3.8% | 这是成熟中文成品基线（10.9/17.6/1.61），照实记录为实测值，不要为了凑 10.5 去缩字号 |

## 5. 一道必须加的廉价门禁：数学定界符 lint

散文层正常、公式靠人重建的组合，最典型的致命错误是**行内数学漏了 `$`**：

- `^{*}\textbf{习题 1.9}`（星号写在数学模式外）
- `P_{ab}(t)`、`\sigma_x`、`(PV=Nk_BT)` 裸写在中文里

后果不是"少个符号"，而是 TeX 报 `! Missing $ inserted` 并**吞掉文档后半部分**——本轮实测：27 页章节只排出 13 页，且后半习题区整段消失，而 `main.pdf` 照常生成、看上去"编译过了"。

所以：把"数学模式外出现 `^` 或 `_`"做成每个 chunk 的必过关卡（参考实现：`tools/audit_chunk.py`）。实现要点：扫描时正确跳过 `\$`、`\[`、`\]`、`\(`、`\)`，只检查数学模式外的字符。

> 证明边界：这条 lint 只证明"没有裸 `^`/`_`"，不证明公式写得对。它拦的是**整段内容被静默吞掉**这一类事故。

## 6. 真实照片的例外必须由引擎背书

插图里混有真实照片（实验成像、显微照片、人物照）时，重画等于伪造数据。但也不能随手把位图当矢量塞进去。

正确流程：

1. 监工逐图判定并写进 `figures/PHOTO_EXCEPTIONS.md`（图号、figid、源页、资产 id、原始格式、理由）。
2. 用 `nf.cmd asset --project ... --page N --bbox ... --name ... --kind source_raster --figure-kind photograph` 登记。
3. **让引擎拒绝你一次**：若误用默认 `--kind vector_pdf`，引擎会报 "a raster cannot be declared vector_pdf"。这个拒绝是特性——它证明登记的类别是真实的，不是声明出来的。
4. 装配时把该 `figure_native` 占位块换成 `kind: figure` + `asset`，图题用转写后的中文。

其余一切线图、示意图、函数图、直方图**一律原生 TikZ 重绘**，并在文件头写清"哪些量是从原图量的、哪些是示意"，否则视为未完成。

## 7. 工作区文件系统会咬人（Windows 实测）

工作区放在 **exFAT** 卷上时，写入工具的原子写（写临时文件 + hardlink/rename）会稳定失败：

```
EISDIR: illegal operation on a directory, link '...\x.txt.tmpdir\x.txt.tmp' -> '...\x.txt'
```

表现为"文件明明不该是目录却报 EISDIR"。这不是内容问题，与权限无关。

应对：**先把工作区放到 NTFS 卷**；必须在 exFAT 上作业时，改用"写到系统临时目录 → `Copy-Item` 落到目标路径"。派 worker 时把这条写进任务单，否则每个 worker 都会各自撞一次。