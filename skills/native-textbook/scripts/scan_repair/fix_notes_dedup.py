"""去重分片 notes 里重复的「[监工修补 …]」行，并让修补行保持唯一。

监工的规范化脚本每轮都会 append 一条说明，多轮之后同一句会累积好几遍
（实测 p0216 累到 6 条）。这里：
  - 把 notes 按行拆分，保留首次出现的 [监工修补 …] 行，丢弃完全重复的行；
  - 不同内容的修补行保留（它们是不同的修复记录）。

Run:  python D:\\nf-stage\\fix_notes_dedup.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
MARK = "[监工修补"
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    notes = data.get("notes") or ""
    if MARK not in notes:
        continue
    lines = [l.rstrip() for l in notes.splitlines()]
    seen, out, dropped = set(), [], 0
    for line in lines:
        key = line.strip()
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(line)
    if dropped:
        data["notes"] = "\n".join(out).rstrip() + "\n"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: dropped {dropped} duplicate note line(s)")
print(f"{len(fixed)} shard(s) cleaned")
print("\n".join(fixed[:10]))
