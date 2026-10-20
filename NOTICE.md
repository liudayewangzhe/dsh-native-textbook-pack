# 第三方组件与许可声明

本仓库的**原创内容**采用 [MIT License](LICENSE)。下列第三方组件保留各自原始许可，其条款优先于 MIT 适用于对应组件。

## 组件清单

| 组件 | 位置 | 许可 | 版权 / 来源 | 许可全文 |
|---|---|---|---|---|
| PyMuPDF 1.28.0（Windows x64 wheel） | `wheels/pymupdf-1.28.0-cp310-abi3-win_amd64.whl` | **AGPL-3.0** 或 Artifex 商业许可（双许可） | Copyright Artifex Software, Inc. · <https://github.com/pymupdf/PyMuPDF> | `LICENSES/AGPL-3.0.txt`；wheel 内 `pymupdf-1.28.0.dist-info/COPYING` |
| zxing-cpp 3.1.1（Windows x64 扩展） | `engine/native-forge/third_party/qr/zxingcpp/` | Apache-2.0 | Copyright ZXing-C++ authors · <https://github.com/zxing-cpp/zxing-cpp> | `engine/native-forge/third_party/qr/zxing_cpp-3.1.1.dist-info/licenses/LICENSE`；`LICENSES/Apache-2.0.txt` |
| ElegantBook 文档类 `elegantbook.cls` | `engine/native-forge/templates/elegantbook.cls` | LPPL-1.3c | Copyright 2013-2022 / 2026- ElegantLaTeX · <https://github.com/ElegantLaTeX/ElegantBook> | <https://www.latex-project.org/lppl/lppl-1-3c/> |
| skill-creator | `skills/skill-creator/` | Apache-2.0 | Copyright Anthropic, PBC | `skills/skill-creator/LICENSE.txt`；`LICENSES/Apache-2.0.txt` |
| humanizer | `skills/humanizer/` | MIT | Copyright (c) 2025 Siqi Chen | `skills/humanizer/LICENSE` |
| humanizer-zh | `skills/humanizer-zh/` | MIT | Copyright (c) 2026 歸藏 | `skills/humanizer-zh/LICENSE` |

## 关于 PyMuPDF（AGPL-3.0）的重要说明

- 本仓库随附的 PyMuPDF wheel 是**原样分发**（未修改），用于离线安装，版权归 Artifex Software, Inc.。
- 该组件以 **GNU Affero GPL v3.0** 分发（或由你自行购买 Artifex 商业许可）。完整条款见 `LICENSES/AGPL-3.0.txt`，上游源码：<https://github.com/pymupdf/PyMuPDF>、<https://github.com/pymupdf/pymupdf>。
- 如果你不能接受 AGPL-3.0，可以：① 不安装随附 wheel，自行执行 `pip install pymupdf`（同受 AGPL 约束）；② 向 Artifex 购买商业许可；③ 不使用 PyMuPDF（引擎读 PDF 的能力会不可用）。
- 引擎调用 PyMuPDF 的源码在 `engine/native-forge/` 中完整提供，符合 AGPL 对源码可得性的要求。

## 未随仓库分发的依赖

以下依赖**不在**本仓库内，需要使用者自行安装，其许可与本仓库无关：

- **TeX Live / XeLaTeX**（LPPL 及其他开源许可）——最终 PDF 编译必需
- **中文字体**：思源宋体/黑体、Noto CJK、Fandol 等（SIL OFL / GPL+字体例外等）——排版必需
- **DeepSeek Harness 桌面版**——技能宿主，本仓库不包含
- **LibreOffice**——仅在 `.pptx` 预览/转换时需要
- **Python 3.10+**（PSF License）

## 会话记录说明

`sessions/` 是作者本机真实会话的脱敏转换记录，保留了当时的绝对路径（如 `C:\Users\...`、`E:\...`）作为历史记录。它们不是配置，也不包含 API 密钥；若你不想公开自己的运行记录，直接删除该目录即可，不影响安装与使用。
