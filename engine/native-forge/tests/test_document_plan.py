"""Small real PDF fixtures validate planning gates, not content or beauty."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plan_document as planning
try:
    import fitz
except ImportError:
    fitz = None


@unittest.skipIf(fitz is None, "PyMuPDF required for real source/pilot fixtures")
class DocumentPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="document-plan-")
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.source = self.root / "source.pdf"
        self.make_pdf(self.source)
        self.preflight = self.root / "preflight.json"
        self.save(self.preflight, {"schema_version": 1, "status": "complete", "route": {"kind": "pdf"},
            "source": str(self.source), "source_sha256": planning.sha256(self.source),
            "source_unchanged_after_scan": True, "page_count": 2, "pages": [{"page": 1}, {"page": 2}],
            "summary": {"candidate_page_counts": {"multiple_text_bands": 2}}})

    def tearDown(self):
        self.temporary.cleanup()

    def make_pdf(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        for number in (1, 2):
            page = document.new_page()
            page.insert_text((40, 50), f"Normal body sample, page {number}.")
        document.save(path)
        document.close()

    def save(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def ref(self, path, role=None):
        result = {"path": path.relative_to(self.project).as_posix(), "sha256": planning.sha256(path)}
        if role:
            result["role"] = role
        return result

    def persist(self, plan):
        self.save(self.project / "layout-plan.json", plan)

    def ready_fixture(self):
        planning.scaffold(self.preflight, self.project)
        plan = planning.read_json(self.project / "layout-plan.json")
        pdf = self.project / "build" / "main.pdf"
        self.make_pdf(pdf)
        preview = self.project / "review" / "page-1.png"
        preview.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(pdf) as document:
            document[0].get_pixmap(matrix=fitz.Matrix(.2, .2)).save(preview)
        review = self.project / "review" / "findings.md"
        review.write_text("Fixture: body reading order and full line ending are visible on the pilot page.", encoding="utf-8")
        contract = self.project / "worker-contract.md"
        contract.write_text("Only write this batch chunk. Preserve source IDs and equation numbers.", encoding="utf-8")
        fingerprint = self.project / "build" / "fingerprint.json"
        self.save(fingerprint, {"files": {"source": plan["source"]["sha256"], "pdf": planning.sha256(pdf)}})
        evidence = [self.ref(preview, "render"), self.ref(review, "review")]
        plan["geometry"] = {"decision": "Use existing A4 geometry with a 164 mm body.", "profile": "legacy-a4",
            "layout_config": None, "reason": "The ordinary single-column sample remains legible at the default width.", "evidence": evidence}
        plan["content_routes"] = [{"kind": "body", "decision": "Native text paragraphs with source identifiers.",
            "reason": "The sampled page contains an ordinary text paragraph.", "evidence": evidence}]
        plan["risk_review_reason"] = "The two-column hint is not confirmed; the actual sampled page is simple body text."
        plan["pilot"] = {"status": "passed", "build": self.ref(pdf), "build_record": self.ref(fingerprint),
            "sample_source_pages": [1], "sample_output_pages": [1], "evidence": evidence,
            "findings": "Body order and line endings were checked against the rendered source sample.",
            "reviewer": "Fixture reviewer", "unresolved": []}
        plan["worker_contract"] = self.ref(contract)
        self.persist(plan)
        return plan

    def assert_blocked(self, plan, message):
        self.persist(plan)
        result = planning.check(self.project)
        self.assertFalse(result["plan_ready"])
        self.assertTrue(any(message in issue for issue in result["issues"]), result)

    def test_scaffold_is_pending_preserves_candidates_and_does_not_open_source(self):
        original_hash = planning.sha256
        def without_source(path):
            self.assertNotEqual(Path(path), self.source)
            return original_hash(path)
        with mock.patch.object(planning, "sha256", side_effect=without_source):
            planning.scaffold(self.preflight, self.project)
        plan = planning.read_json(self.project / "layout-plan.json")
        self.assertEqual(plan["candidate_summary"]["status"], "unconfirmed_hints")
        self.assertEqual(plan["risk_cases"], [])
        self.assertEqual(plan["pilot"]["status"], "pending")
        self.assertEqual(plan["geometry"]["decision"], "")
        self.assertFalse(planning.check(self.project)["plan_ready"])
        with self.assertRaisesRegex(ValueError, "preserved"):
            planning.scaffold(self.preflight, self.project)

    def test_simple_document_can_pass_without_invented_risks(self):
        plan = self.ready_fixture()
        result = planning.check(self.project)
        self.assertTrue(result["plan_ready"], result)
        self.assertIn("不证明描述真实", result["limitation"])
        plan["risk_review_reason"] = "reviewed"
        self.assert_blocked(plan, "risk_review_reason")

    def test_current_risk_requires_real_pages_build_and_evidence(self):
        plan = self.ready_fixture()
        plan["risk_cases"] = [{"id": "line-order", "source_page": 1,
            "evidence": plan["geometry"]["evidence"], "problem": "Two text bands could be mistaken for columns.",
            "decision": "Preserve the ordinary paragraph after inspecting the source page.",
            "validation": {"status": "passed", "build_sha256": plan["pilot"]["build"]["sha256"],
                           "pilot_pages": [1], "evidence": plan["pilot"]["evidence"],
                           "findings": "The paragraph remains in source reading order on the pilot page."}}]
        self.persist(plan)
        self.assertTrue(planning.check(self.project)["plan_ready"])
        for field, invalid in (("source_page", 3), ("source_page", True)):
            changed = deepcopy(plan)
            changed["risk_cases"][0][field] = invalid
            self.assert_blocked(changed, "source_page")
        changed = deepcopy(plan)
        changed["risk_cases"][0]["validation"]["build_sha256"] = "0"*64
        self.assert_blocked(changed, "current pilot")
        changed = deepcopy(plan)
        changed["risk_cases"][0]["validation"]["pilot_pages"] = [3]
        self.assert_blocked(changed, "pilot_pages")
        changed = deepcopy(plan)
        changed["risk_cases"][0]["source_page"] = 2
        self.assert_blocked(changed, "pilot source sample")

    def test_status_words_and_non_render_material_cannot_stand_in_for_checks(self):
        plan = self.ready_fixture()
        for word in ("reviewed", "通过", "完成", "pending"):
            changed = deepcopy(plan)
            changed["pilot"]["findings"] = word
            self.assert_blocked(changed, "findings")
        changed = deepcopy(plan)
        changed["pilot"]["evidence"] = [plan["pilot"]["evidence"][1]]
        self.assert_blocked(changed, "both render and review")
        changed["pilot"]["evidence"] = [{**plan["pilot"]["evidence"][1], "role": "render"}, plan["pilot"]["evidence"][1]]
        self.assert_blocked(changed, "render evidence must")

    def test_changed_sources_preflight_and_evidence_are_rejected(self):
        plan = self.ready_fixture()
        with self.source.open("ab") as stream:
            stream.write(b"\nchanged bytes\n")
        self.assert_blocked(plan, "source: missing or stale")
        # A matching source hash alone cannot erase the preflight's source binding.
        changed = deepcopy(plan)
        changed["source"]["sha256"] = planning.sha256(self.source)
        self.assert_blocked(changed, "preflight: source")
        (self.project / "planning" / "preflight.json").write_text("{}", encoding="utf-8")
        self.assert_blocked(plan, "preflight: missing or stale")
        (self.project / "review" / "findings.md").write_text("changed evidence", encoding="utf-8")
        self.assert_blocked(plan, "evidence[1]: missing or stale")

    def test_paths_cannot_escape_project_and_missing_contract_blocks(self):
        plan = self.ready_fixture()
        plan["worker_contract"] = {"path": "../preflight.json", "sha256": planning.sha256(self.preflight)}
        self.assert_blocked(plan, "escapes project")
        plan["worker_contract"] = {"path": str(self.preflight), "sha256": planning.sha256(self.preflight)}
        self.assert_blocked(plan, "project-relative")
        plan["worker_contract"] = {"path": "missing.md", "sha256": "0"*64}
        self.assert_blocked(plan, "nonempty file")

    def test_unresolved_items_block_unless_explicitly_not_applicable_with_reason(self):
        plan = self.ready_fixture()
        plan["unresolved"] = [{"item": "QR decoding", "status": "not_applicable",
                               "reason": "The selected source sample contains no confirmed QR object."}]
        self.persist(plan)
        self.assertTrue(planning.check(self.project)["plan_ready"])
        plan["unresolved"][0]["reason"] = "done"
        self.assert_blocked(plan, "not_applicable needs")
        plan["unresolved"] = ["Unresolved source formula"]
        self.assert_blocked(plan, "unresolved item")

    def test_actual_geometry_config_or_known_profile_required(self):
        plan = self.ready_fixture()
        plan["geometry"]["profile"] = "reasonably-wide"
        self.assert_blocked(plan, "invented profile")
        config = self.project / "geometry.json"
        self.save(config, {"layout": {"paper_width_mm": 240, "paper_height_mm": 285, "text_width_mm": 145}})
        plan["geometry"]["profile"] = None
        plan["geometry"]["layout_config"] = self.ref(config)
        self.persist(plan)
        self.assertTrue(planning.check(self.project)["plan_ready"])
        self.save(config, {"layout": {"paper_width_mm": "合理加宽"}})
        plan["geometry"]["layout_config"] = self.ref(config)
        self.assert_blocked(plan, "actual positive")

    def test_pdf_and_build_record_must_bind_actual_source_and_output(self):
        plan = self.ready_fixture()
        record = self.project / "build" / "fingerprint.json"
        self.save(record, {"files": {"source": "0"*64, "pdf": plan["pilot"]["build"]["sha256"]}})
        plan["pilot"]["build_record"] = self.ref(record)
        self.assert_blocked(plan, "source/PDF hashes")
        plan["pilot"]["build"] = self.ref(self.project / "review" / "findings.md")
        self.assert_blocked(plan, "readable PDF")

    def test_existing_book_requires_retrospective_and_remains_pending(self):
        self.make_pdf(self.project / "build" / "main.pdf")
        with self.assertRaisesRegex(ValueError, "retrospective"):
            planning.scaffold(self.preflight, self.project)
        planning.scaffold(self.preflight, self.project, retrospective=True)
        plan = planning.read_json(self.project / "layout-plan.json")
        self.assertEqual(plan["planning_mode"], "retrospective")
        self.assertFalse(planning.check(self.project)["plan_ready"])

    def test_cli_reports_failures_without_tracebacks(self):
        plan = self.ready_fixture()
        with redirect_stdout(io.StringIO()) as output:
            status = planning.main(["check", "--project", str(self.project)])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(output.getvalue())["plan_ready"])
        self.persist(["malformed plan"])
        with redirect_stdout(io.StringIO()) as output:
            status = planning.main(["check", "--project", str(self.project)])
        self.assertEqual(status, 2)
        self.assertFalse(json.loads(output.getvalue())["plan_ready"])


if __name__ == "__main__":
    unittest.main()
