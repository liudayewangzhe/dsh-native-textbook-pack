"""Spacing checks must distinguish no coverage from a checked good slide."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACK = Path(__file__).resolve().parents[1]
CHECK = PACK / "skills/native-textbook/scripts/check_slide_spacing.py"


class SpacingCoverageTests(unittest.TestCase):
    def run_check(self, source, *extra):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source.tex").write_text(source, encoding="utf-8")
            result = subprocess.run([sys.executable, str(CHECK), "--tex", str(root / "source.tex"),
                                     "--out", str(root / "report.json"), *extra],
                                    capture_output=True, encoding="utf-8")
            report = json.loads((root / "report.json").read_text(encoding="utf-8")) if (root / "report.json").exists() else None
            return result, report

    def test_unrecognized_macros_are_not_a_pass(self):
        source = (PACK / "skills/native-textbook/assets/slide-template.tex").read_text(encoding="utf-8")
        result, report = self.run_check(source)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["check_status"], "not_applicable")
        self.assertEqual(report["nodes"], 0)

    def test_supported_good_nodes_pass(self):
        source = "\\Slide[1]\n\\node[nftxt,text width=40mm] at (10,20) {第一行};\n" \
                 "\\node[nftxt,text width=40mm] at (10,40) {第二行};\n"
        result, report = self.run_check(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["check_status"], "passed")
        self.assertEqual(report["nodes"], 2)

    def test_known_overlap_is_rejected(self):
        source = "\\Slide[1]\n\\node[nftxt,text width=10mm] at (10,20) {" + "长句" * 20 + "};\n" \
                 "\\node[nftxt,text width=40mm] at (10,24) {下一行};\n"
        result, report = self.run_check(source)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["check_status"], "failed")
        self.assertIn("node_overlap_risk", [f["code"] for f in report["findings"]])

    def test_invalid_geometry_is_a_configuration_error(self):
        result, report = self.run_check("\\Slide[1]", "--lead", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(report)

    def test_zero_width_node_is_not_a_valid_one_line_box(self):
        result, report = self.run_check("\\Slide[1]\n\\node[nftxt,text width=0mm] at (10,20) {正文};\n")
        self.assertEqual(result.returncode, 2)
        self.assertIsNone(report)


if __name__ == "__main__":
    unittest.main()
