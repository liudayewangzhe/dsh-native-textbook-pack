#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 MANIFEST.json 中的文件清单与 SHA256（跨平台）。

约定：计算哈希前把所有文件的 CRLF 归一化为 LF，因此在 Windows（CRLF 检出）
与 Linux/macOS（LF 检出）上校验结果一致。

用法:
    python verify_pack.py                  # 校验脚本所在目录
    python verify_pack.py --pack <dir>     # 校验指定目录
    python verify_pack.py --strict         # 多余文件也算失败
    python verify_pack.py -q               # 只输出结论

退出码: 0 = 全部一致；1 = 有缺失/哈希不符/（strict 下）多余文件；2 = 运行错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

# 这些目录不参与校验（版本库、缓存、引擎离线依赖目录）
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "pylibs", ".venv", "venv"}
# 清单自身不记录自己
SKIP_FILES = {"MANIFEST.json"}


def normalized(data: bytes) -> bytes:
    """CRLF -> LF，消除 git 检出换行差异。"""
    return data.replace(b"\r\n", b"\n")


def sha256_normalized(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(normalized(fh.read())).hexdigest()


def iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_FILES or name.endswith(".tmp") or name.endswith(".tmpdir"):
                continue
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, root).replace("\\", "/"), full


def main() -> int:
    ap = argparse.ArgumentParser(description="按 MANIFEST.json 校验文件完整性")
    ap.add_argument("--pack", default=os.path.dirname(os.path.abspath(__file__)),
                    help="包根目录，默认是本脚本所在目录")
    ap.add_argument("--manifest", default=None, help="清单路径，默认 <pack>/MANIFEST.json")
    ap.add_argument("--strict", action="store_true", help="清单之外的多余文件也判为失败")
    ap.add_argument("-q", "--quiet", action="store_true", help="只输出最终结论")
    args = ap.parse_args()

    root = os.path.abspath(args.pack)
    mpath = args.manifest or os.path.join(root, "MANIFEST.json")
    if not os.path.isfile(mpath):
        print("[错误] 找不到清单: %s" % mpath, file=sys.stderr)
        return 2
    try:
        with open(mpath, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("[错误] 读取清单失败: %s" % exc, file=sys.stderr)
        return 2

    expected = {f["path"]: f for f in manifest.get("files", [])}
    actual = dict(iter_files(root))
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = []
    verified = 0

    for rel in sorted(set(expected) & set(actual)):
        exp = expected[rel]
        full = actual[rel]
        # 大小按归一化后长度比较，避免换行差异误报
        with open(full, "rb") as fh:
            data = normalized(fh.read())
        if len(data) != exp.get("bytes"):
            changed.append((rel, "大小 %d != 清单 %s" % (len(data), exp.get("bytes"))))
            continue
        got = hashlib.sha256(data).hexdigest()
        if got != exp.get("sha256"):
            changed.append((rel, "SHA256 %s… != 清单 %s…" % (got[:10], str(exp.get("sha256"))[:10])))
            continue
        verified += 1

    if not args.quiet:
        print("包目录 : %s" % root)
        print("清单   : %d 个文件 / %s MB / 生成于 %s"
              % (manifest.get("file_count", len(expected)),
                 manifest.get("total_mb", "?"),
                 manifest.get("generated_at", "?")))
        print("")

    for rel in missing:
        print("[缺失] %s" % rel)
    for rel, why in changed:
        print("[不符] %s  (%s)" % (rel, why))
    for rel in extra:
        print("[多余] %s" % rel)

    ok = not missing and not changed and (not extra or not args.strict)
    if ok:
        print("")
        print("OK - %d/%d 个文件校验通过。" % (verified, len(expected)))
        if extra:
            print("提示：有 %d 个清单之外的文件（未计入校验）。" % len(extra))
        return 0

    print("")
    print("失败：缺失 %d，内容不符 %d，多余 %d。"
          % (len(missing), len(changed), len(extra)))
    print("建议：重新 clone/解压；本地改动过文件的话，用 build/make_manifest.py 重新生成清单。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
