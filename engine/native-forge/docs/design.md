# Native Forge 设计与验收合同

目标：复现参考 PRML 工程的原生中文正文、数学、表格和清晰图形，而不是复刻源 PDF 的每页几何。原稿只读；旧 BookForge 保留为历史实现。新入口不依赖 Qwen、MinerU 或本地大模型。

## 根源与模块

1. **来源与证据包**：对原稿计算 SHA-256，按明确 PDF 页码提取带稳定 ID 的文本块、字体/图片/矢量统计、目录及页面预览。提取文字只是证据，不把它当作完整公式解析结果。扫描页及数学异常由 agent 看页面补录。
2. **语义重建与翻译**：按章节/小节生成 `content.json`，有序 block 分别表示正文、公式、表格、图形等。中文和 TeX 一次生成；跨页段落在语义层合并。不生成页面截图式 IR，也不强制保留原页换行。每个 block 回指源证据 ID；所有排除须有理由，未识别内容进 unresolved。
3. **图形资源**：原稿已有矢量图则裁出 PDF、真正移除裁框外内容，保留字体和路径；核验 PDF 内部是否含位图。只有确需本地化、简化或来源不适合保留时才绘制 TikZ/PGFPlots/chemfig/Python 矢量图。照片等原始位图显式记录来源和用途。公式和表格不能走图片回退。
4. **排版**：沿用本地未修改的 ElegantBook 类；一个薄样式层管字体、数学、标题、浮动体、三线表。章节连续排版，局部编译，两轮交叉引用，不用硬编码原页坐标。类文件、样式和内容哈希进入构建记录。
5. **核验**：机器检查源覆盖、未解决项、原生公式/表格、资产用途及内部对象、编译错误/丢字/交叉引用/溢出、实际 PDF 位图。监工 agent 对照原稿检查翻译、公式符号、表格单元格、全部输出页。程序检查与内容/视觉阅读分开记录，前者不能冒充语义正确，AI 复核也不能标为人类复核。
6. **恢复与发布**：所有阶段落盘，已经生成的证据、内容和合格资源复用；只修失败块。发布须技术检查与当前版本监工复核同时通过。内容、资产、模板、原稿或 PDF 一变，旧复核自动失效。最终同时交付 PDF、可编译 TeX、来源/复核报告。

## 数据合同

`project.json`：schema_version、只读原稿 path/sha256、PDF 页码、title、class/template 指纹。`packet/pages/pNNNN.json`：page、width/height、text blocks（id/page/bbox/text）、图片与矢量统计；同名 PNG 只供阅读，不准嵌入成品。

`content.json`：title、blocks、exclusions、unresolved、expectations。每个 block 有 id、kind、source_ids、tex；figure 使用 asset/width/caption/number，不接受正文中的任意 includegraphics。原生图可使用 kind=figure_native 的 TikZ 等 TeX。exclusions 有 source_id/reason/category；category 仅 header_footer、out_of_scope 或 extraction_artifact，必须逐项检查。expectations 写实际应有 equation_tags/table_count/figure_count/required_strings，由阅读原稿确定，不由生成结果反推。

`assets.json`：逐资源 path、kind（vector_pdf/native_pdf/source_raster）、role=figure、source_page/bbox、rationale、sha256。包装在 PDF 内的 PNG 仍按位图处理。vector_pdf 必须零可见图像对象且有矢量路径或原生文字。

`review.json`：当前构建指纹、原稿页与输出页的完整复核清单、translation_checked、formula_table_checked、issues、reviewer（写实际的监工 agent 或人类姓名，区分两者）。复核清单不完整或指纹过期则不能发布。

## 最小命令

`doctor` → 检查真实 Python/PyMuPDF/XeLaTeX/内存。

`prepare --source ... --pages ... --project ... --title ...` → 可缓存证据包，保持原稿只读。

`asset --project ... --page ... --bbox x0 y0 x1 y1 --name ...` → 保留源矢量图并登记。

agent 写 content.json / 复核；可调用受限 DeepSeek 做文字翻译、TeX 和批量检查，Codex 管图片判断与最终验收。

`build --project ...` → 生成/编译，记录日志和指纹。

`qa --project ...` → 技术报告和待填写复核模板；未完成是 draft，不能偷偷升格。

`release --project ...` → 严格重验，输出 PDF、TeX 包、完整报告。

## 本次复现

先独立从英文 PRML 的 PDF 24–32 页重建完整 1.1 小节。明确不纳入页24的前节末尾、页32的 1.2 开始。必须有公式1.1–1.4、表1.1/1.2和图1.2–1.8；不要借用参考中文版的译文/表格数据/图片作为生成输入。然后验证不同领域的 Carey 英文小样。参考工程只用于分析方法和比较效果。

可靠性的边界：本工作流保证未满足验收合同的内容不能发布；它不声称 PDF 文本提取或语言模型可以无需校对地还原任意数学书。扫描图的矢量化需真正重建，不以改扩展名、升 DPI 或截图冒充。
