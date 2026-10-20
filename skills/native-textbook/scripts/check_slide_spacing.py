#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_slide_spacing.py — 课件文本节点的"行盒与间距"确定性检查

为什么需要它：本项目实测发现，**长句折行**与**过紧的行距**造成的压字，
编译日志四桶全空、`check_typography.py`（按渲染后 PDF 的 bbox）也只能部分发现，
而"我用肉眼审核了 15 页"仍然漏掉了 4 处（见下）。原因是：
**手写坐标的课件里，文本的垂直占位 = 行数 × 行距，而人不会每次都去数行数。**

本脚本直接读 TeX 源，抓取显式坐标的文本节点，按可用宽度估算行数，
再检查同一页内相邻节点的基线间距是否容得下前一项的行盒。

实测抓出并修掉的案例（都发生在"目检通过"之后）：
  - p9  第一条 bullet 折成 2 行，与第二条 bullet 重叠
  - p14 第三项按 2 行预留、实测 1 行，间距过大
  - p6  一个空的重复节点与正文节点同坐标
  - p4  "两条等式合排"超宽被裁（宽度检查）

它能证明：**文本节点之间的几何冲突**。
它不能证明：渲染后是否好看、公式语义、图形遮挡（那些要靠看图与 check_typography）。

用法
----
    python check_slide_spacing.py --tex "项目\\main.tex"
    python check_slide_spacing.py --tex main.tex --lead 13.3 --body 9.5 --report qa/spacing.md

参数
----
--lead  正文行距（pt），用于算行盒
--body  正文字号（pt），用于估算字宽
--width 默认取节点自带的 text width
--min-gap-ratio  相邻项最小间距 = 前一项行盒 × 该系数（默认 0.75）
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

# 匹配 \node[...text width=NNNmm ...] at (x,y) { ... };
NODE_RE = re.compile(
    r"\\node\[(?P<opts>[^\]]*?)text width=(?P<w>[\d.]+)mm(?P<opts2>[^\]]*?)\]\s*"
    r"at\s*\(\s*(?P<x>[\d.]+)\s*,\s*(?P<y>[\d.]+)\s*\)\s*\{(?P<body>.*?)\};",
    re.S,
)
# 分页边界
PAGE_RE = re.compile(r"\\Slide\[(\d+)\]")


def strip_tex(txt: str) -> str:
    """把 TeX 片段近似还原为可见文字，用于估宽。"""
    s = txt
    s = re.sub(r"\\begin\{gathered\}", "M M M", s)
    s = re.sub(r"\\end\{gathered\}", "", s)
    # 数学按 M 个半宽字符估（粗略：源码长度的一半，最少 2）
    s = re.sub(r"\$[^$]*\$",
               lambda m: "M" * max(2, min(30, len(m.group(0)) // 2)), s)
    s = re.sub(r"\\dfrac|\\frac|\\int|\\sum|\\lim|\\max|\\left|\\right", "", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    s = re.sub(r"\s+", "", s)
    return s


def width_mm(txt: str, cjk_mm: float, latin_ratio: float = 0.5) -> float:
    w = 0.0
    for ch in strip_tex(txt):
        w += cjk_mm if ord(ch) > 0x2E80 else cjk_mm * latin_ratio
    return w


def main():
    ap = argparse.ArgumentParser(description="课件文本节点行盒与间距检查")
    ap.add_argument("--tex", required=True)
    ap.add_argument("--lead", type=float, default=13.3, help="正文行距 pt（默认 13.3）")
    ap.add_argument("--body", type=float, default=9.5, help="正文字号 pt（默认 9.5）")
    ap.add_argument("--min-gap-ratio", type=float, default=0.90,
                    help="相邻项最小间距 = 前项行盒 × 该系数（默认 0.90；"
                         "取 1.0 即要求完全不重叠，0.9 允许 10% 的行盒咬合以容纳基线差）")
    ap.add_argument("--max-x", type=float, default=20.0,
                    help="只检查左侧正文列（x <= 该值），默认 20mm")
    ap.add_argument("--report")
    ap.add_argument("--out")
    a = ap.parse_args()
    if not all(math.isfinite(value) and value > 0 for value in
               (a.lead, a.body, a.min_gap_ratio, a.max_x)):
        ap.error("lead, body, min-gap-ratio and max-x must be finite and positive")

    PT2MM = 25.4 / 72.0
    lead_mm = a.lead * PT2MM
    cjk_mm = a.body * PT2MM

    src = Path(a.tex).read_text(encoding="utf-8", errors="replace")
    # 按 \Slide 切页
    pages: dict[int, list[str]] = {}
    cur = None
    for line in src.splitlines():
        m = PAGE_RE.search(line)
        if m:
            cur = int(m.group(1))
            pages.setdefault(cur, [])
        if cur is not None:
            pages[cur].append(line)

    findings = []
    per_page = {}
    for pg in sorted(pages):
        body = "\n".join(pages[pg])
        items = []
        for m in NODE_RE.finditer(body):
            opts = m.group("opts") + m.group("opts2")
            if "nftxt" not in opts and "nftxts" not in opts and "nfhd" not in opts:
                continue
            x = float(m.group("x"))
            if x > a.max_x:
                continue
            w = float(m.group("w"))
            y = float(m.group("y"))
            if w <= 0 or not all(math.isfinite(value) for value in (x, y, w)):
                ap.error(f"page {pg}: matched text node has invalid width or coordinates")
            txt = m.group("body").strip()
            nlines = max(1, int(math.ceil(width_mm(txt, cjk_mm) / w)))
            items.append({"y": y, "x": x, "w": w, "lines": nlines, "text": txt})
        items.sort(key=lambda d: d["y"])
        per_page[pg] = [
            {"y": it["y"], "lines": it["lines"], "height_mm": round(it["lines"] * lead_mm, 2),
             "text": re.sub(r"\s+", " ", strip_tex(it["text"]))[:60]}
            for it in items
        ]
        for i, it in enumerate(items):
            if not strip_tex(it["text"]).strip():
                findings.append({
                    "severity": "error", "page": pg, "code": "empty_text_node",
                    "message": f"页 {pg} y={it['y']} 处文本节点为空（残留节点，会占位并可能压到别人）"})
            if i == 0:
                continue
            prev = items[i - 1]
            gap = it["y"] - prev["y"]
            need = prev["lines"] * lead_mm * a.min_gap_ratio
            if gap < need - 1e-6:
                findings.append({
                    "severity": "error", "page": pg, "code": "node_overlap_risk",
                    "message": (f"页 {pg}：y={it['y']}（{strip_tex(it['text'])[:24]}）与上一项 "
                                f"y={prev['y']} 间距 {gap:.1f}mm，但上一项有 {prev['lines']} 行、"
                                f"行盒 {prev['lines']*lead_mm:.1f}mm，需 ≥{need:.1f}mm")})
    n_lines = sum(len(v) for v in per_page.values())
    status = "not_applicable" if n_lines == 0 else (
        "failed" if any(f["severity"] == "error" for f in findings) else "passed")
    print(f"[info] 扫描 {len(per_page)} 页、{n_lines} 个文本节点；"
          f"行距 {a.lead}pt={lead_mm:.2f}mm，字宽 {cjk_mm:.2f}mm")
    for f in findings:
        print(f"  [{f['severity']}] {f['code']} {f['message']}")
    if status == "not_applicable":
        print("  [not_applicable] 未识别到受支持节点；不能据此报告间距检查通过。请检查实际 PDF 或提供受支持的显式节点源。")
    elif not findings:
        print("  ✅ 未发现行盒冲突（这**不**代表没有遮挡：图形压字、字体字形仍须看图）")

    result = {"tex": str(Path(a.tex).resolve()), "lead_pt": a.lead, "body_pt": a.body,
              "lead_mm": round(lead_mm, 3), "nodes": n_lines,
              "findings": findings, "pages": per_page, "check_status": status}
    if a.out:
        import json
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ok] JSON -> {a.out}")
    if a.report:
        L = [f"# 课件文本行盒检查 — {Path(a.tex).name}", "",
             f"- 行距 {a.lead} pt = {lead_mm:.2f} mm；正文字宽 {cjk_mm:.2f} mm",
             f"- 扫描 {len(per_page)} 页 / {n_lines} 个文本节点", "", "## 结论", ""]
        if status == "not_applicable":
            L.append("- 未覆盖：未识别到受支持节点，不能报告间距检查通过；须实测实际 PDF 或补充受支持的源表示。")
        elif findings:
            for f in findings:
                L.append(f"- ❌ **{f['code']}** — {f['message']}")
        else:
            L.append("- ✅ 未发现行盒冲突")
        L += ["", "## 逐页文本占位", ""]
        for pg in sorted(per_page):
            L.append(f"### 页 {pg}")
            L.append("| y | 行数 | 行盒mm | 文本 |")
            L.append("|---|---|---|---|")
            for it in per_page[pg]:
                L.append(f"| {it['y']} | {it['lines']} | {it['height_mm']} | {it['text']} |")
            L.append("")
        L += ["> 本检查只覆盖**同一页左侧正文列内、显式坐标文本节点**的行盒冲突。",
              "> 图形压字、字体级字形遮挡、右栏/居中文案不在覆盖范围，必须配合看图。"]
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text("\n".join(L), encoding="utf-8")
        print(f"[ok] Markdown -> {a.report}")

    return 2 if status == "not_applicable" else (1 if status == "failed" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
