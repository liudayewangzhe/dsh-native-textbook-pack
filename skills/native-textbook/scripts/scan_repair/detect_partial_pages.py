"""检测"只读了上半页（band0）"的页——下身墨迹远超 objects 的 y 上界。

背景：已确认多页出现同一失效模式——worker 只读了 band0（上半页），在整页
y≈0.53 的交界处停下，band1 的内容（公式 + 正文 + 页脚）整体丢失；个别页还据此
编造了"下一页顶部空白/被裁掉"的说法。覆盖审计抓不到，因为局部扩展 bbox 会把
未覆盖行划给最近对象。这里改用几何判据：

    objects 的 y 上界  <<  页面实际墨迹的 y 上界（排除页脚带）

判据：ymax_objects 比 ink_top（0.90 以下最靠下的墨迹行）低 0.12 以上 → 疑似半页漏读。

Run:  python D:\\nf-stage\\detect_partial_pages.py [--pages 1-638] [--threshold 0.12]
"""
import argparse
import json
import sys
from pathlib import Path

import fitz
import numpy as np

INBOX = Path(r"D:\native-forge-work\inbox")
PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")


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


def ink_top(doc, pno, dpi=90, min_ink=6, foot_cut=0.90):
    """页面正文区最低墨迹行的 y（归一化）。

    注意：红底/彩色装饰页不能用灰度阈值判墨——红底会被整体判成"墨迹"，
    于是 every colored page 都报假阳性（实测 p0268/p0263）。这里只在**灰度很低**
    且**三通道接近**（真黑字）时才算墨迹；红底（R 明显大于 G/B）与淡色装饰被排除。
    """
    page = doc[pno - 1]
    scale = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))          # RGB
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    dark = (r < 150) & (g < 150) & (b < 150)                          # 深墨
    neutral = (np.abs(r - g) < 60) & (np.abs(g - b) < 60)             # 灰/黑，排除红蓝底
    rows = (dark & neutral)[: int(pix.height * foot_cut)].sum(axis=1) >= min_ink
    ys = np.where(rows)[0]
    return (float(ys[-1]) / pix.height) if ys.size else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", default="")
    ap.add_argument("--threshold", type=float, default=0.12)
    args = ap.parse_args()

    project = json.loads((PROJECT / "project.json").read_text(encoding="utf-8"))
    pages = parse_pages(args.pages) if args.pages else project["pages"]
    doc = fitz.open(project["source"]["path"])
    suspects = []
    for pno in pages:
        path = INBOX / f"p{pno:04d}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        objs = [o for o in (data.get("objects") or [])
                if o.get("kind") != "header_footer"]
        if not objs:
            continue
        ymax = max(o["bbox"][3] for o in objs)
        top = ink_top(doc, pno)
        if top is None:
            continue
        if top - ymax > args.threshold:
            suspects.append({"page": pno, "objects_ymax": round(ymax, 3),
                             "ink_top": round(top, 3), "gap": round(top - ymax, 3)})
    suspects.sort(key=lambda s: -s["gap"])
    print(f"{len(suspects)} suspect page(s) (objects stop well above the page's lowest ink)")
    for s in suspects:
        print(f"  p{s['page']:04d}  objects<= {s['objects_ymax']:.3f}   ink-> {s['ink_top']:.3f}   gap {s['gap']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
