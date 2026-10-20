"""修两类构建阻塞：跨页重复编号、`heading` 作为 block kind。

1) `expectations.equation_tags contains duplicates`
   原书在 p0314/p0315 出现**重排**（同一批公式印两遍），两页各带同样的 \\tag。
   引擎要求编号唯一。处理：保留**先出现**的那个带编号，后出现者改为无编号
   （equation* + numbered:false），并在 notes 标明"原书重排重复页"。

2) `unresolved: bad kind 'heading'`
   `heading` 可以作为**证据对象**的 kind，但不能作为 **block** 的 kind。
   处理：把 block.kind 从 heading 改成最接近的合法值 —— 若 tex 形如 \\section 用
   `section`，\\subsection 用 `subsection`，否则用 `paragraph`。

Run:  python D:\\nf-stage\\fix_dups_and_heading.py
"""
import json
import re
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
TAG = re.compile(r"\\tag\{([^}]*)\}")

# --- 1) 跨页重复编号：后来的去编号 -------------------------------------------
seen: dict[str, tuple[str, str]] = {}
log_dup = []
ordered = sorted(INBOX.glob("p0*.json"))
data_cache: dict[Path, dict] = {}

for path in ordered:
    data = json.loads(path.read_text(encoding="utf-8"))
    data_cache[path] = data
    for b in data.get("blocks", []):
        if b.get("kind") != "equation":
            continue
        tags = [t.strip().strip("()") for t in TAG.findall(b.get("tex") or "")]
        if not tags:
            continue
        key = tags[0]
        if key not in seen:
            seen[key] = (path.name, b["id"])
            continue
        # 第二次出现 → 去编号
        tex = TAG.sub("", b["tex"])
        if "\\begin{equation}" in tex:
            tex = tex.replace("\\begin{equation}", "\\begin{equation*}", 1)
            tex = tex.replace("\\end{equation}", "\\end{equation*}", 1)
        b["tex"] = tex
        b["numbered"] = False
        log_dup.append(f"{path.name}:{b['id']} 去编号 {key}（首见于 {seen[key][0]}:{seen[key][1]}）")

# --- 2) heading block → 合法 kind --------------------------------------------
log_head = []
for path, data in data_cache.items():
    n = 0
    for b in data.get("blocks", []):
        if b.get("kind") != "heading":
            continue
        tex = b.get("tex") or ""
        if "\\section" in tex:
            b["kind"] = "section"
        elif "\\subsection" in tex:
            b["kind"] = "subsection"
        elif "\\chapter" in tex:
            b["kind"] = "chapter"
        else:
            b["kind"] = "paragraph"
        n += 1
    if n:
        log_head.append(f"{path.name}: {n}")

# --- 写回 --------------------------------------------------------------------
written = 0
for path, data in data_cache.items():
    notes = []
    if any(x.startswith(path.name + ":") for x in log_dup):
        notes.append("原书存在重排重复页，重复编号改为无编号（equation*）。")
    if any(x.startswith(path.name + ":") for x in log_head):
        notes.append("heading 不是合法 block kind，已改为 paragraph/section/subsection。")
    if notes:
        data["notes"] = data.get("notes", "") + "\n[监工修补 2026-10-15] " + " ".join(notes)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1

print(f"去重 {len(log_dup)} 处；heading block 修正 {len(log_head)} 个分片；写回 {written} 个分片")
print("\n".join(log_dup[:8]))
print("\n".join(log_head[:8]))
