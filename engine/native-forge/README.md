# Native Forge：原生中文教材译排

将技术 PDF 重建为可编辑的中文 ElegantBook。正文、公式、表格使用原生 TeX；图形按原稿矢量保留、代码重绘、真实原始位图分别处理。截图公式/表格不允许作为出版回退。语言模型起草，Codex 对照原稿并看全部成品页，符合检查合同后发布。

## 最简单的使用方法

在本机的其他 agent 聊天中说：

> 使用 $native-textbook，把“原稿绝对路径”译排为原生中文教材。范围是第 X 章。公式、表格要可编辑，图形按内容选择保留矢量或重绘，完成内容和全部输出页复核后交付 PDF 与 TeX 包。

技能已安装于 `C:\Users\ltllt\.codex\skills\native-textbook\SKILL.md`，并路由到 `office-files/native-textbook`。若当前 agent 没有刷新技能列表，直接让它读取该文件。引擎目录 `E:\PDF\_ZH\native-forge`；迁移后可设置 `NATIVE_FORGE_HOME`。本机使用已验证的 Codex Python 3.12.14、PyMuPDF 1.28.0 和 XeLaTeX 2024，不要求 Qwen API，不安装本地大模型。

## 程序入口

```powershell
& 'E:\PDF\_ZH\native-forge\nf.cmd' doctor
& 'E:\PDF\_ZH\native-forge\nf.cmd' prepare --source '原稿.pdf' --pages 24-32 --project '项目目录' --title '书名'
& 'E:\PDF\_ZH\native-forge\nf.cmd' asset --project '项目目录' --page 24 --bbox 263 68 472 229 --name f12
# agent 按来源证据写 content.json；机械工作可交给受限 DeepSeek。
& 'E:\PDF\_ZH\native-forge\nf.cmd' redraw --project '项目目录' --spec '图形规范.json' --name f12-native
& 'E:\PDF\_ZH\native-forge\nf.cmd' build --project '项目目录'
& 'E:\PDF\_ZH\native-forge\nf.cmd' qa --project '项目目录'
# 对照原稿和全部输出页，填写当前 build_fingerprint 绑定的 review.json。
& 'E:\PDF\_ZH\native-forge\nf.cmd' release --project '项目目录'
```

`--pages` 是 PDF 物理页码，`--bbox` 是完整来源页的 PDF 点坐标。先看裁出图，再登记出版资源。扫描页需要逐对象 `source_inventory.json`，不能因为抽不到文字就跳过。详细设计见 [docs/design.md](docs/design.md)，worker 合同见 [docs/worker-contract.md](docs/worker-contract.md)，长书并行/合并/恢复见 [docs/large-book.md](docs/large-book.md)。

## 已验证成果

- `projects/prml-curve/deliverable/main.pdf`：完整 1.1 节，6 页、4 个原生公式、2 个原生数值表、7 幅图。图1.2以来源矢量坐标数字化加原函数重绘，其余6图保留源矢量；PDF 位图0。
- `projects/carey-a/deliverable/main.pdf`：习题1.4和1.7选段，2页，原生文字/数学，3组完整矢量化学图，PDF位图0。
- `projects/carey-b/deliverable/main.pdf`：原英文PDF第4页b至g项，1页，5段正文和4组矢量反应图，PDF位图0。
- `projects/legacy-scan-check/deliverable/main.pdf`：从旧项目完整页扫描缓存独立重建，4页、12个展示数学块、3个原生表格，PDF位图0。对应原物理17/23/36页；原PDF不在旧路径，未声称重跑整章。
- `tests/verification.json`：64项引擎测试通过；曲线图、中文流程图、chemfig均完成真实编译与目检，零位图。

每个发布项目都带 `deliverable.zip`：可独立编译的 main.tex、类/样式、资源、来源清单、构建指纹、QA和复核记录。来源 PNG 只是证据包，在出版 PDF 中不嵌入。正文正确性由实际对照复核确认，不能由零位图或编译成功推出。

这里交付的是 agent 驱动、可恢复并有发布拦截的工作流。已验证上列真实选段；尚未把用户提供的所有整本书跑完，也没有把扫描识别能力当成无需复核的自动保证。源文件、旧 BookForge 和旧作品均保留。

根因分析、参考工程证据、模块合同与实测范围见 [重构分析与验收报告](docs/重构分析与验收报告.md)。完整工作流包为 `deliverables/native-forge-workflow.zip`，包含引擎、技能、模板、测试、四组PDF和各自的TeX发布包，不包含整本原稿或API凭据。解压至新位置后设置 `NATIVE_FORGE_HOME`；本机技能已经安装。

## 检查与恢复

源缺块、unresolved、画像冒充矢量、公式/表格图片、丢字、溢出、未定义引用、过期构建/复核都阻止发布。源码、原稿、内容、资产、模板、手工扫描清单与重绘规范变化使旧复核失效。已完成的证据和小节保留；只修失败对象，不重翻整个已通过的小节。低于1GiB空闲物理内存暂停重工作。

原配置指向的 `skill-cleaner` 脚本已不存在；未声称执行该工具。系统技能验证、两处路由检查及技能重复名/描述长度的替代检查结果在 `docs/skill-validation.json`。
