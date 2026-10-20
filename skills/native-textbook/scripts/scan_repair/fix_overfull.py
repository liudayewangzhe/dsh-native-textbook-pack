"""修掉 QA 抓到的 5 处 Overfull \\hbox（不改公式与图的语义，只调排版）。

定位（locate_overfull.py）：
  p0036-b001  图 1.2.2 两个 TikZ 面板超出 minipage     22.1pt
  p0077-b001  三对角矩阵 + 两个列向量过宽               44.9pt
  p0092-b900  图 4.3.2（TikZ）过宽                      23.8pt
  p0105-b011  公式 (4.5.6) 三连等式过长                 133.6pt
  p0114-*     线性方程组解法的目录行（另一处，待补）

Run:  python D:\\nf-stage\\fix_overfull.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
log = []


def load(pg):
    path = INBOX / f"p{pg:04d}.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def save(path, data, note):
    data["notes"] = (data.get("notes", "") + "\n" + note)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def block(data, bid):
    return next((b for b in data["blocks"] if b["id"] == bid), None)


# ---- 1) p0036 图 1.2.2：把两个面板的 TikZ 整体缩小 15% ----
path, data = load(36)
b = block(data, "p0036-b001")
if b and "scale=0.85" not in b["tex"]:
    b["tex"] = b["tex"].replace("\\begin{tikzpicture}[", "\\begin{tikzpicture}[scale=0.85,")
    save(path, data, "[监工修补 2026-10-15] 图 1.2.2 两个面板整体 scale=0.85，消除 22pt 溢出。")
    log.append("p0036-b001 scaled")

# ---- 2) p0077 三对角矩阵：收紧矩阵列距 ----
path, data = load(77)
b = block(data, "p0077-b001")
if b and "arraycolsep" not in b["tex"]:
    b["tex"] = b["tex"].replace(
        "\\begin{equation}\n", "\\begin{equation}\\setlength{\\arraycolsep}{2.6pt}\n", 1)
    save(path, data, "[监工修补 2026-10-15] 矩阵列距收紧到 2.6pt，消除 45pt 溢出。")
    log.append("p0077-b001 arraycolsep")

# ---- 3) p0092 图 4.3.2：x 比例 1cm -> 0.86cm ----
path, data = load(92)
b = block(data, "p0092-b900")
if b and "x=1cm" in b["tex"]:
    b["tex"] = b["tex"].replace("x=1cm,y=1cm", "x=0.86cm,y=0.86cm")
    save(path, data, "[监工修补 2026-10-15] 图 4.3.2 比例改为 0.86cm，消除 24pt 溢出。")
    log.append("p0092-b900 rescaled")

# ---- 4) p0105 公式 (4.5.6)：三连等式改为 split 两行（内容一字不动） ----
path, data = load(105)
b = block(data, "p0105-b011")
if b and "\\begin{split}" not in b["tex"]:
    old = b["tex"]
    body = old[old.index("\\begin{equation}") + len("\\begin{equation}"):]
    body = body[:body.rindex("\\end{equation}")]
    tag = re.search(r"\\tag\{[^}]*\}", body)
    tag_tex = tag.group(0) if tag else ""
    body = body.replace(tag_tex, "")
    first, _, rest = body.partition("=")
    second, _, third = rest.partition("=\\frac{f'(m+1)-f'(m)}{12}")
    new = ("\\begin{equation}\n\\begin{split}\n"
           + first.strip() + " &= " + second.strip() + "\\\\\n"
           + "&= \\frac{f'(m+1)-f'(m)}{12}" + third.rstrip().rstrip(",") + ",\n"
           + "\\end{split}\n" + tag_tex + "\n\\end{equation}")
    b["tex"] = new
    save(path, data, "[监工修补 2026-10-15] 公式 (4.5.6) 改为 split 两行以消除 134pt 溢出，内容与编号不变。")
    log.append("p0105-b011 split")

print("\n".join(log) if log else "nothing to fix")
