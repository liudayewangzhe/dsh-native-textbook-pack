"""逐字符修复分片里的非法 JSON 转义（更稳的版本）。

只在**字符串内部**且反斜杠后面不是合法转义字符时补一个反斜杠，因此不会破坏
已经写对的 `\\\\`、`\\"` 等序列。

Run:  python D:\\nf-stage\\fix_bad_json2.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
LEGAL = set('"\\/bfnrtu')


def repair(raw: str) -> str:
    out, i, in_str, esc = [], 0, False, False
    while i < len(raw):
        ch = raw[i]
        if not in_str:
            out.append(ch)
            if ch == '"':
                in_str = True
            i += 1
            continue
        if esc:
            out.append(ch)
            esc = False
            i += 1
            continue
        if ch == '"':
            out.append(ch)
            in_str = False
            i += 1
            continue
        if ch == "\\":
            nxt = raw[i + 1] if i + 1 < len(raw) else ""
            if nxt in LEGAL:
                out.append(ch)
                esc = True
            else:
                out.append("\\\\")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


fixed = []
for path in sorted(INBOX.glob("p0*.json")):
    raw = path.read_text(encoding="utf-8")
    try:
        json.loads(raw)
        continue
    except Exception as exc:
        err = str(exc)[:60]
    patched = repair(raw)
    try:
        data = json.loads(patched)
    except Exception as exc:
        fixed.append(f"{path.name}: UNFIXED ({exc})")
        continue
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fixed.append(f"{path.name}: fixed ({err})")
print("\n".join(fixed) if fixed else "all shards valid JSON")
