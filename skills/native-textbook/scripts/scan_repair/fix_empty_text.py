"""给 text 为空的 evidence object 补一段可读描述。

引擎要求每个 object 都有非空 text（`every object needs id/page/kind/text`）。
插图/版式元素本身没有文字时，用它的 caption/description 兜底。

Run:  python D:\\nf-stage\\fix_empty_text.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    figs = {f.get("source_id"): f for f in (data.get("figures") or [])}
    n = 0
    for obj in data.get("objects", []):
        if (obj.get("text") or "").strip():
            continue
        f = figs.get(obj["id"]) or {}
        fallback = (f.get("caption") or f.get("description")
                    or {"figure": "插图（见原书对应页）",
                        "table": "表格（见原书对应页）",
                        "equation": "公式（见对应块 LaTeX 转写）",
                        "heading": "标题",
                        "paragraph": "正文（见对应块）",
                        "header_footer": "页眉页脚"}.get(obj.get("kind"), "版式元素"))
        obj["text"] = fallback
        n += 1
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 为空 text 的 evidence object 补入描述性文本。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print("\n".join(fixed) if fixed else "all objects have text")
