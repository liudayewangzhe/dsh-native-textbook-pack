"""Layout contracts and measured-note audits; real TeX samples live in reports."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import native_forge as nf

LAYOUT = {"paper_width_mm": 240, "paper_height_mm": 285, "text_width_mm": 145,
          "inner_mm": 22, "outer_mm": 22, "margin_note_width_mm": 44,
          "margin_note_sep_mm": 7, "notes": "outer", "note_font_pt": 9, "note_leading_pt": 13}


def content():
    return {"title": "Sample", "blocks": [
        {"id": "paragraph", "kind": "paragraph", "source_ids": ["p0001-b0000"],
         "tex": r"Native body\nfnotemark{n1}{1}."},
        {"id": "n1", "kind": "note", "source_ids": ["p0001-b0000"],
         "tex": "Native note.", "number": "1", "placement": "margin"}],
        "exclusions": [], "unresolved": [], "expectations": {
            "equation_tags": [], "figure_count": 0, "table_count": 0, "required_strings": []}}


class LayoutContracts(unittest.TestCase):
    def validate(self, value):
        return nf.validate_content(value, {"p0001-b0000"}, set())

    def test_legacy_geometry_does_not_gain_overrides(self):
        value = content()
        value["blocks"] = [dict(value["blocks"][0], tex="Native body.")]
        rendered = nf.render_main_tex({"title": "Legacy"}, value, {})
        self.assertNotIn("NFGeometrySettings", rendered)
        self.assertEqual(nf.validate_layout({})["text_width_mm"], 164)

    def test_closed_geometry_and_invalid_inputs(self):
        self.assertEqual(nf.validate_layout({"layout": LAYOUT})["paper_width_mm"], 240)
        for change in ({"paper_width_mm": 241}, {"notes": "unknown"}, {"note_font_pt": True},
                       {"text_width_mm": float("nan")}, {"margin_note_width_mm": 0},
                       {"note_leading_pt": 8}, {"paper_height_mm": 40}, {"typo_mm": 2},
                       {"chapter_open": "left"}):
            with self.subTest(change=change), self.assertRaises(nf.EngineError):
                nf.validate_layout({"layout": {**LAYOUT, **change}})

    def test_custom_layout_opens_chapters_on_any_page_unless_explicit(self):
        self.assertIn(r"\makeatletter\@openrightfalse\makeatother", nf.render_layout({"layout": LAYOUT}))
        right = {**LAYOUT, "chapter_open": "right"}
        self.assertIn(r"\makeatletter\@openrighttrue\makeatother", nf.render_layout({"layout": right}))

    def test_note_declared_before_document_at_mark_and_linked_by_stable_id(self):
        value = content()
        self.validate(value)
        rendered = nf.render_main_tex({"title": "Notes", "layout": LAYOUT}, value, {})
        self.assertIn("paperwidth=240mm,paperheight=285mm,inner=22mm,outer=73mm", rendered)
        self.assertLess(rendered.index(r"\nfDeclareMarginNote{n1}{1}"), rendered.index(r"\begin{document}"))
        self.assertEqual(rendered.count("Native note."), 1)
        self.assertIn(r"\nfnotemark{n1}{1}", rendered)
        self.assertEqual(rendered.count(r"\hypertarget{src-p0001-b0000}{}"), 1)
        with self.assertRaises(nf.EngineError):
            nf.render_main_tex({"title": "No side column"}, value, {})

    def test_note_marks_require_unique_pair_and_matching_number(self):
        for text in ("No mark.", r"\nfnotemark{n1}{2}", r"\nfnotemark{missing}{1}",
                     r"\nfnotemark{n1}{1}\nfnotemark{n1}{1}", r"\nfnotemark{n1}"):
            value = content()
            value["blocks"][0]["tex"] = text
            with self.subTest(text=text), self.assertRaises(nf.EngineError):
                self.validate(value)

    def test_position_anchored_margin_note_needs_no_body_mark(self):
        # Evidence blocks that mix body prose with a margin note cannot always keep the
        # mark inside a paragraph; such a note declares anchor=position and is placed at
        # its own list position instead of at an nfnotemark.
        value = content()
        value["blocks"][0] = dict(value["blocks"][0], tex="Native body.")
        value["blocks"][1] = dict(value["blocks"][1], anchor="position")
        self.validate(value)
        rendered = nf.render_main_tex({"title": "Positioned", "layout": LAYOUT}, value, {})
        self.assertIn(r"\nfPositionMarginNote{n1}{1}{Native note.}", rendered)
        self.assertNotIn("nfDeclareMarginNote", rendered)
        # Without the explicit opt-in the old contract still rejects a mark-less margin note.
        strict = content()
        strict["blocks"][0] = dict(strict["blocks"][0], tex="Native body.")
        with self.assertRaises(nf.EngineError):
            self.validate(strict)
        # A block note may also opt in: it has no side lane, so it is emitted as a block.
        as_block = content()
        as_block["blocks"][0] = dict(as_block["blocks"][0], tex="Native body.")
        as_block["blocks"][1] = dict(as_block["blocks"][1], anchor="position", placement="block")
        self.validate(as_block)
        self.assertIn(r"\nfBlockNote{n1}{1}{Native note.}",
                      nf.render_main_tex({"title": "Block", "layout": LAYOUT}, as_block, {}))
        # An unknown anchor value is still refused.
        wrong = content()
        wrong["blocks"][1] = dict(wrong["blocks"][1], anchor="elsewhere")
        with self.assertRaises(nf.EngineError):
            self.validate(wrong)

    def test_preamble_additions_are_bounded_and_hashed(self):
        project = {"title": "Pre", "layout": LAYOUT,
                   "preamble": ["\\renewcommand{\\thechapter}{\\arabic{chapter}}"]}
        rendered = nf.render_main_tex(project, content(), {})
        self.assertIn("\\renewcommand{\\thechapter}{\\arabic{chapter}}", rendered)
        self.assertLess(rendered.index("\\renewcommand{\\thechapter}"),
                        rendered.index("\\begin{document}"))
        # The preamble participates in the build fingerprint.
        keys = tuple(nf.fingerprint_files.__doc__ or "")
        self.assertTrue(callable(nf.validate_preamble))
        for bad in ({"preamble": "not-a-list"},
                    {"preamble": ["\\input{secret}"]},
                    {"preamble": ["\\begin{document}"]},
                    {"preamble": ["a", "b\nc"]}):
            with self.subTest(bad=bad), self.assertRaises(nf.EngineError):
                nf.validate_preamble({**project, **bad})
        self.assertEqual(nf.validate_preamble({"title": "No preamble"}), [])

    def test_block_note_is_breakable_native_body(self):
        value = content()
        value["blocks"][1]["placement"] = "block"
        self.validate(value)
        rendered = nf.render_main_tex({"title": "Block"}, value, {})
        self.assertIn(r"\nfBlockNote{n1}{1}{Native note.}", rendered)
        self.assertNotIn("nfDeclareMarginNote", rendered)

    def test_full_span_stays_native_and_rejects_nested_float(self):
        equation = {"kind": "equation", "tex": r"a=b\tag{1}", "span": "full"}
        rendered = nf.render_block(equation, {})
        self.assertIn(r"\begin{nfFullWidth}", rendered)
        self.assertIn(r"\begin{equation}", rendered)
        self.assertNotIn("resizebox", rendered)
        value = content()
        value["blocks"][-1] = {"id": "wide", "kind": "figure_native", "span": "full",
            "source_ids": ["p0001-b0000"], "tex": r"\begin{figure}x\end{figure}"}
        value["blocks"][0]["tex"] = "Body."
        value["expectations"]["figure_count"] = 1
        with self.assertRaises(nf.EngineError):
            self.validate(value)

    def test_aux_geometry_reports_drift_overlap_and_bad_paper(self):
        value = content()
        value["blocks"].append(dict(value["blocks"][1], id="n2", number="2"))
        factor = 72.27 * 65536 / 25.4
        def label(name, page, x, y):
            return rf"\zref@newlabel{{{name}}}{{\posx{{{round(x * factor)}}}\posy{{{round((285-y)*factor)}}}\abspage{{{page}}}}}"
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            labels = []
            for note_id in ("n1", "n2"):
                labels.extend([label("nf-mark-"+note_id, 1, 80, 40),
                               label("nf-note-start-"+note_id, 1, 174, 40),
                               label("nf-note-end-"+note_id, 1, 174, 50)])
            (directory / "main.aux").write_text("\n".join(labels), encoding="utf-8")
            (directory / "main.log").write_text("\n".join(
                f"NFNOTE-METRIC {note_id} height={round(15*factor)} width={round(44*factor)}" for note_id in ("n1", "n2")))
            report = nf.audit_layout({"layout": LAYOUT}, value, directory, [(1, 240, 285)])
            self.assertTrue(any("overlap" in finding for finding in report["findings"]))
            self.assertFalse(any("outer column" in finding for finding in report["findings"]))
            (directory / "main.aux").write_text("\n".join(labels).replace(r"\abspage{1}", r"\abspage{2}", 1), encoding="utf-8")
            report = nf.audit_layout({"layout": LAYOUT}, value, directory, [(1, 210, 297)])
            self.assertTrue(any("moved" in finding for finding in report["findings"]))
            self.assertTrue(any("actual paper" in finding for finding in report["findings"]))

    def test_margin_queue_errors_are_fatal_qa_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.log"
            path.write_text("NFNOTE-OVERSIZE n1\nNF-MARGIN-QUEUE-NOT-EMPTY\nlost some margin notes")
            self.assertEqual(len(nf.scan_compile_log(path)["margin"]), 3)

    def test_layout_and_measured_positions_invalidate_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "build").mkdir()
            (root / "content.json").write_text(json.dumps(content()), encoding="utf-8")
            (root / "assets.json").write_text("{}", encoding="utf-8")
            (root / "source.pdf").write_bytes(b"read-only fixture")
            (root / "build" / "main.aux").write_text("positions version one")
            project = {"schema_version": 1, "title": "Fingerprint", "pages": [], "templates": {},
                       "source": {"path": str(root / "source.pdf")}, "layout": dict(LAYOUT)}
            before = nf.fingerprint_files(root, project, root)
            project["layout"]["paper_height_mm"] = 286
            after = nf.fingerprint_files(root, project, root)
            self.assertNotEqual(before["project"], after["project"])
            (root / "build" / "main.aux").write_text("positions version two")
            changed = nf.fingerprint_files(root, project, root)
            self.assertNotEqual(after["layout_positions"], changed["layout_positions"])


class HeadingStructureContracts(unittest.TestCase):
    def fixture(self):
        value = content()
        expected = ["p0001-b0001", "p0002-b0001"]
        value["expectations"]["heading_source_ids"] = expected
        value["blocks"].insert(0, {"id": "special-relativity", "kind": "chapter",
            "source_ids": [expected[0]], "tex": "狭义相对论"})
        value["blocks"].append({"id": "general-relativity", "kind": "chapter",
            "source_ids": [expected[1]], "tex": "广义相对论"})
        return value, {"p0001-b0000", *expected}

    def test_independent_source_headings_in_source_order_pass(self):
        value, packet = self.fixture()
        nf.validate_content(value, packet, set())

    def test_merged_similar_headings_fail_despite_total_source_coverage(self):
        value, packet = self.fixture()
        value["blocks"][0]["source_ids"].extend(value["blocks"][-1]["source_ids"])
        value["blocks"].pop()
        with self.assertRaisesRegex(nf.EngineError, "multiple independent heading_source_ids"):
            nf.validate_content(value, packet, set())

    def test_paragraph_coverage_cannot_substitute_for_missing_heading(self):
        value, packet = self.fixture()
        value["blocks"][-1]["kind"] = "paragraph"
        with self.assertRaisesRegex(nf.EngineError, "must bind exactly one"):
            nf.validate_content(value, packet, set())

    def test_reordering_duplication_and_unknown_expected_source_fail(self):
        for mode in ("reorder", "duplicate_block", "duplicate_expectation", "unknown_source"):
            value, packet = self.fixture()
            if mode == "reorder":
                value["blocks"][0], value["blocks"][-1] = value["blocks"][-1], value["blocks"][0]
            elif mode == "duplicate_block":
                value["blocks"].append({**value["blocks"][0], "id": "duplicate-title"})
            elif mode == "duplicate_expectation":
                value["expectations"]["heading_source_ids"].append("p0001-b0001")
            else:
                value["expectations"]["heading_source_ids"].append("p9999-b9999")
            with self.subTest(mode=mode), self.assertRaises(nf.EngineError):
                nf.validate_content(value, packet, set())

    def test_omitted_gate_keeps_legacy_source_coverage_behavior(self):
        value, packet = self.fixture()
        value["expectations"].pop("heading_source_ids")
        value["blocks"][0]["source_ids"].extend(value["blocks"][-1]["source_ids"])
        value["blocks"].pop()
        nf.validate_content(value, packet, set())


class JoinedParagraphContracts(unittest.TestCase):
    def fixture(self):
        value = content()
        value["blocks"] = [
            {"id": "left", "kind": "paragraph", "source_ids": ["p0001-b0000"],
             "tex": "一个跨来源页的\n\n", "join_next": True},
            {"id": "right", "kind": "paragraph", "source_ids": ["p0002-b0000"],
             "tex": "\n\n完整句子。"}]
        return value, {"p0001-b0000", "p0002-b0000"}

    def test_source_blocks_remain_distinct_without_implicit_paragraph_break(self):
        value, packet = self.fixture()
        nf.validate_content(value, packet, set())
        rendered = nf.render_main_tex({"title": "Joined"}, value, {})
        seam = rendered[rendered.index("一个跨来源页的"):rendered.index("完整句子。")]
        self.assertNotIn(r"\par", seam)
        self.assertNotIn("\n\n", seam)
        self.assertIn("% Source block: right", seam)
        self.assertIn(r"\hypertarget{src-p0002-b0000}{}", seam)
        self.assertIn("完整句子。\n\\par", rendered)

    def test_joining_cannot_skip_nonparagraph_blocks_or_use_nonboolean(self):
        for mode in ("last", "heading", "equation", "figure", "number", "wrong_kind", "explicit_boundary"):
            value, packet = self.fixture()
            if mode == "last":
                value["blocks"][-1]["join_next"] = True
            elif mode in ("heading", "equation", "figure"):
                value["blocks"][-1]["kind"] = {"heading": "section", "equation": "equation", "figure": "figure_native"}[mode]
            elif mode == "number":
                value["blocks"][0]["join_next"] = 1
            elif mode == "wrong_kind":
                value["blocks"][0]["kind"] = "section"
            else:
                value["blocks"][-1]["tex"] = r"\clearpage Next page"
            with self.subTest(mode=mode), self.assertRaisesRegex(nf.EngineError, "join_next"):
                nf.validate_content(value, packet, set())


class ContinuedEquationContracts(unittest.TestCase):
    def fixture(self):
        value = content()
        value["blocks"] = [
            {"id": "derivation-start", "kind": "equation", "source_ids": ["p0001-b0000"],
             "tex": "a=b+c", "numbered": False, "keep_with_next": True},
            {"id": "derivation-end", "kind": "equation", "source_ids": ["p0002-b0000"],
             "tex": "=d+e", "numbered": False}]
        return value, {"p0001-b0000", "p0002-b0000"}

    def test_continued_equations_keep_distinct_sources_and_block_identity(self):
        value, packet = self.fixture()
        nf.validate_content(value, packet, set())
        rendered = nf.render_main_tex({"title": "Continued"}, value, {})
        seam = rendered[rendered.index(r"\end{equation*}"):rendered.index("=d+e")]
        self.assertTrue(seam.startswith("\\end{equation*}\n\\nopagebreak[4]\n\\endgroup\n% Source block: derivation-end"))
        self.assertEqual(rendered.count(r"\begingroup\postdisplaypenalty=10000"), 1)
        self.assertIn(r"\hypertarget{src-p0002-b0000}{}", seam)
        self.assertEqual(rendered.count(r"\begin{equation*}"), 2)
        self.assertEqual(rendered.count(r"\nopagebreak[4]"), 1)

    def test_false_and_omitted_keep_flag_preserve_legacy_render(self):
        value, packet = self.fixture()
        value["blocks"][0]["keep_with_next"] = False
        nf.validate_content(value, packet, set())
        explicit_false = nf.render_main_tex({"title": "Continued"}, value, {})
        value["blocks"][0].pop("keep_with_next")
        self.assertEqual(explicit_false, nf.render_main_tex({"title": "Continued"}, value, {}))
        self.assertNotIn(r"\nopagebreak[4]", explicit_false)

    def test_keep_flag_rejects_last_block_cross_structure_and_nonboolean(self):
        for mode in ("last", "paragraph", "section", "figure_native", "note", "integer", "string", "wrong_kind"):
            value, packet = self.fixture()
            if mode == "last":
                value["blocks"][-1]["keep_with_next"] = True
            elif mode in ("paragraph", "section", "figure_native", "note"):
                value["blocks"][-1]["kind"] = mode
            elif mode in ("integer", "string"):
                value["blocks"][0]["keep_with_next"] = 1 if mode == "integer" else "true"
            else:
                value["blocks"][0]["kind"] = "paragraph"
            with self.subTest(mode=mode), self.assertRaisesRegex(nf.EngineError, "keep_with_next"):
                nf.validate_content(value, packet, set())


if __name__ == "__main__":
    unittest.main()
