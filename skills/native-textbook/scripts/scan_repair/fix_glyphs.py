"""修掉两类字体缺字形（QA 的 log.missing_character）。

1) `\\mathrm{\\mu m}` —— \\mathrm 把 μ 交给正文字体，而 TeXGyreTermesX 没有 U+1D707。
   改为 `\\mu\\mathrm{m}`：μ 走数学字体，m 保持正体。
2) content 里的裸字符 ⋯（U+22EF）——正文字体无此字形，数学模式里改用 \\cdots。

Run:  python D:\\nf-stage\\fix_glyphs2.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
CONTENT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh\content.json")

SUBS = [
    (r"\mathrm{\mu m}", r"\mu\mathrm{m}"),
    (r"\mathrm{\mu}", r"\mu"),
    ("\u22ef", r"\cdots"),
]

changed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for b in data.get("blocks", []):
        tex = b.get("tex")
        if not isinstance(tex, str):
            continue
        new = tex
        for bad, good in SUBS:
            if bad in new:
                n += new.count(bad)
                new = new.replace(bad, good)
        if new != tex:
            b["tex"] = new
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 字体缺字形处改用等价 LaTeX（\\mu 不再被 \\mathrm 包住）。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(f"{path.name}: {n}")
print("\n".join(changed) if changed else "no glyph substitutions needed in shards")
