"""`code`/`console` blocks are literal payloads: only id/kind/source_ids/text are allowed.

Workers typed the listing into `tex` as well, which the engine refuses. Keep the raw text
(that is what gets typeset verbatim) and drop the extra field.

Run:  python D:\\nf-stage\\fix_literal_blocks.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
log = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    by_id = {o["id"]: o for o in data.get("objects", [])}
    changed = 0
    for block in data.get("blocks", []):
        if block.get("kind") not in ("code", "console"):
            continue
        # literal blocks accept only id / kind / source_ids / text
        for key in [k for k in block if k not in ("id", "kind", "source_ids", "text")]:
            block.pop(key)
            changed += 1
        if not str(block.get("text", "")).strip():
            # 正文为空时，从 source object 的 text 还原——绝不能拿 source_ids 当兜底，
            # 那会把正文换成 "p0170-s009" 这样的占位串（已发生过一次，正文丢失）。
            parts = [(by_id.get(sid, {}).get("text") or "").strip()
                     for sid in block.get("source_ids", [])]
            parts = [p for p in parts if p]
            block["text"] = "\n".join(parts)
    if changed:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-14] code/console 块删除多余的 tex 字段"
                         "（字面文本只由 text 字段承载）。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log.append(f"{path.name}: {changed} literal block(s) cleaned")
print("\n".join(log) if log else "no literal blocks to clean")
