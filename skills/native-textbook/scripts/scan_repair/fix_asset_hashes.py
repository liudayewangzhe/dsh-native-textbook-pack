"""同步 assets.json 里每个资产的 sha256 / 尺寸与磁盘实际文件。

用途：任何对 assets/ 下图片的改动（重存、转格式、重裁）都会让引擎报
`sha256 does not match`。本脚本按磁盘实际情况刷新：
  - path 若缺失或对不上，按 id 在 assets/ 里找同名文件
  - sha256、width/height（若声明）按实际重算
  - 记录一条 note 便于追溯

Run:  python D:\\nf-stage\\fix_asset_hashes.py [--apply]
"""
import argparse
import hashlib
import json
from pathlib import Path

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    apath = PROJECT / "assets.json"
    raw = json.loads(apath.read_text(encoding="utf-8"))
    adir = PROJECT / "assets"
    fixed, missing = 0, []

    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        p = val.get("path")
        cand = None
        if isinstance(p, str):
            cand = PROJECT / p
            if not cand.is_file():
                cand = None
        if cand is None:
            # 按 id / key 在 assets/ 里找同名
            for ext in (".png", ".jpg", ".jpeg", ".pdf", ".png"):
                t = adir / f"{key}{ext}"
                if t.is_file():
                    cand = t
                    break
        if cand is None:
            missing.append(key)
            continue
        rel = cand.relative_to(PROJECT).as_posix()
        if val.get("path") != rel:
            val["path"] = rel
            fixed += 1
        real = sha256_of(cand)
        if val.get("sha256") != real:
            val["sha256"] = real
            fixed += 1
        try:
            from PIL import Image
            with Image.open(cand) as im:
                w, h = im.size
            if "width" in val and val["width"] != w:
                val["width"] = w
                fixed += 1
            if "height" in val and val["height"] != h:
                val["height"] = h
                fixed += 1
        except Exception:
            pass

    if args.apply and fixed:
        apath.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"修正 {fixed} 个字段" + (" [applied]" if args.apply else " [dry-run]")
          + (f" | 文件缺失 {len(missing)}: {missing[:5]}" if missing else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
