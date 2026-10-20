"""扫描版书源的标准修复 + 构建流水线（单一入口，Python 版）。

为什么要有它：流程里最容易漏的一步是"每轮先 prepare"——它才会为新落盘的页生成
packet；漏掉就报 FileNotFoundError: packet/pages/pNNNN.json。把整条链写成入口，
就不会再漏。（PowerShell 版受执行策略限制，故用 Python。）

用法：
  python D:\\nf-stage\\run_pipeline.py             # 完整流程
  python D:\\nf-stage\\run_pipeline.py --skip-build
  python D:\\nf-stage\\run_pipeline.py --audit     # 顺带跑覆盖审计与编号连续性
"""
import argparse
import subprocess
import sys
from pathlib import Path

PY = r"C:\Users\ltllt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
STAGE = Path(r"D:\nf-stage")
PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
NF = r"C:\Users\ltllt\.dsh\skills\native-textbook\scripts\nf.cmd"
SOURCE = r"C:\Users\ltllt\Desktop\计算物理──从原理到实践 (龚明) .pdf"
TITLE = "计算物理：从原理到实践"

SHARD_FIXES = [
    "fix_bad_json.py", "fix_object_kind.py", "fix_figure_tex2.py", "fix_literal_blocks.py",
    "fix_literal_text.py", "fix_empty_text.py", "fix_excluded_fields.py", "fix_dup_ids.py",
    "fix_multitag.py", "fix_dup_tags.py", "fix_numbered_consistency.py", "fix_nested_math5.py",
    "fix_eq_tag_text.py", "fix_cdots2.py", "fix_glyphs2.py", "clamp_bbox.py",
]

NO_WINDOW = {}
if sys.platform == "win32":
    NO_WINDOW = {"creationflags": 0x08000000}


def run(cmd, label, tail=1):
    print(f"=== {label} ===", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **NO_WINDOW)
    if label == "gen_pages":
        # gen_pages 只应取 stdout 的最后一行（stderr 可能有警告）
        pages = [l for l in (proc.stdout or "").splitlines() if l.strip()]
        return pages[-1].strip() if pages else ""
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = [l for l in out.splitlines() if l.strip()]
    for line in lines[-tail:]:
        print("   ", line[:200])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--audit", action="store_true")
    args = ap.parse_args()

    for name in SHARD_FIXES:
        path = STAGE / name
        if path.is_file():
            run([PY, str(path)], name)
    run([PY, str(STAGE / "fix_array_cols.py"), "--apply"], "fix_array_cols")
    run([PY, str(STAGE / "auto_continues.py")], "auto_continues")
    # 修补行去重：规范化脚本每轮都会 append 说明，多轮会累积（实测有页累到 22 条）
    run([PY, str(STAGE / "fix_notes_dedup.py")], "fix_notes_dedup")

    pages = run([PY, str(STAGE / "gen_pages.py")], "gen_pages").strip().splitlines()[-1].strip()
    print("页码范围:", pages, flush=True)

    run([NF, "prepare", "--source", SOURCE, "--pages", pages,
         "--project", str(PROJECT), "--title", TITLE], "prepare")
    run([PY, str(STAGE / "merge_workers.py"), "--pages", pages], "merge#1")
    run([PY, str(STAGE / "make_assets.py"), "--pages", pages], "make_assets")
    run([PY, str(STAGE / "merge_workers.py"), "--pages", pages], "merge#2")

    if not args.skip_build:
        run([NF, "build", "--project", str(PROJECT)], "build")
        run([PY, "-c",
             "import re,fitz;from pathlib import Path;"
             f"log=Path(r'{PROJECT}/build/main.log').read_text(encoding='utf-8',errors='replace');"
             "print('Overfull:',len(re.findall(r'Overfull \\\\hbox',log)),"
             "'| LaTeX 错误:',len([l for l in log.splitlines() if l.startswith('!')]))"],
            "log-summary")
        run([PY, "-c",
             "import fitz;"
             f"d=fitz.open(r'{PROJECT}/build/main.pdf');"
             "print('成品',d.page_count,'页 |',sum(len(p.get_text()) for p in d),'字')"],
            "pdf-summary")

    if args.audit:
        run([PY, str(STAGE / "audit_coverage.py"), "--pages", pages], "audit_coverage")
        run([PY, str(STAGE / "check_numbering.py")], "check_numbering")
    # 半页漏读检测（"只读了 band0"）：已确认过 p0193/p0165/p0171/p0172/p0173/p0215 等页
    run([PY, str(STAGE / "detect_partial_pages.py"), "--pages", pages], "detect_partial_pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
