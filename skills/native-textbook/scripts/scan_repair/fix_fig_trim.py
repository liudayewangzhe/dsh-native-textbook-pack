"""维护 work/fig_trim.json：一页多图时的合裁框。

背景：`make_assets.py` 默认按 `f{pno}-{number}` 命名资产，一页一个号只会裁**一幅**。
一页有多幅共享同一图号的子图时（如 p0320 的 Kuramoto 8 幅 (a)-(h)），必须在
`work/fig_trim.json` 里给出合裁框，否则资产只裁到最后一幅。

本脚本可重复运行（幂等），把已知的合裁框写入该文件。

Run:  python D:\\nf-stage\\fix_fig_trim.py
"""
import json
from pathlib import Path

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
TRIM = PROJECT / "work" / "fig_trim.json"

# 键 = "<页号>-<图号>"（页号 4 位），值 = 整页归一化 bbox + 说明
ENTRIES = {
    "0320-12.4.1": {
        "bbox": [0.142, 0.174, 0.855, 0.724],
        "note": "Kuramoto 模型 8 幅并排子图 (a)-(h) 合裁框；含子图标注，不含红色图题",
    },
}

data = {}
if TRIM.is_file():
    try:
        data = json.loads(TRIM.read_text(encoding="utf-8"))
    except Exception:
        data = {}

added = 0
for k, v in ENTRIES.items():
    if k not in data:
        data[k] = v
        added += 1
    else:
        data[k].update(v)

TRIM.parent.mkdir(parents=True, exist_ok=True)
TRIM.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"fig_trim.json: 现有 {len(data)} 条，新增/更新 {added or len(ENTRIES)} 条")
for k in ENTRIES:
    print(" ", k, "->", data[k]["bbox"])
