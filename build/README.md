# build：这个包是怎么生成的（便于日后刷新）

包里那两个脚本是**制作工具**，不是运行依赖。装到新机器后可以完全忽略它们。

| 脚本 | 作用 |
|---|---|
| `make_transcripts.py` | 把 DSH 会话 `session.v4.jsonl.zstd` 转成可读 Markdown（只留用户消息、助手正文、工具调用参数与截断后的返回） |
| `make_manifest.py` | 扫描包目录，生成 `MANIFEST.json`（文件清单 + SHA256 + 体积 + 分卷方案） |

## 刷新会话记录（在做过任务的源机器上）

```powershell
# 1. 需要 zstd 解压器；把路径改成你机器上的
$env:NF_ZSTD = 'D:\Anaconda2\Library\bin\zstd.exe'

# 2. 编辑 make_transcripts.py 顶部的 SELECTED 列表，增删要导出的会话 id 与标签
#    （会话 id 就是 %USERPROFILE%\.dsh\sessions\<项目目录>\<会话目录> 的名字）

# 3. 重新生成
python .\make_transcripts.py --out '..\sessions'
```

脚本会跳过这些噪声消息：运行上下文、技能目录清单、工具任务通知、授权回执、压缩检查点、
goal 续跑提示；`subagent-settled` 只保留一行回执。

> 会话原文也可在 DSH 的会话列表里直接重新打开；`.jsonl.zstd` 是 zstd 压缩的 JSONL，每行一个事件。

## 重新打包

```powershell
# 1. 重建清单
python .\make_manifest.py --pack '..' --split-limit-mb 500

# 2. 重新压缩（务必把顶层目录一起打进 zip，解压才会得到一个文件夹）
Compress-Archive -Path '..\dsh-native-textbook-pack' `
                 -DestinationPath '..\dsh-native-textbook-pack.zip' -CompressionLevel Optimal

# 3. 出校验和
Get-FileHash '..\dsh-native-textbook-pack.zip' -Algorithm SHA256 |
  ForEach-Object { "$($_.Hash)  dsh-native-textbook-pack.zip" } |
  Set-Content '..\dsh-native-textbook-pack.zip.sha256' -Encoding ASCII
```

## 分卷规则

`make_manifest.py --split-limit-mb 500` 会按这个上限试算分卷并写进 `MANIFEST.json` 的 `parts` 字段
（只做体积规划，不真正切分文件）。当前包约 22 MB，**1 个压缩包即可**。
将来若加入成书 PDF、样本等导致超过 500 MB，就按 `parts` 的边界切分成多个 zip，
让使用者**全部解压到同一个目录**后再运行 `install.cmd`。

## 刷新 `skills\` 与 `engine\`

本包制作时的来源：

| 内容 | 来源 |
|---|---|
| `skills\native-textbook`、`humanizer*`、`deepseek-claude-subagent` | `%USERPROFILE%\.codex\skills\` |
| `skills\office-files`、`scientific-visuals`、`skill-authoring`、`skill-network`、`skill-creator` | `%USERPROFILE%\.agents\skills\` |
| `skills\diagnose-windows-sandbox-acl` | DSH 随包技能（asar 内的 bundled 根，加载时会物化到临时目录） |
| `engine\native-forge` | `E:\PDF\_ZH\native-forge`，只取 `engine/ scripts/ templates/ tests/ third_party/ docs/` + 根级说明文件 |

复制时排除 `.git`、`__pycache__`、`.github`、`node_modules`。
