"""删除 p0118 页首重复登记的三项（(5.2.20)(5.2.21) 与「它的逆为」）。

依据：p0117 的重做者实测 p0118 页首是「病态矩阵在求解线性方程组时会放大数值误差……
比如考虑」+(5.2.25)，并没有 (5.2.20)(5.2.21)；p0117 已按原书完整转写这三项。
两页并存会让成品出现两个 (5.2.20)(5.2.21)（引擎报 equation_tags duplicates）。

Run:  python D:\\nf-stage\\fix_p118_dup.py
"""
import json
import re
from pathlib import Path

path = Path(r"D:\native-forge-work\inbox\p0118.json")
data = json.loads(path.read_text(encoding="utf-8"))
DROP_TAGS = {"5.2.20", "5.2.21"}

drop_ids = set()
for b in data["blocks"]:
    if b.get("kind") != "equation":
        continue
    tags = {t.strip().strip("()") for t in re.findall(r"\\tag\{([^}]*)\}", b.get("tex") or "")}
    if tags & DROP_TAGS:
        drop_ids.add(b["id"])
        for sid in b["source_ids"]:
            drop_ids.add(sid)

before_blocks = len(data["blocks"])
data["blocks"] = [b for b in data["blocks"] if b["id"] not in drop_ids]
data["objects"] = [o for o in data["objects"] if o["id"] not in drop_ids]
data["excluded_objects"] = [e for e in (data.get("excluded_objects") or [])
                            if (e.get("id") or "") not in drop_ids]
data["notes"] = (data.get("notes", "") +
                 "\n[监工修补 2026-10-15] 删除页首重复登记的 (5.2.20)(5.2.21) 与「它的逆为」"
                 "（实测本页页首无此内容，三项已在 p0117 完整转写），避免编号重复。")
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"p0118: blocks {before_blocks} -> {len(data['blocks'])}, dropped ids {sorted(drop_ids)}")
