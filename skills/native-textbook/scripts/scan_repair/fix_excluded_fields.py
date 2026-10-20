"""给 excluded_objects 条目补齐引擎要求的字段（id/page/kind/text）。

引擎对 source_inventory 的每个条目（含被排除的）都要求 id/page/kind/text；
worker 写的 excluded 条目常只有 id + reason，于是 build 报
"source_inventory page NNN: every object needs id/page/kind/text"。

Run:  python D:\\nf-stage\\fix_excluded_fields.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    excluded = data.get("excluded_objects") or []
    if not excluded:
        continue
    by_id = {o["id"]: o for o in data.get("objects", [])}
    n = 0
    for e in excluded:
        oid = e.get("id") or e.get("source_id")
        if oid:
            e.setdefault("id", oid)
            src = by_id.get(oid, {})
            e.setdefault("page", src.get("page"))
            e.setdefault("kind", src.get("kind") or "paragraph")
            e.setdefault("text", src.get("text") or e.get("reason") or e.get("category") or "已排除项")
        for key in ("id", "page", "kind", "text"):
            if not str(e.get(key) or "").strip():
                e[key] = {"page": 1, "kind": "paragraph", "text": "已排除项", "id": "unknown"}[key]
        n += 1
    data["excluded_objects"] = excluded
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixed.append(f"{path.name}: {n}")
print(f"{len(fixed)} shard(s) updated" if fixed else "no excluded objects to patch")
