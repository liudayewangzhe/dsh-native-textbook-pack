"""跨页标记自动对齐：一侧标了 continues_prev/next，另一侧必须配对。

worker 常只标一侧（p0077 末段未标 continues_next、p0078 首段却标了 continues_prev），
而 merge_workers.py 要求两侧同时成立才拼接，否则正文会被切成两段。
本脚本扫描相邻页分片，把缺失的一侧补上（同时写到 block 与它引用的 object 上）。

Run:  python D:\\nf-stage\\auto_continues.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
pages = {}
for path in sorted(INBOX.glob("p0*.json")):
    pages[int(path.stem[1:])] = (path, json.loads(path.read_text(encoding="utf-8")))

log = []


def first_paragraph(blocks):
    for b in blocks:
        if b.get("kind") == "paragraph":
            return b
    return None


def last_paragraph(blocks):
    for b in reversed(blocks):
        if b.get("kind") == "paragraph":
            return b
    return None


def ends_sentence(block):
    """段落若已以句末标点收尾就是完整的；把它与下一页段落拼接会造出假续句（实测已发生）。"""
    import re
    tex = block.get("tex") or block.get("text") or ""
    tex = re.sub(r"\\(?:par|hfill|quad|qquad)\s*", "", tex).strip()
    tex = re.sub(r"\\end\{(?:equation|align|gather|multline|equation\*|align\*)\}\s*$", "", tex).rstrip()
    return bool(tex) and tex[-1] in "。！？!?"


def mark(data, block, key):
    if not block.get("continues_prev") and not block.get("continues_next"):
        block[key] = True
    else:
        block[key] = True
    for oid in block.get("source_ids", []):
        for obj in data.get("objects", []):
            if obj["id"] == oid:
                obj[key] = True


changed = set()
for page in sorted(pages):
    path, data = pages[page]
    blocks = data.get("blocks") or []
    if not blocks:
        continue
    first = first_paragraph(blocks)
    if first is not None:
        objs = {o["id"]: o for o in data.get("objects", [])}
        prev_flag = bool(first.get("continues_prev")) or any(
            objs.get(s, {}).get("continues_prev") for s in first.get("source_ids", []))
        if prev_flag and page - 1 in pages:
            ppath, pdata = pages[page - 1]
            pb = last_paragraph(pdata.get("blocks") or [])
            if pb is not None and ends_sentence(pb):
                if pb.get("continues_next"):
                    pb["continues_next"] = False
                    changed.add(page - 1)
                    log.append(f"p{page-1:04d} {pb['id']}: continues_next withdrawn "
                               f"(paragraph already ends with sentence punctuation)")
            elif pb is not None and not pb.get("continues_next"):
                mark(pdata, pb, "continues_next")
                changed.add(page - 1)
                log.append(f"p{page:04d} first para has continues_prev -> "
                           f"marked p{page-1:04d} {pb['id']} continues_next")
    last = last_paragraph(blocks)
    if last is not None:
        objs = {o["id"]: o for o in data.get("objects", [])}
        next_flag = bool(last.get("continues_next")) or any(
            objs.get(s, {}).get("continues_next") for s in last.get("source_ids", []))
        if next_flag and page + 1 in pages:
            npath, ndata = pages[page + 1]
            nb = first_paragraph(ndata.get("blocks") or [])
            if nb is not None and not nb.get("continues_prev"):
                mark(ndata, nb, "continues_prev")
                changed.add(page + 1)
                log.append(f"p{page:04d} last para has continues_next -> "
                           f"marked p{page+1:04d} {nb['id']} continues_prev")
            elif nb is not None and ends_sentence(nb):
                pass  # a paragraph that starts a sentence-final statement cannot be a continuation

for page in sorted(changed):
    path, data = pages[page]
    data["notes"] = (data.get("notes", "") +
                     "\n[监工修补 2026-10-14] 跨页标记由 auto_continues.py 与相邻页对齐。")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print("\n".join(log) if log else "no cross-page marks to align")
