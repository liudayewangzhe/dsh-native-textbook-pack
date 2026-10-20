"""Exercise real scheduling transitions with a small, self-authored text source.

This checks orchestration, not PDF quality. It refuses to overwrite --out.
Run from any directory with Python 3.10+: --out <new directory>.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
MODULE = PACK / "skills/native-textbook/scripts/translation_state.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    spec_loader = importlib.util.spec_from_file_location("translation_state_smoke", MODULE)
    state = importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(state)

    def write(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    first = "The kernel is the set of vectors mapped to zero.\n"
    second = "The example program preserves its identifiers.\nprint('kernel')\n"
    write("source.txt", first + "\n" + second)
    write("evidence/c01.txt", first)
    write("evidence/c02.txt", second)
    write("contracts/worker-rules.md", "Translate prose; preserve code, source IDs and mathematical meaning.\n")
    write("contracts/layout.tex", "% Synthetic layout dependency, not a compilable document.\n")
    glossary = {"version": 1, "terms": [{"id": "kernel", "source": "kernel", "target": "核",
                                         "aliases": [], "scope": "linear-algebra", "always": False}]}
    write("glossary.json", glossary)
    spec = {"version": 1, "mode": "book", "source": {"path": "source.txt"},
            "glossary": "glossary.json", "translation_inputs": ["contracts/worker-rules.md"],
            "build_inputs": ["contracts/layout.tex"], "context_chars": 0,
            "chunks": [{"id": "c01", "source": "evidence/c01.txt", "output": "draft/c01.json",
                        "source_ids": ["sec1-definition"], "scope": "linear-algebra"},
                       {"id": "c02", "source": "evidence/c02.txt", "output": "draft/c02.json",
                        "source_ids": ["sec2-code"], "scope": "programming"}]}
    write("translation-spec.json", spec)
    state.init(root, root / "translation-spec.json")
    checks = []

    def output(block):
        return {"title": "调度样例", "blocks": [block], "exclusions": [], "unresolved": [],
                "expectations": {"equation_tags": [], "required_strings": [],
                                 "table_count": 0, "figure_count": 0}}

    def expect_blocked(name):
        try:
            state.verify(root)
        except ValueError:
            checks.append({"check": name, "result": "blocked_as_expected"})
        else:
            raise RuntimeError(f"negative check unexpectedly passed: {name}")

    state.brief(root, "c01")
    write("draft/c01.json", output({"id": "definition", "kind": "paragraph",
          "source_ids": ["sec1-definition"], "tex": "核是被映射到零向量的向量所成的集合。"}))
    state.record(root, "c01")
    expect_blocked("missing_second_package")
    state.brief(root, "c02")
    write("draft/c02.json", output({"id": "program", "kind": "code",
          "source_ids": ["sec2-code"], "text": "print('kernel')"}))
    state.record(root, "c02")
    verified = state.verify(root)
    assert [p["action"] for p in verified["chunks"]] == ["reuse", "reuse"]
    checks.append({"check": "restart", "actions": [p["action"] for p in verified["chunks"]]})

    glossary["terms"][0]["target"] = "零空间"
    write("glossary.json", glossary)
    actions = [p["action"] for p in state.plan(root)["chunks"]]
    assert actions == ["translate", "reuse"], actions
    checks.append({"check": "scoped_terminology_change", "actions": actions})
    expect_blocked("stale_terminology")
    state.brief(root, "c01")
    write("draft/c01.json", output({"id": "definition", "kind": "paragraph",
          "source_ids": ["sec1-definition"], "tex": "零空间是被映射到零向量的向量所成的集合。"}))
    state.record(root, "c01")
    write("contracts/layout.tex", "% Revised layout dependency.\n")
    verified = state.verify(root)
    assert [p["action"] for p in verified["chunks"]] == ["rebuild", "rebuild"]
    assert verified["needs_rebuild"] and not verified["review_valid"]
    checks.append({"check": "layout_change", "actions": [p["action"] for p in verified["chunks"]],
                   "needs_rebuild": True, "review_valid": False})

    path = root / "draft/c02.json"
    accepted = path.read_bytes()
    path.write_bytes(accepted + b"\n")
    expect_blocked("output_tampering")
    path.write_bytes(accepted)
    report = {"stage": "orchestration_smoke_passed", "checks": checks,
              "pdf_built": False, "visual_review": "not_performed",
              "proof_boundary": "Scheduling only. Native engine integration has a separate test."}
    write("smoke-report.json", report)
    print(json.dumps({"report": str(root / "smoke-report.json"), "checks": len(checks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
