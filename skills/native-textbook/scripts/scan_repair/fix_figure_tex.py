"""把自写 \\includegraphics 的块降级为普通 figure（图形宏由引擎生成）。

覆盖两种情况：
  kind=figure        且带 tex        -> 删 tex，交给 make_assets 挂 asset
  kind=figure_native 且 tex 里只有 \\includegraphics -> 降级为 figure 并删 tex
真正的矢量重绘（含 tikzpicture/pgfplots）不动。

Run:  python D:\\nf-stage\\fix_figure_tex2.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
INC = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}")
VECTOR = re.compile(r"\\begin\{(tikzpicture|axis|pgfpicture|groupplot)")

fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for b in data.get("blocks", []):
        tex = b.get("tex")
        if not isinstance(tex, str) or "\\includegraphics" not in tex:
            continue
        if VECTOR.search(tex):
            # a real vector figure that merely embeds a raster too: drop only the include
            b["tex"] = INC.sub("", tex)
            n += 1
            continue
        if b.get("kind") == "figure_native":
            b["kind"] = "figure"
        b.pop("tex", None)
        n += 1
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 自写 \\includegraphics 的块已降级为普通 figure（图形宏由引擎生成）。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print("\n".join(fixed) if fixed else "no includegraphics blocks")
