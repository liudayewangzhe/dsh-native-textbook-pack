# 长文档编排：语义工作包、术语与可恢复状态

新建长文档、多 worker、跨批次续跑，或修改术语后定向修订时读取本页。它管理制作过程；书籍仍输出 Native Forge 的语义 JSON/TeX，课件仍输出独立页级合同。`draft_verified` 只表示可集成草稿，不能代替内容、原生性、排版、视觉或发布验收。

## 1. 先做文档工程，再分派翻译

执行顺序：来源前检 → 产品与范围合同 → 对象/阅读顺序清单 → 版式及绘图路线 → 真实风险样张 → 语义工作包 → 有界 worker → 监工集成 → 构建与分层验收。规划阶段可以列待补项；不得倒过来要求规划者先交通过样张。

| 模块 | 权威输入与输出 | 责任和门槛 |
|---|---|---|
| 来源适配 | 原文、SHA-256、物理页/章节范围、只读 packet、对象 ID | 主控核实阅读顺序；OCR、Markdown、参考译本都是辅助证据 |
| 文档计划 | book / slide、几何、字号、注释、对象路线、封面模式 | 看真实源页；按风险选样张，样张通过后才扩量 |
| 语义与术语 | 完整小节/页组、原生对象合同、作用域术语、邻居上下文 | 机器管理身份和依赖，主控处理语义、歧义、科学判断 |
| 工作包与状态 | `translation-manifest.json`、只读 brief、独立 worker 输出、`run-state.json` | 主控单写共享状态；worker 不能自行接管旧稿或填写审查通过 |
| 原生制作 | book content/assets；slide 页级 TeX；图形代码与资产来源 | 公式/表格原生；图先语义合同再保留矢量或重绘 |
| 验收与反馈 | 当前 PDF、源页对照、排版/视觉/复编报告、缺陷回归 | 成功生成不等于成功验收；错误进入下次开工会调用的规则 |

DOCX、EPUB、Markdown 也可作为来源：先保留原文件与资源，使用对应文档技能读取标题、列表、脚注、代码、公式及图表关系，建立稳定对象 ID 与来源定位。它们没有 PDF 物理页时用章节/段落/对象锚点，不伪造页码。需要对照版面时另导出来源 PDF，记录其与原文件的关系。HTML/Markdown 中间层不能证明复杂数学或多栏阅读顺序正确；最终制作仍走原生 TeX。PDF 仍以实际源页核验，不能把重排后的 Markdown 当作唯一真相。

## 2. 工作包边界

- book 按完整论述单元分包。段落、证明、列表、公式组、表格及其续表、图与图注不能按字符数硬切。过大时由监工选择可解释的语义边界，或增加该包预算；完整性优先于均匀大小。
- slide 按完整源页或同主题完整页组分包。保留源页序、比例、标题带、图文组、毫米坐标、实际字号和一源页一输出页合同，不转成连续书籍。
- 代码、控制台输出、行号、正文解释和相关图必须区分。代码字符、缩进、命令、文件名及 API 标识保留；解释另译。术语表用来约束译文，不对代码或 TeX 做全局字符串替换。
- 来源 ID 在调度清单中只归一个包。一个抽取对象跨越多个语义小节时，将这些小节留在同一包，或先由监工按真实区域建立有来源映射的子对象；不伪造 ID，也不为分包丢弃内容。
- 邻居摘录只供指代、符号和论证衔接，不属于本包输出范围。跨包前置定义或远距离依赖由监工放入版本化的翻译输入，不能假设短摘录已经包含全部语境。

并发数由实际内存、可用 worker、接口容量与首批质量确定，不照搬固定八路。Windows 空闲物理内存低于 1 GiB 时遵守既有硬停止规则。优先让主线定期产生可检查 PDF；失败包单独修，不因局部失败重译全书。

## 3. 建立状态并派单

工具：[translation_state.py](../scripts/translation_state.py)，仅依赖 Python 标准库。下列示例的路径、ID和术语必须替换为本项目的真实值。先创建所引用的文件，再初始化；脚本不抽取 PDF、不推断阅读顺序、不替你分割小节。

项目内 `translation-spec.json` 示例：

```json
{
  "version": 1,
  "mode": "book",
  "source": {"path": "source/original.pdf"},
  "glossary": "glossary.json",
  "translation_inputs": ["contracts/worker-rules.md"],
  "build_inputs": ["contracts/layout.tex", "assets.json"],
  "context_chars": 400,
  "chunks": [
    {"id": "c01", "source": "evidence/c01.txt", "output": "draft/c01.json",
     "source_ids": ["p0001-s0000"], "scope": "global"}
  ]
}
```

`source.path` 可指向外部只读原稿；其余文件都在项目根目录内。`translation_inputs` 放本批会改变翻译/转写行为的完整规则快照、源范围和对象合同；`build_inputs` 放布局、封面、绘图源、字体/编译环境清单及资产字节依赖。只列 `assets.json` 而不列它引用的资产文件，不能检测资产内容变化，必须把真实依赖也列全。记录器不自动解析 TeX 的整个依赖图。

`context_chars` 是工作包预算参数，400 只是示例，不能当作语义完整的判据。作用域字段用于技术多义词；slide 的 chunk 另需 `source_pages`，按 [slide-worker-contract.md](slide-worker-contract.md) 返回 `pages`，不能写成 book 的 `blocks`。

```powershell
python scripts/translation_state.py init --project '<项目>' --spec '<项目>/translation-spec.json'
python scripts/translation_state.py plan --project '<项目>'
python scripts/translation_state.py brief --project '<项目>' --chunk c01
# 主控把生成的只读 brief、必读合同和相关图像证据交给受限 worker。
# worker 只写 draft/c01.json；主控检查其输出，然后显式记为草稿。
python scripts/translation_state.py record --project '<项目>' --chunk c01
python scripts/translation_state.py verify --project '<项目>'
```

初始化锁定原稿字节、工作包顺序、读写路径及来源归属；拒绝覆盖已有清单。原稿换版或授权范围改变，建立新的制作谱系，不删除旧证据来强行复用状态。只有格式化/注释等无语义的改动才可能复用对应依赖；具体以实际指纹与检查结果为准。

`brief` 固定本包来源、邻居实际摘录、全部命中术语、规则和构建依赖；worker 不能据此扩大来源或写入权限。`record` 要求 brief 仍有效，校验输出结构、来源集合及未决项，再记录输出哈希。它是监工显式采纳一个草稿的动作，**不是独立审校**。修补草稿后可以明确重新 record，必须重新检查受影响内容。

## 4. 术语是有来源的语义状态

`glossary.json` 示例：

```json
{
  "version": 1,
  "terms": [
    {"id": "kernel-linear", "source": "kernel", "target": "核",
     "aliases": [], "scope": "linear-algebra", "always": false,
     "definition": "线性映射到零向量的原像", "evidence_refs": ["p0012-s0003"]}
  ]
}
```

主控先从章节结构、定义、符号表及风险段落建术语骨架，后续按新证据补充。不要只凭固定数量的首页/中间页抽样就宣布全书术语完备。本块及实际注入上下文命中的术语全部保留；全书通用词可由主控标 `always`。若提示过长，拆语义包或缩减非必要背景，不能静默截断本块术语。

同一有效作用域内的 source/alias 冲突必须消歧；不同明确领域可有同形不同义词。`global` 与局部同时适用时也不能保留冲突目标。英文词边界避免 `cat` 命中 `category`，中文匹配仍需人工确认词义。`definition`、符号、翻译约束等语义信息应进入版本化 `translation_inputs`；脚本自动术语指纹只覆盖其声明支持的字段，不能假设任意自定义注释会触发重译。

反馈闭环采用三层分离：

1. worker 只在自己的文件提交观察：本包 ID、来源 ID、原文证据、候选译法、理由、不确定项，以及源/输出/brief 哈希。没有新发现也明确返回空观察。
2. 主控验证证据确实属于当前来源；冲突先保留，不用字符串相似度自动合并实体，不把多数模型赞成当作学科证据。记录采用/拒绝理由及原 canonical 哈希。
3. 主控批次边界统一修订 canonical glossary，保留修改前版本和已消费观察哈希，再运行 `plan`。当前版本由主控执行语义合并，**没有自动合并器或自动证据真实性判定**；不宣称观察 JSON 已被脚本审校。

这保留了单写者模式，避免多个 worker 改共享术语或互相覆盖。术语变化必须重新计算旧命中与新别名命中影响，不能只查旧记录中的 term ID。

## 5. 失效范围与恢复

| 变化/异常 | 编排动作 | 仍需做的工作 |
|---|---|---|
| 原始来源文件字节改变 | 阻断旧谱系 | 核实换版与授权，另建清单 |
| 本包源、有效术语、规则或实际邻居摘录改变 | 相关包重新翻译/修订 | 新 brief、新输出、新 record；检查边界衔接 |
| 模板、封面、绘图/字体环境等 build 输入改变 | `rebuild`，复用未变译文 | 重建 PDF；旧 PDF 的视觉审查不能沿用 |
| 输出缺失、空白、损坏、包含未决项或来源不符 | 阻断 record / verify | 隔离失败包，保留真实原因 |
| 输出未经跟踪或记账后被改动 | `untracked` / `output_changed` | 主控查明来源并显式检查、重新记账，不能自动信任 |
| 仅未注入的邻居部分改变 | 按实际依赖决定是否复用 | 若存在更远语义依赖，将其补入翻译输入后重新规划 |

`verify` 给出按阅读顺序的 `ordered_outputs`，并单列 `needs_rebuild`、`review_valid`。只改变 build 输入时可通过草稿完整性校验，但必须重建与重新审查 PDF。状态工具从不写 `reviewed`、`released`，不合并 `content.json`，不覆盖 `review.json`。

`needs_rebuild` 表示相对草稿记账时的构建输入是否变化，不跟踪实际 PDF 的构建缓存；即使它为 false，也不能推断现有 PDF 最新。新集成或修订后的文稿仍须运行构建和现有指纹门禁。

book 集成前停止 worker 写入，先 `verify`，再将其确切顺序交给引擎 `scripts/merge_chunks.py --project ... --chunks ...`；禁止 `Glob` 后按文件名猜顺序。合并器仍执行真实引擎内容/资产/来源验证。slide 则由主控按页合同集成 TeX，运行专用三项检查及逐页审核，不能调用 book 发布器。

旧项目无需整书迁移。保留旧 content 与审校证据，为本次涉及的完整范围建立独立清单；未知旧输出必须经过新 brief 与显式检查，状态最多是草稿。清单与文件哈希只能证明身份、依赖和结构，不能证明一句没漏译、数学正确或图画对了。

## 6. 终稿仍执行既有强项

图形和封面继续读 [figure-craft.md](figure-craft.md)、[cover-and-geometry.md](cover-and-geometry.md)；中文排版继续读 [chinese-typography.md](chinese-typography.md)。扫描、位图公式、代码、边注、宽版和前置页按文档地图的专门规则处理，不能被统一 Markdown 转换链抹平。

完成草稿后：授权源内容对照 → 原生对象与技术检查 → 排版几何和字号回抽 → 全部输出页 L1、复杂对象 L2 与独立高风险审查 → 当前 PDF 哈希绑定 → 脱离工作目录三遍复编、像素与书签比较 → 各分支发布。只做部分尾处理时逐维记录真实范围，不把 `semantic_review:not_performed` 写成全书 `reviewed`。

复发问题按工具/生成/合同/监督层定位：给出最小坏样例，证明检查器能报错，再证明修复后的样例通过。工作流收益以真实缺陷减少和可复现证据衡量，不编造质量保证或节省比例。
