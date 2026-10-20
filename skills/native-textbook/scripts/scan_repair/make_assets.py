"""Crop figure regions from the scanned source and register them as assets.

`nf.cmd asset --kind source_raster` refuses a crop whose page carries one big
full-page scan, so this script does the crop itself: it reads the page's original
JPEG, maps the page-point bbox into image pixels (no resampling) and writes a PNG.

Display width is derived from the source size so a figure is never enlarged past
its scanned resolution:  width = crop_width_pt / text_width_pt.

Run:  python D:\\nf-stage\\make_assets.py [--pages 23-45] [--dry-run]
"""
import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import fitz
from PIL import Image

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
INBOX = Path(r"D:\native-forge-work\inbox")
REDRAWN = {"1.1.1"}                       # already native TikZ
TEXT_WIDTH_PT = 152 / 25.4 * 72           # layout text width
CAPTION_PREFIX = re.compile(r"^图\s*\d+(?:\.\d+)*\s*[\.．]?\s*")


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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    project = json.loads((PROJECT / "project.json").read_text(encoding="utf-8"))
    pages = parse_pages(args.pages) if args.pages else project["pages"]
    source = Path(project["source"]["path"])
    doc = fitz.open(source)
    assets_path = PROJECT / "assets.json"
    assets = json.loads(assets_path.read_text(encoding="utf-8"))
    (PROJECT / "assets").mkdir(exist_ok=True)
    trim_path = PROJECT / "work" / "fig_trim.json"
    trim = json.loads(trim_path.read_text(encoding="utf-8-sig")) if trim_path.is_file() else {}

    cropped, rewritten = [], []
    for pno in pages:
        shard_path = INBOX / f"p{pno:04d}.json"
        if not shard_path.is_file():
            continue
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        figs = shard.get("figures") or []
        if not figs:
            continue
        packet = json.loads((PROJECT / "packet" / "pages" / f"p{pno:04d}.json").read_text(encoding="utf-8"))
        W, H = packet["width"], packet["height"]
        page = doc[pno - 1]
        infos = [i for i in page.get_image_info(xrefs=True) if i.get("width")]
        infos.sort(key=lambda i: i["width"] * i["height"], reverse=True)
        image = infos[0]
        ir = fitz.Rect(image["bbox"])
        xref = image["xref"]
        raw = doc.extract_image(xref)
        pil = Image.open(io.BytesIO(raw["image"])).convert("RGB")
        sx = pil.width / ir.width
        sy = pil.height / ir.height
        changed = False
        for fig in figs:
            number = fig.get("number")
            if number in REDRAWN:
                continue
            figure_blocks = [b for b in shard["blocks"]
                             if b.get("kind") == "figure" and fig["source_id"] in b.get("source_ids", [])]
            if not figure_blocks:
                # fallback: the page's remaining figure block that still lacks an asset
                figure_blocks = [b for b in shard["blocks"]
                                 if b.get("kind") == "figure" and not b.get("asset")]
            if not figure_blocks:
                # Registered as evidence of a layout element (part/chapter opener), not a figure.
                continue
            name = f"f{pno:04d}-{number}"
            x0, y0, x1, y1 = trim.get(f"{pno:04d}-{number}", fig["bbox"])
            clip = fitz.Rect(x0 * W, y0 * H, x1 * W, y1 * H)
            px = [max(0, int((clip.x0 - ir.x0) * sx)), max(0, int((clip.y0 - ir.y0) * sy)),
                  min(pil.width, int((clip.x1 - ir.x0) * sx)), min(pil.height, int((clip.y1 - ir.y0) * sy))]
            if px[2] <= px[0] or px[3] <= px[1]:
                print(f"BAD CROP {name}: {px}", file=sys.stderr)
                continue
            target = PROJECT / "assets" / f"{name}.png"
            if not args.dry_run:
                pil.crop(tuple(px)).save(target)
            width = min(0.98, max(0.30, (clip.x1 - clip.x0) / TEXT_WIDTH_PT))
            assets[name] = {
                "path": f"assets/{name}.png",
                "kind": "source_raster",
                "role": "figure",
                "source_page": pno,
                "bbox": [round(clip.x0, 2), round(clip.y0, 2), round(clip.x1, 2), round(clip.y1, 2)],
                "rationale": ("原始扫描位图区域（照片/实测曲线），按源像素无损裁切，未重绘；"
                              f"源页 p{pno:04d}，裁切框 {px}"),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "",
                "pixel_box": px,
                "source_image_size": [pil.width, pil.height],
            }
            cropped.append(f"{name} {px[2]-px[0]}x{px[3]-px[1]}")

            caption = CAPTION_PREFIX.sub("", (fig.get("caption") or "").strip()).strip()
            for block in figure_blocks:
                if block.get("kind") == "figure":
                    block.pop("tex", None)
                    block.update({"kind": "figure", "asset": name, "number": number,
                                  "caption": caption, "width": f"{width:.3f}\\linewidth",
                                  "asset_kind": "source_raster",
                                  "figure_kind": fig.get("figure_kind", "photograph")})
                    rewritten.append(f"{pno}:{block['id']}->{name}")
                    changed = True
        if changed and not args.dry_run:
            shard_path.write_text(json.dumps(shard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.dry_run:
        assets_path.write_text(json.dumps(assets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"cropped": cropped, "rewritten": rewritten}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
