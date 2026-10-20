"""清掉 4 处重复的公式编号。

根因分两类：
  A) fix_missing_tag.py 的误补：p0104 的 b006/b007/b008 是习题列表（\\text{(2)} 等），
     不是编号公式，却被补上了 (4.5.2)/(4.5.3)，与真正的 (4.5.2) 撞号。
     → 撤销这三处 tag，并把畸形嵌套 `\\begin{equation}\\begin{equation*}...\\end{equation*}` 还原为 equation*。
  B) 跨页断开的同一公式在两页各标一次：p0055/p0056 的 (2.3.26)、p0156/p0157 的 (6.1.22)。
     → 保留后页（含完整式）的 tag，前页改为不带编号的续行。

Run:  python D:\\nf-stage\\fix_dup_tags.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
log = []


def load(pg):
    p = INBOX / f"p{pg:04d}.json"
    return p, json.loads(p.read_text(encoding="utf-8"))


def blk(data, bid):
    return next((b for b in data["blocks"] if b["id"] == bid), None)


def save(path, data, note):
    data["notes"] = data.get("notes", "") + "\n" + note
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# A) p0104 的三处误补
path, data = load(104)
n = 0
for bid in ("p0104-b006", "p0104-b007", "p0104-b008"):
    b = blk(data, bid)
    if not b:
        continue
    tex = b["tex"]
    tex = re.sub(r"\\tag\{[^}]*\}", "", tex)
    # 还原畸形嵌套：\begin{equation}\begin{equation*} ... \end{equation*}\end{equation}
    tex = tex.replace("\\begin{equation}\\begin{equation*}", "\\begin{equation*}")
    tex = tex.replace("\\end{equation*}\\end{equation}", "\\end{equation*}")
    tex = tex.replace("\\begin{equation}\n\\begin{equation*}", "\\begin{equation*}")
    tex = tex.replace("\\end{equation*}\n\\end{equation}", "\\end{equation*}")
    b["tex"] = tex.strip()
    b["numbered"] = False
    n += 1
if n:
    save(path, data, f"[监工修补 2026-10-15] 撤销 fix_missing_tag 对 {n} 个习题块的误补编号（它们不是编号公式），"
                      "并把畸形嵌套 equation/equation* 还原。")
    log.append(f"p0104: {n} blocks untagged")

# B) 跨页重复：保留后页 tag，前页去 tag
for front_pg, front_id, back_pg, back_id, tag in (
        (55, "p0055-b015", 56, "p0056-b000", "2.3.26"),
        (156, "p0156-b016", 157, "p0157-b001", "6.1.22")):
    p1, d1 = load(front_pg)
    b1 = blk(d1, front_id)
    if b1 is None:
        continue
    tex = re.sub(r"\\tag\{[^}]*\}", "", b1["tex"])
    # 续行不参与编号
    if "\\begin{equation}" in tex and "\\end{equation}" in tex:
        tex = tex.replace("\\begin{equation}", "\\begin{equation*}", 1)
        tex = tex.replace("\\end{equation}", "\\end{equation*}", 1)
    b1["tex"] = tex.strip()
    b1["numbered"] = False
    save(p1, d1, f"[监工修补 2026-10-15] 本块是跨页断开公式 {tag} 的前半，改为 equation* 不计编号，"
                  f"编号归 {back_id}。")
    log.append(f"p{front_pg} {front_id}: tag {tag} removed (kept on p{back_pg})")

print("\n".join(log) if log else "nothing to fix")
