# 工作流包使用说明

本机的工作流已经安装在 `E:\PDF\_ZH\native-forge`，技能已安装在 `C:\Users\ltllt\.codex\skills\native-textbook`。本ZIP是可校验的备份与复用包，不需要再次安装才能使用。

在本机其他agent的聊天中输入：

> 使用 $native-textbook，把“英文PDF绝对路径”的第X章重建为原生中文教材，完成来源和全部输出页复核，交付PDF与可编译TeX包。

如果agent的技能列表尚未刷新，让它读取上述 `SKILL.md`。来源阅读和范围规划由监工负责；DeepSeek在受限项目目录内起草；发布必须经过实际复核。

ZIP内的 `samples/*.pdf` 是四组已验收PDF，`samples/*-tex.zip` 是各自可独立编译的源码包。`docs/重构分析与验收报告.md` 记录根因、六个模块、复现和验证边界。`workflow-manifest.json` 可逐文件校验SHA-256。

如果在本机解压到另一目录，设置环境变量 `NATIVE_FORGE_HOME` 为该目录后运行 `nf.cmd doctor`。技能也随包保存在 `skill/native-textbook`，需要时复制到agent的技能目录。启动器使用本机已验证的Codex Python；XeLaTeX、字体和PyMuPDF由doctor检查，ZIP不包含这些大型依赖、英文整书或API凭据。具体命令和数据合同见README与docs。

对整本书按语义小节并行起草、顺序合并、逐段复核；本包实测为四组真实选段，共13页。不要把这些样段描述成整本书已经完成。
