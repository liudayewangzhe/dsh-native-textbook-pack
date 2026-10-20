"""把资产名里的括号等 LaTeX 敏感字符换成连字符，并同步所有引用。

事故：worker 给子图起名 `f0281-11.4.1(a)`，`\\includegraphics{f0281-11.4.1(a)}` 里
`(a)` 被 LaTeX 当成尺寸修饰，xelatex 报
`assets/f0281-11.4.1.png Graphic file (type bmp)` 之类而失败。

处理：把资产名与文件名里的 `(` `)` `（` `）` 空格 换成 `-`（合并重复连字符），
同步更新：
  - assets/ 下的物理文件名
  - assets.json 里的 id/asset/file
  - inbox 各分片 block.asset 与 figures[].asset
  - 保留 figures[].number 不变（图号仍写 11.4.1，子图标记在 caption）

Run:  python D:\\nf-stage\\fix_asset_names.py [--apply]
"""
import argparse
import json
import re
from pathlib import Path

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
INBOX = Path(r"D:\native-forge-work\inbox")
BAD = re.compile(r"[()（）\s]+")


def clean(name: str) -> str:
    if not isinstance(name, str):
        return name
    out = BAD.sub("-", name)
    return re.sub(r"-{2,}", "-", out).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    renames: dict[str, str] = {}

    assets_dir = PROJECT / "assets"
    for f in sorted(assets_dir.glob("*")):
        if f.is_file() and BAD.search(f.stem):
            new = clean(f.stem) + f.suffix
            renames[f.stem] = clean(f.stem)
            if args.apply:
                f.rename(assets_dir / new)
            print(f"file {f.name} -> {new}")

    apath = PROJECT / "assets.json"
    raw = json.loads(apath.read_text(encoding="utf-8"))
    data = raw if isinstance(raw, list) else raw.get("assets", raw)
    touched = 0

    def fix_item(item):
        nonlocal touched
        if not isinstance(item, dict):
            return
        for key in ("id", "asset", "file", "name"):
            v = item.get(key)
            if isinstance(v, str) and BAD.search(v):
                item[key] = clean(v)
                touched += 1

    if isinstance(data, list):
        for it in data:
            fix_item(it)
    elif isinstance(data, dict):
        for k, v in list(data.items()):
            if BAD.search(k):
                data[clean(k)] = data.pop(k)
                touched += 1
            fix_item(v)
    if args.apply and touched:
        apath.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"assets.json: {touched} field(s)" + (" [applied]" if args.apply else " [dry-run]"))

    n = 0
    for path in sorted(INBOX.glob("p0*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for b in d.get("blocks", []):
            v = b.get("asset")
            if isinstance(v, str) and BAD.search(v):
                b["asset"] = clean(v)
                dirty = True
                n += 1
        for coll in ("figures", "tables"):
            for it in d.get(coll) or []:
                v = it.get("asset")
                if isinstance(v, str) and BAD.search(v):
                    it["asset"] = clean(v)
                    dirty = True
                    n += 1
        if dirty and args.apply:
            d["notes"] = (d.get("notes", "") +
                          "\n[监工修补 2026-10-15] 资产名含 LaTeX 敏感字符（括号/空格），已替换为连字符。")
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"shard asset 引用: {n}" + (" [applied]" if args.apply else " [dry-run]"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
