# 本包携带的 skill 清单

DSH 扫描技能的根目录与优先级（来自 DSH 自身的 `dsh-skill-filesystem` 文档）：

| rank | 来源 | 路径 |
|---|---|---|
| 100 | project-dsh | `<项目根>/.dsh/skills` |
| 200 | project-agents | `<项目根>/.agents/skills` |
| 300 | custom | 配置里的 `customSkillDirs` |
| 400 | user-dsh | `%USERPROFILE%\.dsh\skills` ← **本安装器装到这里** |
| 500 | user-agents | `%USERPROFILE%\.agents\skills` |
| 600 | bundled | DSH 随包自带的技能根 |

规则：技能必须是扫描根**顶层**的目录 bundle `<name>/SKILL.md`（或平铺的 `<name>.md`），
**不递归发现**嵌套的 `**/SKILL.md`。`SKILL.md` 需要 YAML frontmatter 里的 `name` 与 `description`。

## 装进来的

| skill | 作用 | 用在哪 |
|---|---|---|
| **native-textbook** | 核心技能：把技术书 / 扫描件 / 课件 PDF 重建成原生中文 LaTeX PDF（可编辑公式表格、矢量图、渲染与视觉校验）。含 book 与 slide 两条分支 | 全部转换任务；本包的主体 |
| office-files | 文档类技能的路由器，`native-textbook` 被登记为 `office-files/native-textbook` | 入口路由 |
| scientific-visuals | 出版级图表 / matplotlib / 可视化路由 | 重绘图表、图 QA |
| deepseek-claude-subagent | 用一个受限 wrapper 把机械的、大批量的文字工作交给另一个模型（批量翻译、TeX 转写） | 长书的 chunk 初稿 |
| humanizer-zh | 中文去 AI 味 / 语言润色 pass | 译稿语言层精修 |
| humanizer | 英文去 AI 味（同族，`humanizer-zh` 的英文版） | 英文源材料 |
| skill-creator | 创建 / 修改 / 评测 skill | 要改 native-textbook 时 |
| skill-authoring | skill 编写的路由与规范 | 同上 |
| skill-network | 技能之间的路由与组合图 | 排查"该用哪个技能" |
| diagnose-windows-sandbox-acl | Windows 上 DSH 文件沙箱报权限错时的诊断与修复脚本 | 见 `playbook/04-踩坑与注意点.md` |

## 故意没有装的

| skill | 原因 |
|---|---|
| office-pptx / office-docx / office-xlsx | 它们是 **DSH 随包自带**的（`<DSH安装目录>\resources\runtime\office-skills\`），并且检查脚本位于 `<skill目录>\..\scripts\check_office.py`。如果装进 `~/.dsh/skills`（rank 400 高于 bundled 600），会**遮蔽**随包版本，而用户目录里没有那个 `scripts\`，反而会把 `.pptx` 检查弄坏。需要交付可编辑 PPTX 时，直接 `skill` 调用 `office-pptx` 即可。 |
| wiki-* / ccf-* / horosa-* / matlab-* 等 | 与教材转换无关，属于使用者自己的其它技能集。 |
| book-to-skill | 与本次任务无关（它解决"把书蒸馏成技能"，不是"把书译排成中文 PDF"）。需要时可自行安装。 |

## 卸载 / 回滚

安装器会先把同名旧技能重命名成 `<name>.bak-<时间戳>` 再覆盖。回滚：

```powershell
$S = "$env:USERPROFILE\.dsh\skills"
Remove-Item "$S\native-textbook" -Recurse -Force
Rename-Item "$S\native-textbook.bak-20261015-120000" "native-textbook"
```

引擎装在 `%USERPROFILE%\.dsh\native-forge`（可用 `-EngineHome` 改），直接删目录即可。
用户级环境变量 `NATIVE_FORGE_HOME` 用
`[Environment]::SetEnvironmentVariable('NATIVE_FORGE_HOME',$null,'User')` 清除。
