#!/usr/bin/env python3
"""Scaffold/check a source-bound document plan. plan_ready is not book acceptance."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

SHA = re.compile(r"[0-9a-f]{64}")
PLACEHOLDERS = {"", "pending", "todo", "tbd", "reviewed", "pass", "passed", "done", "ok",
                "待填", "待定", "待核验", "已复核", "已检查", "通过", "完成"}
LIMITATION = "plan_ready != 内容/美观验收；仅检查结构、路径、哈希和待办，不证明描述真实或替代 build/qa/release。"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def meaningful(value):
    return isinstance(value, str) and value.strip().lower().rstrip(".!。！") not in PLACEHOLDERS


def preflight_shape(record):
    count = record.get("page_count")
    return (record.get("schema_version") == 1 and record.get("status") == "complete"
            and isinstance(record.get("route"), dict) and record["route"].get("kind") == "pdf"
            and isinstance(count, int) and not isinstance(count, bool) and count > 0
            and isinstance(record.get("pages"), list) and all(isinstance(page, dict) for page in record["pages"])
            and [page.get("page") for page in record.get("pages", [])] == list(range(1, count + 1))
            and record.get("source_unchanged_after_scan") is True
            and isinstance(record.get("source"), str)
            and isinstance(record.get("source_sha256"), str) and SHA.fullmatch(record["source_sha256"]))


def scaffold(preflight, project, retrospective=False):
    preflight, project = Path(preflight).resolve(), Path(project).resolve()
    target = project / "layout-plan.json"
    if target.exists():
        raise ValueError("existing layout-plan.json preserved; no overwrite")
    if (project / "build" / "main.pdf").exists() and not retrospective:
        raise ValueError("existing build requires --retrospective; do not mislabel backfilled planning")
    record = read_json(preflight)
    if not isinstance(record, dict) or not preflight_shape(record):
        raise ValueError("requires a complete single-PDF preflight; PPTX routes to presentations")
    cached = (project / "planning" / "preflight.json").resolve()
    if not cached.is_relative_to(project):
        raise ValueError("planning/preflight.json resolves outside project")
    if cached.exists() and sha256(cached) != sha256(preflight):
        raise ValueError("existing planning/preflight.json differs; no overwrite")
    cached.parent.mkdir(parents=True, exist_ok=True)
    if not cached.exists():
        shutil.copyfile(preflight, cached)
    # The source PDF is not opened, parsed, rendered, or translated by scaffold.
    value = {"schema_version": 1, "planning_mode": "retrospective" if retrospective else "prospective",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {"path": record["source"], "sha256": record["source_sha256"], "page_count": record["page_count"]},
        "preflight": {"path": "planning/preflight.json", "sha256": sha256(cached)},
        "candidate_summary": {"status": "unconfirmed_hints", "summary": record.get("summary", {})},
        "geometry": {"decision": "", "profile": None, "layout_config": None, "reason": "", "evidence": []},
        "content_routes": [{"kind": "body", "decision": "", "reason": "", "evidence": []}],
        "risk_cases": [], "risk_review_reason": "",
        "pilot": {"status": "pending", "build": {"path": "", "sha256": ""},
                  "build_record": {"path": "", "sha256": ""}, "sample_source_pages": [],
                  "sample_output_pages": [], "evidence": [], "findings": "", "reviewer": "", "unresolved": []},
        "worker_contract": {"path": "", "sha256": ""}, "unresolved": []}
    with target.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return target


def check(project):
    project = Path(project).resolve()
    plan = read_json(project / "layout-plan.json")
    issues = []
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        return {"plan_ready": False, "issues": ["schema_version must be 1"], "limitation": LIMITATION}

    def require(condition, message):
        if not condition:
            issues.append(message)
        return bool(condition)

    def text(value, where):
        return require(meaningful(value), f"{where}: concrete description required, not a status word")

    def reference(ref, where):
        if not require(isinstance(ref, dict), f"{where}: expected path/sha256 reference"):
            return None
        name, expected = ref.get("path"), ref.get("sha256")
        if not require(isinstance(name, str) and bool(name.strip()), f"{where}: missing path"):
            return None
        path = Path(name)
        if not require(not path.is_absolute() and not path.drive, f"{where}: evidence must use a project-relative path"):
            return None
        path = (project / path).resolve()
        if not require(path.is_relative_to(project), f"{where}: resolved path escapes project"):
            return None
        if not require(path.is_file() and path.stat().st_size > 0, f"{where}: nonempty file required"):
            return None
        if not require(isinstance(expected, str) and bool(SHA.fullmatch(expected)) and sha256(path) == expected,
                       f"{where}: missing or stale SHA-256"):
            return None
        return path

    def evidence(items, where, pilot=False):
        if not require(isinstance(items, list) and bool(items), f"{where}: evidence references required"):
            return
        roles = set()
        for index, item in enumerate(items):
            path = reference(item, f"{where}[{index}]")
            if isinstance(item, dict) and isinstance(item.get("role"), str):
                roles.add(item["role"])
                if path and item["role"] == "render":
                    with path.open("rb") as stream:
                        head = stream.read(1024)
                    require(head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or b"%PDF-" in head,
                            f"{where}[{index}]: render evidence must be PNG, JPEG or PDF")
        if pilot:
            require({"render", "review"} <= roles, f"{where}: both render and review evidence required")

    def unresolved(items, where):
        if not require(isinstance(items, list), f"{where}: expected an array"):
            return
        for index, item in enumerate(items):
            require(isinstance(item, dict) and item.get("status") == "not_applicable"
                    and meaningful(item.get("item")) and meaningful(item.get("reason")),
                    f"{where}[{index}]: unresolved item blocks planning; not_applicable needs item and reason")

    def page_list(pages, maximum, where):
        valid = isinstance(pages, list) and bool(pages)
        valid = valid and all(type(page) is int and 1 <= page <= maximum for page in pages)
        valid = valid and len(set(pages)) == len(pages)
        require(valid, f"{where}: unique physical page numbers within 1..{maximum} required")

    require(plan.get("planning_mode") in ("prospective", "retrospective"), "planning_mode: explicit prospective/retrospective required")
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    source_count = source.get("page_count")
    if not require(type(source_count) is int and source_count > 0, "source.page_count: positive integer required"):
        source_count = 0
    path_value, source_hash = source.get("path"), source.get("sha256")
    source_path = Path(path_value) if isinstance(path_value, str) and path_value else None
    if require(source_path is not None and source_path.is_absolute() and source_path.is_file(), "source.path: existing absolute source path required"):
        require(isinstance(source_hash, str) and bool(SHA.fullmatch(source_hash)) and sha256(source_path) == source_hash,
                "source: missing or stale SHA-256")
    pf = reference(plan.get("preflight"), "preflight")
    if pf:
        record = read_json(pf)
        if require(isinstance(record, dict) and bool(preflight_shape(record)), "preflight: complete single-PDF scan required"):
            require(source_path is not None and Path(record["source"]).resolve() == source_path.resolve()
                    and record["source_sha256"] == source_hash and record["page_count"] == source_count,
                    "preflight: source path/hash/page count do not match plan")

    geometry = plan.get("geometry") if isinstance(plan.get("geometry"), dict) else {}
    text(geometry.get("decision"), "geometry.decision")
    text(geometry.get("reason"), "geometry.reason")
    evidence(geometry.get("evidence"), "geometry.evidence")
    if geometry.get("profile") == "legacy-a4" and geometry.get("layout_config") is None:
        pass  # Named existing default: A4, 164 mm body, 23 mm side margins.
    elif geometry.get("profile") is None:
        config_path = reference(geometry.get("layout_config"), "geometry.layout_config")
        if config_path:
            config = read_json(config_path)
            layout = config.get("layout", {}) if isinstance(config, dict) else {}
            require(isinstance(layout, dict) and all(type(layout.get(key)) in (int, float)
                    and math.isfinite(layout[key]) and layout[key] > 0
                    for key in ("paper_width_mm", "paper_height_mm", "text_width_mm")),
                    "geometry.layout_config: actual positive paper/text dimensions required; build validates geometry")
    else:
        require(False, "geometry: use profile=legacy-a4 or layout_config reference, not an invented profile")
    routes = plan.get("content_routes")
    if require(isinstance(routes, list) and bool(routes), "content_routes: explicit routes required"):
        for index, route in enumerate(routes):
            if not require(isinstance(route, dict), f"content_routes[{index}]: expected object"):
                continue
            for field in ("kind", "decision", "reason"):
                text(route.get(field), f"content_routes[{index}].{field}")
            evidence(route.get("evidence"), f"content_routes[{index}].evidence")

    pilot = plan.get("pilot") if isinstance(plan.get("pilot"), dict) else {}
    require(pilot.get("status") == "passed", "pilot.status: pilot must be completed with evidence")
    pdf = reference(pilot.get("build"), "pilot.build")
    output_count = 0
    if pdf:
        import fitz
        try:
            with fitz.open(pdf) as document:
                require(document.is_pdf and not document.needs_pass, "pilot.build: readable PDF required")
                output_count = document.page_count
        except (RuntimeError, ValueError):
            require(False, "pilot.build: readable PDF required")
    build_hash = pilot.get("build", {}).get("sha256") if isinstance(pilot.get("build"), dict) else None
    fingerprint = reference(pilot.get("build_record"), "pilot.build_record")
    if fingerprint:
        record = read_json(fingerprint)
        files = record.get("files", {}) if isinstance(record, dict) else {}
        require(isinstance(files, dict) and files.get("source") == source_hash and files.get("pdf") == build_hash,
                "pilot.build_record: source/PDF hashes must match current artifacts")
    page_list(pilot.get("sample_source_pages"), source_count, "pilot.sample_source_pages")
    page_list(pilot.get("sample_output_pages"), output_count, "pilot.sample_output_pages")
    evidence(pilot.get("evidence"), "pilot.evidence", pilot=True)
    text(pilot.get("findings"), "pilot.findings")
    text(pilot.get("reviewer"), "pilot.reviewer")
    unresolved(pilot.get("unresolved"), "pilot.unresolved")
    risks = plan.get("risk_cases")
    if require(isinstance(risks, list), "risk_cases: expected an array"):
        if not risks:
            text(plan.get("risk_review_reason"), "risk_review_reason for an empty risk_cases list")
        seen = set()
        for index, risk in enumerate(risks):
            where = f"risk_cases[{index}]"
            if not require(isinstance(risk, dict), f"{where}: expected object"):
                continue
            identifier = risk.get("id")
            if text(identifier, where+".id"):
                require(identifier not in seen, where+".id: duplicate")
                seen.add(identifier)
            page_list([risk.get("source_page")], source_count, where+".source_page")
            require(isinstance(pilot.get("sample_source_pages"), list) and risk.get("source_page") in pilot["sample_source_pages"],
                    where+".source_page: must be included in the pilot source sample")
            for field in ("problem", "decision"):
                text(risk.get(field), where+"."+field)
            evidence(risk.get("evidence"), where+".evidence")
            validation = risk.get("validation") if isinstance(risk.get("validation"), dict) else {}
            require(validation.get("status") == "passed" and validation.get("build_sha256") == build_hash,
                    where+".validation: must pass against the current pilot PDF hash")
            page_list(validation.get("pilot_pages"), output_count, where+".validation.pilot_pages")
            require(isinstance(validation.get("pilot_pages"), list) and isinstance(pilot.get("sample_output_pages"), list)
                    and all(page in pilot["sample_output_pages"] for page in validation["pilot_pages"]),
                    where+".validation.pilot_pages: must be included in the pilot output sample")
            text(validation.get("findings"), where+".validation.findings")
            evidence(validation.get("evidence"), where+".validation.evidence", pilot=True)
    reference(plan.get("worker_contract"), "worker_contract")
    unresolved(plan.get("unresolved"), "unresolved")
    return {"plan_ready": not issues, "planning_mode": plan.get("planning_mode"), "issues": issues, "limitation": LIMITATION}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("scaffold", help="copy preflight and create an unfinished plan; never overwrite")
    create.add_argument("--preflight", type=Path, required=True)
    create.add_argument("--project", type=Path, required=True)
    create.add_argument("--retrospective", action="store_true", help="label a backfilled plan for existing work")
    verify = commands.add_parser("check", help="read-only structural/hash gate; does not execute evidence")
    verify.add_argument("--project", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "scaffold":
            print(json.dumps({"plan": str(scaffold(args.preflight, args.project, args.retrospective)), "plan_ready": False,
                              "limitation": LIMITATION}, ensure_ascii=False))
            return 0
        result = check(args.project)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["plan_ready"] else 2
    except (OSError, ValueError, TypeError, AttributeError, ImportError) as error:
        print(json.dumps({"plan_ready": False, "issues": [str(error)], "limitation": LIMITATION}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
