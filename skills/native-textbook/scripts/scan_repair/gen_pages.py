"""输出当前已转写页的紧凑页码范围，供 prepare / merge / audit / build 使用。

用法：
  python D:\\nf-stage\\gen_pages.py            # 打印范围字符串
  然后在 PowerShell 里： $pages = & $py D:\nf-stage\gen_pages.py
"""
import json
from pathlib import Path

INBOX = Path(r"D:\native-forge-work\inbox")
pages = sorted(int(p.stem[1:]) for p in INBOX.glob("p0*.json") if p.stem[1:].isdigit())

parts, start, prev = [], None, None
for p in pages:
    if start is None:
        start = prev = p
        continue
    if p == prev + 1:
        prev = p
        continue
    parts.append(f"{start}-{prev}" if start != prev else f"{start}")
    start = prev = p
if start is not None:
    parts.append(f"{start}-{prev}" if start != prev else f"{start}")
print(",".join(parts))
