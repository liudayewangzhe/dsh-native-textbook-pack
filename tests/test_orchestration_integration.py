"""Real PDF prepare -> provenance scheduler -> Native Forge merge regressions.

Uses a generated English source and the shipped engine/templates. No model, fake
compiler, review approval, TeX installation, or checked-in test output is needed.
This checks draft integration only; it does not certify rendered PDF quality.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import fitz
except ImportError:  # pragma: no cover - dependency-dependent
    fitz = None


REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "engine/native-forge/engine/native_forge.py"
MERGE = REPO / "engine/native-forge/scripts/merge_chunks.py"
STATE = REPO / "skills/native-textbook/scripts/translation_state.py"
engine_spec = importlib.util.spec_from_file_location("orchestration_test_engine", ENGINE)
nf = importlib.util.module_from_spec(engine_spec)
engine_spec.loader.exec_module(nf)


@unittest.skipIf(fitz is None, "PyMuPDF is required for the real PDF integration fixture")
class OrchestrationIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Keep the real memory gate, including the user's 1 GiB hard floor.
        nf.ensure_ram(minimum=1 << 30)
        temporary = tempfile.TemporaryDirectory(prefix="native-orchestration-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project with spaces"
        self.source = self.root / "source.pdf"
        self.literal = "energy = 2\nprint(energy)"
        with fitz.open() as doc:
            first = doc.new_page(width=320, height=240)
            first.insert_text((25, 35), "A native code example", fontsize=14)
            first.insert_text((25, 80), "The program prints the energy value.", fontsize=10)
            first.insert_text((25, 130), self.literal, fontname="cour", fontsize=10)
            second = doc.new_page(width=320, height=240)
            second.insert_text((25, 35), "Energy doubles when input doubles.", fontsize=10)
            second.insert_text((25, 85), "E = 2 m (1.1)", fontsize=12)
            second.insert_text((25, 140), "m    E\n1    2\n2    4", fontname="cour", fontsize=10)
            doc.save(self.source)
        self.source_hash = nf.sha256_file(self.source)
        self.run_json(ENGINE, "prepare", "--source", self.source, "--pages", "1-2",
                      "--project", self.project, "--title", "原生集成小样")
        packet_pages = [nf.read_json(self.project / f"packet/pages/p{page:04d}.json")
                        for page in (1, 2)]
        for page in packet_pages:
            self.assertEqual(len(page["blocks"]), 3, "each fixture region must stay a complete source unit")
        page_ids = [[block["id"] for block in page["blocks"]] for page in packet_pages]
        self.ordered_ids = page_ids[0] + page_ids[1]
        self.assertEqual(packet_pages[0]["blocks"][2]["text"], self.literal)

        first_blocks = [
            {"id": "heading", "kind": "section", "source_ids": [page_ids[0][0]],
             "tex": "原生代码示例"},
            {"id": "explanation", "kind": "paragraph", "source_ids": [page_ids[0][1]],
             "tex": "程序打印能量值。"},
            # The actual engine contract is literal text, with no redundant tex.
            {"id": "program", "kind": "code", "source_ids": [page_ids[0][2]],
             "text": self.literal},
        ]
        second_blocks = [
            {"id": "explanation", "kind": "paragraph", "source_ids": [page_ids[1][0]],
             "tex": "输入加倍时，能量也加倍。"},
            {"id": "energy", "kind": "equation", "source_ids": [page_ids[1][1]],
             "tex": r"E = 2m \tag{1.1}"},
            {"id": "values", "kind": "table", "source_ids": [page_ids[1][2]],
             "tex": "\\begin{tabular}{rr}\nm & E \\\\\n1 & 2 \\\\\n2 & 4 \\\\\n\\end{tabular}"},
        ]
        self.outputs = {}
        chunks = []
        for name, page, ids, blocks in zip(("a", "b"), packet_pages, page_ids,
                                           (first_blocks, second_blocks)):
            self.put(f"chunks/{name}.txt", "\n\n".join(b["text"] for b in page["blocks"]) + "\n")
            self.outputs[name] = {
                "title": "原生集成小样", "blocks": blocks, "exclusions": [], "unresolved": [],
                "expectations": {"equation_tags": ["1.1"] if name == "b" else [],
                                 "required_strings": [], "table_count": int(name == "b"),
                                 "figure_count": 0},
            }
            chunks.append({"id": name, "source": f"chunks/{name}.txt",
                           "output": f"draft/{name}.json", "source_ids": ids})
        self.put("rules.md", "Translate complete prose units; preserve code, math and table cells.\n")
        self.put("layout.tex", "% Shared layout input; not a translation instruction.\n")
        self.put("glossary.json", {"version": 1, "terms": [
            {"id": "energy", "source": "energy", "target": "能量"}]})
        self.put("spec.json", {"version": 1, "mode": "book", "source": {"path": str(self.source)},
                               "glossary": "glossary.json", "context_chars": 64,
                               "translation_inputs": ["rules.md", "packet/packet.json",
                                                      "packet/pages/p0001.json", "packet/pages/p0002.json"],
                               "build_inputs": ["layout.tex", "assets.json"], "chunks": chunks})

    def put(self, relative, value):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n"
                          if isinstance(value, (dict, list)) else value, encoding="utf-8")

    def run_command(self, script, *args):
        return subprocess.run([sys.executable, str(script), *(str(arg) for arg in args)],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8")

    def run_json(self, script, *args):
        result = self.run_command(script, *args)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def state(self, command, *args):
        return self.run_json(STATE, command, "--project", self.project, *args)

    def record_all(self):
        self.state("init", "--spec", self.project / "spec.json")
        for name in ("a", "b"):
            self.state("brief", "--chunk", name)
            self.put(f"draft/{name}.json", self.outputs[name])
            recorded = self.state("record", "--chunk", name)
            self.assertEqual(recorded["stage"], "draft_recorded")
            self.assertFalse(recorded["review_valid"])

    def verified_merge(self):
        """The documented handoff must verify before consuming ordered outputs."""
        verified = self.run_command(STATE, "verify", "--project", self.project)
        if verified.returncode:
            raise RuntimeError(verified.stderr)
        plan = json.loads(verified.stdout)
        merged = self.run_json(MERGE, "--project", self.project, "--chunks", *plan["ordered_outputs"])
        return plan, merged

    def test_real_prepare_record_verify_and_merge_preserve_native_contract(self):
        self.record_all()
        plan, result = self.verified_merge()
        self.assertEqual(plan["stage"], "draft_verified")
        self.assertFalse(plan["review_valid"])
        self.assertEqual([Path(p).name for p in plan["ordered_outputs"]], ["a.json", "b.json"])
        self.assertEqual(result["chunks"], 2)
        content = nf.read_json(self.project / "content.json")
        self.assertEqual([s for block in content["blocks"] for s in block["source_ids"]], self.ordered_ids)
        self.assertEqual([b["id"] for b in content["blocks"]],
                         [f"chunk{index:04d}:{block['id']}" for index, name in enumerate(("a", "b"), 1)
                          for block in self.outputs[name]["blocks"]])
        project = nf.read_json(self.project / "project.json")
        packet = nf.load_packet(self.project, project)
        counts = nf.validate_content(content, set(packet), set(nf.load_assets(self.project)))
        self.assertEqual((counts["code"], counts["equation"], counts["table"]), (1, 1, 1))
        code = next(block for block in content["blocks"] if block["kind"] == "code")
        self.assertEqual(nf.literal_payload(code)[1], self.literal.encode("utf-8"))
        self.assertNotIn("tex", code)
        ledger = nf.read_json(self.project / "merge-ledger.json")
        self.assertEqual([row["path"] for row in ledger["chunks"]], plan["ordered_outputs"])
        self.assertEqual(project["status"], "draft")
        self.assertFalse((self.project / "review.json").exists())
        self.assertEqual(nf.sha256_file(self.source), self.source_hash)
        brief = nf.read_json(self.project / "state/briefs/a.json")
        self.assertTrue(brief["context"]["read_only"])
        self.assertTrue(brief["context"]["next_excerpt"].startswith("Energy doubles"))

    def test_tampered_recorded_draft_is_blocked_before_manuscript_replacement(self):
        self.record_all()
        self.verified_merge()
        before = (self.project / "content.json").read_bytes()
        changed = copy.deepcopy(self.outputs["a"])
        changed["blocks"][2]["text"] = "energy = 999\nprint(energy)"
        self.put("draft/a.json", changed)
        with self.assertRaisesRegex(RuntimeError, "output_changed"):
            self.verified_merge()
        self.assertEqual((self.project / "content.json").read_bytes(), before)

    def test_missing_recorded_chunk_is_blocked_before_manuscript_replacement(self):
        self.record_all()
        self.verified_merge()
        before = (self.project / "content.json").read_bytes()
        (self.project / "draft/b.json").unlink()
        with self.assertRaisesRegex(RuntimeError, "output_missing"):
            self.verified_merge()
        self.assertEqual((self.project / "content.json").read_bytes(), before)

    def test_packet_tamper_invalidates_recorded_drafts(self):
        self.record_all()
        self.verified_merge()
        before = (self.project / "content.json").read_bytes()
        packet = nf.read_json(self.project / "packet/pages/p0002.json")
        packet["blocks"][0]["text"] = "A modified source extraction."
        self.put("packet/pages/p0002.json", packet)
        with self.assertRaisesRegex(RuntimeError, "translation_dependencies_changed"):
            self.verified_merge()
        self.assertEqual((self.project / "content.json").read_bytes(), before)

    def test_real_engine_rejects_bad_table_and_omitted_chunk_atomically(self):
        self.record_all()
        plan, _ = self.verified_merge()
        before = (self.project / "content.json").read_bytes()
        changed = copy.deepcopy(self.outputs["b"])
        changed["blocks"][2]["tex"] = "m & E"
        self.put("draft/b.json", changed)
        rejected = self.run_command(MERGE, "--project", self.project, "--chunks", *plan["ordered_outputs"])
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("table tex must contain a native", rejected.stderr)
        self.assertEqual((self.project / "content.json").read_bytes(), before)
        omitted = self.run_command(MERGE, "--project", self.project, "--chunks", plan["ordered_outputs"][0])
        self.assertNotEqual(omitted.returncode, 0)
        self.assertIn("neither covered nor excluded", omitted.stderr)
        self.assertEqual((self.project / "content.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
