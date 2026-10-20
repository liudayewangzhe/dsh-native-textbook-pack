# 来源前检入口

新来源、扫描/OCR 混合页、代码/化学/课件、边注与多栏、多面板宽对象，或批量审查不同书目时，先读引擎 `docs/preflight.md`（默认 `E:\PDF\_ZH\native-forge\docs\preflight.md`；迁移时按 `NATIVE_FORGE_HOME` 解析）。该文件是前检字段、候选边界和验收的单一说明。

**文字层正常但公式和插图全是位图**的来源（Calibre 从 EPUB 生成、部分出版社纯图排版）另走 [bitmap-math-sources.md](bitmap-math-sources.md)：前检的"有文字层"结论在这类来源上会误导，必须先用字体直方图 + 图像面积分布确认类型。

用带 PyMuPDF 的 Python 在引擎目录执行：

```powershell
python scripts/preflight_pdf.py --manifest inputs.json --out reports/source-preflight
```

`inputs.json` 为 `[{"id":"source-a","path":"原稿的绝对路径"}]`。该命令只读来源，记录哈希、逐页观测和候选，不翻译、不 OCR、不访问外链。先看代表页，再决定语义拆分和版式。零文字层不是空页；有文字层不证明 OCR 或字体映射正确；表格、旁注、多栏、方形图均须视审确认。

需要编辑或交付 `.pptx` 时路由 `presentations`；需要保留 PPT 风味的原生中文 PDF 时读 [slide-native-pdf.md](slide-native-pdf.md)。PDF 课件按页尺寸、面板与阅读顺序分析，不能统一塞进书籍模板。本前检只测试 PPTX 容器路由，不声称完成演示稿转换或恢复备注/动画。

二维码需分别登记发现、模块/留白保留、原样链接和本地解码比对。当前脚本只提供方形图候选与链接注解；没有解码实现。未经原稿区域及最终 PDF 区域的本地解码证据，不能写“二维码已验证”，更不能自动打开其外链。

DeepSeek 只收项目目录中的派生摘要和短样本，监工逐项核对其结论。个页转写错误留在项目问题单，不升级为全局清洗。前检报告与书籍翻译、内容校对、视觉验收分别完成。
