"""把所有分片的 bbox 限制在页内（0–1）并保证 x0<x1、y0<y1。

监工的重标定脚本曾与 worker 并发改写同一文件，留下个别越界框（例如 y1=1.003），
会被引擎的「bbox 必须在页内」判据拒绝。这里做一次全量收敛。

Run:  python D:\\nf-stage\\clamp_bbox.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for obj in data.get("objects", []):
        bbox = obj.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            continue
        x0, y0, x1, y1 = (float(v) for v in bbox)
        nx0, nx1 = max(0.0, min(x0, x1)), min(1.0, max(x0, x1))
        ny0, ny1 = max(0.0, min(y0, y1)), min(1.0, max(y0, y1))
        if nx1 - nx0 < 0.002:
            nx1 = min(1.0, nx0 + 0.002)
        if ny1 - ny0 < 0.002:
            ny1 = min(1.0, ny0 + 0.002)
        new = [round(nx0, 4), round(ny0, 4), round(nx1, 4), round(ny1, 4)]
        if new != [round(float(v), 4) for v in bbox]:
            obj["bbox"] = new
            changed += 1
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {changed} bbox clamped")
print("\n".join(fixed) if fixed else "all bboxes inside the page")
