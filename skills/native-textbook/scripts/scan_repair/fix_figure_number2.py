"""修 figures[]/tables[] 里的 number，并给"只有图题、没有资产"的图块绑定子图资产。

构建报的两类阻塞：
  1. `number must be a label-safe string` —— 图号在 `figures[]` 里写成了 `11.4.1(a)`，
     而 merge 以 figures[] 为准，所以只改 block.number 无效。规范化为 `11.4.1`，
     并把子图标记并进 caption。
  2. `asset None is not declared in assets.json` —— 有的页把**三个并排子图**登记在
     figures[]（各有 asset），而 figure block 只引用了图题对象，于是 block 没有资产。
     处理：若同页 figures[] 有同号的条目，把第一个的 asset/number 绑给该 block。

Run:  python D:\\nf-stage\\fix_figure_number2.py
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

    # --- 1) 规范化 figures[] / tables[] 的 number（并把子图标记并入 caption）---
    for coll in ("figures", "tables"):
        for item in data.get(coll) or []:
            num = item.get("number")
            if not isinstance(num, str) or not num or LABEL_OK.match(num):
                continue
            sub = re.search(r"[（(]([a-zA-Z0-9]+)[)）]", num)
            base = re.sub(r"[^0-9.]", "", re.match(r"[0-9.]+", num).group(0) if re.match(r"[0-9.]+", num) else "")
            if not base:
                continue
            item["number"] = base
            if sub:
                cap = item.get("caption") or ""
                tag = f"（{sub.group(1)}）"
                if tag not in cap:
                    item["caption"] = tag + cap
            log.append(f"{coll} number {num!r}->{base!r}")

    # --- 2) block 的 number 同步 ---
    for b in data.get("blocks", []):
        if b.get("kind") not in ("figure", "figure_native", "table"):
            continue
        num = b.get("number")
        if isinstance(num, str) and num and not LABEL_OK.match(num):
            m = re.match(r"[0-9][0-9.]*", num)
            if m:
                b["number"] = m.group(0).rstrip(".")
                log.append(f"{b['id']} number->{b['number']!r}")

    # --- 3) 无资产的 figure block 绑定同号子图资产 ---
    figs = data.get("figures") or []
    for b in data.get("blocks", []):
        if b.get("kind") not in ("figure", "figure_native") or b.get("asset"):
            continue
        same = [f for f in figs if f.get("number") == b.get("number") and f.get("asset")]
        if same:
            b["asset"] = same[0]["asset"]
            b.setdefault("caption", same[0].get("caption") or "")
            b.setdefault("number", same[0].get("number"))
            b.setdefault("numbered", True)
            log.append(f"{b['id']} 绑定资产 {same[0]['asset']}")

    if log:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 规范 figures/tables 的 number 并绑定子图资产：\n  - "
                         + "\n  - ".join(log))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {len(log)}")

print(f"{len(fixed)} shard(s) fixed")
print("\n".join(fixed[:14]))
