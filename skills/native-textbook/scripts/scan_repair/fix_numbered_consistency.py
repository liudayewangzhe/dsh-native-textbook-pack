"""统一 equation 块的 numbered 与 \\tag 的一致性。

引擎的两条规则：
  - `numbered: false` 的块**不能**带 \\tag，且环境必须是 starred/unnumbered；
  - 需要编号的块必须**恰好一个** \\tag{...}。
监工的几个补丁脚本各自改了其中一半，于是出现 `numbered:false` 却带 \\tag 的组合。

策略（按证据优先级）：
  - 若块带 \\tag{...}  → 视为需要编号：numbered=true，环境用 equation；
  - 若无 \\tag 且 numbered=false → 环境改成 starred（equation*）。

Run:  python D:\\nf-stage\\fix_numbered_consistency.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
TAG = re.compile(r"\\tag\{[^}]*\}")
fixed = []

for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for b in data.get("blocks", []):
        if b.get("kind") != "equation":
            continue
        tex = b.get("tex") or ""
        has_tag = bool(TAG.search(tex))
        numbered = b.get("numbered")
        if numbered is None:
            numbered = has_tag
        if has_tag and numbered is False:
            b["numbered"] = True          # 带 \tag 就是编号公式：把 numbered 也改成 true
            numbered = True
            n += 1
        if not numbered:
            # 去编号：环境改 starred
            if "\\begin{equation}" in tex:
                tex = tex.replace("\\begin{equation}", "\\begin{equation*}", 1)
                tex = tex.replace("\\end{equation}", "\\end{equation*}", 1)
            b["numbered"] = False
            b["tex"] = tex
            n += 1
        else:
            b["numbered"] = True
            if b.get("tex") != tex:
                b["tex"] = tex
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] 统一 numbered 与 \\tag：无编号块改用 starred 环境。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print(f"{len(fixed)} shard(s) normalised")
print("\n".join(fixed[:8]))
