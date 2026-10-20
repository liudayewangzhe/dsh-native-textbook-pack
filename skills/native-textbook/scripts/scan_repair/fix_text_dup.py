"""修证据对象 text 里"整句重复一遍"的污染，并去掉分带重叠造成的重复行。

现象（worker 报告）：p0323-s002 的 text 变成
  「型，以及 Kuramoto-Sivashinsky 方程。以及 Kuramoto-Sivashinsky 方程。1964 年他毕业于…」
即同一句被并了两遍——我的修补脚本在"续行补全"时把已存在的前缀又接了一次。

做法：对每个 object 的 text，按句号/分号切段，若**相邻段完全相同**（或后段是前段的后缀），
去掉重复的一份；同时去掉连续重复的整行。幂等。

Run:  python D:\\nf-stage\\fix_text_dup.py [--apply]
"""
import argparse
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")


def dedup_sentences(text: str) -> str:
    if not text:
        return text
    # 按句子边界切，保留分隔符
    parts = re.split(r"(?<=[。！？；])", text)
    out = []
    for seg in parts:
        if not seg:
            continue
        if out and seg.strip() == out[-1].strip():
            continue                                  # 完全相同的相邻句
        if out and seg.strip() and out[-1].strip().endswith(seg.strip()):
            continue                                  # 后段是前段的后缀
        out.append(seg)
    res = "".join(out)
    # 连续重复整行
    lines, seen_prev = [], None
    for ln in res.split("\n"):
        if ln.strip() and ln.strip() == (seen_prev or "").strip():
            continue
        seen_prev = ln
        lines.append(ln)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    hits, n = [], 0
    for path in sorted(INBOX.glob("p0*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for o in data.get("objects", []):
            t = o.get("text")
            if isinstance(t, str) and t:
                new = dedup_sentences(t)
                if new != t:
                    o["text"] = new
                    dirty = True
                    n += 1
        if dirty:
            data["notes"] = (data.get("notes", "") +
                             "\n[监工修补 2026-10-15] 证据对象 text 存在相邻重复句/行，已去重。")
            if args.apply:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            hits.append(path.name)
    print(f"{n} object(s) 去重，涉及 {len(hits)} 分片" + (" [applied]" if args.apply else " [dry-run]"))
    print(" ".join(hits[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
