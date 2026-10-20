"""Unit tests for engine/redraw.py.

Runs against a temp minimal project; XeLaTeX is mocked with a tiny Python script that writes a
vector-only PDF, so no TeX installation is required.
"""

import contextlib
import io
import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(ENGINE_DIR))

import native_forge as nf  # noqa: E402
import redraw as rd  # noqa: E402

try:
    import fitz
except ImportError:  # pragma: no cover - environment dependent
    fitz = None

FAKE_XELATEX = '''
import json, os, sys
spec = {}
if os.path.exists("fake_spec.json"):
    with open("fake_spec.json", encoding="utf-8") as handle:
        spec = json.load(handle)
with open("passes.txt", "a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")
with open("figure.log", "w", encoding="utf-8") as handle:
    handle.write(spec.get("log", "This is XeTeX, Version 3.141592653\\n"))
if spec.get("pdf", True):
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=200, height=150)
    page.draw_rect(fitz.Rect(20, 20, 180, 130))
    page.insert_text((30, 40), "figure", fontsize=10)
    if spec.get("raster"):
        pix = fitz.Pixmap(fitz.csRGB, 4, 4, bytes([0, 0, 255] * 16), False)
        page.insert_image(fitz.Rect(20, 20, 60, 60), stream=pix.tobytes("png"))
    doc.save("figure.pdf", no_new_id=True)
    doc.close()
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


def make_source_pdf(path, pages=2):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((30, 30), "figure region", fontsize=10)
        page.draw_rect(fitz.Rect(30, 100, 150, 140))
    doc.save(path, no_new_id=True)
    doc.close()


def xy_spec(**overrides):
    spec = {"type": "xy_plot", "source_page": 1, "bbox": [10, 10, 110, 90],
            "rationale": "redraw of the source figure 1.2 curve",
            "xlim": [0, 6.283185307179586], "ylim": [-1.5, 1.5],
            "xlabel": "$x$", "ylabel": "图例 $y$",
            "series": [{"type": "line", "function": {"kind": "sin", "amplitude": 1.0,
                        "angular_frequency": 1.0, "phase": 0.0, "offset": 0.0}}]}
    spec.update(overrides)
    return spec


def flow_spec(**overrides):
    spec = {"type": "flowchart", "source_page": 2, "bbox": [10, 10, 110, 90],
            "rationale": "redraw of the source flow diagram",
            "nodes": [{"id": "start", "label": "开始", "x": 0, "y": 0, "shape": "ellipse"},
                      {"id": "check", "label": "判断 $x>0$", "x": 0, "y": 3, "shape": "diamond"}],
            "edges": [{"from": "start", "to": "check", "label": "输入"}]}
    spec.update(overrides)
    return spec


def function_series(kind="sin", samples=None, **params):
    function = {"kind": kind, "amplitude": 1.0, "angular_frequency": 1.0, "phase": 0.0,
                "offset": 0.0}
    function.update(params)
    if samples is not None:
        function["samples"] = samples
    return {"type": "line", "function": function}


@unittest.skipUnless(fitz, "PyMuPDF (fitz) is required")
class RedrawCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="native-forge-redraw-")
        cls.root = Path(cls.tmp.name)
        cls.templates = write_templates(cls.root / "templates")
        cls.source = cls.root / "source.pdf"
        make_source_pdf(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def new_project(self, name):
        project = self.root / name
        nf.prepare(self.source, "1-2", project, "TEXTBOOK TITLE", templates_dir=self.templates)
        return project

    def write_spec(self, name, spec):
        path = self.root / f"{name}-spec.json"
        path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return path

    def fake_compiler(self):
        script = self.root / "fake_xelatex.py"
        if not script.is_file():
            script.write_text(FAKE_XELATEX, encoding="utf-8")
        return mock.patch.object(nf, "resolve_xelatex", lambda: [sys.executable, str(script)])

    def run_redraw(self, project, name, spec, **compiler):
        spec_path = self.write_spec(name, spec)
        if compiler:
            work = Path(project) / "redraw" / name
            work.mkdir(parents=True, exist_ok=True)
            (work / "fake_spec.json").write_text(json.dumps(compiler), encoding="utf-8")
        with self.fake_compiler():
            return rd.redraw(project, spec_path, name)

    def reject(self, project, name, spec, **compiler):
        with self.assertRaises(nf.EngineError) as caught:
            self.run_redraw(project, name, spec, **compiler)
        return str(caught.exception)

    def assets(self, project):
        return json.loads((Path(project) / "assets.json").read_text(encoding="utf-8"))


class TestRedrawValidation(RedrawCase):
    def test_common_contract_fields(self):
        project = self.new_project("val-common")
        cases = {
            "type": (xy_spec(type="photo"), "type 'photo' must be one of"),
            "page-zero": (xy_spec(source_page=0), "source_page must be a positive integer"),
            "page-absent": (xy_spec(source_page=9), "not among the prepared pages"),
            "bbox-shape": (xy_spec(bbox=[10, 10, 110]), "bbox must be [x0, y0, x1, y1]"),
            "bbox-order": (xy_spec(bbox=[90, 10, 10, 90]), "x0 < x1"),
            "rationale": (xy_spec(rationale="  "), "rationale must be a non-empty string"),
        }
        for label, (spec, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.reject(project, "val-" + label, spec))
        self.assertEqual(self.assets(project), {})

    def test_malformed_points_and_functions(self):
        project = self.new_project("val-series")
        cases = {
            "flat-points": (xy_spec(series=[{"type": "line", "points": [1, 2]}]),
                            "points[0] must be [x, y]"),
            "nan-point": (xy_spec(series=[{"type": "line", "points": [[0, math.nan]]}]),
                          "points[0] must be [x, y]"),
            "inf-point": (xy_spec(series=[{"type": "line", "points": [[math.inf, 0], [1, 1]]}]),
                          "points[0] must be [x, y]"),
            "both": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]],
                                      "function": {"kind": "sin"}}]),
                     "exactly one of points or function"),
            "neither": (xy_spec(series=[{"type": "line"}]), "exactly one of points or function"),
            "kind": (xy_spec(series=[function_series(kind="tan")]), "kind must be one of"),
            "amplitude": (xy_spec(series=[{"type": "line", "function": {"kind": "sin"}}]),
                          "amplitude must be a finite number"),
            "samples-low": (xy_spec(series=[function_series(samples=5)]), "samples must be an integer"),
            "samples-high": (xy_spec(series=[function_series(samples=2000)]),
                             "samples must be an integer"),
            "samples-bool": (xy_spec(series=[function_series(samples=True)]),
                             "samples must be an integer"),
            "color": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]],
                                       "color": "hotpink"}]), "color must be one of"),
            "color-mix": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]],
                                           "color": "blue!101"}]), "color must be one of"),
            "line-width": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]],
                                            "line_width": "30pt"}]),
                           "line_width must be a width in pt"),
            "line-width-junk": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]],
                                                 "line_width": "abc"}]),
                                "line_width must be a width in pt"),
            "label": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]], "label": " "}]),
                      "label must be a non-empty TeX string"),
            "mark": (xy_spec(series=[{"type": "scatter", "points": [[0, 0], [1, 1]],
                                      "mark": "heart"}]), "mark must be one of"),
            "series-empty": (xy_spec(series=[]), "series must be a non-empty list"),
            "series-absent": (xy_spec(series=None), "series must be a non-empty list"),
        }
        for label, (spec, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.reject(project, "val-" + label, spec))

    def test_axes_size_and_grid_rules(self):
        project = self.new_project("val-axes")
        cases = {
            "xlim": (xy_spec(xlim=[1, 1]), "xlim must be [lo, hi]"),
            "ylim": (xy_spec(ylim="big"), "ylim must be [lo, hi]"),
            "xlabel": (xy_spec(xlabel=""), "xlabel must be a non-empty TeX string"),
            "ylabel": (xy_spec(ylabel=3), "ylabel must be a non-empty TeX string"),
            "width-high": (xy_spec(width_cm=31), "width_cm must be a number within"),
            "width-low": (xy_spec(width_cm=0), "width_cm must be a number within"),
            "height": (xy_spec(height_cm="7"), "height_cm must be a number within"),
            "grid": (xy_spec(grid="yes"), "grid must be true or false"),
        }
        for label, (spec, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.reject(project, "val-" + label, spec))

    def test_flowchart_structure_rules(self):
        project = self.new_project("val-flow")
        bad_nodes = {"id": "x", "label": "节点", "x": 0, "y": 0, "shape": "rectangle"}
        cases = {
            "shape": (flow_spec(nodes=[dict(bad_nodes, shape="hexagon")]), "shape 'hexagon'"),
            "duplicate": (flow_spec(nodes=[bad_nodes, dict(bad_nodes, x=2)]), "duplicate node id"),
            "bad-id": (flow_spec(nodes=[dict(bad_nodes, id="a b")]), "id must use letters"),
            "coordinate": (flow_spec(nodes=[dict(bad_nodes, x=101)]), "within [-100, 100]"),
            "label": (flow_spec(nodes=[dict(bad_nodes, label="")]), "label must be a non-empty"),
            "nodes-empty": (flow_spec(nodes=[]), "nodes must be a non-empty list"),
            "edge-unknown-from": (flow_spec(edges=[{"from": "ghost", "to": "start"}]),
                                  "does not reference a known node id"),
            "edge-unknown-to": (flow_spec(edges=[{"from": "start", "to": "ghost"}]),
                                "does not reference a known node id"),
            "edge-self-loop": (flow_spec(edges=[{"from": "start", "to": "start"}]),
                               "self-loop"),
            "edge-label": (flow_spec(edges=[{"from": "start", "to": "check", "label": " "}]),
                           "label must be a non-empty"),
            "edges-not-list": (flow_spec(edges="nope"), "edges must be a list"),
        }
        for label, (spec, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.reject(project, "val-" + label, spec))

    def test_raw_tex_rules(self):
        project = self.new_project("val-tex")
        base = {"source_page": 1, "bbox": [10, 10, 110, 90], "rationale": "redraw raw figure"}
        cases = {
            "tikz-missing": (dict(base, type="tikz", tex="\\draw (0,0) -- (1,1);"),
                             "must contain '\\\\begin{tikzpicture}'"),
            "chemfig-missing": (dict(base, type="chemfig", tex="\\draw (0,0) -- (1,1);"),
                                "must contain '\\\\chemfig'"),
            "chemfig-empty": (dict(base, type="chemfig", tex="  "), "must be non-empty"),
            "document-env": (dict(base, type="tikz",
                                  tex="\\begin{document}\\begin{tikzpicture}\\end{tikzpicture}"),
                             "body-only"),
        }
        for label, (spec, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.reject(project, "val-" + label, spec))

    def test_forbidden_macros_are_rejected_everywhere(self):
        project = self.new_project("val-macros")
        cases = {
            "legend": (xy_spec(series=[{"type": "line", "points": [[0, 0], [1, 1]],
                                        "label": "\\includegraphics{hidden.png}"}]),
                       "forbidden macro"),
            "node": (flow_spec(nodes=[{"id": "a", "label": "\\immediate\\write18{dir}",
                                       "x": 0, "y": 0, "shape": "rectangle"}]), "forbidden macro"),
            "raw-tex": ({"type": "tikz", "source_page": 1, "bbox": [10, 10, 110, 90],
                         "rationale": "raw", "tex":
                         "\\begin{tikzpicture}\\input{extra}\\end{tikzpicture}"}, "forbidden macro"),
            "axis-label": (xy_spec(xlabel="\\catcode`\\@=11"), "forbidden macro"),
        }
        for label, (spec, message) in cases.items():
            with self.subTest(case=label):
                self.assertIn(message, self.reject(project, "val-" + label, spec))


class TestRedrawBuild(RedrawCase):
    def test_xy_plot_compiles_and_registers_vector_asset(self):
        project = self.new_project("xy-ok")
        result = self.run_redraw(project, "curve1", xy_spec())
        self.assertEqual(result["command"], "redraw")
        self.assertEqual(result["type"], "xy_plot")
        work = project / "redraw" / "curve1"
        for name in ("spec.json", "figure.tex", "figure.log", "figure.pdf"):
            self.assertTrue((work / name).is_file(), name)
        tex = (work / "figure.tex").read_text(encoding="utf-8")
        for fragment in ("\\documentclass[tikz,border=3pt,10pt]{standalone}",
                         "\\usepackage[UTF8,fontset=windows]{ctex}",
                         "\\usepackage{pgfplots}", "\\pgfplotsset{compat=1.18}"):
            self.assertIn(fragment, tex)

        entry = self.assets(project)["curve1"]
        self.assertEqual(entry["path"], "redraw/curve1/figure.pdf")
        self.assertEqual(entry["kind"], "native_pdf")
        self.assertEqual(entry["role"], "figure")
        self.assertEqual(entry["source_page"], 1)
        self.assertEqual(entry["bbox"], [10.0, 10.0, 110.0, 90.0])
        self.assertEqual(entry["rationale"], "redraw of the source figure 1.2 curve")
        self.assertEqual(entry["sha256"], nf.sha256_file(project / entry["path"]))
        metadata = entry["redraw"]
        self.assertEqual(metadata["type"], "xy_plot")
        self.assertEqual(metadata["spec_sha256"], nf.sha256_file(project / metadata["spec_path"]))
        self.assertEqual(metadata["tex_sha256"], nf.sha256_file(project / metadata["tex_path"]))
        self.assertEqual(metadata["engine_sha256"], nf.sha256_file(ENGINE_DIR / "redraw.py"))
        self.assertEqual(metadata["source_sha256"], nf.sha256_file(self.source))
        self.assertEqual(metadata["redraw_sha256"],
                         nf.stable_sha256({k: v for k, v in metadata.items()
                                           if k != "redraw_sha256"}))
        self.assertEqual(nf.validate_assets(project, self.assets(project), fitz), [])

        with fitz.open(work / "figure.pdf") as doc:
            page = doc[0]
            self.assertEqual([i for i in page.get_image_info(xrefs=True)
                              if (i["bbox"][2] - i["bbox"][0]) > 0.01], [])
            self.assertTrue(page.get_drawings())

    def test_tex_coordinates_are_finite_and_samples_exact(self):
        project = self.new_project("xy-coords")
        spec = xy_spec(series=[
            {"type": "line", "points": [[0.1, 1e-09], [0.2, -0.5]]},
            function_series(samples=13),
            function_series(kind="cos"),
        ], xlabel="时间 $t$", ylabel="值", grid=True)
        self.run_redraw(project, "curve2", spec, pdf=True)
        tex = (project / "redraw" / "curve2" / "figure.tex").read_text(encoding="utf-8")
        self.assertIn("xlabel={时间 $t$}", tex)
        self.assertIn("grid=major", tex)
        plots = [re.search(r"coordinates \{(.*)\};$", line).group(1)
                 for line in tex.splitlines() if line.startswith("\\addplot")]
        counts = [len(re.findall(r"\([^()]*\)", coordinates)) for coordinates in plots]
        self.assertEqual(counts, [2, 13, 201])  # source points, explicit sampling, default sampling
        self.assertEqual(plots[0], "(0.1,0.000000001) (0.2,-0.5)")
        self.assertNotRegex(plots[0] + plots[1], r"[eE][-+]?\d|nan|inf")
        for pair in ("(0,0)", "(1.570796327,1)", "(3.141592654,0)", "(6.283185307,0)"):
            self.assertIn(pair, plots[1])
        self.assertIn("-1)", plots[1])  # sin(3*pi/2)

        points = rd.series_points(function_series(), [0, 6.283185307179586])
        self.assertEqual(len(points), 201)
        self.assertEqual(points[0][0], 0.0)
        self.assertAlmostEqual(points[-1][0], 6.283185307179586, places=12)
        self.assertAlmostEqual(points[50][1], math.sin(points[50][0]), places=12)
        self.assertEqual(rd.fmt_num(1e-09), "0.000000001")
        self.assertEqual(rd.fmt_num(-0.0), "0")
        self.assertEqual(rd.fmt_num(1.5), "1.5")
        self.assertEqual(rd.fmt_num(2500000), "2500000")

    def test_flowchart_tex_structure(self):
        project = self.new_project("flow-ok")
        result = self.run_redraw(project, "flow1", flow_spec())
        self.assertEqual(result["type"], "flowchart")
        tex = (project / "redraw" / "flow1" / "figure.tex").read_text(encoding="utf-8")
        for fragment in (r"\usetikzlibrary{shapes.geometric, arrows.meta}",
                         r"\node[draw, ellipse] (start) at (0cm,0cm) {开始};",
                         r"\node[draw, diamond] (check) at (0cm,3cm) {判断 $x>0$};",
                         r"\draw[-{Latex}] (start) -- node[midway, above, font=\small] {输入} (check);"):
            self.assertIn(fragment, tex)
        self.assertIn("flow1", self.assets(project))

    def test_tikz_and_chemfig_bodies_compile(self):
        project = self.new_project("raw-ok")
        tikz_body = r"\begin{tikzpicture}\draw (0,0) rectangle (2,1);\end{tikzpicture}"
        self.run_redraw(project, "tikz1", {"type": "tikz", "source_page": 1,
                                           "bbox": [10, 10, 110, 90], "rationale": "raw tikz",
                                           "tex": tikz_body})
        tex = (project / "redraw" / "tikz1" / "figure.tex").read_text(encoding="utf-8")
        self.assertIn(tikz_body, tex)
        self.assertIn(r"\usetikzlibrary{shapes.geometric, arrows.meta}", tex)

        chemfig_body = r"\chemfig{H-C(-[2]H)(-[6]H)-H}"
        self.run_redraw(project, "chem1", {"type": "chemfig", "source_page": 2,
                                           "bbox": [10, 10, 110, 90], "rationale": "raw chemfig",
                                           "tex": chemfig_body})
        tex = (project / "redraw" / "chem1" / "figure.tex").read_text(encoding="utf-8")
        self.assertIn(chemfig_body, tex)
        self.assertIn("\\usepackage{chemfig}", tex)
        self.assertEqual(sorted(self.assets(project)), ["chem1", "tikz1"])

    def test_two_xelatex_passes_without_shell_escape(self):
        project = self.new_project("passes")
        self.run_redraw(project, "curve3", xy_spec())
        passes = (project / "redraw" / "curve3" / "passes.txt").read_text("utf-8").splitlines()
        self.assertEqual(len(passes), 2)
        for line in passes:
            self.assertIn("--no-shell-escape", line)
            self.assertIn("figure.tex", line)

    def test_existing_asset_or_output_is_never_overwritten(self):
        project = self.new_project("occupied")
        self.run_redraw(project, "curve4", xy_spec())
        manifest = (project / "assets.json").read_bytes()
        pdf = project / "redraw" / "curve4" / "figure.pdf"
        pdf_sha = nf.sha256_file(pdf)
        message = self.reject(project, "curve4", xy_spec())
        self.assertIn("already declared", message)
        self.assertIn("refusing to overwrite", message)
        self.assertEqual((project / "assets.json").read_bytes(), manifest)
        self.assertEqual(nf.sha256_file(pdf), pdf_sha)

        stale = project / "redraw" / "stale1"
        stale.mkdir(parents=True)
        (stale / "figure.pdf").write_bytes(b"%PDF-1.4 hand-made")
        message = self.reject(project, "stale1", xy_spec())
        self.assertIn("refusing to overwrite", message)
        self.assertEqual((stale / "figure.pdf").read_bytes(), b"%PDF-1.4 hand-made")
        self.assertNotIn("stale1", self.assets(project))

    def test_source_hash_mismatch_blocks_redraw(self):
        source = self.root / "tamper.pdf"
        make_source_pdf(source, pages=1)
        project = self.root / "tamper-project"
        nf.prepare(source, "1", project, "TEXTBOOK TITLE", templates_dir=self.templates)
        source.write_bytes(b"broken")
        message = self.reject(project, "curve5", xy_spec(source_page=1))
        self.assertIn("source PDF changed since prepare", message)
        self.assertFalse((project / "redraw").exists())
        self.assertEqual(self.assets(project), {})

    def test_raster_output_log_errors_and_failed_compile_are_rejected(self):
        project = self.new_project("rejects")
        message = self.reject(project, "raster1", xy_spec(), raster=True)
        self.assertIn("visible raster", message)
        self.assertFalse((project / "redraw" / "raster1" / "figure.pdf").exists())

        message = self.reject(project, "glyph1", xy_spec(),
                              log="Missing character: There is no 中 in font SimSun!\n")
        self.assertIn("missing_character", message)

        message = self.reject(project, "overflow1", xy_spec(),
                              log="Overfull \\hbox (12.0pt too wide) in paragraph at lines 3--4\n")
        self.assertIn("overfull", message)

        message = self.reject(project, "exit1", xy_spec(), exit=1, pdf=False,
                              log="! Undefined control sequence.\n")
        self.assertIn("xelatex failed", message)
        self.assertIn("Undefined control sequence",
                      (project / "redraw" / "exit1" / "figure.log").read_text("utf-8"))
        self.assertEqual(self.assets(project), {})


class TestRedrawCli(RedrawCase):
    def run_cli(self, *argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with self.fake_compiler(), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = rd.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_writes_json_and_reports_errors(self):
        project = self.new_project("cli")
        spec_path = self.write_spec("cli", xy_spec())
        code, stdout, stderr = self.run_cli("--project", str(project), "--spec", str(spec_path),
                                            "--name", "curve-cli")
        self.assertEqual(code, 0, stderr)
        result = json.loads(stdout)
        self.assertEqual(result["command"], "redraw")
        self.assertEqual(result["asset"], "curve-cli")
        self.assertEqual(result["redraw_sha256"], self.assets(project)["curve-cli"][
            "redraw"]["redraw_sha256"])

        code, stdout, stderr = self.run_cli("--project", str(project), "--spec",
                                            json.dumps(xy_spec(source_page=1)), "--name",
                                            "curve-inline")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["asset"], "curve-inline")

        code, _, stderr = self.run_cli("--project", str(project), "--spec",
                                       json.dumps(xy_spec(type="photo")), "--name", "bad1")
        self.assertEqual(code, 1)
        self.assertIn("ERROR", stderr)
        self.assertIn("spec invalid", stderr)
        self.assertEqual(sorted(self.assets(project)), ["curve-cli", "curve-inline"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
