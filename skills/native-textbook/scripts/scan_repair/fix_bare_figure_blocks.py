"""把"裸 figure block"（无 asset、无 caption、未在 figures[] 声明）转为 excluded_objects。

引擎要求每个 kind=figure 的 block 都要有资产与图题（编号图必须有非空 caption）。
worker 有时把**框线/装饰**登记成 figure block 却没在 figures[] 里声明，于是构建报
`asset None is not declared in assets.json` / `caption must be a string`。

判据（三者同时成立才算裸 figure）：
  - block.kind in (figure, figure_native)
  - 没有 asset（或 asset 为空）
  - 没有非空 caption
  - 其 source_id 不在本页 figures[] 的 source_id 里

处理：删掉该 block，把它的证据对象补进 excluded_objects（说明为版式装饰）。

Run:  python D:\\nf-stage\\fix_bare_figure_blocks.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    declared = set()
    for f in data.get("figures") or []:
        sid = f.get("source_id") or f.get("id") or f.get("source_ids")
        if isinstance(sid, str):
            declared.add(sid)
        elif isinstance(sid, list):
            declared.update(sid)

    keep, dropped = [], []
    for b in data.get("blocks", []):
        if b.get("kind") not in ("figure", "figure_native"):
            keep.append(b)
            continue
        has_asset = bool(b.get("asset"))
        has_caption = bool((b.get("caption") or "").strip())
        refs = set(b.get("source_ids") or [])
        if not has_asset and not has_caption and not (refs & declared):
            dropped.append(b)
        else:
            keep.append(b)

    if not dropped:
        continue
    excluded = data.setdefault("excluded_objects", [])
    have = {e.get("id") for e in excluded}
    for b in dropped:
        for sid in b.get("source_ids") or []:
            if sid in have:
                continue
            obj = next((o for o in data.get("objects", []) if o["id"] == sid), {})
            excluded.append({"id": sid, "page": obj.get("page"),
                             "kind": obj.get("kind") or "figure",
                             "text": (obj.get("text") or "版式装饰（框线/边框）")[:60],
                             "reason": "算法框/习题框的框线装饰，按项目约定只作证据对象并排除"})
            have.add(sid)
    data["blocks"] = keep
    data["notes"] = (data.get("notes", "") +
                     f"\n[监工修补 2026-10-15] 删除 {len(dropped)} 个裸 figure block"
                     "（无 asset/caption、未在 figures[] 声明，属框线装饰），证据对象改列 excluded_objects。")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixed.append(f"{path.name}: {len(dropped)}")

print(f"{len(fixed)} shard(s) fixed")
print("\n".join(fixed[:12]))
