#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare_typography.py — 源 PDF 与目标 PDF 的字号/行距回抽比对

为什么要它：模板里声明的字号与最终 PDF 实际渲染的字号**不一致**。实测同一份
4:3 中文课件：封面声明 16 pt 实为 14.94 pt，正文声明 9.5 pt 而中文实测 9.46 pt、
同页数学 9.96 pt，行距声明 13.3 pt 实为 15.6–15.9 pt。因此"照模板数字写"不能
作为达标证据，必须从**实际交付 PDF** 回抽并与源比对。

同样地，整册误缩事故（正文 9.963 → 7.512 pt，乘了 72/96）也能被本工具直接看出：
目标字号相对源整体下移约 25%。

做法
----
1. 分别从源 PDF 与目标 PDF 抽取每个"字号"的出现次数，按出现次数排序得到主字号
   （正文级）、次字号（注释级）……并各自计算按字号分层的**基础行距**（节律）。
2. 用"占位顺序"把源与目标的同层级字号配对（最多 N 个层级），给出偏差百分比。
3. 输出偏差超过阈值（默认 3%）的项作为 findings。

注意
----
- 配对是**按字号大小顺序**做的，不是语义配对。源第 1 大字号配目标第 1 大字号。
  这对"整体等比缩放/误缩"最敏感；若源与目标层级数量不同，会在报告里写清。
- 中文与数学常常是**两个不同的实测字号**（如中文 9.46、数学 9.96），所以同一
  层级可能出现两个相邻值，偏差属正常；阈值判断要看整体，不逐值死磕。
- 本工具不做判断"哪个对"。它只给事实：源实测 X、目标实测 Y、偏差 Z%。

用法
----
    python compare_typography.py --source "源.pdf" --target "out\\main.pdf" \\
        --mode slide --out "qa\\size-compare.json" --report "qa\\size-compare.md"

    # 只比较指定页范围（避免封面/空白页干扰）
    python compare_typography.py --source src.pdf --target out.pdf --pages "2-15"
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    print("需要 PyMuPDF：pip install pymupdf", file=sys.stderr)
    raise SystemExit(2)

MATH_HINTS = ("math", "cmmi", "cmsy", "cmex", "cmr", "msam", "msbm", "stix", "xits",
              "latinmodern-math", "euler", "asana", "nimbusroman", "texgyre",
              "lmroman", "mnsymbol")
CJK_HINTS = ("cjk", "song", "hei", "kai", "ming", "yahei", "simsun", "simhei",
             "noto sans sc", "noto serif sc", "source han", "stsong", "msyh")


def kind_of(font: str) -> str:
    f = font.lower()
    if any(h in f for h in CJK_HINTS):
        return "cjk"
    if any(h in f for h in MATH_HINTS):
        return "math"
    return "latin"


def parse_pages(spec, total):
    if not spec:
        return None
    want = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            want.update(range(int(a), int(b) + 1))
        else:
            want.add(int(part))
    return {p for p in want if 1 <= p <= total}


def extract(path: Path, pages_spec=None):
    doc = fitz.open(path)
    total = doc.page_count
    want = parse_pages(pages_spec, total)
    sizes = Counter()
    per_size_kind = defaultdict(Counter)
    gaps = defaultdict(list)          # size -> [baseline gaps]
    for i in range(total):
        if want and (i + 1) not in want:
            continue
        page = doc[i]
        lines = []
        for b in page.get_text("dict").get("blocks", []):
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                sp = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
                if not sp:
                    continue
                size = max(s["size"] for s in sp)
                main = max(sp, key=lambda s: (s["bbox"][2] - s["bbox"][0]))
                sizes[round(size, 1)] += 1
                per_size_kind[round(size, 1)][kind_of(main["font"])] += 1
                lines.append((float(main["origin"][1]), size))
        lines.sort()
        for (y1, s1), (y2, s2) in zip(lines, lines[1:]):
            if abs(s1 - s2) > 0.2 or s1 <= 1:
                continue
            g = y2 - y1
            if g <= 0.5 or not (0.9 * s1 <= g <= 2.4 * s1):
                continue
            gaps[round(s1, 1)].append(g)
    doc.close()

    rhythm = {}
    for size, gl in gaps.items():
        c = Counter(round(g * 2) / 2 for g in gl)
        base, n = c.most_common(1)[0]
        if n < 2:
            continue
        rhythm[size] = {"base_gap_pt": base, "count": n, "total": len(gl),
                        "ratio": round(base / size, 3)}
    return {
        "path": str(path.resolve()),
        "pages_total": total,
        "pages_used": "all" if not want else f"{min(want)}-{max(want)}",
        "size_histogram": dict(sorted(sizes.items(), key=lambda kv: -kv[1])),
        "size_kinds": {str(k): dict(v) for k, v in sorted(per_size_kind.items(),
                                                        key=lambda kv: -sum(kv[1].values()))},
        "size_rhythm": rhythm,
    }


def _share(hist, size, total):
    return (hist.get(str(size), 0) / total) if total else 0.0


def pair_levels(src, tgt, min_share=0.02, top=6, max_dev=0.30, size_weight=1.0,
                share_weight=0.8):
    """按"字号相近 + 出现占比相近"配对，而不是单纯按字号大小排序。

    单纯按大小排序会把源的标题级（14.3 pt，占比很小）配到目标的另一级
    （如 8.0 pt），产生无意义的偏差告警。这里加两个约束：
      - 只保留有一定占比的字号（避免一次性的脚注/标注被当成层级）；
      - 配对半径 max_dev：|目标/源 - 1| > max_dev 的候选**不允许配对**，
        未配上的层级单独报为 unpaired，而不是硬塞一个巨大偏差。
    整体缩放事故（如 0.75）由"正文级比例"单独检测，不依赖逐级配对。

    size_weight 调高时更偏好"字号最接近"的配对；用于课件这类层级少、
    中文与数学字号相邻的文档，避免把小字号配到公式级。
    """
    src_total = sum(src["size_histogram"].values()) or 1
    tgt_total = sum(tgt["size_histogram"].values()) or 1
    src_items = [(float(s), c, c / src_total) for s, c in src["size_histogram"].items()]
    tgt_items = [(float(s), c, c / tgt_total) for s, c in tgt["size_histogram"].items()]
    src_items.sort(key=lambda x: -x[1])
    tgt_items.sort(key=lambda x: -x[1])
    src_c = [x for x in src_items if x[2] >= min_share][:top] or src_items[:1]
    tgt_c = [x for x in tgt_items if x[2] >= min_share][:top] or tgt_items[:1]

    cands = []
    for i, (s, sc, ss) in enumerate(src_c):
        for j, (t, tc, ts) in enumerate(tgt_c):
            if s <= 0 or t <= 0:
                continue
            if abs(t / s - 1.0) > max_dev:       # 配对半径
                continue
            size_d = abs(math.log(t / s))
            share_d = abs(math.log((ts + 1e-6) / (ss + 1e-6)))
            cands.append((size_weight * size_d + share_weight * share_d,
                          i, j, s, t, sc, tc, ss, ts))
    cands.sort(key=lambda x: x[0])

    used_s, used_t, pairs = set(), set(), []
    for cost, i, j, s, t, sc, tc, ss, ts in cands:
        if i in used_s or j in used_t:
            continue
        used_s.add(i); used_t.add(j)
        pairs.append({"cost": round(cost, 4), "source_pt": s, "target_pt": t,
                      "source_share": round(ss, 4), "target_share": round(ts, 4),
                      "source_count": sc, "target_count": tc,
                      "deviation_pct": round((t - s) / s * 100, 1)})
    pairs.sort(key=lambda p: -p["source_count"])

    rows = []
    for k, p in enumerate(pairs, 1):
        rows.append({
            "level": k,
            "source_pt": p["source_pt"], "target_pt": p["target_pt"],
            "deviation_pct": p["deviation_pct"],
            "source_share": p["source_share"], "target_share": p["target_share"],
            "over_tolerance": abs(p["deviation_pct"]) > 3.0,
            "match_cost": p["cost"],
            "source_kinds": src["size_kinds"].get(str(p["source_pt"]), {}),
            "target_kinds": tgt["size_kinds"].get(str(p["target_pt"]), {}),
            "source_count": p["source_count"], "target_count": p["target_count"],
        })
    matched_s = {p["source_pt"] for p in pairs}
    matched_t = {p["target_pt"] for p in pairs}
    unpaired = []
    for s, sc, ss in src_c:
        if s not in matched_s:
            unpaired.append({"side": "source", "size_pt": s, "count": sc,
                             "share": round(ss, 4)})
    for t, tc, ts in tgt_c:
        if t not in matched_t:
            unpaired.append({"side": "target", "size_pt": t, "count": tc,
                             "share": round(ts, 4)})

    # 整体尺度：只用"正文级"（占比最大）的字号
    body_s = src_c[0][0] if src_c else None
    body_t = tgt_c[0][0] if tgt_c else None
    scale = {"source_body_pt": body_s, "target_body_pt": body_t,
             "body_scale_ratio": round(body_t / body_s, 4) if (body_s and body_t) else None,
             "source_distinct_sizes": len(src["size_histogram"]),
             "target_distinct_sizes": len(tgt["size_histogram"]),
             "unpaired_levels": unpaired}
    return rows, scale


def side_by_side(src, tgt, tol_pct):  # noqa: D401  (保留旧签名，内部改用配对)
    rows, scale = pair_levels(src, tgt)
    for r in rows:
        r["over_tolerance"] = abs(r["deviation_pct"]) > tol_pct
    return rows, scale


def main():
    ap = argparse.ArgumentParser(description="源/目标 PDF 字号与行距回抽比对")
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--mode", choices=["book", "slide"], default="book")
    ap.add_argument("--pages", help="只比较这些页（两文件同范围），如 2-15")
    ap.add_argument("--tol-pct", type=float, default=None,
                    help="逐级字号偏差容差百分比；默认按 --scale 选（relayout 3，cross-language 10）")
    ap.add_argument("--scale", choices=["relayout", "cross-language", "auto"], default="auto",
                    help="relayout=同一语言重排（严格 ±3%%）；"
                         "cross-language=英/外文源→中文（放宽，中文天然略小）；auto 按字体类型判断")
    ap.add_argument("--global-tol", type=float, default=None,
                    help="正文字号整体比例容差（比例偏离 1±该值即报 global_scale）；默认 relayout 0.08 / cross-language 0.18")
    ap.add_argument("--out")
    ap.add_argument("--report")
    a = ap.parse_args()

    src = extract(Path(a.source), a.pages)
    tgt = extract(Path(a.target), a.pages)

    # 自动判断是否"外文源 → 中文目标"：只看**主体字号**（出现最多的字号）
    # 的字体类型。若不这样限定，数学字体（CMMI 等）会因字号层级多而被误判成主体。
    def dominant_kind(rec):
        if not rec["size_histogram"]:
            return "latin"
        main = max(rec["size_histogram"].items(), key=lambda kv: kv[1])[0]
        kinds = rec["size_kinds"].get(str(main), {})
        if not kinds:
            return "latin"
        return max(kinds.items(), key=lambda kv: kv[1])[0]

    scale_mode = a.scale
    if scale_mode == "auto":
        sk, tk = dominant_kind(src), dominant_kind(tgt)
        scale_mode = "cross-language" if (sk != "cjk" and tk == "cjk") else "relayout"
        print(f"[info] 检测到 源主体字体类型={sk}，目标={tk} → scale={scale_mode}")

    tol = a.tol_pct if a.tol_pct is not None else (3.0 if scale_mode == "relayout" else 10.0)
    gtol = a.global_tol if a.global_tol is not None else (0.08 if scale_mode == "relayout" else 0.18)

    rows, scale = side_by_side(src, tgt, tol)
    # 课件模式下提高"字号贴近度"的权重：15 页文档层级少、中文与公式字号相邻，
    # 按占比配对会把源的小字号配到目标公式级，产生假偏差（实测 7.0 -> 9.0）。
    if scale_mode == "cross-language" and src["pages_total"] <= 30:
        rows, scale = pair_levels(src, tgt, size_weight=3.0, share_weight=0.4)
        for r in rows:
            r["over_tolerance"] = abs(r["deviation_pct"]) > tol

    findings = []
    for r in rows:
        if r["over_tolerance"]:
            findings.append({
                "severity": "error", "code": "size_deviation",
                "message": f"第 {r['level']} 级字号偏差 {r['deviation_pct']}%"
                           f"（源 {r['source_pt']} pt → 目标 {r['target_pt']} pt，"
                           f"超出 ±{tol}%）",
                "source_kinds": r["source_kinds"], "target_kinds": r["target_kinds"]})
    for u in scale.get("unpaired_levels", []):
        findings.append({
            "severity": "info", "code": "level_unpaired",
            "message": f"{u['side']} 侧 {u['size_pt']} pt（占比 {u['share']}）在"
                       f"另一侧没有 ±30% 内的对应层级——可能是该侧独有层级，"
                       f"也可能是层级数量/用途不同，需人工判断"})
    if scale["body_scale_ratio"] is not None:
        br = scale["body_scale_ratio"]
        if br < 1 - gtol or br > 1 + gtol:
            findings.append({
                "severity": "error", "code": "global_scale",
                "message": f"正文字号整体比例 {br}"
                           f"（源 {scale['source_body_pt']} → 目标 {scale['target_body_pt']} pt）"
                           f"，超出 1±{gtol}；≈0.75 即典型的 72/96 整册误缩"})

    # 行距比对：用配对出的"正文级"字号的基础行距
    def body_rhythm(rec, body_size):
        if body_size is None or not rec["size_rhythm"]:
            return None
        return rec["size_rhythm"].get(body_size)

    sr = body_rhythm(src, scale["source_body_pt"])
    tr = body_rhythm(tgt, scale["target_body_pt"])
    lead_cmp = None
    if sr and tr:
        lead_cmp = {
            "source": {"size_pt": scale["source_body_pt"],
                       "gap_pt": sr["base_gap_pt"], "ratio": sr["ratio"]},
            "target": {"size_pt": scale["target_body_pt"],
                       "gap_pt": tr["base_gap_pt"], "ratio": tr["ratio"]},
            "gap_deviation_pct": round((tr["base_gap_pt"] - sr["base_gap_pt"]) /
                                       sr["base_gap_pt"] * 100, 1),
            "ratio_deviation_pct": round((tr["ratio"] - sr["ratio"]) /
                                         sr["ratio"] * 100, 1),
        }
        if abs(lead_cmp["ratio_deviation_pct"]) > 25:
            findings.append({
                "severity": "warn", "code": "leading_ratio_deviation",
                "message": f"行距/字号比偏差 {lead_cmp['ratio_deviation_pct']}%"
                           f"（源 {sr['ratio']} → 目标 {tr['ratio']}）。"
                           "注意：中文通常需要比英文更大的行距（1.5–1.7），"
                           "小幅偏大属正常；超过 25% 才需查因"})

    result = {"source": src, "target": tgt, "levels": rows,
              "scale": scale, "leading_compare": lead_cmp, "findings": findings}
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"[ok] JSON -> {a.out}")
    else:
        print(text)

    if a.report:
        L = [f"# 字号/行距回抽比对 — {Path(a.target).name}", "",
             f"- 源：`{src['path']}`（{src['pages_total']} 页，用 {src['pages_used']}）",
             f"- 目标：`{tgt['path']}`（{tgt['pages_total']} 页，用 {tgt['pages_used']}）",
             f"- 比对模式：`{scale_mode}`　逐级容差：±{tol}%　整体比例容差：1±{gtol}", "",
             "## 字号层级比对（按字号+占比配对，非按大小排序）", "",
             "| 级 | 源 pt | 目标 pt | 偏差 | 源占比 | 目标占比 | 源字体类型 | 目标字体类型 |",
             "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            d = "—" if r["deviation_pct"] is None else f"{r['deviation_pct']}%"
            flag = " ❌" if r["over_tolerance"] else ""
            L.append(f"| {r['level']} | {r['source_pt']} | {r['target_pt']} | {d}{flag} | "
                     f"{r['source_share']} | {r['target_share']} | "
                     f"{r['source_kinds']} | {r['target_kinds']} |")
        L += ["", f"正文字号整体比例：**{scale['body_scale_ratio']}**"
                  f"（源 {scale['source_body_pt']} pt → 目标 {scale['target_body_pt']} pt）", ""]
        if scale.get("unpaired_levels"):
            L += ["未配对的层级（另一侧 ±30% 内无对应）：", ""]
            for u in scale["unpaired_levels"]:
                L.append(f"- {u['side']} {u['size_pt']} pt（占比 {u['share']}，"
                         f"出现 {u['count']} 次）")
            L.append("")
        if lead_cmp:
            L += ["## 行距节律比对", "",
                  f"- 源：{lead_cmp['source']['size_pt']} pt / {lead_cmp['source']['gap_pt']} pt"
                  f"（比例 {lead_cmp['source']['ratio']}）",
                  f"- 目标：{lead_cmp['target']['size_pt']} pt / {lead_cmp['target']['gap_pt']} pt"
                  f"（比例 {lead_cmp['target']['ratio']}）",
                  f"- 基线距偏差 {lead_cmp['gap_deviation_pct']}%，"
                  f"行距比偏差 {lead_cmp['ratio_deviation_pct']}%", ""]
        L += ["## findings", ""]
        for f in findings:
            mark = {"error": "❌", "warn": "⚠️", "info": "ℹ️"}[f["severity"]]
            L.append(f"- {mark} **{f['code']}** — {f['message']}")
        L += ["",
              "> 判读须知：",
              "> 1. 配对按「字号相近 + 出现占比相近」，并限制在 ±30% 半径内；配不上的层级",
              ">    单独报 `level_unpaired`，不会硬塞成巨大偏差。",
              "> 2. 中文与数学常是两个相邻实测值（如 9.46 与 9.96），同层级出现相邻值属正常。",
              "> 3. **整体比例**（`body_scale_ratio`）比逐级偏差更能说明问题：",
              ">    ≈0.75 即典型的 72/96 误缩；≈1.0 说明整体尺度保持。",
              "> 4. 外文源→中文时，中文正文字号**天然可略小于源**（字面率不同），",
              ">    用 `--scale cross-language`（默认自动识别）放宽到 ±10%。"]
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text("\n".join(L), encoding="utf-8")
        print(f"[ok] Markdown -> {a.report}")

    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warn")
    print(f"[summary] error={n_err} warn={n_warn}")
    for f in findings:
        if f["severity"] in ("error", "warn"):
            print(f"  [{f['severity']}] {f['code']}: {f['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
