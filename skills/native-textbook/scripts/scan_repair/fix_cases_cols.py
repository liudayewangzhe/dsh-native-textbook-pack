"""修 `cases` 环境里列数超过 2 的块（LaTeX 报 Extra alignment tab）。

`cases` 只有两列（值 & 条件）。worker 常把三元/多元联立写进 cases，于是
`x = 0, & y = 0, & z = 0, \\` 这种三列行直接崩编译。

处理：把 `\\begin{cases} ... \\end{cases}` 换成
      `\\left\\{\\begin{array}{lll} ... \\end{array}\\right.`
列数按块内**最多的 `&` 数 + 1** 决定（并给每行补足列数，避免 underfull 对齐）。

Run:  python D:\\nf-stage\\fix_cases_cols.py [--apply]
"""
import argparse
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
CASES = re.compile(r"\\begin\{cases\}(.*?)\\end\{cases\}", re.S)


def convert(body: str) -> str:
    rows = [r for r in body.split(r"\\")]
    cols = 1
    for r in rows:
        n = r.count("&") + 1
        cols = max(cols, n)
    fixed_rows = []
    for r in rows:
        if not r.strip():
            continue
        pad = cols - (r.count("&") + 1)
        fixed_rows.append(r.rstrip() + (" & " * pad if pad > 0 else ""))
    return ("\\left\\{\\begin{array}{" + "l" * cols + "}\n"
            + " \\\\\n".join(fixed_rows) + "\n\\end{array}\\right.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    fixed = []
    for path in sorted(INBOX.glob("p0*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        n = 0
        for b in data.get("blocks", []):
            tex = b.get("tex")
            if not isinstance(tex, str) or "\\begin{cases}" not in tex:
                continue
            def repl(m):
                body = m.group(1)
                maxamp = max((r.count("&") + 1) for r in body.split(r"\\")) if body.strip() else 1
                if maxamp <= 2:
                    return m.group(0)          # 正常两列，保持原样
                return convert(body)
            new = CASES.sub(repl, tex)
            if new != tex:
                b["tex"] = new
                n += 1
        if n:
            data["notes"] = (data.get("notes", "") +
                             f"\n[监工修补 2026-10-15] {n} 个 cases 块含超过 2 列，"
                             "改为 \\left\\{+array 并补足列数（修 Extra alignment tab）。")
            if args.apply:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            fixed.append(f"{path.name}: {n}" + ("" if args.apply else " (dry-run)"))
    print(f"{len(fixed)} shard(s) affected")
    print("\n".join(fixed[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
