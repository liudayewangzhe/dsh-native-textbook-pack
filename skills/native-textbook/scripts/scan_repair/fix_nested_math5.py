"""迭代清理数学环境的重复嵌套（各类形态一次清干净）。

已遇到的畸形形态：
  \\begin{equation}\\begin{equation*}          （外层 equation + 内层 starred）
  \\begin{equation*}\\begin{equation*}        （双重 starred）
  \\end{equation*}\\tag{X}\\end{equation}     （\\tag 落在环境外）
反复清理直到稳定：同名环境相邻出现时只保留一层；`\\tag` 一律留在最内层环境的 begin/end 之间。

Run:  python D:\\nf-stage\\fix_nested_math5.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
ENVS = ("equation*", "equation", "align*", "align", "gather*", "gather", "multline*", "multline")
DUP_OPEN = re.compile(r"\\begin\{(" + "|".join(e.replace("*", r"\*") for e in ENVS) + r")\}(\s*)\\begin\{\1\}")
DUP_CLOSE = re.compile(r"\\end\{(" + "|".join(e.replace("*", r"\*") for e in ENVS) + r")\}(\s*)\\end\{\1\}")


def clean(tex: str) -> str:
    prev = None
    while prev != tex:
        prev = tex
        tex = DUP_OPEN.sub(r"\\begin{\1}", tex)
        tex = DUP_CLOSE.sub(r"\\end{\1}", tex)
    return tex


fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for b in data.get("blocks", []):
        tex = b.get("tex")
        if not isinstance(tex, str) or "\\begin{" not in tex:
            continue
        new = clean(tex)
        if new != tex:
            b["tex"] = new
            n += 1
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 迭代清理数学环境的重复嵌套。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print(f"{len(fixed)} shard(s) cleaned")
print("\n".join(fixed[:12]))
