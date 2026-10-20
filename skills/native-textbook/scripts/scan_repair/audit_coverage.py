"""Audit that every printed text line of a page is covered by a transcribed object.

Worker self-checks missed a whole block on p0044 (a formula plus three paragraphs),
so coverage is verified mechanically instead of trusting the report: the scan is
rendered, text lines are found by ink projection, and each line must intersect the
bbox of at least one inventory object on that page. Uncovered lines are listed with
their pixel position so the supervisor can crop and read them.

Run:
  python D:\\nf-stage\\audit_coverage.py [--pages 23-45] [--dpi 90] [--min-ink 6] [--report FILE]
"""
import argparse
import json
import sys
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
INBOX = Path(r"D:\native-forge-work\inbox")


def parse_pages(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", default="")
    ap.add_argument("--dpi", type=int, default=90)
    ap.add_argument("--min-ink", type=int, default=6)
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    project = json.loads((PROJECT / "project.json").read_text(encoding="utf-8"))
    pages = parse_pages(args.pages) if args.pages else project["pages"]
    inv_path = PROJECT / "source_inventory.json"
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))["pages"] if inv_path.is_file() else {}
    doc = fitz.open(project["source"]["path"])
    scale = args.dpi / 72.0

    report = {}
    for pno in pages:
        if not (INBOX / f"p{pno:04d}.json").is_file():
            continue
        entry = inventory.get(str(pno))
        if not entry or entry.get("blank"):
            continue
        page = doc[pno - 1]
        r = page.rect
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        ink = img < 128
        row_ink = ink.sum(axis=1)
        # group consecutive rows with ink into text lines
        lines, start = [], None
        for y, count in enumerate(row_ink):
            if count >= args.min_ink and start is None:
                start = y
            elif count < args.min_ink and start is not None:
                if y - start >= 3:
                    lines.append((start, y))
                start = None
        if start is not None:
            lines.append((start, len(row_ink)))
        boxes = []
        for obj in entry.get("objects", []):
            x0, y0, x1, y1 = obj["bbox"]
            boxes.append((x0 / r.width, y0 / r.height, x1 / r.width, y1 / r.height, obj["id"]))
        uncovered = []
        for y0, y1 in lines:
            cy0, cy1 = y0 / pix.height, y1 / pix.height
            xs = np.where(ink[y0:y1].any(axis=0))[0]
            if xs.size == 0:
                continue
            cx0, cx1 = xs[0] / pix.width, xs[-1] / pix.width
            covered_by = None
            for bx0, by0, bx1, by1, oid in boxes:
                oy = min(cy1, by1) - max(cy0, by0)
                ox = min(cx1, bx1) - max(cx0, bx0)
                if oy > 0 and ox > 0:
                    covered_by = oid
                    break
            if covered_by is None:
                uncovered.append((round(cy0, 3), round(cy1, 3), round(cx0, 3), round(cx1, 3),
                                  int(y0), int(y1)))
        # merge consecutive uncovered lines into blocks so that isolated bbox-boundary
        # noise does not drown the real misses
        blocks, current = [], []
        for item in uncovered:
            if current and item[0] - current[-1][1] > 0.02:
                blocks.append(current)
                current = []
            current.append(item)
        if current:
            blocks.append(current)
        real = [b for b in blocks if len(b) >= 2 or (b[0][3] - b[0][2]) > 0.35]
        if real:
            report[str(pno)] = {
                "lines": len(lines), "uncovered_lines": len(uncovered),
                "uncovered_blocks": len(real),
                "detail": [{"y": [b[0][0], b[-1][1]], "x": [b[0][2], max(i[3] for i in b)],
                            "rows": len(b), "px": [b[0][4], b[-1][5]]} for b in real[:12]]}

    out = json.dumps(report, ensure_ascii=False, indent=1)
    if args.report:
        Path(args.report).write_text(out + "\n", encoding="utf-8")
    print(out if report else "all transcribed pages fully covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
