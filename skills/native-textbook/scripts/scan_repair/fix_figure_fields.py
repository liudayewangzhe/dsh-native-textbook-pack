"""修 figure 的 number/asset 与空 tex 段落三类构建阻塞。

引擎校验：
  - `number must be a label-safe string`：图号/表号会进 \\label，不能含括号、空格、点以外符号。
    worker 常写 "11.4.1(a)"、"图 11.4.1" 之类 → 规范化为 "11.4.1"（子图标记移到 caption）。
  - `asset None is not declared in assets.json`：figure block 声明了编号却没有资产 → 若该对象
    其实是框线/装饰（无 caption 或 caption 里写明"框线/装饰"），转为 excluded；否则保留并标记待裁。
  - `paragraph requires non-empty tex`：段落 tex 为空 → 从证据对象 text 还原。

Run:  python D:\\nf-stage\\fix_figure_fields.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
LABEL_OK = re.compile(r"^[A-Za-z0-9.\-:]+$")
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    log = []
    by_id = {o["id"]: o for o in data.get("objects", [])}

    # --- 1) figure/table 的 number 规范化 ---
    for b in data.get("blocks", []):
        if b.get("kind") not in ("figure", "figure_native", "table"):
            continue
        num = b.get("number")
        if isinstance(num, str) and num and not LABEL_OK.match(num):
            clean = re.match(r"[^（(]*", num)
            newnum = (clean.group(0) if clean else "").strip().strip("图 表").strip()
            newnum = re.sub(r"[^A-Za-z0-9.\-:]", "", newnum)
            if newnum:
                b["number"] = newnum
                log.append(f"{b['id']} number {num!r}->{newnum!r}")

    # --- 2) 段落空 tex 还原 ---
    for b in data.get("blocks", []):
        if b.get("kind") in ("paragraph", "heading", "section", "subsection", "chapter"):
            if not (b.get("tex") or "").strip():
                parts = [(by_id.get(s, {}).get("text") or "").strip() for s in b.get("source_ids") or []]
                parts = [p for p in parts if p]
                if parts:
                    b["tex"] = " ".join(parts)
                    log.append(f"{b['id']} 从证据对象还原 tex")

    # --- 3) 无资产的 figure block：装饰转 excluded，真图保留待裁 ---
    excl = data.setdefault("excluded_objects", [])
    have = {e.get("id") for e in excl}
    keep = []
    for b in data.get("blocks", []):
        if b.get("kind") not in ("figure", "figure_native") or b.get("asset"):
            keep.append(b)
            continue
        cap = (b.get("caption") or "").strip()
        text_join = " ".join((by_id.get(s, {}).get("text") or "") for s in b.get("source_ids") or [])
        looks_decor = (not cap) or any(k in (cap + text_join) for k in ("框线", "边框", "装饰", "外框"))
        if looks_decor:
            for sid in b.get("source_ids") or []:
                if sid in have:
                    continue
                obj = by_id.get(sid, {})
                excl.append({"id": sid, "page": obj.get("page"),
                             "kind": obj.get("kind") or "figure",
                             "text": (obj.get("text") or "版式装饰")[:60],
                             "reason": "框线/装饰，按项目约定只作证据对象并排除"})
                have.add(sid)
            log.append(f"{b['id']} 无资产的 figure 判为装饰 → excluded")
            continue
        keep.append(b)
    data["blocks"] = keep

    if log:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 规范化 figure number / 还原空 tex / 装饰图块转 excluded：\n  - "
                         + "\n  - ".join(log))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {len(log)}")

print(f"{len(fixed)} shard(s) fixed")
print("\n".join(fixed[:12]))
