# 引擎移植说明（Native Forge）

本目录是 `E:\PDF\_ZH\native-forge` 的**代码子集**（引擎 + 脚本 + 模板 + 测试 + 第三方扩展 + 文档），
不含那台机器上 5.2 GB 的 `projects/`、`audit/`、`reports/` 成果目录。

正常情况**不需要读本文件**：在包根目录运行 `install.cmd` 会自动完成下面所有事。
这里只是把"哪些地方是机器相关的"讲清楚，便于手工排障。

## 1. 已由安装器处理的机器相关项

| 位置 | 原值（制作机） | 安装后 |
|---|---|---|
| `nf.cmd` | 写死 `C:\Users\ltllt\.cache\codex-runtimes\...\python.exe` | **重新生成**：用目标机器上探测到的 Python，并支持用环境变量 `NF_PY` 覆盖 |
| `skills\native-textbook\scripts\nf.cmd` | 默认 `NATIVE_FORGE_HOME=E:\PDF\_ZH\native-forge` | 改写为实际引擎安装目录 |
| PyMuPDF | 装在制作机的 user site-packages | 装进 `<引擎目录>\pylibs`，由生成的 `nf.cmd` 加进 `PYTHONPATH` |
| `NATIVE_FORGE_HOME` | 未设置 | 设为引擎安装目录（用户级环境变量） |

## 2. 仍然写死的路径（历史记录，不影响运行）

- `engine\native_forge.py` 里的 `XELATEX_LEGACY = E:\PDF\_ZH\tools\texlive\bin\windows\xelatex.exe`
  —— 只是 `shutil.which("xelatex")` 失败后的**兜底**。目标机器上装了 TeX Live 并把 `xelatex` 放进 PATH 即可，不必改。
- `engine\docs\*.md`、`README.md`、`PACKAGE.md`、`deliverables\` 等文档里的绝对路径 —— 是当时的运行记录，不是配置。
- `skills\native-textbook\scripts\scan_repair\*.py` 里的 `INBOX` / `PROJECT` / `SLICES` 常量
  —— 这些脚本是在《计算物理》项目现场写的一次性修复工具，**用之前必须改路径**。
  它们的价值在于"当时怎么修的"，不是"拿来即跑"。

## 3. 硬性外部依赖

| 依赖 | 检查方式 |
|---|---|
| Python 3.10+ | `python -V`；`cp310-abi3` 的 PyMuPDF wheel 在 3.10+ 通用 |
| PyMuPDF | `python -c "import fitz;print(fitz.__doc__)"` |
| numpy / Pillow | DSH 自带运行时里有；扫描件修复脚本与校对图脚本需要 |
| XeLaTeX | `xelatex --version`；引擎用 `shutil.which` 解析 |
| 中文字体 | 模板用 ctex/elegantbook，缺字体会在编译日志里报缺字警告 |

## 4. 自检与冒烟

```powershell
# 环境体检（JSON 输出；ok=true 才是 0 退出码）
& "<引擎目录>\nf.cmd" doctor

# 真跑一次最小项目
& "<引擎目录>\nf.cmd" prepare --source "<任意小PDF>" --pages 1-2 `
      --project "<可写目录>\smoke" --title "冒烟测试"
# 期望：返回 JSON 含 "command": "prepare" / "content": "created"，
#       并在 <smoke>\packet\pages\ 下生成 pNNNN.json 与 pNNNN.png
```

内存门禁：空闲物理内存低于 1 GiB 时引擎会拒绝重活（`available physical RAM ... halting`）。
这是**规定动作**，不是故障。仅当总内存充足但空闲读数贴着阈值时，可用引擎自带的运算符开关：

```powershell
$env:NF_RAM_FLOOR_MIB = "768"   # 允许范围 512–1024 MiB，超出会被夹取；不要下发给 worker
```

## 5. 测试

`tests\` 里有引擎自身的验收测试（`test_native_forge.py`、`test_redraw.py`、`test_cli_acceptance.py`、`test_inventory.py`）。
需要 `pytest`；DSH 自带运行时**不含** pytest，要用的话先
`python -m pip install --user pytest`。测试同样受内存门禁约束。
