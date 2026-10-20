"""把非法 kind 的 evidence object 归一化到合同允许的六类。

引擎（native_forge.py load_packet）只接受 paragraph/equation/table/figure/heading/header_footer；
worker 偶尔把程序清单登记成 kind="code"（合同里 code 只是 block 类型），于是 build 报
"source_inventory page N: every object needs id/page/kind/text"。

Run:  python D:\\nf-stage\\fix_object_kind.py
"""
import json
from pathlib import Path

ALLOWED = {"paragraph", "equation", "table", "figure", "heading", "header_footer"}
MAP = {"code": "paragraph", "console": "paragraph", "list": "paragraph", "quote": "paragraph",
       "caption": "heading", "image": "figure", "plot": "figure", "box": "paragraph",
       "algorithm": "paragraph", "note": "paragraph"}

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for obj in data.get("objects", []):
        k = obj.get("kind")
        if k not in ALLOWED:
            obj["kind"] = MAP.get(str(k).lower(), "paragraph")
            n += 1
    for entry in data.get("excluded_objects") or []:
        k = entry.get("kind")
        if k not in ALLOWED:
            entry["kind"] = MAP.get(str(k).lower(), "paragraph")
            n += 1
    for key in ("blocks",):
        for b in data.get(key) or []:
            k = b.get("kind")
            if k not in ALLOWED | {"code", "console", "figure_native", "chapter", "section",
                                   "subsection", "figure", "excluded", "toc"}:
                b["kind"] = "paragraph"
                n += 1
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 非法 kind 的 evidence object 归一化为合同允许值。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print("\n".join(fixed) if fixed else "all object kinds allowed")
