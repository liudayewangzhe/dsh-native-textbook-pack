"""按实测墨迹重算分片的 bbox 纵向位置（保守版，只改 y）。

背景：部分 worker 把 band1（下半带）的坐标当**带内相对值**写进 bbox，没加整页偏移，
于是对象整体上移约 0.10–0.15（实测 p0219 的 (8.3.30) 记 0.222、真值 0.103）。
旧脚本 bbox_rebase.py 用锚点假设、曾两次改坏文件，故本脚本改为**只依据墨迹投影**：

  1. 把 b0/b1 两张分带图拼回整页墨迹剖面（b1 偏移取 slice_index.json 的 box y0）；
  2. 对每个 object，取其 bbox 的 y 区间，在整页剖面上找"最贴近的连续墨迹段"；
  3. 若该段与 bbox 的偏差 > 0.02（页高比例）且 < 0.25，则把 bbox 的 y0/y1 平移到该段；
  4. 只改 y（x 不动），并写 notes 记录。

用法：
  python D:\\nf-stage\\fix_bbox_shift.py --pages 217-219 [--apply]
"""
import argparse
import json
from pathlib import Path

import fitz
import numpy as np

SLICES = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh\work\slices")
INBOX = Path(r"D:\native-forge-work\inbox")
SHIFT_MIN, SHIFT_MAX = 0.02, 0.25

_INDEX = None


def _index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = json.loads((SLICES / "slice_index.json").read_text(encoding="utf-8"))["pages"]
    return _INDEX


def page_profile(pno: int) -> np.ndarray | None:
    """拼回整页墨迹剖面：返回每行是否为墨迹行的布尔数组（长度=整页像素高）。

    slice_index.json 结构：{"pages": {"217": {"width":W,"height":H,
        "bands":[{"band":0,"file":"p0217_b0.png","box":[0,0,W,818]},
                 {"band":1,"file":"p0217_b1.png","box":[0,726,W,H]}]}}}
    """
    entry = _index().get(str(pno))
    if not entry:
        return None
    H = int(entry["height"])
    prof = np.zeros(H, dtype=bool)
    for band in entry["bands"]:
        f = SLICES / band["file"]
        if not f.is_file():
            continue
        doc = fitz.open(f)
        pix = doc[0].get_pixmap()
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        dark = (arr < 150).all(axis=2).sum(axis=1) >= 6
        off = int(band["box"][1])
        n = min(len(dark), H - off)
        if n > 0:
            prof[off:off + n] |= dark[:n]
        doc.close()
    return prof


def segments(prof: np.ndarray):
    """把墨迹行剖面的连续段列出 [(y0, y1), ...]，单位 px。"""
    ys = np.where(prof)[0]
    if ys.size == 0:
        return []
    out, start, prev = [], ys[0], ys[0]
    for y in ys[1:]:
        if y <= prev + 3:
            prev = y
            continue
        out.append((start, prev))
        start = prev = y
    out.append((start, prev))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", required=True, help="例如 217-219 或 217,218,219")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    pages: list[int] = []
    for part in args.pages.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))

    total = 0
    for pno in pages:
        prof = page_profile(pno)
        if prof is None:
            print(f"p{pno:04d}: 无切片索引，跳过")
            continue
        H = len(prof)
        segs = segments(prof)
        path = INBOX / f"p{pno:04d}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        moved = []
        for o in data.get("objects", []):
            bb = o.get("bbox")
            if not bb or o.get("kind") in ("header_footer",):
                continue
            y0, y1 = bb[1] * H, bb[3] * H
            span = max(y1 - y0, 4)
            # 找与 [y0,y1] 重叠最多 / 中心最近的墨迹段
            best, best_d = None, 1e9
            for s0, s1 in segs:
                d = abs((s0 + s1) / 2 - (y0 + y1) / 2)
                ov = min(y1, s1) - max(y0, s0)
                if ov > 0:
                    d *= 0.2             # 已重叠的段优先
                if d < best_d:
                    best, best_d = (s0, s1), d
            if best is None:
                continue
            shift = (best[0] - y0) / H
            new_span_ratio = (best[1] - best[0]) / span
            if SHIFT_MIN < abs(shift) < SHIFT_MAX and 0.4 < new_span_ratio < 2.5:
                bb[1] = round(best[0] / H, 4)
                bb[3] = round(min(best[1] / H, 0.999), 4)
                moved.append((o["id"], round(shift, 3)))
        if moved:
            total += len(moved)
            data["notes"] = (data.get("notes", "") +
                             f"\n[监工修补 2026-10-15] 按整页墨迹投影平移 {len(moved)} 个对象的 bbox 纵坐标"
                             "（修正 band1 折算压缩）。")
            if args.apply:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"p{pno:04d}: {len(moved)} object(s) shifted" + (" [applied]" if args.apply else " [dry-run]"))
            for oid, sh in moved[:6]:
                print(f"    {oid}  dy={sh:+.3f}")
    print(f"合计 {total} 个对象" + ("已写入" if args.apply else "（dry-run，未写盘）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
