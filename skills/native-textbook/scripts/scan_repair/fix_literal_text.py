"""恢复被 fix_literal_blocks.py 冲掉的 code 块正文，并修正该脚本的兜底逻辑。

事故：`fix_literal_blocks.py` 在 code 块的 text 为空时，用 `"\\n".join(source_ids)`
兜底，等于把正文替换成 `p0170-s009` 这样的占位串。p0170 的算法 6.1 二分法清单
（6 个 code 块中唯一一个）因此丢失正文。

本脚本：对 text 形如纯 `pNNNN-sNNN` 占位串的 code/console 块，用其 source object
的 text 还原；若 object text 也没有，则保留占位串并在 notes 标记待补。

Run:  python D:\\nf-stage\\fix_literal_text.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
PLACEHOLDER = re.compile(r"^\s*p\d{4}-s\d{3}(\s*\n\s*p\d{4}-s\d{3})*\s*$")
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    objs = {o["id"]: o for o in data.get("objects", [])}
    n = 0
    for b in data.get("blocks", []):
        if b.get("kind") not in ("code", "console"):
            continue
        text = b.get("text") or ""
        if not PLACEHOLDER.match(text):
            continue
        parts = []
        for sid in b.get("source_ids") or []:
            t = (objs.get(sid, {}).get("text") or "").strip()
            if t and not PLACEHOLDER.match(t):
                parts.append(t)
        if parts:
            b["text"] = "\n".join(parts)
            n += 1
        else:
            data["notes"] = (data.get("notes", "") +
                             f"\n[监工修补 2026-10-15] code 块 {b['id']} 的正文曾被占位串替换，"
                             "源 object 的 text 亦为空，待重新从分带图补录。")
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 从 source object 的 text 还原了被占位串替换的 code 块正文。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print("\n".join(fixed) if fixed else "no placeholder-literal blocks")
