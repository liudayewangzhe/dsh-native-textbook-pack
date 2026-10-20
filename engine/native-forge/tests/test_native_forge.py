"""Unit tests for engine/native_forge.py.

Runs against temp minimal PDFs and temp templates; XeLaTeX is mocked with a tiny
Python script, so no TeX installation is required.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(ENGINE_DIR))

import native_forge as nf  # noqa: E402

try:
    import fitz
except ImportError:  # pragma: no cover - environment dependent
    fitz = None

PAGES = [1, 2, 3]
RASTER_RECT = (30.0, 220.0, 110.0, 300.0)
VECTOR_RASTER_FREE_RECT = (30.0, 100.0, 150.0, 140.0)

FAKE_XELATEX = '''
import json, os, sys
spec = {}
if os.path.exists("fake_spec.json"):
    with open("fake_spec.json", encoding="utf-8") as handle:
        spec = json.load(handle)
with open("main.log", "w", encoding="utf-8") as handle:
    handle.write(spec.get("log", "This is XeTeX, Version 3.141592653\\n"))
if spec.get("pdf", True):
    import fitz
    doc = fitz.open()
    for text in spec.get("pages", ["alpha beta gamma", "1.1", "section 1.1 body"]):
        page = doc.new_page(width=300, height=400)
        page.insert_text((30, 40), text, fontsize=10)
    if spec.get("raster_path"):
        doc[0].insert_image(fitz.Rect(20, 80, 100, 160), filename=spec["raster_path"])
    if spec.get("raster"):
        pix = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 4, 4), False)
        pix.clear_with(255)
        doc[0].insert_image(fitz.Rect(20, 80, 100, 160), stream=pix.tobytes("png"))
    doc.save("main.pdf", no_new_id=True)
sys.exit(int(spec.get("exit", 0)))
'''


def write_templates(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "elegantbook.cls").write_text("% stub class\n\\ProvidesClass{elegantbook}\n",
                                               encoding="utf-8")
    (directory / "nativeforge.sty").write_text("% stub style\n\\ProvidesPackage{nativeforge}\n",
                                               encoding="utf-8")
    return directory


def make_source_pdf(path, pages=3, with_raster=True):
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((30, 30), "chapter heading", fontsize=12)
        page.insert_text((30, 60), "line one\nline two", fontsize=10)
        page.insert_text((30, 80), "alpha beta gamma", fontsize=10)
        page.draw_rect(fitz.Rect(*VECTOR_RASTER_FREE_RECT))
        page.draw_line(fitz.Point(30, 150), fitz.Point(150, 150))
        page.insert_text((30, 180), "(1.1)", fontsize=10)
    if with_raster:
        pix = fitz.Pixmap(fitz.csRGB, 8, 8, bytes([255, 0, 0] * 64), False)
        doc[pages - 1].insert_image(fitz.Rect(*RASTER_RECT), stream=pix.tobytes("png"))
    doc.save(path, no_new_id=True)
    doc.close()


def packet_texts(project_dir, pages=PAGES):
    texts = {}
    for page in pages:
        path = Path(project_dir) / "packet" / "pages" / f"p{page:04d}.json"
        for block in json.loads(path.read_text(encoding="utf-8"))["blocks"]:
            texts[block["id"]] = block["text"]
    return texts


def base_content(project_dir, asset_name="fig1"):
    texts = packet_texts(project_dir)
    ids = sorted(texts)
    equation_id = next(i for i in ids if "1.1" in texts[i])
    rest = [i for i in ids if i != equation_id]
    section_id, table_id, figure_id, native_id = rest[:4]
    return {
        "title": "TEXTBOOK TITLE",
        "blocks": [
            {"id": "b-section", "kind": "section", "source_ids": [section_id], "tex": "1.1 示例小节"},
            {"id": "b-para", "kind": "paragraph", "source_ids": rest[4:], "tex": "本节正文段落。"},
            {"id": "b-eq", "kind": "equation", "source_ids": [equation_id],
             "tex": "a = b + c \\tag{1.1}"},
            {"id": "b-table", "kind": "table", "source_ids": [table_id],
             "tex": "\\begin{tabular}{ll}\nA & B \\\\\n\\end{tabular}"},
            {"id": "b-fig", "kind": "figure", "source_ids": [figure_id], "asset": asset_name,
             "caption": "示例图", "number": "1.2"},
            {"id": "b-native", "kind": "figure_native", "source_ids": [native_id],
             "tex": "\\begin{tikzpicture}\n\\draw (0,0) -- (1,1);\n\\end{tikzpicture}"},
        ],
        "exclusions": [],
        "unresolved": [],
        "expectations": {"equation_tags": ["1.1"], "table_count": 1, "figure_count": 2,
                         "required_strings": ["alpha beta gamma", "1.1"]},
    }


def load_content(project_dir):
    return json.loads((Path(project_dir) / "content.json").read_text(encoding="utf-8"))


def save_content(project_dir, content):
    (Path(project_dir) / "content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def qa_report(project_dir):
    path = Path(project_dir) / "qa" / "qa_report.json"
    return json.loads(path.read_text(encoding="utf-8"))


def finding_checks(project_dir):
    return [finding["check"] for finding in qa_report(project_dir)["findings"]]


def finding_text(project_dir):
    return "\n".join(finding["detail"] for finding in qa_report(project_dir)["findings"])


class TemporaryProjectCase(unittest.TestCase):
    """Provides temp dirs plus a prepared project fixture (source + templates)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="native-forge-")
        cls.root = Path(cls.tmp.name)
        cls.templates = write_templates(cls.root / "templates")
        cls.source = cls.root / "source.pdf"
        make_source_pdf(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def new_project(self, name="project", pages="1-3", with_raster=True):
        project = self.root / name
        if not self.source.is_file() or not with_raster:
            source = self.root / f"{name}-source.pdf"
            make_source_pdf(source, with_raster=with_raster)
        else:
            source = self.source
        nf.prepare(source, pages, project, "TEXTBOOK TITLE", templates_dir=self.templates)
        return project, source

    def fixture(self, name="fixture"):
        """Prepared project with a vector asset and a fully covering content.json."""
        project, source = self.new_project(name)
        nf.asset(project, 1, list(VECTOR_RASTER_FREE_RECT), "fig1")
        save_content(project, base_content(project))
        return project, source

    def copy_project(self, project, name):
        target = self.root / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(project, target)
        return target

    def write_fake_spec(self, project, **spec):
        build_dir = Path(project) / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "fake_spec.json").write_text(json.dumps(spec), encoding="utf-8")
        fake_script = self.root / "fake_xelatex.py"
        if not fake_script.is_file():
            fake_script.write_text(FAKE_XELATEX, encoding="utf-8")
        return mock.patch.object(nf, "resolve_xelatex",
                                 lambda: [sys.executable, str(fake_script)])

    def build_project(self, project, **spec):
        with self.write_fake_spec(project, **spec):
            return nf.build(project, templates_dir=self.templates)

    def qa_project(self, project):
        return nf.qa(project, templates_dir=self.templates)

    def release_project(self, project):
        return nf.release(project, templates_dir=self.templates)


class TestPureHelpers(unittest.TestCase):
    def test_parse_pages(self):
        self.assertEqual(nf.parse_pages("24-32"), list(range(24, 33)))
        self.assertEqual(nf.parse_pages("24,26,30-32"), [24, 26, 30, 31, 32])
        self.assertEqual(nf.parse_pages(" 7 "), [7])
        for bad in ("", "abc", "0-2", "32-24", "1--2", "24,"):
            with self.assertRaises(nf.EngineError):
                nf.parse_pages(bad)
        with self.assertRaises(nf.EngineError):
            nf.parse_pages("1-5", page_count=4)

    def test_latex_escape(self):
        escaped = nf.latex_escape("100% of A_1 & {B} #2 $x$ \\ ~ ^")
        for fragment in ("\\%", "\\_", "\\&", "\\{B\\}", "\\#", "\\$", "\\textbackslash{}",
                         "\\textasciitilde{}", "\\textasciicircum{}"):
            self.assertIn(fragment, escaped)

    def test_stable_sha256_is_order_independent(self):
        self.assertEqual(nf.stable_sha256({"a": 1, "b": [1, 2]}),
                         nf.stable_sha256({"b": [1, 2], "a": 1}))
        self.assertNotEqual(nf.stable_sha256({"a": 1}), nf.stable_sha256({"a": 2}))
        self.assertTrue(nf.canonical_json({"b": 1, "a": 2}).startswith("{\n  \"a\": 2"))

    def test_ram_guard_halts_low_and_unknown(self):
        self.assertEqual(nf.ensure_ram(reader=lambda: 4 << 30), 4 << 30)
        # Pass the floor explicitly: the operator override must not change what this asserts.
        with self.assertRaises(nf.EngineError):
            nf.ensure_ram(reader=lambda: 512 << 20, minimum=nf.RAM_MINIMUM)
        with self.assertRaises(nf.EngineError):
            nf.ensure_ram(reader=lambda: None)
        available = nf.available_physical_memory()
        self.assertTrue(available is None or available > 0)

    def test_ram_floor_override_is_clamped(self):
        default = nf.RAM_MINIMUM
        with mock.patch.dict("os.environ", {"NF_RAM_FLOOR_MIB": "700"}):
            self.assertEqual(nf.configured_ram_minimum(), 700 << 20)
            # The relaxed floor still halts below the clamped value, and the default guard
            # is unchanged when the caller states an explicit minimum.
            with self.assertRaises(nf.EngineError):
                nf.ensure_ram(reader=lambda: 600 << 20)
            self.assertEqual(nf.ensure_ram(reader=lambda: 800 << 20), 800 << 20)
            with self.assertRaises(nf.EngineError):
                nf.ensure_ram(reader=lambda: 800 << 20, minimum=default)
        # Never below the hard floor and never above the default.
        with mock.patch.dict("os.environ", {"NF_RAM_FLOOR_MIB": "1"}):
            self.assertEqual(nf.configured_ram_minimum(), nf.RAM_MINIMUM_FLOOR)
        with mock.patch.dict("os.environ", {"NF_RAM_FLOOR_MIB": "99999"}):
            self.assertEqual(nf.configured_ram_minimum(), default)
        with mock.patch.dict("os.environ", {"NF_RAM_FLOOR_MIB": "not-a-number"}):
            self.assertEqual(nf.configured_ram_minimum(), default)

    def test_xelatex_resolution(self):
        with mock.patch.object(nf.shutil, "which", return_value="C:/fake/xelatex.exe"):
            self.assertEqual(nf.resolve_xelatex(), ["C:/fake/xelatex.exe"])
        with mock.patch.object(nf.shutil, "which", return_value=None), \
                mock.patch.object(nf, "XELATEX_LEGACY", Path("C:/definitely/missing/xelatex.exe")):
            self.assertIsNone(nf.resolve_xelatex())
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "xelatex.exe"
            legacy.write_bytes(b"MZ")
            with mock.patch.object(nf.shutil, "which", return_value=None), \
                    mock.patch.object(nf, "XELATEX_LEGACY", legacy):
                self.assertEqual(nf.resolve_xelatex(), [str(legacy)])

    def test_doctor_reports_environment(self):
        report = nf.doctor(templates_dir=write_templates(Path(self._tmpdir())))
        for key in ("python", "pymupdf", "xelatex", "memory", "templates", "ok"):
            self.assertIn(key, report)
        self.assertIsInstance(report["ok"], bool)
        self.assertIsInstance(report["memory"]["ok"], bool)
        self.assertEqual(report["memory"]["required_bytes"], nf.RAM_MINIMUM)

    def _tmpdir(self):
        tmp = tempfile.TemporaryDirectory(prefix="native-forge-doctor-")
        self.addCleanup(tmp.cleanup)
        return tmp.name


@unittest.skipUnless(fitz, "PyMuPDF (fitz) is required")
class TestPrepare(TemporaryProjectCase):
    def test_prepare_creates_packet_scaffold_and_keeps_source_readonly(self):
        source_sha = nf.sha256_file(self.source)
        project, _ = self.new_project("prep")
        project_json = json.loads((project / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(project_json["schema_version"], 1)
        self.assertEqual(project_json["pages"], PAGES)
        self.assertEqual(project_json["title"], "TEXTBOOK TITLE")
        self.assertEqual(project_json["source"]["sha256"], source_sha)
        self.assertEqual(project_json["status"], "draft")
        self.assertEqual(sorted(project_json["templates"]), sorted(nf.TEMPLATE_FILES))
        self.assertTrue(project_json["templates"]["nativeforge.sty"]["sha256"])
        self.assertEqual(nf.sha256_file(self.source), source_sha)

        page_json = project / "packet" / "pages" / "p0001.json"
        page_png = project / "packet" / "pages" / "p0001.png"
        self.assertTrue(page_json.is_file() and page_png.is_file())
        data = json.loads(page_json.read_text(encoding="utf-8"))
        self.assertEqual(data["page"], 1)
        self.assertGreater(data["width"], 0)
        self.assertGreater(data["vector_path_count"], 0)
        self.assertTrue(data["fonts"])
        self.assertEqual(page_png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn("page_sha256", data)

        ids = [block["id"] for block in data["blocks"]]
        self.assertEqual(ids, [f"p0001-b{i:04d}" for i in range(len(ids))])
        self.assertTrue(all(block["page"] == 1 for block in data["blocks"]))
        joined = "\n".join(block["text"] for block in data["blocks"])
        self.assertIn("line one\nline two", joined)
        raster = json.loads((project / "packet" / "pages" / "p0003.json").read_text("utf-8"))
        self.assertGreaterEqual(raster["visible_raster_occurrences"], 1)
        self.assertTrue(any(image["visible"] for image in raster["images"]))

        scaffold = load_content(project)
        self.assertEqual(scaffold["blocks"], [])
        self.assertEqual(scaffold["expectations"],
                         {"equation_tags": [], "table_count": 0, "figure_count": 0,
                          "required_strings": []})

    def test_prepare_cache_hit_and_invalidation(self):
        project, _ = self.new_project("cache")
        before = (project / "packet" / "pages" / "p0002.json").read_bytes()
        again = nf.prepare(self.source, "1-3", project, "TEXTBOOK TITLE",
                           templates_dir=self.templates)
        self.assertTrue(again["cached"])
        self.assertEqual((project / "packet" / "pages" / "p0002.json").read_bytes(), before)

        (project / "packet" / "pages" / "p0002.json").write_text("{}", encoding="utf-8")
        refreshed = nf.prepare(self.source, "1-3", project, "TEXTBOOK TITLE",
                               templates_dir=self.templates)
        self.assertFalse(refreshed["cached"])
        data = json.loads((project / "packet" / "pages" / "p0002.json").read_text("utf-8"))
        self.assertEqual(data["page_sha256"], nf.stable_sha256(
            {k: v for k, v in data.items() if k != "page_sha256"}))

    def test_prepare_rejects_missing_source_and_bad_ranges(self):
        with self.assertRaises(nf.EngineError):
            nf.prepare(self.root / "missing.pdf", "1-2", self.root / "p1", "T",
                       templates_dir=self.templates)
        with self.assertRaises(nf.EngineError):
            nf.prepare(self.source, "1-99", self.root / "p2", "T", templates_dir=self.templates)
        with self.assertRaises(nf.EngineError):
            nf.prepare(self.source, "1-2", self.root / "p3", "   ", templates_dir=self.templates)


@unittest.skipUnless(fitz, "PyMuPDF (fitz) is required")
class TestAssets(TemporaryProjectCase):
    def test_vector_crop_removes_outside_content(self):
        project, _ = self.new_project("asset-vec")
        result = nf.asset(project, 1, list(VECTOR_RASTER_FREE_RECT), "fig9")
        entry = result["entry"]
        self.assertEqual(entry["kind"], "vector_pdf")
        self.assertEqual(entry["role"], "figure")
        self.assertEqual(entry["source_page"], 1)
        target = project / entry["path"]
        self.assertTrue(target.is_file())
        self.assertEqual(nf.sha256_file(target), entry["sha256"])

        doc = fitz.open(target)
        try:
            self.assertEqual(doc.page_count, 1)
            page = doc[0]
            self.assertEqual([i for i in page.get_image_info(xrefs=True)
                              if (i["bbox"][2] - i["bbox"][0]) > 0.01], [])
            self.assertTrue(page.get_drawings())
            self.assertNotIn("chapter heading", page.get_text())
            self.assertNotIn("alpha beta gamma", page.get_text())
        finally:
            doc.close()
        assets = json.loads((project / "assets.json").read_text("utf-8"))
        self.assertIn("fig9", assets)

    def test_asset_refuses_overwrite(self):
        project, _ = self.new_project("asset-overwrite")
        nf.asset(project, 1, list(VECTOR_RASTER_FREE_RECT), "fig1")
        with self.assertRaises(nf.EngineError):
            nf.asset(project, 1, list(VECTOR_RASTER_FREE_RECT), "fig1")
        with self.assertRaises(nf.EngineError):
            nf.asset(project, 9, list(VECTOR_RASTER_FREE_RECT), "fig9")
        with self.assertRaises(nf.EngineError):
            nf.asset(project, 1, [150.0, 100.0, 30.0, 140.0], "figbad")

    def test_raster_region_requires_explicit_source_raster(self):
        project, _ = self.new_project("asset-raster")
        with self.assertRaises(nf.EngineError) as caught:
            nf.asset(project, 3, list(RASTER_RECT), "foto")
        self.assertIn("source_raster", str(caught.exception))
        self.assertFalse((project / "assets" / "foto.pdf").exists())

        result = nf.asset(project, 3, list(RASTER_RECT), "foto", kind="source_raster")
        entry = result["entry"]
        self.assertEqual(entry["kind"], "source_raster")
        target = project / entry["path"]
        self.assertTrue(target.is_file())
        self.assertIsNotNone(nf.sniff_raster(target))
        self.assertEqual(nf.sha256_file(target), entry["sha256"])
        self.assertEqual(entry["image"]["width"], 8)

    def test_declared_raster_pdf_is_rejected_as_vector(self):
        project, _ = self.new_project("asset-liar")
        assets_dir = project / "assets"
        assets_dir.mkdir(exist_ok=True)
        liar = assets_dir / "fake-vector.pdf"
        doc = fitz.open()
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, 8, 8, bytes([0, 255, 0] * 64), False)
        page.insert_image(fitz.Rect(40, 40, 200, 200), stream=pix.tobytes("png"))
        page.insert_text((40, 20), "text so the page is not empty")
        doc.save(str(liar), no_new_id=True)
        doc.close()
        (project / "assets.json").write_text(json.dumps({"liar": {
            "path": "assets/fake-vector.pdf", "kind": "vector_pdf", "role": "figure",
            "source_page": 1, "bbox": [0, 0, 100, 100], "rationale": "hand registered",
            "sha256": nf.sha256_file(liar)}}), encoding="utf-8")
        save_content(project, base_content(project, asset_name="liar"))
        with self.assertRaises(nf.EngineError) as caught:
            self.build_project(project)
        self.assertIn("raster", str(caught.exception))


@unittest.skipUnless(fitz, "PyMuPDF (fitz) is required")
class TestContentValidation(TemporaryProjectCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_project, cls.base_source = cls().fixture("validation-base")

    def broken(self, name, mutate):
        project = self.copy_project(self.base_project, name)
        content = load_content(project)
        mutate(content)
        save_content(project, content)
        with self.assertRaises(nf.EngineError) as caught:
            self.build_project(project)
        return str(caught.exception)

    def test_missing_coverage_and_unknown_source(self):
        message = self.broken("v-coverage", lambda c: c["blocks"][1]["source_ids"].pop())
        self.assertIn("neither covered nor excluded", message)
        message = self.broken("v-unknown-source", lambda c: c["blocks"][0].update(
            {"source_ids": ["p0001-b9999"]}))
        self.assertIn("is not a packet block id", message)

    def test_block_shape_rules(self):
        self.assertIn("duplicate block id", self.broken(
            "v-duplicate", lambda c: c["blocks"][1].update({"id": c["blocks"][0]["id"]})))
        self.assertIn("not one of", self.broken(
            "v-kind", lambda c: c["blocks"][1].update({"kind": "bullet"})))
        self.assertIn("source_ids must be a non-empty list", self.broken(
            "v-empty-source", lambda c: c["blocks"][2].update({"source_ids": []})))
        self.assertIn("requires non-empty tex", self.broken(
            "v-empty-tex", lambda c: c["blocks"][1].update({"tex": " "})))
        self.assertIn("unresolved must be empty", self.broken(
            "v-unresolved", lambda c: c.update({"unresolved": ["formula 1.3 unreadable"]})))

    def test_native_math_table_and_figure_rules(self):
        self.assertIn("one \\tag", self.broken(
            "v-notag", lambda c: c["blocks"][2].update({"tex": "a = b"})))
        self.assertIn("forbidden macro", self.broken(
            "v-table-png", lambda c: c["blocks"][3].update(
                {"tex": "\\includegraphics{table1.png}"})))
        self.assertIn("tabular", self.broken(
            "v-table-plain", lambda c: c["blocks"][3].update({"tex": "A & B"})))
        self.assertIn("paragraph tex must not claim table", self.broken(
            "v-para-table", lambda c: c["blocks"][1].update(
                {"tex": "\\begin{tabular}{ll}A & B\\end{tabular}"})))
        self.assertIn("paragraph tex must not claim table", self.broken(
            "v-para-equation", lambda c: c["blocks"][1].update(
                {"tex": "\\begin{equation}x=1\\end{equation}"})))
        self.assertIn("forbidden macro", self.broken(
            "v-fig-tex", lambda c: c["blocks"][4].update(
                {"tex": "\\includegraphics{f.png}"})))
        self.assertIn("not declared in assets.json", self.broken(
            "v-fig-asset", lambda c: c["blocks"][4].update({"asset": "missing"})))

    def test_forbidden_macros_are_banned_everywhere(self):
        self.assertIn("forbidden macro", self.broken(
            "v-ig", lambda c: c["blocks"][2].update(
                {"tex": "a = \\includegraphics[width=\\linewidth]{solve.png} \\tag{1.1}"})))
        self.assertIn("forbidden macro", self.broken(
            "v-comment", lambda c: c["blocks"][1].update(
                {"tex": "正文。% \\includegraphics{hidden.png}"})))
        self.assertIn("forbidden macro", self.broken(
            "v-input", lambda c: c["blocks"][1].update({"tex": "\\input{extra.tex}"})))
        self.assertIn("forbidden macro", self.broken(
            "v-write", lambda c: c["blocks"][1].update({"tex": "\\immediate\\write18{dir}"})))
        self.assertIn("forbidden macro", self.broken(
            "v-caption", lambda c: c["blocks"][4].update({"caption": "\\includegraphics{x}"})))

    def test_expectation_counts_and_tags(self):
        self.assertIn("equation \\tag set must match", self.broken(
            "v-tags", lambda c: c["expectations"].update({"equation_tags": ["1.2"]})))
        self.assertIn("equation \\tag set must match", self.broken(
            "v-tags-many", lambda c: c["expectations"].update(
                {"equation_tags": ["1.1", "1.2"]})))
        self.assertIn("table_count is 2", self.broken(
            "v-table-count", lambda c: c["expectations"].update({"table_count": 2})))
        self.assertIn("figure_count is 3", self.broken(
            "v-figure-count", lambda c: c["expectations"].update({"figure_count": 3})))
        self.assertIn("expectations.required_strings is mandatory", self.broken(
            "v-required", lambda c: c["expectations"].pop("required_strings")))

    def test_exclusion_rules(self):
        self.assertIn("category", self.broken(
            "v-category", lambda c: c.update(
                {"exclusions": [{"source_id": c["blocks"][1]["source_ids"][0],
                                 "reason": "r", "category": "junk"}]})))
        self.assertIn("already covered", self.broken(
            "v-overlap", lambda c: c.update({"exclusions": [
                {"source_id": c["blocks"][0]["source_ids"][0], "reason": "r",
                 "category": "header_footer"}]})))
        def exclude_twice(content):
            source_id = content["blocks"][1]["source_ids"].pop()
            content["exclusions"] = [
                {"source_id": source_id, "reason": "r", "category": "out_of_scope"},
                {"source_id": source_id, "reason": "r2", "category": "out_of_scope"}]
        self.assertIn("excluded twice", self.broken("v-double-exclusion", exclude_twice))

    def test_exclusion_with_reason_is_accepted(self):
        project = self.copy_project(self.base_project, "v-exclusion-ok")
        content = load_content(project)
        dropped = content["blocks"][1]["source_ids"].pop()
        content["exclusions"].append({"source_id": dropped, "reason": "页眉页脚",
                                      "category": "header_footer"})
        save_content(project, content)
        result = self.build_project(project)
        self.assertEqual(result["block_counts"]["table"], 1)
        self.assertEqual(result["build_fingerprint"], nf.stable_sha256(
            json.loads((project / "build" / "fingerprint.json").read_text("utf-8"))["files"]))


@unittest.skipUnless(fitz, "PyMuPDF (fitz) is required")
class TestBuildQaRelease(TemporaryProjectCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_project, cls.base_source = cls().fixture("pipeline-base")

    def test_build_writes_tex_fingerprint_and_mocked_pdf(self):
        project = self.copy_project(self.base_project, "b-ok")
        result = self.build_project(project)
        tex = (project / "build" / "main.tex").read_text(encoding="utf-8")
        self.assertIn("\\documentclass[lang=cn,11pt,math=cm]{elegantbook}", tex)
        self.assertIn("\\usepackage{nativeforge}", tex)
        self.assertIn("\\title{TEXTBOOK TITLE}", tex)
        self.assertIn("\\section{1.1 示例小节}", tex)
        self.assertIn("\\begin{equation}", tex)
        self.assertIn("\\tag{1.1}", tex)
        self.assertIn("\\includegraphics[width=0.8\\linewidth,height=0.78\\textheight,keepaspectratio]{assets/fig1.pdf}", tex)
        self.assertIn("\\caption{示例图}", tex)
        self.assertIn("\\begin{tikzpicture}", tex)
        self.assertNotIn("\\input{", tex)
        self.assertTrue((project / "build" / "elegantbook.cls").is_file())
        self.assertTrue((project / "build" / "assets" / "fig1.pdf").is_file())
        self.assertTrue((project / "build" / "main.pdf").is_file())

        fingerprint = json.loads((project / "build" / "fingerprint.json").read_text("utf-8"))
        self.assertEqual(fingerprint["build_fingerprint"], nf.stable_sha256(fingerprint["files"]))
        self.assertEqual(fingerprint["build_fingerprint"], result["build_fingerprint"])
        for key in ("source", "content", "assets_manifest", "assets", "templates",
                    "build_templates", "tex", "pdf"):
            self.assertIn(key, fingerprint["files"])
        self.assertEqual(fingerprint["files"]["assets"]["fig1"],
                         nf.sha256_file(project / "assets" / "fig1.pdf"))

    def test_build_compile_failure_preserves_log(self):
        project = self.copy_project(self.base_project, "b-fail")
        with self.assertRaises(nf.EngineError) as caught:
            self.build_project(project, exit=1, log="! Undefined control sequence.\n",
                               pdf=False)
        self.assertIn("log preserved", str(caught.exception))
        self.assertIn("Undefined control sequence", (project / "build" / "main.log").read_text("utf-8"))
        self.assertFalse((project / "build" / "fingerprint.json").exists())

    def test_qa_rejects_bad_compile_diagnostics(self):
        cases = {
            "log.fatal": "! LaTeX Error: Something bad.\n",
            "log.missing_character": "Missing character: There is no 中 in font cmr10!\n",
            "log.overfull": "Overfull \\hbox (12.0pt too wide) in paragraph at lines 3--4\n",
            "log.undefined": "LaTeX Warning: Reference `fig:1.2' on page 1 undefined on input line 9.\n",
            "log.rerun": "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.\n",
        }
        for expected_check, log in cases.items():
            with self.subTest(check=expected_check):
                project = self.copy_project(self.base_project, "q-" + expected_check.split(".")[1])
                self.build_project(project, log=log)
                with self.assertRaises(nf.EngineError) as caught:
                    self.qa_project(project)
                self.assertIn("qa failed", str(caught.exception))
                self.assertIn(expected_check, finding_checks(project))
                self.assertEqual(qa_report(project)["status"], "fail")

    def test_qa_pass_previews_review_scaffold_and_draft_status(self):
        project = self.copy_project(self.base_project, "q-ok")
        self.build_project(project)
        report = self.qa_project(project)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["project_status"], "draft")
        self.assertEqual(report["preview_pages"], report["output_pages"])
        preview = sorted((project / "build" / "preview").glob("*.png"))
        self.assertEqual(len(preview), report["output_pages"])
        self.assertEqual(preview[0].read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

        review = json.loads((project / "review.json").read_text("utf-8"))
        fingerprint = json.loads((project / "build" / "fingerprint.json").read_text("utf-8"))
        self.assertEqual(review["build_fingerprint"], fingerprint["build_fingerprint"])
        self.assertEqual([p["page"] for p in review["source_pages"]], PAGES)
        self.assertEqual([p["page"] for p in review["output_pages"]],
                         list(range(1, report["output_pages"] + 1)))
        self.assertFalse(any(p["checked"] for p in review["source_pages"] + review["output_pages"]))
        self.assertFalse(review["translation_checked"])
        self.assertFalse(review["formula_table_checked"])
        self.assertEqual(review["issues"], [])
        self.assertEqual(review["reviewer"], "")
        self.assertEqual(json.loads((project / "project.json").read_text("utf-8"))["status"],
                         "draft")

    def test_qa_rejects_stale_fingerprint_bindings(self):
        mutations = {
            "content": lambda project: save_content(project, {**load_content(project),
                                                              "title": "CHANGED"}),
            "source": lambda project: Path(self.base_source).write_bytes(b"broken"),
            "assets": lambda project: (project / "assets" / "fig1.pdf").write_bytes(b"%x"),
            "templates": lambda project: (self.templates / "nativeforge.sty").write_text(
                "% changed\n", encoding="utf-8"),
            "pdf": lambda project: (project / "build" / "main.pdf").write_bytes(b"%x"),
        }
        for key, mutate in mutations.items():
            with self.subTest(stale=key):
                project = self.copy_project(self.base_project, "stale-" + key)
                self.build_project(project)
                if key == "source":
                    original = Path(self.base_source).read_bytes()
                    try:
                        mutate(project)
                        with self.assertRaises(nf.EngineError):
                            self.qa_project(project)
                    finally:
                        Path(self.base_source).write_bytes(original)
                else:
                    mutate(project)
                    with self.assertRaises(nf.EngineError):
                        self.qa_project(project)
                self.assertIn("fingerprint", finding_checks(project))
                self.assertIn(key, finding_text(project).replace("assets.fig1", "assets"))
                write_templates(self.templates)

    def test_qa_flags_expectation_drift(self):
        project = self.copy_project(self.base_project, "q-expect")
        content = load_content(project)
        content["expectations"]["required_strings"].append("nowhere-to-be-found")
        save_content(project, content)
        self.build_project(project)
        with self.assertRaises(nf.EngineError):
            self.qa_project(project)
        self.assertIn("expectations.required_strings_missing", finding_checks(project))

    def test_release_requires_complete_current_review(self):
        project = self.copy_project(self.base_project, "r-review")
        self.build_project(project)
        self.qa_project(project)
        with self.assertRaises(nf.EngineError) as caught:
            self.release_project(project)
        self.assertIn("source_pages: page 1 is not checked", str(caught.exception))
        self.assertIn("translation_checked must be true", str(caught.exception))

        def approve(review):
            for entry in review["source_pages"] + review["output_pages"]:
                entry["checked"] = True
            review["translation_checked"] = True
            review["formula_table_checked"] = True
            review["reviewer"] = "reviewer-name"

        for label, mutate in (
                ("missing-page", lambda r: r["source_pages"].pop()),
                ("extra-page", lambda r: r["output_pages"].append({"page": 99, "checked": True})),
                ("issues", lambda r: r.update({"issues": ["equation 1.3 symbol wrong"]})),
                ("no-reviewer", lambda r: r.update({"reviewer": "  "})),
                ("unchecked", lambda r: r["output_pages"][0].update({"checked": False}))):
            with self.subTest(rejection=label):
                review_path = project / "review.json"
                review = json.loads(review_path.read_text("utf-8"))
                approve(review)
                mutate(review)
                review_path.write_text(json.dumps(review), encoding="utf-8")
                with self.assertRaises(nf.EngineError) as caught:
                    self.release_project(project)
                self.assertIn("release blocked", str(caught.exception))
                self.assertEqual(json.loads((project / "project.json").read_text("utf-8"))["status"],
                                 "draft")

    def test_release_outputs_deliverable_zip_and_manifest(self):
        project = self.copy_project(self.base_project, "r-ok")
        self.build_project(project)
        self.qa_project(project)
        review = json.loads((project / "review.json").read_text("utf-8"))
        for entry in review["source_pages"] + review["output_pages"]:
            entry["checked"] = True
        review.update({"translation_checked": True, "formula_table_checked": True,
                       "reviewer": "reviewer-name"})
        (project / "review.json").write_text(json.dumps(review), encoding="utf-8")

        result = self.release_project(project)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(json.loads((project / "project.json").read_text("utf-8"))["status"],
                         "completed")
        deliverable = project / "deliverable"
        for rel in ("main.pdf", "main.tex", "content.json", "project.json", "review.json",
                    "manifest.json", "qa/qa_report.json", "elegantbook.cls",
                    "nativeforge.sty", "assets/fig1.pdf", "assets.json", "build_fingerprint.json"):
            self.assertTrue((deliverable / rel).is_file(), rel)
        self.assertEqual(json.loads((deliverable / "project.json").read_text("utf-8"))["status"],
                         "completed")
        manifest = json.loads((deliverable / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["build_fingerprint"], result["build_fingerprint"])
        listed = {item["path"]: item["sha256"] for item in manifest["files"]}
        self.assertEqual(listed["main.pdf"], nf.sha256_file(deliverable / "main.pdf"))
        self.assertEqual(listed["assets/fig1.pdf"], nf.sha256_file(project / "assets" / "fig1.pdf"))
        import zipfile
        with zipfile.ZipFile(project / "deliverable.zip") as archive:
            self.assertIn("main.tex", archive.namelist())
            self.assertIn("manifest.json", archive.namelist())
        sha_line = (project / "deliverable.zip.sha256").read_text("utf-8")
        self.assertEqual(sha_line.split()[0], nf.sha256_file(project / "deliverable.zip"))

    def test_rebuild_makes_review_stale(self):
        project = self.copy_project(self.base_project, "r-stale")
        self.build_project(project)
        self.qa_project(project)
        review = json.loads((project / "review.json").read_text("utf-8"))
        for entry in review["source_pages"] + review["output_pages"]:
            entry["checked"] = True
        review.update({"translation_checked": True, "formula_table_checked": True,
                       "reviewer": "reviewer-name"})
        (project / "review.json").write_text(json.dumps(review), encoding="utf-8")

        content = load_content(project)
        content["blocks"][1]["tex"] = "修订后的正文段落。"
        save_content(project, content)
        self.build_project(project)
        with self.assertRaises(nf.EngineError) as caught:
            self.release_project(project)
        self.assertIn("different build fingerprint", str(caught.exception))
        self.assertEqual(json.loads((project / "project.json").read_text("utf-8"))["status"],
                         "draft")

    def test_build_refuses_changed_templates_and_source(self):
        project = self.copy_project(self.base_project, "b-stale")
        (self.templates / "nativeforge.sty").write_text("% changed\n", encoding="utf-8")
        try:
            with self.assertRaises(nf.EngineError) as caught:
                self.build_project(project)
            self.assertIn("template(s) changed since prepare", str(caught.exception))
        finally:
            write_templates(self.templates)
        Path(self.base_source).write_bytes(b"broken")
        try:
            with self.assertRaises(nf.EngineError) as caught:
                self.build_project(project)
            self.assertIn("source PDF changed", str(caught.exception))
        finally:
            make_source_pdf(self.base_source)
            nf.prepare(self.base_source, "1-3", self.base_project, "TEXTBOOK TITLE",
                       templates_dir=self.templates)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestSupervisorContracts(TemporaryProjectCase):
    def setUp(self):
        self.project, _ = self.fixture(self._testMethodName)
        self.content = load_content(self.project)

    def validate(self):
        return nf.validate_content(self.content, set(packet_texts(self.project)), {'fig1'})

    def test_repeated_included_source_ids_are_valid(self):
        self.content['blocks'][1]['source_ids'].append(self.content['blocks'][0]['source_ids'][0])
        self.validate()

    def test_full_section_and_equation_tex_preserved(self):
        section = self.content['blocks'][0]
        section['tex'] = r'\section*{Native title}'
        equation = self.content['blocks'][2]
        equation['tex'] = r'\begin{equation}a=b+c\tag{1.1}\end{equation}'
        self.validate()
        self.assertEqual(nf.render_block(section, {}), section['tex'])
        self.assertEqual(nf.render_block(equation, {}), equation['tex'])

    def test_original_unnumbered_math_is_never_fabricated(self):
        equation = self.content['blocks'][2]
        equation.update(tex=r'\begin{align*}104-95&=5\end{align*}', numbered=False)
        self.content['expectations']['equation_tags'] = []
        self.validate()
        self.assertEqual(nf.render_block(equation, {}), equation['tex'])
        equation['tex'] = r'\begin{equation}a=b\end{equation}'
        with self.assertRaises(nf.EngineError):
            self.validate()

    def test_numeric_width_raw_math_caption_and_original_number(self):
        figure = self.content['blocks'][4]
        figure.update(width=0.56, caption=r'原生 $x_1$ 与 $y$')
        self.validate()
        tex = nf.render_block(figure, {'fig1': {'path': 'assets/fig1.pdf'}})
        self.assertIn(r'width=0.56\linewidth', tex)
        self.assertIn(r'\caption{原生 $x_1$ 与 $y$}', tex)
        self.assertIn(r'\renewcommand{\thefigure}{1.2}', tex)
        figure.pop('number')
        self.validate()
        tex = nf.render_block(figure, {'fig1': {'path': 'assets/fig1.pdf'}})
        self.assertIn(r'\caption*{', tex)
        self.assertNotIn(r'\thefigure', tex)

    def test_stale_out_of_scope_packet_json_is_ignored(self):
        project = nf.load_project(self.project)
        project['pages'] = [1]
        (self.project / 'packet/pages/p0002.json').write_text('INVALID STALE JSON')
        ids = nf.load_packet(self.project, project)
        self.assertTrue(ids)
        self.assertTrue(all(key.startswith('p0001-') for key in ids))

    def test_qa_rejects_undeclared_output_bitmap(self):
        self.build_project(self.project, raster=True)
        with self.assertRaises(nf.EngineError):
            self.qa_project(self.project)
        self.assertIn('raster.output', finding_checks(self.project))

    def test_qa_accounts_for_explicit_source_raster_actual_uses(self):
        entry = nf.asset(self.project, 3, list(RASTER_RECT), 'original', 'source_raster')['entry']
        self.content['blocks'][4]['asset'] = 'original'
        save_content(self.project, self.content)
        self.build_project(self.project, raster_path=str(self.project / entry['path']))
        report = self.qa_project(self.project)
        self.assertEqual(report['raster_occurrences'], {'output': 1, 'explicit_source_raster_uses': 1})
        self.build_project(self.project, raster=True)
        with self.assertRaises(nf.EngineError):
            self.qa_project(self.project)
        self.assertIn('raster.output', finding_checks(self.project))

    def test_compile_log_and_copied_asset_tampering_invalidates_build(self):
        self.build_project(self.project)
        (self.project / 'build/main.log').write_text('cleaned-away-warning')
        with self.assertRaises(nf.EngineError):
            self.qa_project(self.project)
        self.assertIn('log:', finding_text(self.project))
        self.build_project(self.project)
        (self.project / 'build/assets/fig1.pdf').write_bytes(b'% altered')
        with self.assertRaises(nf.EngineError):
            self.qa_project(self.project)
        self.assertIn('build_assets', finding_text(self.project))
