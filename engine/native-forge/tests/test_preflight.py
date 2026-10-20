"""Real tiny source fixtures exercise preflight; source books are never edited."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preflight_pdf as preflight
try:
    import fitz
except ImportError:
    fitz = None


@unittest.skipIf(fitz is None, "PyMuPDF required")
class SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-preflight-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def image(self):
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 64, 64), False)
        pixmap.clear_with(180)
        return pixmap.tobytes("png")

    def source(self, pages=2):
        path = self.root / "source.pdf"
        document = fitz.open()
        for _ in range(pages):
            page = document.new_page(width=600, height=800)
            page.insert_text((40, 40), "Native source text remains readable.", fontsize=11)
        document.save(path)
        document.close()
        return path

    def test_page_image_is_not_a_detected_wide_equation_or_table(self):
        document = fitz.open()
        page = document.new_page(width=600, height=800)
        page.insert_image(page.rect, stream=self.image())
        observation = preflight.page_observations(page)
        self.assertIn("large_page_image_low_text", observation["candidates"])
        self.assertNotIn("source_object_wider_than_reference_body", observation["candidates"])
        self.assertEqual(observation["text_characters"], 0)
        self.assertEqual(observation["max_image_area_ratio"], 1)
        self.assertNotIn("no_observed_content", observation["candidates"])
        document.close()

    def test_hidden_text_layer_is_observed_without_declaring_ocr_correct(self):
        document = fitz.open()
        page = document.new_page(width=600, height=800)
        page.insert_image(page.rect, stream=self.image())
        page.insert_textbox(fitz.Rect(40, 40, 550, 700), "Hidden OCR layer may be wrong. " * 10,
                            fontsize=11, render_mode=3)
        observation = preflight.page_observations(page)
        self.assertIn("large_page_image_with_text_layer", observation["candidates"])
        self.assertNotIn("ocr_verified", observation)
        document.close()

    def test_code_math_and_rules_are_only_typographic_candidates(self):
        document = fitz.open()
        page = document.new_page(width=600, height=800)
        page.insert_text((40, 40), "def function(x):\n    return x + 1\n>>> function(3)", fontname="cour", fontsize=11)
        page.insert_text((40, 140), "a+b=c+d+e+f+g+h", fontname="symb", fontsize=16)
        for y in (220, 250, 280, 310):
            page.draw_line((40, y), (520, y))
        for x in (40, 250, 520):
            page.draw_line((x, 220), (x, 310))
        observation = preflight.page_observations(page)
        self.assertIn("code_or_literal", observation["candidates"])
        self.assertIn("mathematical_typography", observation["candidates"])
        self.assertIn("ruled_table_or_diagram", observation["candidates"])
        self.assertNotIn("formula_complexity", observation)
        document.close()

    def test_square_photo_is_not_claimed_to_be_decoded_qr(self):
        document = fitz.open()
        page = document.new_page(width=600, height=800)
        page.insert_image(fitz.Rect(40, 40, 100, 100), stream=self.image())
        page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 40, 100, 100), "uri": "https://example.org/resource"})
        page = document.reload_page(page)
        observation = preflight.page_observations(page)
        self.assertIn("square_image_not_yet_qr", observation["candidates"])
        self.assertEqual(observation["external_uris"], ["https://example.org/resource"])
        self.assertNotIn("decoded_qr", observation)
        document.close()

    def test_landscape_pdf_and_pptx_have_distinct_routes(self):
        pdf = self.root / "slides.pdf"
        document = fitz.open()
        page = document.new_page(width=960, height=540)
        page.insert_text((40, 50), "Panel A                         Panel B")
        observation = preflight.page_observations(page)
        document.save(pdf)
        document.close()
        self.assertIn("landscape_or_presentation_pdf", observation["candidates"])
        self.assertIsNone(preflight.input_route(pdf)["book_conversion"])
        pptx = self.root / "editable.pptx"
        with zipfile.ZipFile(pptx, "w") as package:
            package.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>')
        self.assertEqual(preflight.input_route(pptx)["route"], "presentations")
        self.assertFalse(preflight.input_route(pptx)["book_conversion"])
        invalid = self.root / "invalid.pptx"
        invalid.write_bytes(b"not a presentation")
        with self.assertRaises(ValueError):
            preflight.input_route(invalid)

    def test_multiband_coordinates_do_not_claim_semantic_columns(self):
        document = fitz.open()
        page = document.new_page(width=600, height=800)
        for row in range(8):
            page.insert_text((40, 120+row*20), "Main paragraph with more words", fontsize=11)
            page.insert_text((440, 120+row*20), "Right small note", fontsize=8)
        observation = preflight.page_observations(page)
        self.assertIn("multiple_text_bands", observation["candidates"])
        self.assertIn("margin_text_or_figure_labels", observation["candidates"])
        self.assertNotIn("confirmed_columns", observation)
        document.close()

    def test_source_hash_is_preserved_and_cache_avoids_repeat_scanning(self):
        path = self.source()
        before = preflight.file_hash(path)
        entry = {"id": "sample", "path": str(path)}
        with mock.patch.object(preflight, "ensure_memory"):
            first = preflight.scan_source(entry, self.root / "scan")
            with mock.patch.object(preflight, "page_observations", side_effect=AssertionError("cache should be reused")):
                second = preflight.scan_source(entry, self.root / "scan")
        self.assertEqual(preflight.file_hash(path), before)
        self.assertTrue(first["source_unchanged_after_scan"])
        self.assertEqual(first["pages"], second["pages"])

    def test_memory_pause_saves_completed_pages_and_resume_continues(self):
        entry = {"id": "sample", "path": str(self.source(3))}
        with mock.patch.object(preflight, "ensure_memory", side_effect=[None, None, MemoryError("stop")]):
            with self.assertRaises(MemoryError):
                preflight.scan_source(entry, self.root / "scan")
        checkpoint = json.loads((self.root / "scan" / "sample.json").read_text(encoding="utf-8"))
        self.assertEqual(checkpoint["status"], "paused_low_memory")
        self.assertEqual(len(checkpoint["pages"]), 1)
        original = preflight.page_observations
        with mock.patch.object(preflight, "ensure_memory"), mock.patch.object(preflight, "page_observations", wraps=original) as observe:
            final = preflight.scan_source(entry, self.root / "scan")
        self.assertEqual(observe.call_count, 2)
        self.assertEqual(final["status"], "complete")

    def test_source_change_during_scan_is_rejected(self):
        path = self.source(1)
        original_hash = preflight.file_hash
        calls = 0
        def changed_hash(target):
            nonlocal calls
            if Path(target) == path:
                calls += 1
                return original_hash(target) if calls == 1 else "changed"
            return original_hash(target)
        with mock.patch.object(preflight, "ensure_memory"), mock.patch.object(preflight, "file_hash", side_effect=changed_hash):
            with self.assertRaisesRegex(ValueError, "source changed"):
                preflight.scan_source({"id": "sample", "path": str(path)}, self.root / "scan")


if __name__ == "__main__":
    unittest.main()
