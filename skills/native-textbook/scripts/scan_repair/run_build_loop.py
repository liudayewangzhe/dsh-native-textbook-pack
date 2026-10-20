"""循环「修 → merge → build」直到构建成功（最多 N 轮）。

背景：worker 持续落盘新页，每次修完 `unresolved` 又会被新页带进新的小瑕疵，
于是出现「修完一版、构建仍失败」的循环，PDF 长时间停在旧版本。

这个入口把修复脚本与 merge/build 串成闭环：每轮先跑全部 fix 脚本，再 merge；
若 build 报 `unresolved ... (N left)` 之类，就再修一轮；成功后打印摘要。

用法：
  python D:\\nf-stage\\run_build_loop.py [--rounds 4]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

PY = sys.executable
STAGE = Path(r"D:\nf-stage")
PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
NF = r"C:\Users\ltllt\.dsh\skills\native-textbook\scripts\nf.cmd"

FIXES = [
    "fix_bad_json.py", "fix_object_kind.py", "fix_figure_tex2.py", "fix_literal_blocks.py",
    "fix_literal_text.py", "fix_empty_text.py", "fix_excluded_fields.py", "fix_bad_block_kind.py",
    "fix_bare_figure_blocks.py", "fix_caption_only_figures.py", "fix_figure_fields.py",
    "fix_figure_number2.py", "fix_cases_cols.py", "fix_asset_names.py", "fix_asset_hashes.py",
    "fix_dups_and_heading.py",
    "fix_dup_ids.py", "fix_multitag.py", "fix_dup_tags.py", "fix_numbered_consistency.py",
    "fix_nested_math5.py", "fix_eq_tag_text.py", "fix_cdots2.py", "fix_glyphs2.py",
    "fix_frontmatter_and_glyph.py", "clamp_bbox.py",
]

NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def run(cmd, label, show=0):
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **NO_WINDOW)
    out = (proc.stdout or "") + (proc.stderr or "")
    if show:
        print(f"--- {label} ---")
        for line in [l for l in out.splitlines() if l.strip()][-show:]:
            print("   ", line[:190])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()

    for attempt in range(1, args.rounds + 1):
        print(f"===== attempt {attempt} =====", flush=True)
        for name in FIXES:
            p = STAGE / name
            if p.is_file():
                run([PY, str(p)], name)
        run([PY, str(STAGE / "fix_array_cols.py"), "--apply"], "fix_array_cols")
        run([PY, str(STAGE / "auto_continues.py")], "auto_continues")
        run([PY, str(STAGE / "fix_notes_dedup.py")], "fix_notes_dedup")

        pages = run([PY, str(STAGE / "gen_pages.py")], "gen_pages").strip().splitlines()[-1].strip()
        run([NF, "prepare", "--source",
             r"C:\Users\ltllt\Desktop\计算物理──从原理到实践 (龚明) .pdf",
             "--pages", pages, "--project", str(PROJECT),
             "--title", "计算物理：从原理到实践"], "prepare")
        m1 = run([PY, str(STAGE / "merge_workers.py"), "--pages", pages], "merge#1")
        run([PY, str(STAGE / "make_assets.py"), "--pages", pages], "make_assets")
        m2 = run([PY, str(STAGE / "merge_workers.py"), "--pages", pages], "merge#2")

        unresolved = re.search(r'"unresolved":\s*\[(.*?)\]', m2, re.S)
        left = unresolved.group(1).strip() if unresolved else ""
        if left and left != "":
            print("   unresolved:", left[:180], flush=True)
            continue                      # 修一轮再来

        build = run([NF, "build", "--project", str(PROJECT)], "build")
        if "ERROR" not in build:
            print("build OK", flush=True)
            run([PY, "-c",
                 "import re,fitz;from pathlib import Path;"
                 f"log=Path(r'{PROJECT}/build/main.log').read_text(encoding='utf-8',errors='replace');"
                 "print('Overfull:',len(re.findall(r'Overfull \\\\hbox',log)),"
                 "'| LaTeX errors:',len([l for l in log.splitlines() if l.startswith('!')]))"],
                "log-summary", show=2)
            run([PY, "-c",
                 "import fitz;"
                 f"d=fitz.open(r'{PROJECT}/build/main.pdf');"
                 "print('pages:',d.page_count,'| chars:',sum(len(p.get_text()) for p in d))"],
                "pdf-summary", show=2)
            return 0
        print("   build failed, retrying after another fix round", flush=True)

    print("still failing after all attempts", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
