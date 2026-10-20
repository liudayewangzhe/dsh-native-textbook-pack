"""把编译日志里的 Overfull/Missing 行号映射回生成它的源块。

用法：python D:\\nf-stage\\locate_overfull.py
输出每个溢出点对应的 "% Source block: pXXXX-bYYY" 及其 tex 片段。
"""
import json
import re
from pathlib import Path

PROJ = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
INBOX = Path(r"D:\native-forge-work\inbox")

tex = (PROJ / "build" / "main.tex").read_text(encoding="utf-8").splitlines()
log = (PROJ / "build" / "main.log").read_text(encoding="utf-8", errors="replace")

SRC = re.compile(r"% Source block: (p\d{4}-b\d{3})")
anchor = {}
for i, line in enumerate(tex):
    m = SRC.search(line)
    if m:
        anchor[i] = m.group(1)

points = []
for m in re.finditer(r"Overfull \\hbox \(([\d.]+)pt too wide\)[^\n]*?(?:detected at line (\d+)|at lines (\d+)--(\d+))", log):
    width = float(m.group(1))
    line = int(m.group(2) or m.group(3))
    points.append((line, width))

print(f"{len(points)} overfull point(s)")
for line, width in sorted(points):
    blk = None
    for i in range(min(line - 1, len(tex) - 1), -1, -1):
        if i in anchor:
            blk = anchor[i]
            break
    print(f"\n--- overfull {width:.1f}pt at main.tex:{line} -> {blk} ---")
    if blk:
        pg = int(blk[1:5])
        path = INBOX / f"p{pg:04d}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        b = next((x for x in data["blocks"] if x["id"] == blk), None)
        if b:
            print((b.get("tex") or b.get("text") or "")[:300])
