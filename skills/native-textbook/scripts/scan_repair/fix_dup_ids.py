"""消除分片内重复的 object / block id。

引擎拒绝重复证据 id（`source_inventory duplicate evidence id p0115-s018`）。
worker 偶尔会把同一个 id 写两次（多为一处笔误），保留先出现者，后者重命名并把
其 block 的 source_ids 一并改指到新 id，避免引用悬空。

Run:  python D:\\nf-stage\\fix_dup_ids.py
"""
import json
from collections import Counter
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    objs = data.get("objects") or []
    ids = [o.get("id") for o in objs]
    dups = {i for i, c in Counter(ids).items() if c > 1}
    if not dups:
        continue
    renames = {}
    seen = set()
    for o in objs:
        oid = o.get("id")
        if oid not in dups:
            seen.add(oid)
            continue
        if oid not in seen:
            seen.add(oid)          # keep the first occurrence as-is
            continue
        n = 1
        while f"{oid}x{n}" in ids:
            n += 1
        new_id = f"{oid}x{n}"
        renames[oid] = renames.get(oid) or []
        renames[oid].append(new_id)
        o["id"] = new_id
        ids.append(new_id)
    # rewire blocks: the k-th reference to a duplicated id points at the k-th copy
    used = Counter()
    for b in data.get("blocks", []):
        new_sids = []
        for sid in b.get("source_ids") or []:
            if sid in renames:
                used[sid] += 1
                idx = used[sid] - 1
                if idx < len(renames[sid]):
                    new_sids.append(renames[sid][idx])
                    continue
            new_sids.append(sid)
        b["source_ids"] = new_sids
    data["notes"] = (data.get("notes", "") +
                     "\n[监工修补 2026-10-15] 重复的 evidence id 已重命名并同步 block 引用。")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixed.append(f"{path.name}: {sorted(dups)}")

print("\n".join(fixed) if fixed else "no duplicate ids")
