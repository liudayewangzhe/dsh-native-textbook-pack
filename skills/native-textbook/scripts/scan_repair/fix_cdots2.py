"""撤销 fix_cdots 的误判包裹，并只对真正处于文本模式的 \\cdots 加 $。

逐行统计 $ 的奇偶对跨行公式（equation/align 环境里没有 $）会误判，导致 50+ 处
数学模式里的 \\cdots 被错误地包成 $\\cdots$，反而触发 "! Missing $ inserted"。

策略：先把所有 $\\cdots$ 还原为 \\cdots，再用「是否位于数学环境或未闭合的 $ 之内」
的跨行状态机判断，只包裹文本模式处。

Run:  python D:\\nf-stage\\fix_cdots2.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
MATH_ENV = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|"
                      r"equation\*|align\*|gather\*|multline\*|array|matrix|pmatrix|bmatrix|"
                      r"cases|split|aligned|gathered)\*?\}")
ENV_END = re.compile(r"\\end\{[^}]*\}")
DOLLAR = re.compile(r"(?<!\\)\$")

fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for b in data.get("blocks", []):
        tex = b.get("tex")
        if not isinstance(tex, str) or "\\cdots" not in tex:
            continue
        # equation 块的 tex **整体**就是数学模式：
        #   既可能带 \begin{equation}，也可能是"裸式"（引擎的 DISPLAY_ENVIRONMENT 分支原样输出）。
        # 裸式时状态机的 depth 会从 0 起，把 \cdots 误判成文本模式包成 $\cdots$，
        # 于是数学模式里嵌了 $ → "! Missing $ inserted"。故 equation 块只做还原、不再包裹。
        if b.get("kind") == "equation" or b.get("numbered") is True:
            if "$\\cdots$" in tex:
                b["tex"] = tex.replace("$\\cdots$", "\\cdots")
                n += 1
            continue
        # 1) undo previous over-wrapping
        tex2 = tex.replace("$\\cdots$", "\\cdots")
        # 2) walk the text tracking math context across lines
        out, depth, i = [], 0, 0
        while i < len(tex2):
            m_env = MATH_ENV.match(tex2, i)
            if m_env:
                depth += 1
                out.append(m_env.group(0))
                i = m_env.end()
                continue
            m_end = ENV_END.match(tex2, i)
            if m_end:
                depth = max(0, depth - 1)
                out.append(m_end.group(0))
                i = m_end.end()
                continue
            if tex2.startswith("\\[", i):
                depth += 1
                out.append("\\[")
                i += 2
                continue
            if tex2.startswith("\\]", i):
                depth = max(0, depth - 1)
                out.append("\\]")
                i += 2
                continue
            if tex2[i] == "$" and (i == 0 or tex2[i - 1] != "\\"):
                depth = 1 - depth  # inline math toggles
                out.append("$")
                i += 1
                continue
            tok = re.match(r"\\cdots\{\}?|\\cdots", tex2[i:])
            if tok:
                out.append(tok.group(0) if depth > 0 else "$" + tok.group(0) + "$")
                n += 1
                i += tok.end()
                continue
            out.append(tex2[i])
            i += 1
        new = "".join(out)
        if new != tex:
            b["tex"] = new
    if n:
        data["notes"] = (data.get("notes", "") +
                         "\n[监工修补 2026-10-15] \\cdots 的数学模式包裹按跨行上下文重算，只包裹文本模式处。")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fixed.append(f"{path.name}: {n}")
print(f"{len(fixed)} shard(s) adjusted")
print("\n".join(fixed[:10]))
