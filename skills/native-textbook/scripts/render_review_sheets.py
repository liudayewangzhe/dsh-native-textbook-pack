#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_review_sheets.py — 生成"纯视觉审核"用的接触表与高倍页图

配合 references/visual-audit.md 使用。本脚本只做渲染，不做判断：
它保证"该看的页都渲染出来了"并且每张图都有哈希可绑定，避免审核时漏页。

产出（全部在 --out 目录）
------------------------
- `contact-NN.png`   每张 6 页（2×3）的接触表，用于 L1 看整页节奏/留白/对齐
- `hires-pNN.png`    指定页的高倍单页图，用于 L2 看公式分母/积分限/图内标签
- `pdf-pNN.png`      全部页的单页图（`--all-pages` 时）
- `manifest.json`    输入 PDF 与其 sha256、每张 PNG 的 sha256、缩放倍数、工具链

另外可调用 Poppler `pdftoppm` 做**第二个渲染器**的交叉渲染（推荐，不同渲染器
暴露不同缺陷）。找不到 pdftoppm 时跳过并如实记录，不伪造。

用法
----
    python render_review_sheets.py --pdf "项目\\out\\main.pdf" --out "项目\\qa\\review" \\
        --sheet-pages 6 --thumb-width 480 \\
        --hi-res-pages "1,3,5,6,8,10,11,13,15" --hi-res-zoom 3

    # 全书单页渲染 + 独立渲染器交叉核对
    python render_review_sheets.py --pdf main.pdf --out qa/review --all-pages --poppler-dpi 144
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    print("需要 PyMuPDF：pip install pymupdf", file=sys.stderr)
    raise SystemExit(2)

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pages(spec: str, total: int):
    if not spec:
        return []
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in sorted(set(out)) if 1 <= p <= total]


def render_page(doc, pno: int, zoom: float):
    pix = doc[pno - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix


def main():
    ap = argparse.ArgumentParser(description="生成视觉审核用的接触表与高倍页图")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet-pages", type=int, default=6, help="每张接触表放几页（默认6）")
    ap.add_argument("--thumb-width", type=int, default=480, help="缩略图宽度像素（默认480）")
    ap.add_argument("--hi-res-pages", default="", help='高倍页，如 "1,3,5-8"')
    ap.add_argument("--hi-res-zoom", type=float, default=3.0, help="高倍倍数（默认3 ≈216dpi）")
    ap.add_argument("--all-pages", action="store_true", help="渲染全部页的单页图")
    ap.add_argument("--cols", type=int, default=3, help="接触表列数（默认3）")
    ap.add_argument("--label-pages", action="store_true", default=True,
                    help="在缩略图角落标注页码（默认开）")
    ap.add_argument("--poppler-dpi", type=int, default=0,
                    help=">0 时另用 pdftoppm 以该 dpi 渲染全部页做交叉核对")
    ap.add_argument("--no-sheets", action="store_true", help="不生成接触表")
    a = ap.parse_args()

    pdf = Path(a.pdf)
    if not pdf.exists():
        print(f"[error] 找不到 {pdf}", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf)
    total = doc.page_count
    pdf_hash = sha256_file(pdf)
    manifest = {
        "pdf": str(pdf.resolve()),
        "pdf_sha256": pdf_hash,
        "pdf_bytes": pdf.stat().st_size,
        "pages_total": total,
        "rendered_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "tools": {"pymupdf": fitz.__doc__},
        "files": [],
        "skipped": [],
    }
    print(f"[info] {pdf.name}: {total} 页, sha256={pdf_hash[:16]}…")

    def record(name: str, path: Path, kind: str, pages, zoom=None, dpi=None):
        e = {"file": name, "kind": kind, "pages": pages,
             "sha256": sha256_file(path), "bytes": path.stat().st_size}
        if zoom:
            e["zoom"] = zoom
        if dpi:
            e["dpi"] = dpi
        manifest["files"].append(e)

    # ---- 单页缩略图缓存（生成接触表时复用）
    cache = {}

    def thumb_pixmap(pno: int, target_w: int):
        key = (pno, target_w)
        if key not in cache:
            pw = max(doc[pno - 1].rect.width, 1)
            cache[key] = doc[pno - 1].get_pixmap(
                matrix=fitz.Matrix(target_w / pw, target_w / pw), alpha=False)
        return cache[key]

    # ---- L1 接触表
    if not a.no_sheets:
        if Image is None:
            print("[warn] 未安装 Pillow，跳过接触表（L1）。请 pip install pillow",
                  file=sys.stderr)
            manifest["skipped"].append("contact sheets: Pillow not installed")
        else:
            per = max(1, a.sheet_pages)
            rows = (per + a.cols - 1) // a.cols
            sheet_pages = [list(range(i, min(i + per, total) + 1))
                           for i in range(1, total + 1, per)]
            # 先渲染一张算出单元格高度
            first = render_page(doc, 1, 1.0)
            aspect = first.height / max(first.width, 1)
            cw = a.thumb_width
            ch = int(cw * aspect)
            pad, cap = 10, 18
            for si, pages in enumerate(sheet_pages, 1):
                cols_used = min(a.cols, len(pages))
                W = cols_used * (cw + pad) + pad
                H = rows * (ch + cap + pad) + pad
                sheet = Image.new("RGB", (W, H), "#e8e8e8")
                dr = ImageDraw.Draw(sheet)
                for k, pno in enumerate(pages):
                    pix = thumb_pixmap(pno, cw)
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    if im.width != cw:
                        im = im.resize((cw, int(im.height * cw / im.width)))
                    cx = pad + (k % a.cols) * (cw + pad)
                    cy = pad + (k // a.cols) * (ch + cap + pad)
                    sheet.paste(im, (cx, cy))
                    if a.label_pages:
                        dr.text((cx + 2, cy + ch + 2), f"p{pno}", fill="black")
                name = f"contact-{si:02d}.png"
                p = out / name
                sheet.save(p)
                record(name, p, "contact_sheet", pages)
            print(f"[ok] {len(sheet_pages)} 张接触表（每张 {per} 页）")

    # ---- L2 高倍页
    hi = parse_pages(a.hi_res_pages, total)
    for pno in hi:
        pix = render_page(doc, pno, a.hi_res_zoom)
        name = f"hi-res-p{pno:02d}.png"
        p = out / name
        pix.save(str(p))
        record(name, p, "hi_res_page", [pno], zoom=a.hi_res_zoom)
    if hi:
        print(f"[ok] {len(hi)} 张高倍页图 zoom={a.hi_res_zoom}（≈{a.hi_res_zoom*72:.0f} dpi）")

    # ---- 全部单页
    if a.all_pages:
        for pno in range(1, total + 1):
            pix = render_page(doc, pno, 1.0)
            name = f"pdf-p{pno:02d}.png"
            p = out / name
            pix.save(str(p))
            record(name, p, "page_1x", [pno], zoom=1.0)
        print(f"[ok] {total} 张单页图 (1x)")

    doc.close()

    # ---- 第二渲染器（Poppler）交叉核对
    if a.poppler_dpi > 0:
        exe = shutil.which("pdftoppm")
        if not exe:
            print("[warn] 未找到 pdftoppm，跳过 Poppler 交叉渲染（如实记入 manifest）",
                  file=sys.stderr)
            manifest["skipped"].append("poppler: pdftoppm not found on PATH")
        else:
            prefix = out / "poppler"
            cmd = [exe, "-r", str(a.poppler_dpi), "-png", str(pdf), str(prefix)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"[warn] pdftoppm 退出码 {r.returncode}: {r.stderr.strip()[:300]}",
                      file=sys.stderr)
                manifest["skipped"].append(f"poppler failed rc={r.returncode}")
            else:
                got = sorted(out.glob("poppler-*.png"))
                for p in got:
                    record(p.name, p, "poppler_page", [], dpi=a.poppler_dpi)
                print(f"[ok] Poppler {a.poppler_dpi} dpi 渲染 {len(got)} 页（第二渲染器）")

    mp = out / "manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] manifest -> {mp}")
    print(f"[next] 用 read_image 实际查看 contact-*.png（L1）与 hi-res-p*.png（L2）；"
          f"审查记录绑定 pdf_sha256={pdf_hash[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
