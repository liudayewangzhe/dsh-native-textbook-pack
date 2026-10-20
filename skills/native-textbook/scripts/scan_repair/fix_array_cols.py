"""修正 array/tabular 环境声明的列数与实际内容不符的问题。

XeLaTeX 报 `! Extra alignment tab has been changed to \\cr`（p0115 的矩阵声明 `{cccccc}`
而内容有 7 列）。这里按环境块统计每行的最大 `&` 数，若声明列数偏少就补足（保持原来的
列对齐字符类型）。

Run:  python D:\\nf-stage\\fix_array_cols.py [--apply]
"""
import argparse
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
ENV = re.compile(r"\\begin\{(array|tabular|tabularx|longtable)\}\{([^{}]*)\}")


def declared(spec: str) -> int:
    return len(re.findall(r"[lcrX]", spec))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    fixes = []
    for path in sorted(INBOX.glob("p0*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for block in data.get("blocks", []):
            tex = block.get("tex")
            if not isinstance(tex, str) or "\\begin{array}" not in tex and "\\begin{tabular" not in tex:
                continue
            for m in list(ENV.finditer(tex)):
                env, spec = m.group(1), m.group(2)
                # body of this environment (up to its \end)
                body_start = m.end()
                body_end = tex.find(f"\\end{{{env}}}", body_start)
                body = tex[body_start:body_end if body_end > 0 else len(tex)]
                body = re.sub(r"\\begin\{[^}]*\}.*?\\end\{[^}]*\}", "", body, flags=re.S)
                need = 1
                for line in body.split("\\\\"):
                    line = re.sub(r"\\hline|\\toprule|\\midrule|\\bottomrule|\\endfirsthead|\\endhead|\\endfoot|\\endlastfoot", "", line)
                    need = max(need, line.count("&") + 1)
                have = declared(spec)
                if need > have:
                    kind = "c" if "c" in spec else ("l" if "l" in spec else "r")
                    new_spec = spec + kind * (need - have)
                    tex = tex[:m.start(2)] + new_spec + tex[m.end(2):]
                    fixes.append(f"{path.name} {block['id']}: {env} cols {have} -> {need}")
                    changed = True
                break  # one env per pass is enough; re-scan next run
            if changed:
                block["tex"] = tex
                break
        if changed and args.apply:
            data["notes"] = (data.get("notes", "") +
                             "\n[监工修补 2026-10-14] 表格/矩阵声明的列数按内容补足，避免 Extra alignment tab。")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(fixes) if fixes else "column counts consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
