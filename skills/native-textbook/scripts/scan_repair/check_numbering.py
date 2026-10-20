"""Check equation / figure / table numbering continuity against the printed sequence.

The printed book numbers formulas as 章.节.序号 (e.g. 2.1.15) and figures/tables as
章.节.序号 as well. A gap in the sequence inside one section is either a real source
skip (which must be kept and listed) or a transcription miss. This report lists the
sequences so the supervisor can tell the two apart by looking at the source pages.

Run:  python D:\\nf-stage\\check_numbering.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
TAG_RE = re.compile(r"\\tag\{([^}]*)\}")
NUM_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

content = json.loads((PROJECT / "content.json").read_text(encoding="utf-8"))
eq = defaultdict(list)
figs = defaultdict(list)
tabs = defaultdict(list)

for block in content["blocks"]:
    kind, tex = block.get("kind"), block.get("tex", "") or ""
    if kind == "equation":
        for tag in TAG_RE.findall(tex):
            m = NUM_RE.match(tag.strip())
            if m:
                eq[(int(m.group(1)), int(m.group(2)))].append((int(m.group(3)), block["id"]))
            else:
                eq[("other", tag.strip())].append((0, block["id"]))
    elif kind in ("figure", "figure_native"):
        num = block.get("number") or block.get("figure_number")
        if num:
            m = NUM_RE.match(str(num))
            if m:
                figs[(int(m.group(1)), int(m.group(2)))].append(int(m.group(3)))

for block in content["blocks"]:
    if block.get("kind") == "table":
        m = re.search(r"\\renewcommand\{\\thetable\}\{([^}]*)\}", block.get("tex", ""))
        if m:
            mm = NUM_RE.match(m.group(1))
            if mm:
                tabs[(int(mm.group(1)), int(mm.group(2)))].append(int(mm.group(3)))

report = {"equations": [], "figures": [], "tables": []}
for key in sorted(eq, key=str):
    seq = sorted(eq[key])
    nums = [n for n, _ in seq]
    gaps = [n for n in range(1, max(nums) + 1) if n not in nums] if nums else []
    report["equations"].append({"section": f"{key[0]}.{key[1]}", "count": len(nums),
                                "range": [min(nums), max(nums)] if nums else None,
                                "missing": gaps,
                                "sources": {str(n): b for n, b in seq}})
for key in sorted(figs):
    report["figures"].append({"section": f"{key[0]}.{key[1]}", "numbers": sorted(figs[key])})
for key in sorted(tabs):
    report["tables"].append({"section": f"{key[0]}.{key[1]}", "numbers": sorted(tabs[key])})

print(json.dumps(report, ensure_ascii=False, indent=1))
(Path(r"D:\native-forge-work\inbox") / "numbering.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
