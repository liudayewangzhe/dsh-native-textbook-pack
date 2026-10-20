#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_typography.py — 排版与视觉缺陷的确定性检查器（原生中文教材 / 课件 PDF）

为什么需要它：编译成功、文字可抽取、页数正确，都不能证明"看起来是对的"。
本脚本只产出版式的**几何事实**，供"纯视觉审核"这一步定位问题；它不能替代看图。

检查项
------
1. 纸外文字 / 纸外图形     无限裁剪，避免默认页面 clip 掩盖已越纸内容
2. 文字互相重叠            逐对相交面积 + IoU，排除同基线续排与上标/下标误报
3. 文字与图形遮挡          正文文字被填充图形盖住（横幅、色块、TikZ 覆盖层）
4. 行距（leading）         相邻行基线距，按字号归一化，报告众数与离群
5. 字号清单                正文/标题/公式/脚注的号数分布，检出"整册缩小"事故
6. 版心与留白              正文左右/上下边界、单行最长宽度、页脚/页眉基线位置
7. 行末填充率              两端对齐是否留下大空洞（<92% 且非段末即可疑）
8. 文本块垂直碎块          同一栏内段落被浮动体切成多块、跨页断段
9. 栅格/矢量组成           每页 image occurrences 与矢量 drawing 数量
10. 段落缩进与段间距       首行缩进、段间距是否一致

用法
----
    python check_typography.py --pdf "项目\\main.pdf" --mode book   --out qa\\typo.json
    python check_typography.py --pdf "项目\\main.pdf" --mode slide  --out qa\\typo.json
    python check_typography.py --pdf a.pdf --mode book --report qa\\typo.md --fail-on error

`--mode` 只决定阈值预设，不改变测量方式。所有 bbox 均为 PDF pt、页面左上原点、
坐标已经过页面旋转归一化。退出码：0 = 无 error；1 = 有 error（用 --fail-on error）。
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

# ---------------------------------------------------------------- 阈值预设
PRESETS = {
    "book": {
        "bleed_pt": 0.6,            # 允许的越界容差（发排出血/数学斜体探出）
        "overlap_area_pt2": 3.0,    # 文字互相重叠的显著性阈值
        "overlap_iou": 0.18,        # IoU 超过它才报警，避免上下标误报
        # 正文行距/字号比。实测两本成熟中文教材（金融物理、经典力学）均为 1.61。
        "leading_ratio_min": 1.30,  # 低于此中文正文过挤（1.2 是绝对下限）
        "leading_ratio_max": 2.10,  # 上限，超过则版面松散
        "leading_outlier": 0.22,    # 相对该字号基础行距的偏离比例
        "body_size_min_pt": 8.5,    # 正文最小可读字号
        "fill_ratio_min": 0.92,     # 非段末行末填充率下限（两端对齐空洞）
        "margin_min_pt": 28.0,      # 正文距纸边最小留白（约 10 mm）
        "chunk_gap_pt": 26.0,       # 同栏内两个文本块的垂直间隔超过它算被切开
    },
    "slide": {
        "bleed_pt": 0.6,
        "overlap_area_pt2": 2.0,
        "overlap_iou": 0.14,
        "leading_ratio_min": 1.20,
        "leading_ratio_max": 2.40,
        "leading_outlier": 0.35,
        "body_size_min_pt": 8.0,    # 4:3 课件按原比例缩到 128 mm 宽，正文约 9.5 pt
        "fill_ratio_min": 0.90,
        "margin_min_pt": 14.0,
        "chunk_gap_pt": 34.0,
    },
}

# 数学/等宽字体族提示（用于分类，不要求精确）
MATH_HINTS = ("math", "cmmi", "cmsy", "cmex", "cmr", "cmmib", "msam", "msbm",
              "stix", "xits", "latinmodern-math", "euler", "cambria math", "asana",
              "nimbusroman", "texgyretermes", "texgyrepagella", "lmroman",
              "mnsymbol", "txfonts", "mathtime", "kpfonts")
MONO_HINTS = ("mono", "courier", "consol", "menlo", "dejavu sans mono", "lmmono",
              "typewriter", "tt")
CJK_HINTS = ("cjk", "song", "hei", "kai", "ming", "yahei", "simsun", "simhei",
             "fangsong", "noto sans sc", "noto serif sc", "source han", "stsong",
             "stheiti", "arphic", "uming", "ukai", "wqy", "msyh", "msjh",
             "pingfang", "hiragino", "gothic", "batang", "gulim", "fangzheng")

# 数学排版会把一个大公式拆成大量单字形 span，它们的 bbox 必然相交。
# 参与"互相重叠"判定的字符：任何有字面的字符都算，但纯符号/框线字形除外。
_SYMBOL_ONLY = set("⎛⎜⎝⎞⎟⎠⎡⎢⎣⎤⎥⎦√⏟⏞⏜⏝⌈⌉⌊⌋()[]{}/|\\_-+=<>~^·⋅∙…⋯")


def kind_of(font: str) -> str:
    f = font.lower()
    # CJK 优先：字体名里同时含 latin 与 cjk 标记时仍属 CJK 载体
    if any(h in f for h in CJK_HINTS):
        return "cjk"
    if any(h in f for h in MATH_HINTS):
        return "math"
    if any(h in f for h in MONO_HINTS):
        return "mono"
    return "latin"


def is_symbol_noise(text: str) -> bool:
    """纯符号/纯框线字形：数学括号、根号、underbrace 等，重叠属排版正常。"""
    t = "".join(ch for ch in text if not ch.isspace())
    if not t:
        return True
    return all(ch in _SYMBOL_ONLY for ch in t)


def rect_intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def normalize_page(page):
    """返回页面在旋转归一化后的矩形。PyMuPDF 的 page.rect 已随旋转调整。"""
    return page.rect


def collect_lines(page):
    """抽取文字行：bbox、基线(origin)、字号、字体、颜色、文本。"""
    out = []
    d = page.get_text("dict")
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            size = max(s["size"] for s in spans)
            main = max(spans, key=lambda s: (s["bbox"][2] - s["bbox"][0]) * (s["bbox"][3] - s["bbox"][1]))
            out.append({
                "bbox": [x0, y0, x1, y1],
                "origin": [float(main["origin"][0]), float(main["origin"][1])],
                "size": float(size),
                "font": main["font"],
                "kind": kind_of(main["font"]),
                "color": int(main.get("color", 0)),
                "text": "".join(s["text"] for s in spans),
                "block": b.get("number", -1),
            })
    return out


def int_to_rgb(v: int):
    return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def rel_luminance(rgb):
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb1, rgb2):
    l1, l2 = rel_luminance(rgb1), rel_luminance(rgb2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def collect_graphics(page):
    """填充图形（可能盖住文字）与全部图形 bbox，并记录填充色。"""
    filled, allg = [], []
    try:
        for dr in page.get_drawings():
            r = dr.get("rect")
            if r is None:
                continue
            bbox = [r.x0, r.y0, r.x1, r.y1]
            allg.append(bbox)
            if dr.get("fill") is not None:
                filled.append((bbox, dr.get("fill")))
    except Exception:
        pass
    return filled, allg


def analyse_page(page, pno, cfg, prev_tail):
    R = normalize_page(page)
    W, H = R.width, R.height
    lines = collect_lines(page)
    filled, allg = collect_graphics(page)

    res = {
        "page": pno, "size_pt": [round(W, 2), round(H, 2)],
        "n_lines": len(lines), "n_filled": len(filled), "n_drawings": len(allg),
        "overflow_text": [], "overflow_graphics": [], "overlaps": [],
        "obscured": [], "leading_outliers": [], "underfull": [],
    }
    eps = cfg["bleed_pt"]

    # 1) 纸外内容（无限裁剪，不用 clip 先剪掉）
    for ln in lines:
        b = ln["bbox"]
        if b[0] < -eps or b[1] < -eps or b[2] > W + eps or b[3] > H + eps:
            res["overflow_text"].append({
                "text": ln["text"][:60], "bbox": [round(v, 2) for v in b],
                "over_pt": round(max(-b[0], -b[1], b[2] - W, b[3] - H), 2)})
    for b in allg:
        if b[0] < -eps or b[1] < -eps or b[2] > W + eps or b[3] > H + eps:
            res["overflow_graphics"].append({
                "bbox": [round(v, 2) for v in b],
                "over_pt": round(max(-b[0], -b[1], b[2] - W, b[3] - H), 2)})
            if len(res["overflow_graphics"]) > 40:
                break

    # 2) 文字互相重叠
    # 只比较"文字性"行（CJK / latin / mono）。数学行是逐字形 span，bbox 天然相交，
    # 纯符号字形（⎛⎟⏟√）也属正常排版，二者都不参与判定。
    cand = [i for i, ln in enumerate(lines)
            if ln["kind"] != "math" and not is_symbol_noise(ln["text"])]
    order = sorted(cand, key=lambda i: (lines[i]["bbox"][1], lines[i]["bbox"][0]))
    for ai in range(len(order)):
        i = order[ai]
        a = lines[i]
        for bi in range(ai + 1, len(order)):
            j = order[bi]
            b = lines[j]
            if b["bbox"][1] > a["bbox"][3] + 0.5:      # 已按 y 排序，可提前结束
                break
            inter = rect_intersect(a["bbox"], b["bbox"])
            if inter <= 0:
                continue
            ar = (a["bbox"][2] - a["bbox"][0]) * (a["bbox"][3] - a["bbox"][1])
            br = (b["bbox"][2] - b["bbox"][0]) * (b["bbox"][3] - b["bbox"][1])
            union = ar + br - inter
            iou = inter / union if union > 0 else 0
            sa, sb = a["size"], b["size"]
            # 排除上下标/同基线续排：字号差异大或基线非常接近但水平错开
            base_gap = abs(a["origin"][1] - b["origin"][1])
            if base_gap < 0.35 * min(sa, sb):
                continue
            # 中文没有词间空格，同一段被拆成多行的行盒可能轻微相触：要求明显相交
            if inter < cfg["overlap_area_pt2"] or iou < cfg["overlap_iou"]:
                continue
            res["overlaps"].append({
                "a": a["text"][:40], "b": b["text"][:40],
                "inter_pt2": round(inter, 2), "iou": round(iou, 3),
                "bbox_a": [round(v, 1) for v in a["bbox"]],
                "bbox_b": [round(v, 1) for v in b["bbox"]]})

    # 3) 文字被填充图形盖住
    # 判据：文字有实际内容（非纯符号、非单个数学字形），其中心落在某个填充图形内，
    # 该图形不是整页底色、也不是高亮块。再按填充色与文字色的对比度分级：
    #   对比度 < 2.0  → error：文字几乎与底色同色，实际不可见（真正被盖住）
    #   对比度 >= 2.0 → warn ：文字压在色块上（多半是设计底色，需目检确认可读）
    page_area = W * H
    for ln in lines:
        if is_symbol_noise(ln["text"]) or len("".join(ln["text"].split())) < 2:
            continue
        b = ln["bbox"]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        for g, gcol in filled:
            if not (g[0] <= cx <= g[2] and g[1] <= cy <= g[3]):
                continue
            garea = max((g[2] - g[0]) * (g[3] - g[1]), 1e-6)
            tarea = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
            if garea > 0.6 * page_area:      # 整页/近整页底色，属背景
                break
            if garea <= 3.0 * tarea:         # 高亮块/公式底色，正常
                break
            tcol = int_to_rgb(ln.get("color", 0))
            gcol_rgb = tuple(int(round(c * 255)) for c in gcol[:3]) if gcol else (255, 255, 255)
            cr = round(contrast_ratio(tcol, gcol_rgb), 2)
            res["obscured"].append({
                "text": ln["text"][:50],
                "text_bbox": [round(v, 1) for v in b],
                "fill_bbox": [round(v, 1) for v in g],
                "text_rgb": list(tcol), "fill_rgb": list(gcol_rgb),
                "contrast": cr,
                "severity": "error" if cr < 2.0 else "warn"})
            break

    # 4) 行距（垂直节奏）—— 按字号分层
    #    做法：先把行按字号分箱（±0.2 pt），同一字号内部统计相邻基线差的直方图
    #    取众数，即该字号的"基础行距"。理由：一个 page 里正文 10.9 pt、边注
    #    9.0 pt、公式 10 pt 的行距不同；混在一起统计会得到不存在的中间值。
    #    实测校准：金融物理与经典力学两份成熟中文书的正文都是 10.9 pt / 17.5 pt
    #    （比例 1.61），边注 9.0 pt / 16–17 pt。偏离该字号基础行距的间隔另记。
    seq = sorted([ln for ln in lines], key=lambda l: (l["origin"][1], l["bbox"][0]))
    by_size = defaultdict(list)
    for a, b in zip(seq, seq[1:]):
        s1, s2 = a["size"], b["size"]
        if s1 <= 1 or abs(s1 - s2) > 0.2:
            continue
        gap = b["origin"][1] - a["origin"][1]
        if gap <= 0.5 or not (0.9 * s1 <= gap <= 2.4 * s1):
            continue
        by_size[round(s1, 1)].append((gap, a["text"][:28], b["text"][:28]))

    leadings = []
    size_rhythm = {}
    for size, items in by_size.items():
        bins = Counter(round(g * 2) / 2 for g, _, _ in items)
        top = bins.most_common(1)[0]
        if top[1] < 2:                      # 样本太少，不足以断定节奏
            continue
        base = top[0]
        size_rhythm[size] = {"base_gap_pt": base, "count": top[1],
                             "total": len(items), "ratio": round(base / size, 3)}
        tol = max(0.6, 0.06 * base)
        for g, ta, tb in items:
            if abs(g - base) <= tol:
                leadings.append((g, g / size, size, ta, tb))
            else:
                res["leading_outliers"].append(
                    {"size_pt": size, "gap_pt": round(g, 2), "ratio": round(g / size, 3),
                     "base_gap_pt": base, "a": ta, "b": tb})
    res["_size_rhythm"] = size_rhythm

    # 8) 文本块垂直碎块（正文被浮动体切开 / 同栏被切成多块）
    res["chunks"] = []
    by_col2 = defaultdict(list)
    for ln in lines:
        if ln["kind"] == "math":
            continue
        by_col2[round(ln["bbox"][0] / 40.0)].append(ln)
    for _, col in by_col2.items():
        col.sort(key=lambda l: l["origin"][1])
        run = [col[0]] if col else []
        for a, b in zip(col, col[1:]):
            gap = b["origin"][1] - a["origin"][1]
            if gap > cfg["chunk_gap_pt"]:
                res["chunks"].append({"from": run[0]["text"][:28], "to": run[-1]["text"][:28],
                                      "lines": len(run)})
                run = []
            run.append(b)
        if run:
            res["chunks"].append({"from": run[0]["text"][:28], "to": run[-1]["text"][:28],
                                  "lines": len(run)})

    # 7) 行末填充率
    right_edges = [ln["bbox"][2] for ln in lines if (ln["bbox"][2] - ln["bbox"][0]) > 40]
    if right_edges:
        right_edges.sort()
        mode_right = right_edges[int(len(right_edges) * 0.9)]
        for ln in lines:
            w = ln["bbox"][2] - ln["bbox"][0]
            if w <= 40 or w >= mode_right - 0.5:
                continue
            ratio = w / mode_right if mode_right else 1
            if ratio < cfg["fill_ratio_min"]:
                res["underfull"].append({"text": ln["text"][:50], "ratio": round(ratio, 3),
                                         "bbox": [round(v, 1) for v in ln["bbox"]]})

    # 5/6) 版心与留白、字号清单（页级聚合，全局汇总时再算）
    # 只用"成行的正文"（宽度 >= 版心 60%）判断边距；标题带、页脚横线、
    # 装饰色块贴边属设计，不是边距过小。
    long_lines = [ln for ln in lines if (ln["bbox"][2] - ln["bbox"][0]) > 40]
    body_left = body_right = None
    if long_lines:
        rights = sorted(l["bbox"][2] for l in long_lines)
        ref_right = rights[int(len(rights) * 0.9)]
        la = min(l["bbox"][0] for l in long_lines)
        ref_w = ref_right - la
        full = [l for l in long_lines if ref_w > 0 and
                (l["bbox"][2] - l["bbox"][0]) >= 0.6 * ref_w]
        if full:
            body_left = min(l["bbox"][0] for l in full)
            body_right = max(l["bbox"][2] for l in full)
        else:
            body_left, body_right = la, ref_right
    res["body_box"] = None if body_left is None else [
        round(body_left, 2), round(body_right, 2)]
    res["_leadings"] = leadings
    res["_lines"] = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in ln.items()}
                     for ln in lines if ln["kind"] != "math"]
    return res


def aggregate(pages, cfg):
    all_leading = [x for p in pages for x in p["_leadings"]]
    # 合并各页的按字号节奏表
    rhythm = defaultdict(lambda: {"count": 0, "total": 0, "gap_weighted": 0.0})
    for p in pages:
        for size, r in p["_size_rhythm"].items():
            e = rhythm[size]
            e["count"] += r["count"]
            e["total"] += r["total"]
            e["gap_weighted"] += r["base_gap_pt"] * r["count"]
    size_rhythm = {}
    for size, e in rhythm.items():
        base = e["gap_weighted"] / e["count"] if e["count"] else 0
        size_rhythm[size] = {"base_gap_pt": round(base, 2), "ratio": round(base / size, 3),
                             "lines": e["total"]}

    agg = {
        "leading_count": len(all_leading),
        "leading_gap_mode": None, "leading_ratio_mode": None,
        "leading_ratio_p05": None, "leading_ratio_p95": None,
        "leading_outliers": [],
    }
    if all_leading:
        ratios = sorted(r for _, r, _, _, _ in all_leading)
        gaps = [g for g, _, _, _, _ in all_leading]
        agg["leading_ratio_mode"] = round(Counter(round(r, 2) for r in ratios).most_common(1)[0][0], 3)
        agg["leading_gap_mode"] = round(Counter(round(g, 1) for g in gaps).most_common(1)[0][0], 2)
        agg["leading_ratio_p05"] = round(ratios[int(len(ratios) * 0.05)], 3)
        agg["leading_ratio_p95"] = round(ratios[int(len(ratios) * 0.95)], 3)
    agg["size_rhythm"] = dict(sorted(size_rhythm.items(), key=lambda kv: -kv[1]["lines"]))

    sizes = Counter()
    fonts = Counter()
    kinds = Counter()
    for p in pages:
        for ln in p["_lines"]:
            sizes[round(ln["size"], 1)] += 1
            fonts[ln["font"]] += 1
            kinds[ln["kind"]] += 1
    agg["size_histogram"] = dict(sorted(sizes.items(), key=lambda kv: -kv[1]))
    agg["font_usage"] = dict(fonts.most_common(30))
    agg["kind_usage"] = dict(kinds)
    return agg


def build_findings(pages, agg, cfg, mode):
    F = []

    def add(sev, code, msg, **kw):
        F.append(dict(severity=sev, code=code, message=msg, **kw))

    ov = [p for p in pages if p["overflow_text"]]
    add("error" if ov else "ok", "text_off_paper",
        f"{len(ov)} 页存在越出纸张的正文行（无限裁剪检出）",
        pages=[p["page"] for p in ov][:30])

    og = [p for p in pages if p["overflow_graphics"]]
    add("warn" if og else "ok", "graphics_off_paper",
        f"{len(og)} 页存在越出纸张的图形对象（可能是装饰出血，也可能是裁切事故）",
        pages=[p["page"] for p in og][:30])

    ol = [p for p in pages if p["overlaps"]]
    n_ol = sum(len(p["overlaps"]) for p in ol)
    add("error" if n_ol else "ok", "text_overlap",
        f"{n_ol} 处文字互相重叠，分布在 {len(ol)} 页（先看图确认不是上标误报）",
        pages=[p["page"] for p in ol][:30])

    ob = [p for p in pages if p["obscured"]]
    n_ob = sum(len(p["obscured"]) for p in ob)
    blind = [o for p in ob for o in p["obscured"] if o.get("severity") == "error"]
    add("error" if blind else ("warn" if n_ob else "ok"), "text_obscured_by_fill",
        f"{n_ob} 处文字压在填充图形上；其中 {len(blind)} 处文字色与底色对比度 <2.0，"
        f"实际不可见（真正被盖住）。其余为设计底色，须目检确认可读",
        pages=[p["page"] for p in ob][:30],
        blind_examples=[{k: o[k] for k in ("text", "contrast", "text_rgb", "fill_rgb")}
                        for o in blind[:8]])

    lr = agg.get("leading_ratio_mode")
    rhythm = agg.get("size_rhythm", {})
    body_rhythm = next(iter(rhythm.items()), None)
    if body_rhythm:
        bsize, br = body_rhythm
        msg = (f"正文 {bsize} pt 基础行距 {br['base_gap_pt']} pt（比例 {br['ratio']}，"
               f"预设 {cfg['leading_ratio_min']}–{cfg['leading_ratio_max']}）；"
               f"各字号节奏 " +
               "，".join(f"{s}pt→{r['base_gap_pt']}pt" for s, r in list(rhythm.items())[:5]))
        sev = "error" if br["ratio"] < cfg["leading_ratio_min"] else \
              ("warn" if br["ratio"] > cfg["leading_ratio_max"] else "ok")
        add(sev, "leading", msg)
    elif lr is None:
        add("info", "leading", "未能得到稳定的行距节奏（正文行样本太少）")

    lo = [p for p in pages if p["leading_outliers"]]
    n_lo = sum(len(p["leading_outliers"]) for p in lo)
    add("info" if n_lo else "ok", "leading_outlier",
        f"{n_lo} 处行距偏离该字号基础行距 >{int(cfg['leading_outlier']*100)}%"
        "（公式/表格撑开属正常，连续出现说明段落间距不一致）",
        pages=[p["page"] for p in lo][:30])

    hist = agg.get("size_histogram", {})
    body = max(hist.items(), key=lambda kv: kv[1])[0] if hist else None
    if body is not None:
        small = {k: v for k, v in hist.items() if k < cfg["body_size_min_pt"] and v > 3}
        add("warn" if small else "ok", "body_size",
            f"出现次数最多的字号 {body} pt；小于下限 {cfg['body_size_min_pt']} pt 且出现>3次的字号：{small or '无'}"
            "（若整册字号被 72/96 缩小，这里会整体下移）")

    uf = [p for p in pages if p["underfull"]]
    n_uf = sum(len(p["underfull"]) for p in uf)
    add("info" if n_uf else "ok", "underfull_lines",
        f"{n_uf} 行行末填充率 <{cfg['fill_ratio_min']}（段末正常；连续多行说明对齐/断词没做好）",
        pages=[p["page"] for p in uf][:30])

    mr = cfg["margin_min_pt"]
    tight = [p for p in pages if p["body_box"] and (p["body_box"][0] < mr or
                                                    p["size_pt"][0] - p["body_box"][1] < mr)]
    # 课件常按原比例满幅排版，边距小不等于错，故降级为 info；书籍仍算 warn。
    add("warn" if (tight and mode == "book") else ("info" if tight else "ok"), "tight_margin",
        f"{len(tight)} 页正文距纸边 <{mr} pt（书籍应为 warn；课件按原始比例可能属设计）",
        pages=[p["page"] for p in tight][:30])

    return F


def summarize(pages):
    return [{"page": p["page"], "size_pt": p["size_pt"], "lines": p["n_lines"],
             "drawings": p["n_drawings"], "filled": p["n_filled"],
             "body_box": p["body_box"]} for p in pages]


def main():
    ap = argparse.ArgumentParser(description="原生中文 PDF 排版与视觉缺陷确定性检查")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--mode", choices=sorted(PRESETS), default="book")
    ap.add_argument("--out", help="JSON 报告路径")
    ap.add_argument("--report", help="Markdown 报告路径")
    ap.add_argument("--pages", help="只查指定页，如 1-20,35")
    ap.add_argument("--fail-on", choices=["error", "warn", "never"], default="never")
    ap.add_argument("--max-pages", type=int, default=0, help="0 表示全部")
    a = ap.parse_args()

    cfg = PRESETS[a.mode]
    doc = fitz.open(a.pdf)
    want = None
    if a.pages:
        want = set()
        for part in a.pages.split(","):
            if "-" in part:
                s, e = part.split("-")
                want.update(range(int(s), int(e) + 1))
            else:
                want.add(int(part))

    pages = []
    n = doc.page_count if not a.max_pages else min(doc.page_count, a.max_pages)
    for i in range(n):
        pno = i + 1
        if want and pno not in want:
            continue
        pages.append(analyse_page(doc[i], pno, cfg, None))
    doc.close()

    agg = aggregate(pages, cfg)
    findings = build_findings(pages, agg, cfg, a.mode)

    head = {
        "pdf": str(Path(a.pdf).resolve()),
        "mode": a.mode,
        "pages_total": n,
        "pages_checked": len(pages),
        "thresholds": cfg,
        "font_usage": agg["font_usage"],
        "kind_usage": agg["kind_usage"],
        "size_histogram": agg["size_histogram"],
        "leading": {k: agg[k] for k in ("leading_ratio_mode", "leading_gap_mode",
                                        "leading_ratio_p05", "leading_ratio_p95",
                                        "leading_outliers")},
        "size_rhythm": agg["size_rhythm"],
    }
    # 精简页记录
    slim = []
    for p in pages:
        q = {k: v for k, v in p.items() if not k.startswith("_")}
        q["leading_samples"] = [{"ratio": round(r, 3), "gap": round(g, 2), "size": round(s, 2)}
                                for g, r, s, _, _ in p["_leadings"][:400]]
        q["chunks"] = p["chunks"]
        slim.append(q)

    result = {"header": head, "findings": findings, "pages": slim}
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"[ok] JSON -> {a.out}")
    else:
        print(text)

    if a.report:
        L = [f"# 排版检查报告 — {Path(a.pdf).name}", "",
             f"- 模式：{a.mode}　检查页数：{len(pages)}/{n}",
             f"- 字号直方图（pt: 次数）：{agg.get('size_histogram')}",
             f"- 页数字号节奏（字号→基础行距）：" +
             "，".join(f"{s}pt→{r['base_gap_pt']}pt(比例{r['ratio']})"
                       for s, r in list(agg.get("size_rhythm", {}).items())[:6]), "",
             "## 结论", ""]
        for f in findings:
            mark = {"error": "❌", "warn": "⚠️", "info": "ℹ️", "ok": "✅"}[f["severity"]]
            L.append(f"- {mark} **{f['code']}** — {f['message']}")
            if f.get("pages"):
                L.append(f"  - 页：{f['pages']}")
            for ex in f.get("blind_examples", [])[:5]:
                L.append(f"  - 不可见文字示例：`{ex['text']}` 文字色{ex['text_rgb']} "
                         f"底色{ex['fill_rgb']} 对比度{ex['contrast']}")
        L += ["", "## 逐页几何", "",
              "| 页 | 尺寸pt | 行数 | 矢量对象 | 填充 | 正文左右边界 |", "|---|---|---|---|---|---|"]
        for p in pages:
            bb = p["body_box"] or ["-", "-"]
            L.append(f"| {p['page']} | {p['size_pt'][0]}×{p['size_pt'][1]} | {p['n_lines']} | "
                     f"{p['n_drawings']} | {p['n_filled']} | {bb[0]}–{bb[1]} |")
        L += ["", "> 几何事实不等于视觉正确。必须再对标记页做逐页看图（见 visual-audit.md）。"]
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text("\n".join(L), encoding="utf-8")
        print(f"[ok] Markdown -> {a.report}")

    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warn")
    print(f"[summary] error={n_err} warn={n_warn}")
    for f in findings:
        if f["severity"] in ("error", "warn"):
            print(f"  [{f['severity']}] {f['code']}: {f['message']}")

    if a.fail_on == "error" and n_err:
        return 1
    if a.fail_on == "warn" and (n_err or n_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
