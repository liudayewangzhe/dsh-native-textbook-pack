"""删掉"纯图题"figure block（同页同号图已有带资产的真图 block）。

p0254 的情形：三个并排子图各自是有资产的 figure block，另有一个 number 相同、
source_id 指向图题对象的 figure block（b004），它没有资产 → 引擎报
`asset None is not declared in assets.json`。图题已由真图 block 的 caption 输出，
这个多余块应删掉（其证据对象列入 excluded_objects）。

判据：同页存在 number 相同的、**有 asset** 的 figure block 时，把无 asset 的同号 figure
block 删掉。

Run:  python D:\\nf-stage\\fix_caption_only_figures.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    figs = [b for b in data.get("blocks", [])
            if b.get("kind") in ("figure", "figure_native") and b.get("asset")]
    have_num = {b.get("number") for b in figs}
    drop = [b for b in data.get("blocks", [])
            if b.get("kind") in ("figure", "figure_native")
            and not b.get("asset") and b.get("number") in have_num]
    if not drop:
        continue
    excl = data.setdefault("excluded_objects", [])
    ids = {e.get("id") for e in excl}
    by_id = {o["id"]: o for o in data.get("objects", [])}
    for b in drop:
        for sid in b.get("source_ids") or []:
            if sid in ids:
                continue
            obj = by_id.get(sid, {})
            excl.append({"id": sid, "page": obj.get("page"), "kind": obj.get("kind") or "figure",
                         "text": (obj.get("text") or "图题（已由同一图号的 caption 输出）")[:60],
                         "reason": "图题已由同一图号真图 block 的 caption 输出，避免重复"})
            ids.add(sid)
    data["blocks"] = [b for b in data["blocks"] if b not in drop]
    data["notes"] = (data.get("notes", "") +
                     f"\n[监工修补 2026-10-15] 删除 {len(drop)} 个纯图题 figure block"
                     "（同号图已有带资产的 block），证据对象转 excluded_objects。")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixed.append(f"{path.name}: {len(drop)}")

print(f"{len(fixed)} shard(s) fixed")
print("\n".join(fixed[:10]))
