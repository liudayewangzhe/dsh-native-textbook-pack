"""给空 tex 的 heading/subsection 块补上标题文字（引擎拒绝空 tex）。

构建报 `blocks[N] (p0217-b000): subsection requires non-empty tex` —— worker 把
小节标题的 object 登记了，block 的 tex 却留空（或只写了注释）。

策略：从该 block 的 source object 的 text 里取标题文字，按 kind 补成
\\section{...} / \\subsection{...} / \\chapter{...}；若确实没有文字可依据，则把块
降级为 paragraph 并写入 object text（避免标题级错误）。

Run:  python D:\\nf-stage\\fix_empty_heading_tex.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
CMD = {"chapter": "chapter", "section": "section", "subsection": "subsection"}
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    objs = {o["id"]: o for o in data.get("objects", [])}
    n = 0
    for b in data.get("blocks", []):
        kind = b.get("kind")
        if kind not in CMD:
            continue
        tex = (b.get("tex") or "").strip()
        if re.search(r"\\(chapter|section|subsection)\s*(\*)?\{[^}]*\S[^}]*\}", tex):
            continue
        # collect title text from the block's own tex or its source objects
        cand = re.sub(r"\\[a-zA-Z]+\*?", "", tex).strip("{} ")
        if not cand:
            for sid in b.get("source_ids") or []:
                t = (objs.get(sid, {}).get("text") or "").strip()
                if t:
                    cand = t
                    break
        cand = re.sub(r"^\s*\d+(\.\d+)*\s*[\.、]?\s*", "", cand).strip()
        cand = cand.strip("{} ")
        if not cand:
            b["kind"] = "paragraph"
            b["tex"] = "（原书此处为小节标题，标题文字未辨认）"
            n += 1
            continue
        b["tex"] = "\\" + CMD[kind] + "{" + cand + "}"
        n += 1
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 空的 heading/subsection tex 按源对象文字补齐。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print("\n".join(fixed) if fixed else "no empty heading tex")
