# 安装后 5 分钟验收流程

按顺序做完这四步，就能确认"这台机器可以接手原生中文教材转换任务"。

## 第 1 步 · 技能目录里看到了什么

```powershell
Get-ChildItem "$env:USERPROFILE\.dsh\skills" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } |
  Select-Object -ExpandProperty Name
```

应该看到 `native-textbook`、`office-files`、`scientific-visuals`、`deepseek-claude-subagent`、
`humanizer-zh`、`humanizer`、`skill-creator`、`skill-authoring`、`skill-network`、
`diagnose-windows-sandbox-acl` 共 10 个。

> DSH 只在**会话启动时**扫描技能目录。装完必须完全退出并重开，否则新技能不可见。

## 第 2 步 · 引擎自检

```powershell
$NF = "$env:USERPROFILE\.dsh\native-forge\nf.cmd"
& $NF doctor
```

期望：JSON 里 `pymupdf.available = true`、`templates.ok = true`、`xelatex.found = true`。
`memory.ok = false` 表示当前空闲内存低于 1 GiB——那是工作流故意设的门禁，不是装坏了。

## 第 3 步 · 真实跑一次 prepare

```powershell
& $NF prepare --source 'D:\tmp\小样本.pdf' --pages 1-2 --project 'D:\tmp\smoke' --title '冒烟测试'
```

期望：返回 `"command": "prepare"`、`"content": "created"`；
`D:\tmp\smoke\` 下出现 `project.json`、`content.json`、`assets.json`、
`packet\packet.json`、`packet\pages\p0001.json`、`packet\pages\p0001.png` 等。
产物长什么样，可以对照 `..\examples\project-skeleton\`（那是一次真实运行的输出，去掉了大图）。

内存不足时可临时放宽（引擎只允许 512 MiB–1 GiB）：

```powershell
$env:NF_RAM_FLOOR_MIB = 768
```

## 第 4 步 · 在 DSH 里复现一次真任务

新开一个会话，说：

> 用 native-textbook 技能，把 `D:\书\原稿.pdf` 的第 3 章译排成原生中文教材。
> 公式、表格要可编辑，图形按内容保留矢量或重绘，做完内容和全部输出页复核后交付 PDF 与 TeX 包。

观察它是否：加载 `native-textbook` → 读 `references\first-draft-and-polish.md` → 跑 `prepare` →
派 worker 写 content.json → `build/qa` → 排版检查 → 视觉审核 → `release`。
哪一步塌了，去 `..\playbook\04-踩坑与注意点.md` 对照。

## 记录建议

第一次跑通后，把你自己的坑补进 `..\playbook\04-踩坑与注意点.md`（技能正文里也写了这条规矩：
**交付后必须回写，不回写等于这次白做**）。
