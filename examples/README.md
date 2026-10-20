# examples 目录说明

这里放**可直接抄用**的实物：真实派单模板、项目骨架、命令脚本。
和 `playbook\` 的区别：playbook 讲"为什么/注意什么"，这里给"照抄就行"的东西。

| 文件 | 用途 |
|---|---|
| `commands.ps1` | 参数化的一串命令：从 `doctor` 到 `release`，改开头三个变量即可跑 |
| `worker-brief-template.md` | 派给 worker 的任务书模板（book 分块译排 / 扫描页转写 / 独立视觉审查三种） |
| `project-skeleton/` | 一次 `prepare` 之后的项目结构（合成样张：含 `source.pdf`、packet JSON 与页面渲染图，可安全公开） |
| `smoke-test.md` | 装完机器后 5 分钟内的验收流程与预期输出 |

模板与结构来自真实会话：`..\sessions\05-经典力学-主控.md`、`..\sessions\10-计算物理-扫描件主控.md`、
`..\sessions\08-worker加监工模式.md`、`..\sessions\11-计算物理-独立视觉审查.md`。
想看完整原文和当时的踩坑，去 `..\sessions\`。
