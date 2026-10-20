# 原生中文教材转换 · 命令速抄（PowerShell）
#
# 用法：改上面三个变量，然后把需要的小节复制到 DSH 会话里（或直接在终端跑）。
# 真实会话里的用法见 ..\sessions\ ；参数细节见 ..\playbook\03-命令速查.md

# ---- 只需要改这里 -------------------------------------------------
$NF      = "$env:USERPROFILE\.dsh\native-forge\nf.cmd"   # 引擎入口（install.ps1 生成）
$SOURCE  = "D:\书\原稿.pdf"                              # 原稿绝对路径（只读）
$PROJ    = "D:\work\mybook"                              # 项目目录（可写）
$TITLE   = "我的教材"
# -------------------------------------------------------------------

# 0) 环境自检：PyMuPDF / 模板 / XeLaTeX / 内存
& $NF doctor

# 1) 建项目：只从原稿切出指定物理页码，生成证据包 packet\pages\pNNNN.{json,png}
& $NF prepare --source $SOURCE --pages 24-32 --project $PROJ --title $TITLE

# 2) 抽图：按原稿页坐标抽矢量资产（先看抽出来的图，再登记）
& $NF asset --project $PROJ --page 24 --bbox 263 68 472 229 --name f12

# 3) 重绘：简单图用 TikZ/PGFPlots/chemfig 生成可编辑矢量（规范文件由 agent 写）
& $NF redraw --project $PROJ --spec "$PROJ\specs\f12.json" --name f12-native

# 4) 编译 + QA（正文/公式/表格必须是原生 TeX；位图要有来源依据）
& $NF build --project $PROJ
& $NF qa    --project $PROJ

# 5) 排版几何检查（越纸 / 压字 / 行距 / 版心留白 / 行末填充率）
python "$env:USERPROFILE\.dsh\skills\native-textbook\scripts\check_typography.py" `
       --pdf "$PROJ\build\main.pdf" --mode book --report "$PROJ\qa\typo.md"

# 6) 字号/行距回抽比对（源 vs 交付；报 ≈0.75 就是 72/96 误缩）
#    注意是 --source / --target，不是 --pdf
python "$env:USERPROFILE\.dsh\skills\native-textbook\scripts\compare_typography.py" `
       --source $SOURCE --target "$PROJ\build\main.pdf" --mode book --report "$PROJ\qa\compare.md"

# 7) 视觉审核材料（接触表 + 高倍页图，绑定当前 PDF 哈希）
python "$env:USERPROFILE\.dsh\skills\native-textbook\scripts\render_review_sheets.py" `
       --pdf "$PROJ\build\main.pdf" --out "$PROJ\qa\review" `
       --hi-res-pages "1,2,3" --hi-res-zoom 3 --poppler-dpi 144

# 8) slide 分支的三项检查（保留 PPT 风味的课件 PDF）
# python "...\scripts\check_slide_pdf.py"     --pdf main.pdf --config slide-check.json --out qa/slide-check.json
# python "...\scripts\check_typography.py"    --pdf main.pdf --mode slide --report qa/typo.md
# python "...\scripts\check_slide_spacing.py" --tex main.tex --report qa/spacing.md

# 9) 发布（有 unresolved / 未覆盖来源 / 未做视觉审核 / 指纹过期都会被拦）
& $NF release --project $PROJ

# ---- 扫描件（无文字层）专用：见 references\scanned-source-repair.md ----
# python "...\scripts\scan_repair\detect_partial_pages.py"   # 找"只读了半页"的页
# python "...\scripts\scan_repair\check_numbering.py"        # 编号缺口
# python "...\scripts\scan_repair\make_assets.py"            # 按乱序 bbox 造资产
# 这些脚本写于 cpp-zh 项目，里面的 INBOX / PROJECT 常量需要改成你自己的路径

# ---- 低内存时（引擎自带、只能放宽到 512 MiB–1 GiB）----
# $env:NF_RAM_FLOOR_MIB = 768
# & $NF doctor
