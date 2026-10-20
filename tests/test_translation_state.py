"""Behavioral regressions for the provenance scheduler (no model or TeX needed)."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/native-textbook/scripts/translation_state.py"
module = importlib.util.spec_from_file_location("translation_state", SCRIPT)
ts = importlib.util.module_from_spec(module)
module.loader.exec_module(ts)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-state-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put("source.pdf", b"source identity, not a PDF parsing fixture")
        self.put("chunks/a.txt", "A category has energy.")
        self.put("chunks/b.txt", "B contains momentum.")
        self.put("chunks/c.txt", "C ends the argument.")
        self.put("rules.md", "Translate whole semantic units; preserve math and code.")
        self.put("layout.tex", "layout-v1")
        self.put("assets.json", {})
        self.glossary = {"version": 1, "terms": [
            {"id": "energy", "source": "energy", "target": "能量"},
            {"id": "momentum", "source": "momentum", "target": "动量"}]}
        self.put("glossary.json", self.glossary)
        self.spec = {"version": 1, "mode": "book", "source": {"path": "source.pdf"},
                     "glossary": "glossary.json", "context_chars": 0,
                     "translation_inputs": ["rules.md"], "build_inputs": ["layout.tex", "assets.json"],
                     "chunks": [{"id": name, "source": f"chunks/{name}.txt", "output": f"draft/{name}.json",
                                 "source_ids": [f"p000{i}-s0000"]} for i, name in enumerate("abc", 1)]}
        self.put("spec.json", self.spec)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        elif isinstance(value, (dict, list)):
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        else:
            path.write_text(value, encoding="utf-8")

    def initialize(self):
        self.put("spec.json", self.spec)
        return ts.init(self.root, self.root / "spec.json")

    def output(self, name):
        index = "abc".index(name) + 1
        return {"title": "小样", "blocks": [{"id": f"{name}-paragraph", "kind": "paragraph",
                "tex": "按原文保留的中文内容。", "source_ids": [f"p000{index}-s0000"]}],
                "exclusions": [], "unresolved": [],
                "expectations": {"equation_tags": [], "required_strings": [], "table_count": 0, "figure_count": 0}}

    def finish(self, names="abc"):
        for name in names:
            ts.brief(self.root, name)
            self.put(f"draft/{name}.json", self.output(name))
            ts.record(self.root, name)

    def actions(self):
        return {row["id"]: row["action"] for row in ts.plan(self.root)["chunks"]}

    def test_restart_reuses_only_recorded_outputs(self):
        self.initialize()
        self.finish("a")
        self.assertEqual(self.actions(), {"a": "reuse", "b": "translate", "c": "translate"})
        self.finish("bc")
        result = ts.verify(self.root)
        self.assertEqual(result["stage"], "draft_verified")
        self.assertFalse(result["review_valid"])
        self.assertEqual([Path(p).name for p in result["ordered_outputs"]], ["a.json", "b.json", "c.json"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.initialize()

    def test_original_source_change_is_fatal(self):
        self.initialize()
        self.finish()
        self.put("source.pdf", b"different bytes")
        with self.assertRaisesRegex(ValueError, "source bytes changed"):
            ts.plan(self.root)

    def test_untracked_and_modified_outputs_do_not_auto_adopt(self):
        self.initialize()
        self.put("draft/a.json", self.output("a"))
        self.assertEqual(ts.plan(self.root)["chunks"][0]["reasons"], ["untracked_output"])
        with self.assertRaisesRegex(ValueError, "blocked"):
            ts.verify(self.root)
        self.finish()
        changed = self.output("a")
        changed["blocks"][0]["tex"] = "意外改变"
        self.put("draft/a.json", changed)
        self.assertEqual(ts.plan(self.root)["chunks"][0]["reasons"], ["output_changed"])
        self.assertEqual(self.actions()["b"], "reuse")
        ts.record(self.root, "a")  # explicit supervisor adoption, never automatic
        self.assertEqual(self.actions()["a"], "reuse")

    def test_blank_missing_foreign_duplicate_and_unresolved_are_rejected(self):
        self.initialize()
        ts.brief(self.root, "a")
        bad = []
        for mutate in (
                lambda data: data.update(blocks=[]),
                lambda data: data["blocks"][0].update(source_ids=["foreign"]),
                lambda data: data["blocks"][0].update(source_ids=[]),
                lambda data: data["blocks"][0].update(tex=" "),
                lambda data: data.update(unresolved=["unreadable equation"]),
                lambda data: data.update(unresolved="none"),
                lambda data: data["blocks"].append(copy.deepcopy(data["blocks"][0])),
                lambda data: data.update(exclusions=[{"source_id": "p0001-s0000", "category": "out_of_scope", "reason": "outside"}]),
                lambda data: data.update(expectations={"table_count": True}),
                lambda data: data["blocks"][0].update(kind="invented_kind")):
            value = self.output("a")
            mutate(value)
            bad.append(value)
        for value in bad:
            with self.subTest(value=value):
                self.put("draft/a.json", value)
                with self.assertRaises(ValueError):
                    ts.record(self.root, "a")
        self.put("draft/a.json", " \n")
        with self.assertRaises(ValueError):
            ts.record(self.root, "a")

    def test_legal_exclusion_accounts_for_an_owned_id(self):
        self.spec["chunks"][0]["source_ids"].append("header1")
        self.initialize()
        ts.brief(self.root, "a")
        value = self.output("a")
        value["exclusions"] = [{"source_id": "header1", "category": "header_footer", "reason": "running header"}]
        self.put("draft/a.json", value)
        ts.record(self.root, "a")
        self.assertEqual(self.actions()["a"], "reuse")

    def test_glossary_change_is_selective_and_nonsemantic_notes_are_ignored(self):
        self.initialize()
        self.finish()
        self.glossary["terms"][0]["notes"] = "editor comment"
        self.put("glossary.json", self.glossary)
        self.assertEqual(set(self.actions().values()), {"reuse"})
        self.glossary["terms"][0]["target"] = "能"
        self.put("glossary.json", self.glossary)
        self.assertEqual(self.actions(), {"a": "translate", "b": "reuse", "c": "reuse"})
        with self.assertRaisesRegex(ValueError, "brief is stale"):
            ts.record(self.root, "a")
        self.finish("a")
        self.glossary["terms"][0]["aliases"] = ["argument"]
        self.put("glossary.json", self.glossary)
        self.assertEqual(self.actions(), {"a": "translate", "b": "reuse", "c": "translate"})

    def test_neighbor_changes_only_injected_excerpt_invalidates(self):
        self.spec["context_chars"] = 8
        self.put("chunks/b.txt", "12345678 unchanged center abcdefgh")
        self.initialize()
        self.finish()
        self.put("chunks/b.txt", "12345678 changed interior abcdefgh")
        self.assertEqual(self.actions(), {"a": "reuse", "b": "translate", "c": "reuse"})
        self.put("chunks/b.txt", "changed! changed interior abcdefgh")
        self.assertEqual(self.actions(), {"a": "translate", "b": "translate", "c": "reuse"})
        self.put("chunks/b.txt", "changed! changed interior changed!")
        self.assertEqual(self.actions(), {"a": "translate", "b": "translate", "c": "translate"})

    def test_all_55_local_terms_and_word_boundaries(self):
        self.glossary["terms"] = [{"id": f"t{i}", "source": f"term{i}", "target": f"术语{i}"} for i in range(55)]
        self.glossary["terms"].append({"id": "cat", "source": "cat", "target": "猫"})
        self.put("glossary.json", self.glossary)
        self.put("chunks/a.txt", "category " + " ".join(f"term{i}" for i in range(55)))
        self.initialize()
        value = ts.brief(self.root, "a")
        self.assertEqual(len(value["terms"]), 55)
        self.assertNotIn("cat", {term["id"] for term in value["terms"]})

    def test_scoped_homonyms_and_conflicting_aliases(self):
        self.spec["chunks"][0]["scope"] = "finance"
        self.glossary["terms"] = [{"id": "money", "source": "bank", "target": "银行", "scope": "finance"},
                                  {"id": "river", "source": "bank", "target": "河岸", "scope": "geography"}]
        self.put("glossary.json", self.glossary)
        self.put("chunks/a.txt", "bank")
        self.initialize()
        self.assertEqual([term["target"] for term in ts.brief(self.root, "a")["terms"]], ["银行"])
        self.glossary["terms"].append({"id": "clash", "source": "shore", "aliases": ["bank"], "target": "岸", "scope": "global"})
        self.put("glossary.json", self.glossary)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            ts.plan(self.root)

    def test_template_change_rebuilds_without_retranslation(self):
        self.initialize()
        self.finish()
        self.put("layout.tex", "layout-v2")
        self.assertEqual(set(self.actions().values()), {"rebuild"})
        result = ts.verify(self.root)
        self.assertTrue(result["needs_rebuild"])
        self.assertFalse(result["review_valid"])
        self.assertEqual(result["stage"], "draft_verified")

    def test_translation_rules_change_invalidates_all_chunks(self):
        self.initialize()
        self.finish()
        self.put("rules.md", "New symbol policy")
        self.assertEqual(set(self.actions().values()), {"translate"})

    def test_path_and_ownership_errors_fail_before_state_creation(self):
        for mutate in (
                lambda spec: spec["chunks"][0].update(output="../outside.json"),
                lambda spec: spec["chunks"][0].update(output="C:\\outside.json"),
                lambda spec: spec["chunks"][0].update(output="rules.md"),
                lambda spec: spec["chunks"][0].update(output="run-state.json"),
                lambda spec: spec["chunks"][0].update(output="state/briefs/a.json"),
                lambda spec: spec["chunks"][1].update(id="a"),
                lambda spec: spec["chunks"][1].update(output="draft/a.json"),
                lambda spec: spec["chunks"][1].update(source_ids=["p0001-s0000"])):
            with self.subTest(mutate=mutate):
                spec = copy.deepcopy(self.spec)
                mutate(spec)
                self.put("bad-spec.json", spec)
                with self.assertRaises(ValueError):
                    ts.init(self.root, self.root / "bad-spec.json")
                self.assertFalse((self.root / ts.MANIFEST).exists())

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / "escape").symlink_to(Path(outside), target_is_directory=True)
            except OSError:
                self.skipTest("symlink privilege unavailable")
            self.spec["chunks"][0]["output"] = "escape/overwrite.json"
            with self.assertRaisesRegex(ValueError, "escapes root"):
                self.initialize()

    def test_slide_uses_its_own_contract(self):
        self.spec["mode"] = "slide"
        for index, chunk in enumerate(self.spec["chunks"], 1):
            chunk["source_pages"] = [index]
        self.initialize()
        info = ts.brief(self.root, "a")
        slide = {"source_sha256": info["source_sha256"], "pages": [{"source_page": 1,
                 "output_page": 1, "visible_title": "original", "title_cn": "标题", "unresolved": [],
                 "objects": [{"id": "eq1", "kind": "equation", "latex": r"\frac{a}{b}",
                              "source_ids": ["p0001-s0000"]}]}]}
        self.put("draft/a.json", slide)
        ts.record(self.root, "a")
        self.assertEqual(self.actions()["a"], "reuse")
        slide["pages"][0]["source_page"] = 99
        self.put("draft/a.json", slide)
        with self.assertRaisesRegex(ValueError, "page order"):
            ts.record(self.root, "a")

    def test_cli_invalid_input_has_nonzero_exit(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "verify", "--project", str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("translation state blocked", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_brief_tampering_is_not_a_valid_worker_receipt(self):
        self.initialize()
        ts.brief(self.root, "a")
        self.put("draft/a.json", self.output("a"))
        path = self.root / "state/briefs/a.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["source_text"] = "different worker input, same claimed hash"
        self.put("state/briefs/a.json", saved)
        with self.assertRaisesRegex(ValueError, "brief is stale or modified"):
            ts.record(self.root, "a")

    def test_input_cannot_be_the_generated_state_file(self):
        self.put("run-state.json", "would be destroyed")
        self.spec["chunks"][0]["source"] = "run-state.json"
        # Existing state already blocks init, even before input validation.
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.initialize()
        (self.root / "run-state.json").unlink()
        self.put("state/briefs/input.txt", "do not overwrite")
        self.spec["chunks"][0]["source"] = "state/briefs/input.txt"
        with self.assertRaisesRegex(ValueError, "input conflicts"):
            self.initialize()

    def test_slide_output_mapping_is_explicit(self):
        self.spec["mode"] = "slide"
        for index, chunk in enumerate(self.spec["chunks"], 1):
            chunk["source_pages"] = [index + 10]
            chunk["output_pages"] = [index]
        self.initialize()
        info = ts.brief(self.root, "a")
        value = {"source_sha256": info["source_sha256"], "pages": [{"source_page": 11,
                 "output_page": 2, "unresolved": [], "objects": [{"id": "text1", "kind": "text",
                 "text": "中文", "source_ids": ["p0001-s0000"]}]}]}
        self.put("draft/a.json", value)
        with self.assertRaisesRegex(ValueError, "output page mapping"):
            ts.record(self.root, "a")
        value["pages"][0]["output_page"] = 1
        self.put("draft/a.json", value)
        ts.record(self.root, "a")

    def test_manifest_scope_order_and_path_changes_are_not_silent(self):
        self.initialize()
        self.finish("ab")
        manifest = json.loads((self.root / ts.MANIFEST).read_text(encoding="utf-8"))
        for mutate in (lambda value: value["chunks"].pop(),
                       lambda value: value["chunks"].reverse(),
                       lambda value: value["chunks"][0].update(output="draft/new.json"),
                       lambda value: value.update(translation_inputs=[])):
            changed = copy.deepcopy(manifest)
            mutate(changed)
            self.put(ts.MANIFEST, changed)
            with self.assertRaisesRegex(ValueError, "manifest identity changed"):
                ts.verify(self.root)
        self.put(ts.MANIFEST, manifest)
        self.finish("c")
        self.assertEqual(ts.verify(self.root)["stage"], "draft_verified")

    def test_original_source_cannot_be_a_future_brief(self):
        self.put("state/briefs/a.json", b"source bytes that brief would overwrite")
        self.spec["source"]["path"] = "state/briefs/a.json"
        with self.assertRaisesRegex(ValueError, "original source conflicts"):
            self.initialize()
        self.assertEqual((self.root / "state/briefs/a.json").read_bytes(), b"source bytes that brief would overwrite")

    def test_real_blank_slide_can_share_a_package_with_nonblank_pages(self):
        self.spec["mode"] = "slide"
        self.spec["chunks"][0]["source_pages"] = [1, 2]
        self.spec["chunks"][1]["source_pages"] = [3]
        self.spec["chunks"][2]["source_pages"] = [4]
        self.initialize()
        info = ts.brief(self.root, "a")
        value = {"source_sha256": info["source_sha256"], "pages": [
            {"source_page": 1, "output_page": 1, "unresolved": [], "objects": [
                {"id": "text1", "kind": "text", "text": "中文", "source_ids": ["p0001-s0000"]}]},
            {"source_page": 2, "output_page": 2, "unresolved": [], "objects": [],
             "blank": True, "checked": True, "reason": "source inventory confirms an intentionally blank page"}]}
        self.put("draft/a.json", value)
        ts.record(self.root, "a")
        for field in ("blank", "checked", "reason"):
            bad = copy.deepcopy(value)
            bad["pages"][1].pop(field)
            self.put("draft/a.json", bad)
            with self.assertRaisesRegex(ValueError, "empty slide requires"):
                ts.record(self.root, "a")

    def test_cli_brief_prints_receipt_not_source(self):
        self.initialize()
        result = subprocess.run([sys.executable, str(SCRIPT), "brief", "--project", str(self.root), "--chunk", "a"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(set(receipt), {"brief", "translation_fingerprint", "build_fingerprint"})
        saved = json.loads(Path(receipt["brief"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["source_text"], "A category has energy.")

    def test_code_and_console_use_authoritative_raw_text_contract(self):
        self.initialize()
        ts.brief(self.root, "a")
        for kind in ("code", "console"):
            value = self.output("a")
            value["blocks"][0] = {"id": "literal1", "kind": kind, "source_ids": ["p0001-s0000"],
                                  "text": 'value_name = "100%"\nprint(value_name)\n'}
            self.put("draft/a.json", value)
            ts.record(self.root, "a")
            self.assertEqual(self.actions()["a"], "reuse")
            for forbidden in ("tex", "language"):
                bad = copy.deepcopy(value)
                bad["blocks"][0][forbidden] = "python"
                self.put("draft/a.json", bad)
                with self.assertRaisesRegex(ValueError, "literal block has unsupported fields"):
                    ts.record(self.root, "a")
            bad = copy.deepcopy(value)
            bad["blocks"][0]["text"] = "bad\x00control"
            self.put("draft/a.json", bad)
            with self.assertRaisesRegex(ValueError, "control characters"):
                ts.record(self.root, "a")

    def test_native_figure_uses_tex_and_registered_figure_uses_asset(self):
        self.initialize()
        ts.brief(self.root, "a")
        value = self.output("a")
        value["blocks"][0].update(kind="figure_native", tex=r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}")
        self.put("draft/a.json", value)
        ts.record(self.root, "a")
        bad = copy.deepcopy(value)
        bad["blocks"][0]["asset"] = "figure1"
        self.put("draft/a.json", bad)
        with self.assertRaisesRegex(ValueError, "figure_native puts"):
            ts.record(self.root, "a")
        value["blocks"][0] = {"id": "fig1", "kind": "figure", "source_ids": ["p0001-s0000"],
                              "asset": "registered-figure", "caption": ""}
        self.put("draft/a.json", value)
        ts.record(self.root, "a")
        value["blocks"][0]["tex"] = r"\includegraphics{not-registered}"
        self.put("draft/a.json", value)
        with self.assertRaisesRegex(ValueError, "registered asset"):
            ts.record(self.root, "a")


if __name__ == "__main__":
    unittest.main()
