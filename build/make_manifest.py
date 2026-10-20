"""生成 MANIFEST.json：文件清单 + SHA256 + 体积统计。

跨平台约定：计算哈希与字节数前先把文件内容做 CRLF -> LF 归一化，
因此同一份内容无论以 LF 还是 CRLF 检出，清单都一致。
对应校验脚本是仓库根目录的 verify_pack.py。

用法:
    python build/make_manifest.py --pack "<包根目录>" [--split-limit-mb 500] [--out 路径]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

# 清单自身不记录自己；忽略缓存/版本库/离线依赖目录
SKIP_NAMES = {"MANIFEST.json"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "pylibs", ".venv", "venv"}


def normalized_bytes(path: str) -> bytes:
    """读取文件并做幂等的换行归一化（与 verify_pack.py 必须完全一致）。"""
    with open(path, "rb") as fh:
        data = fh.read()
    while b"\r\r\n" in data:
        data = data.replace(b"\r\r\n", b"\n")
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_normalized(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--split-limit-mb", type=float, default=500.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    root = os.path.abspath(args.pack)
    out = args.out or os.path.join(root, "MANIFEST.json")

    files = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name in SKIP_NAMES or name.endswith(".tmp") or name.endswith(".tmpdir"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace("\\", "/")
            data = normalized_bytes(full)
            size = len(data)
            total += size
            files.append({"path": rel, "bytes": size, "sha256": sha256_normalized(data)})

    files.sort(key=lambda x: x["path"])
    limit = args.split_limit_mb * 1024 * 1024
    parts, cur, cursize = [], [], 0
    for f in files:
        if cur and cursize + f["bytes"] > limit:
            parts.append(cur)
            cur, cursize = [], 0
        cur.append(f["path"])
        cursize += f["bytes"]
    if cur:
        parts.append(cur)

    manifest = {
        "name": "dsh-native-textbook-pack",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hash_mode": "sha256-lf-normalized",
        "file_count": len(files),
        "total_bytes": total,
        "total_mb": round(total / 1048576, 2),
        "split_limit_mb": args.split_limit_mb,
        "parts": [{"index": i + 1, "files": p} for i, p in enumerate(parts)],
        "install": {
            "entry": "install.cmd",
            "powershell": "install.ps1",
            "skills_target": r"%USERPROFILE%\.dsh\skills",
            "engine_target": r"%USERPROFILE%\.dsh\native-forge",
        },
        "verify": {
            "python": "verify_pack.py",
            "powershell": "verify-pack.ps1",
        },
        "files": files,
    }
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(f"files={len(files)}  total={total/1048576:.2f} MB  parts={len(parts)}  -> {out}")
    for p in manifest["parts"]:
        n = len(p["files"])
        b = sum(f["bytes"] for f in files if f["path"] in set(p["files"]))
        print(f"  part {p['index']}: {n} files, {b/1048576:.2f} MB")


if __name__ == "__main__":
    main()
