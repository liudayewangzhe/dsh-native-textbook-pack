# 2026-10-20：native-textbook 编排升级

这次升级在原生 PDF 制作与验收之上增加可恢复的长文档编排。保留 `native-textbook` 名称与 book / slide 两条输出链，不另造一个重叠技能。

## 来源和取舍

研究来源：[deusyu/translate-book](https://github.com/deusyu/translate-book/tree/a663b1b4f1e625b286cd2a81dffd16571e6f2aa2)，固定 commit `a663b1b4f1e625b286cd2a81dffd16571e6f2aa2`，MIT，Copyright 2025 Rainman。本次借鉴其设计思想，状态工具独立实现；没有复制它的 Python 源码或把 Calibre 输出链嵌入本引擎。

| 借鉴的机制 | 本机适配 | 保留的边界 |
|---|---|---|
| 源字节身份、chunk manifest | 原稿哈希 + 语义包顺序/范围/路径 | 不以相同文件名接管新版来源 |
| 独立 worker + 邻居摘录 | 完整论述单元/课件页组、只读上下文 | 不硬切公式、表格、证明、代码或一页图文 |
| canonical glossary + 反馈 + run state | 有领域作用域的术语、主控单写、显式草稿记账 | 本块命中不截断，冲突有证据后裁决 |
| 术语变更定向重译 | 源、实际上下文、术语、规则、输出指纹 | 模板/字体/资产变化只触发重建与重审 |
| manifest 检查后合并 | 先核查状态，再用原引擎验证并合并 | 身份和结构通过不证明语义、视觉通过 |

没有移植的默认值与捷径：固定八路并发、按字符超限硬切、只保留固定数量本块术语、自动接管未跟踪输出、Markdown/HTML/Calibre 作为技术 PDF 的最终出版后端。

上游源码核查发现两个值得避免的机制：`scripts/convert.py` 对过长块调用强制切分，数学块并非总被豁免；`scripts/glossary.py` 在命中数超过总上限时会截掉本块术语。它们是本次固定版本的观察，不能外推到后续版本。新工具用真实行为测试保护完整本块术语；语义边界由主控建立，不做字符自动切块。

## 本机经验如何进入设计

先查阅现行 skill、历史 Codex/DSH 翻译过程与相应交付记录，再决定合并方式。原始个人聊天和本机路径没有新增上传。仓库已有脱敏经验仍见 [sessions/index.md](../sessions/index.md) 与 `playbook/`。

| 本机已出现的风险 | 升级的对应处理 |
|---|---|
| 课件文字正常但分母、矩阵、波形、推导项在最终 PDF 中损坏 | 保留页几何、坐标校准、原生数学、实际导出 PDF 的全部页面检查 |
| “全部看过”后仍漏遮挡与箭头问题 | 保留逐对象清单、双角色审查和负向回归，模型自评不能替代证据 |
| technical pass 仍有图题混译、代码/索引关系问题 | 调度身份、内容校对、排版和视觉维度分开，不让新状态工具宣告终审 |
| 另一环境重编导致分页变化 | 把模板、字体、宏包/编译环境、绘图代码纳入构建依赖，保留独立复编判据 |
| 用户授权画新封面，却被“只能照原封面”条款限制 | 明确 `faithful_reconstruction` 与 `authorized_redesign`；重设计也保留真实元数据和原生绘图审核 |
| 本机新规则尚未进入公开包 | 同步位图数学来源、前置页与干净来源规则，以及来源/视觉/门禁文档的新版本 |

历史 QA 文件只说明当时记录了什么。本次是技能与工具升级，没有重新完成这些历史整书的逐行翻译终审。

## 保留的制作能力

原生数学、可编辑表格、TikZ/PGFPlots/chemfig 等重绘、原 PDF 真矢量提取、真实照片例外、图形语义合同、原生封面、书籍/课件分流、中文字号与留白、边注/宽版、扫描修复、代码语境、全部输出页视觉审核、当前指纹审查、独立包三遍复编均继续生效。原有资产、脚本和参考文件保留；新增入口指向这些能力，不以新文档替换它们。

具体执行与 CLI 见 [translation-orchestration.md](../skills/native-textbook/references/translation-orchestration.md)。可运行的小样本见 [orchestration-smoke.md](../examples/orchestration-smoke.md)。实际验证范围与结果见 [UPGRADE-VALIDATION.md](UPGRADE-VALIDATION.md)。
