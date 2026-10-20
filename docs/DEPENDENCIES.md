# 依赖与下载地址

本文回答三件事：**必须装什么、哪些随仓库自带、每一项装完怎么验证**。

> 适用平台：Windows 10/11 为先。Linux/macOS 的手工步骤见 [INSTALL.md](INSTALL.md)，本文的下载地址同样适用。
>
> 外部链接在 2026-10 逐条核实过可访问；镜像内容与版本会变，以你打开页面时为准。

---

## 1. 依赖总表

| 依赖 | 必需性 | 是否随仓库 | 用途 | 获取方式 |
|---|---|---|---|---|
| DeepSeek Harness（DSH）桌面版 | **必需** | 否 | 技能宿主、提供会话与 Python 运行时 | 官方下载页 <https://www.deepseek.com/download/>（本仓库不提供安装包） |
| Python 3.10+ | **必需** | 否（DSH 自带运行时即可） | 引擎与全部脚本 | [python.org](https://www.python.org/downloads/windows/) / [阿里云镜像](https://mirrors.aliyun.com/python-release/windows/) |
| PyMuPDF（`fitz`）1.28.0 | **必需** | ✅ `wheels/` | 读 PDF、抽文本/矢量、渲染校对图 | 安装器离线装；也可 `pip`（见 §5） |
| numpy、Pillow | **必需** | 否（DSH 运行时自带） | 扫描件修复、视觉审核图的像素处理 | 随 DSH 运行时 |
| TeX Live（XeLaTeX + ctex + 字体） | **必需**（构建/交付阶段） | 否 | 编译 `build/main.pdf`、生成可复编 TeX 包 | [TUNA](https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/Images/) / [USTC](https://mirrors.ustc.edu.cn/CTAN/systems/texlive/Images/) / [阿里云](https://mirrors.aliyun.com/CTAN/systems/texlive/Images/) |
| 中文字体 | **必需** | TeX Live 自带 Fandol 可用 | 正文、标题、强调 | TeX Live 的 `fandol`；或 Noto CJK / 思源（见 §4） |
| DeepSeek API key | 可选 | 否 | 仅用 `deepseek-claude-subagent` 外包大批量起草时需要 | [platform.deepseek.com](https://platform.deepseek.com/) |
| LibreOffice | 可选 | 否（DSH 自带 CLI） | 仅 `.pptx/.docx` 预览或转换时需要 | 用 DSH 自带的那套，不要另装 |
| Poppler（`pdftoppm`） | 可选 | 否 | 视觉复核的**第二渲染器**交叉核对 | 由系统包管理器提供；未装时脚本跳过并记录 |
| Git | 可选 | 否 | `git clone` 取仓库；也可直接下载 ZIP | [git-scm.com](https://git-scm.com/downloads) |

**随仓库自带**：`skills/`、`engine/native-forge/`、`wheels/`（PyMuPDF）、`playbook/` 与全部文档。  
**最小外部依赖**：DSH 桌面版 + Python 3.10+（DSH 自带运行时即可）。  
**要真正产出 PDF 还差**：TeX Live（含 `xelatex`、`ctex`、`fandol` 字体）与中文字体；这两项不随仓库分发，必须自装。

---

## 2. DeepSeek Harness（DSH）桌面版

**状态**：技能宿主，本仓库**不包含**、也不负责分发。

**官方下载**（2026-10 核实可访问）：

- 下载页：<https://www.deepseek.com/download/>
- Windows x64：<https://download.deepseek.com/desktop/dsh-latest-windows-x64.exe>
- macOS（Apple 芯片，13+）：<https://download.deepseek.com/desktop/dsh-latest-macos-arm64.dmg>

装好后确认 `%USERPROFILE%\.dsh`（macOS 为 `~/.dsh`）存在即可。

**为什么需要**：`skills/` 里的技能由 DSH 在会话启动时扫描加载；`native-textbook` 的 worker 派单、视觉复核、独立审查都依赖会话与子会话能力。

**装完怎么验证**：

```powershell
# 1) DSH 能正常启动并开一个新会话
# 2) 确认 DSH 的用户级目录存在
Test-Path "$env:USERPROFILE\.dsh"
```

### 2.1 DSH 自带 Python 的路径判断方法

安装器会优先找 DSH 运行时里的 Python。手工确认：

```powershell
Get-ChildItem "$env:USERPROFILE\.dsh\dsh-runtimes" -Directory -ErrorAction SilentlyContinue |
  ForEach-Object { Join-Path $_.FullName 'dependencies\python\python.exe' } |
  Where-Object { Test-Path $_ }
```

命中后验证版本与依赖：

```powershell
$PY = '<上一步输出的路径>'
& $PY -V
& $PY -c "import fitz, numpy, PIL; print('fitz', fitz.__doc__); print('numpy', numpy.__version__)"
```

- `& $PY -V` 应显示 **3.10 或更高**（本仓库实测环境为 3.12.14）。
- `import fitz` 成功说明 PyMuPDF 已可用；失败也不用慌，安装器会把它装进 `%USERPROFILE%\.dsh\native-forge\pylibs`。

> 如果你的 DSH 版本没有 `dsh-runtimes` 目录，就用系统 Python（见 §3），安装器的探测顺序会自动兜底。

---

## 3. Python 3.10+

**版本要求**：3.10 及以上。推荐 **3.12.10** 或 **3.13.16**（均有 Windows 64 位安装包）。

**为什么是 3.10+**：随仓库的 wheel 是 `pymupdf-1.28.0-cp310-abi3-win_amd64.whl`，`cp310-abi3` 表示 Python 3.10 及以上通用。

### 3.1 官方下载

- 下载页：<https://www.python.org/downloads/windows/>
- 3.12.10（3.12 系列最后一个带 Windows 安装包的版本，页面实测）：
  <https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe>
- 3.13.16：<https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe>

### 3.2 国内镜像（Windows 安装包）

- 阿里云（目录里有 `python-3.x.x-amd64.exe`，实测以下两个文件可下载）：
  - <https://mirrors.aliyun.com/python-release/windows/python-3.12.10-amd64.exe>
  - <https://mirrors.aliyun.com/python-release/windows/python-3.13.16-amd64.exe>
  - 目录页：<https://mirrors.aliyun.com/python-release/windows/>
- 华为云 Python 镜像：<https://mirrors.huaweicloud.com/python/>

  > 实测该镜像按版本分目录（如 `/python/3.12.14/`），内容以**源码包**（`Python-3.x.y.tgz`）为主；要 Windows 安装器请优先用 python.org 或阿里云。

**安装时勾选**：`Add python.exe to PATH`（安装器不依赖 PATH，但手工排障时方便）。

**装完怎么验证**：

```powershell
python -V
python -c "import sys; print(sys.executable)"
```

输出应为 `Python 3.10.x` 以上与一个真实存在的 `python.exe` 路径。

---

## 4. TeX Live（XeLaTeX + ctex + 中文字体）

这是**唯一一个体积大、必须自装**的依赖：最终 PDF 由 XeLaTeX 编译，中文排版靠 `ctex`/`elegantbook`，字体至少要有 Fandol 或一套中文字体。

**现状（2026-10 核实）**：TeX Live 2026 于 2026-03-01 发布；完整 ISO 约 **6.3 GiB**。

### 4.1 方式 A：完整 ISO（推荐，离线可复现）

| 镜像 | ISO 目录 | 说明 |
|---|---|---|
| 清华 TUNA | <https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/Images/> | 目录内 `texlive2026.iso` / `texlive2026-20260301.iso`，约 6.3 GiB，附带 `.sha512` |
| 中科大 USTC | <https://mirrors.ustc.edu.cn/CTAN/systems/texlive/Images/> | 同上，实测目录可访问 |
| 阿里云 | <https://mirrors.aliyun.com/CTAN/systems/texlive/Images/> | 目录存在；该站页面有「公网 ISO 镜像暂停下载」提示（2026-10 观察），以实际页面为准 |

安装：Windows 上双击挂载 ISO，运行根目录的 `install-tl-windows.bat`，选择 **scheme-full**。  
ISO 安装完后如需更新宏包，可切换仓库：

```powershell
tlmgr option repository https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet
```

### 4.2 方式 B：在线安装器（体积小，但受网络影响）

- 官方说明：<https://www.tug.org/texlive/acquire-netinstall.html>
- `install-tl-windows.exe`（约 20 MB）：
  - <https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/install-tl-windows.exe>
  - <https://mirrors.ustc.edu.cn/CTAN/systems/texlive/tlnet/install-tl-windows.exe>
- `install-tl.zip`（无需运行 exe 时用）：
  <https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/install-tl.zip>
- 安装器里把仓库指向 TUNA 的 `.../systems/texlive/tlnet`，可显著加速。

> 镜像站对脚本/HEAD 请求可能返回 403 或限流；浏览器里能打开就说明镜像可用，下次再试或换一个镜像即可。

### 4.3 宏包：full 还是最小集合？

- **推荐 `scheme-full`**：本工作流会用到 `ctex`、`xeCJK`、`fandol`、`amsmath`、`booktabs`、`longtable`、`tabularx`、`tikz`、`pgfplots`、`chemfig`、`geometry`、`fancyhdr` 等；full 最省心。
- 若要精简：至少安装中文与 XeTeX 相关集合（`collection-langchinese`、`collection-xetex`）及上述常用宏包。
  **精简安装未在本仓库实测**，缺宏包时编译日志会报 `File 'xxx.sty' not found`，按报错补装即可。

> 模板 `elegantbook.cls` 与 `nativeforge.sty` **随引擎自带**（`engine/native-forge/templates/`），不需要额外装 ElegantBook。

### 4.4 中文字体

**方案 1：Fandol（TeX Live 自带，最省事）**

TeX Live 的 `fandol` 包内含宋/黑/楷/仿宋及粗体，CTAN 目录实测可访问：
<https://mirrors.tuna.tsinghua.edu.cn/CTAN/fonts/fandol/>

**方案 2：Noto CJK / 思源（更完整，适合正式出版）**

- GitHub Releases：<https://github.com/notofonts/noto-cjk/releases>
  - 宋体：`Serif2.003` → 简体中文包 `09_NotoSerifCJKsc.zip`（约 139 MB）
  - 黑体：`Sans2.004` → 简体中文包 `18_NotoSansSC.zip`（约 50 MB）
- 思源宋体/黑体与 Noto CJK 同源（Adobe Source Han 系列），按各发行版说明安装即可。
- Windows 已自带宋体/黑体/楷体（SimSun/SimHei/KaiTi），临时验证可用；正式交付建议显式指定字体，避免不同机器字面不一致。

**装完怎么验证**：

```powershell
# 1) xelatex 能否解析
xelatex --version

# 2) Fandol 是否随 TeX Live 安装（应输出 texlive 下的 FandolSong-Regular.otf 路径）
kpsewhich FandolSong-Regular.otf

# 3) 最小中文编译（在任意空目录）
@'
\documentclass[UTF8]{ctexart}
\begin{document}
原生中文排版测试：公式 $E=mc^2$，汉字“永”。
\end{document}
'@ | Set-Content -Path .\zh-test.tex -Encoding UTF8
xelatex -interaction=nonstopmode zh-test.tex
```

`zh-test.pdf` 生成且日志无 `Missing character` 即字体可用。

---

## 5. PyMuPDF（随仓库自带）

**随仓库文件**：`wheels/pymupdf-1.28.0-cp310-abi3-win_amd64.whl`（Windows x64，Python 3.10+）。
`install.ps1` 会优先用 `--no-index` 离线安装到 `%USERPROFILE%\.dsh\native-forge\pylibs`；离线失败才联网 `pip install "pymupdf>=1.24"`。

**手工安装（Windows）**：

```powershell
$PY = '<带 pip 的 python.exe>'
$PACK = '<解压后的仓库目录>'
$NF = "$env:USERPROFILE\.dsh\native-forge"
& $PY -m pip install --no-index --find-links "$PACK\wheels" --target "$NF\pylibs" pymupdf==1.28.0
```

**联网安装（国内镜像）**：

```powershell
& $PY -m pip install --target "$NF\pylibs" pymupdf -i https://pypi.tuna.tsinghua.edu.cn/simple
# 或
& $PY -m pip install --target "$NF\pylibs" pymupdf -i https://mirrors.aliyun.com/pypi/simple/
```

**注意版本**：

- 随仓库锁定 **1.28.0**，与引擎实测环境一致。PyPI 当前最新已到 2.x（2026-10 页面显示 `pymupdf 2.0`，要求 Python ≥3.11）；**不建议在生产项目里随手升级主版本**，引擎按 1.28.0 验证。
- 镜像目录（浏览器可访问；脚本/HEAD 请求可能被 403 限流）：
  - <https://pypi.tuna.tsinghua.edu.cn/simple/pymupdf/>
  - <https://mirrors.aliyun.com/pypi/simple/pymupdf/>
  - <https://mirrors.ustc.edu.cn/pypi/simple/pymupdf/>
- 官方项目页：<https://pypi.org/project/PyMuPDF/>

**装完怎么验证**：

```powershell
# 引擎自检（推荐）
& "$env:USERPROFILE\.dsh\native-forge\nf.cmd" doctor
# 期望：pymupdf.available = true，version = 1.28.0

# 或直接导入
$env:PYTHONPATH = "$env:USERPROFILE\.dsh\native-forge\pylibs;$env:PYTHONPATH"
& $PY -c "import fitz; print(fitz.__doc__)"
```

> 许可证提醒：PyMuPDF 是 **AGPL-3.0 或 Artifex 商业许可**双许可。随仓库分发的是原样 wheel，详见 [NOTICE.md](../NOTICE.md) 与 `LICENSES/`。

---

## 6. DeepSeek API key（可选）

只在你要用 `deepseek-claude-subagent` 把大批量、机械性的翻译/TeX 转写外包给 DeepSeek 时才需要。

- 入口：<https://platform.deepseek.com/>（实测 200；登录后在 API keys 页面创建，具体菜单以站点当前界面为准）
- 不需要 key 也能跑完整条主流程：把起草交给 DSH 会话里的模型，只是 token 消耗与并行方式不同。

**装完怎么验证**：在 DSH 里发一个使用 `deepseek-claude-subagent` 的小任务，能正常返回即通；报鉴权错误时回到平台确认 key、额度与配置位置。

---

## 7. LibreOffice（可选，DSH 自带）

本工作流的主线是 **PDF → 原生 TeX → PDF**，不需要 LibreOffice。它只在两种情况下出现：

- 需要预览/转换 `.pptx`、`.docx` 等 Office 交付物（走 DSH 的 `office-files` / `office-pptx` 技能）；
- 需要把 Office 文件导出 PDF 做参考。

**做法**：用 DSH 随包自带的那套，不要另装，避免版本与路径冲突。  
若你在别的场景确实需要独立版本：<https://www.libreoffice.org/download/download-libreoffice/>（2026-10 页面显示稳定版 26.8.1）。

---

## 8. Poppler（可选，第二渲染器）

`pdftoppm` 用于视觉复核时做**独立第二渲染器**交叉核对。未安装时 `render_review_sheets.py` 会跳过 Poppler 分支并如实记录，不会伪造第二渲染器结果。

Windows 可通过系统包管理器或第三方 Windows 构建获取（包名以你本机可用源为准；本仓库未固定某个 Poppler 发行包）。安装后：

```powershell
pdftoppm -v
```

---

## 9. 一键核对清单

安装完成后逐条跑，全部符合再开工：

| # | 检查 | 通过标准 |
|---|---|---|
| 1 | `Test-Path "$env:USERPROFILE\.dsh\skills\native-textbook\SKILL.md"` | `True` |
| 2 | `& "$env:USERPROFILE\.dsh\native-forge\nf.cmd" doctor` | `ok:true`、`pymupdf.available:true`、`templates.ok:true`、`xelatex.found:true` |
| 3 | `xelatex --version` | 输出版本号 |
| 4 | `kpsewhich FandolSong-Regular.otf` | 输出 texlive 路径 |
| 5 | `python verify_pack.py`（Windows 可用 `.\verify-pack.ps1`） | 退出码 0（在仓库根目录） |

`doctor` 里 `memory.ok:false` 只表示当前空闲内存不足 1 GiB，属于工作流的**内存门禁**，不是安装失败；处理见 [FAQ.md](FAQ.md#内存门禁)。
