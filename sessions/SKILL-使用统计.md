# 本机 248 个会话里，skill 到底被怎么用了

数据来源：`C:\Users\ltllt\.dsh\sessions\` 下全部会话（`session.v4.jsonl.zstd` 解压后统计 `tool/call`）。
统计口径：只算 `skill` 工具的显式加载，以及工具调用参数里真的出现过的技能目录路径。

## 显式加载（`skill` 工具）

| skill | 会话数 | 用在哪 |
|---|---|---|
| `native-textbook` | **10** | 五个原著转换项目的主体 |
| `diagnose-windows-sandbox-acl` | 4 | 其中 3 次与教材工作流相关（含 10-15 那次"为什么持续运行失败"排查） |
| `vedic-astrology` | 2 | 与教材无关（命理任务） |
| `office-pptx` | 1 | Lecture2-Signals 要额外交付可编辑 `.pptx` 时 |

`native-textbook` 的 10 次分布在：

| 时间 | 会话 | 干什么 |
|---|---|---|
| 10-13 20:11 | `session-d6503ac3` | 把 Codex 技能接入 DSH（顺带验证 native-textbook 可用） |
| 10-13 21:14 | `session-11a87192` | 从会话 zip 恢复后继续 |
| 10-13 21:28 | `cda35a03` | 《金融物理》起草 worker |
| 10-14 10:30 | `session-56cd956b` | 《经典力学》主控 |
| 10-14 10:56 | `3a7a4f1f` | 《经典力学》翻译 worker |
| 10-14 14:21 | `session-8baf44b0` | Lecture2-Signals PPT 双版本（+`office-pptx`） |
| 10-14 14:33 | `d5fbdc49` | worker + 监工 |
| 10-14 15:45 | `session-a7e38e0e` | 反向升级 native-textbook 技能本身 |
| 10-14 22:07 | `session-7f08e267` | 《计算物理》扫描件主控（275 个 subagent） |
| 10-14 22:31 | `455ac490` | 《计算物理》独立视觉审查 |

## 不走 `skill` 工具、但实际被"当脚本用"的技能

| skill | 用法 | 会话 |
|---|---|---|
| `deepseek-claude-subagent` | 读它的 `SKILL.md`，直接调 `scripts\invoke-deepseek-claude.cmd` 做批量翻译 | `session-8eacd363`（ME4300） |
| `humanizer-zh` | 读 `SKILL.md`，另写驱动脚本跑中文语言润色 pass | `session-8eacd363`、`session-d6503ac3` |

## 关键结论（决定了本包装什么）

1. **核心只有 `native-textbook` 一个**。worker 子会话通常**不加载技能**，它们读项目自己的
   `WORKER_CONTRACT.md` / `WORKER_BRIEF.md`。所以真正需要装的是主控会加载的那几个。
2. `office-pptx` 属于 DSH 随包技能，只在"要交 `.pptx`"时才出现，本包不重复携带（避免遮蔽随包版本）。
3. `diagnose-windows-sandbox-acl` 出现频率不低——Windows 上的文件权限问题在这条工作流里是**常规故障**，不是偶发。
4. 其余技能名（`ccf-*`、`wiki-*`、`matlab-*`、`book-to-skill` 等）在会话里只是**系统提示词里的技能目录**，
   没有一次真实加载，因此不进本包。
