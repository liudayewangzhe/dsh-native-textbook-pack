"""Track native translation work packages; this is not a PDF quality gate.

Only the supervising agent runs init/brief/record. Workers write their assigned
output, never the manifest, glossary, briefs or run state. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import tempfile

VERSION = 1
MANIFEST = "translation-manifest.json"
STATE = "run-state.json"
BOOK_KINDS = {"chapter", "section", "subsection", "paragraph", "equation",
              "table", "figure", "figure_native", "code", "console", "note"}
EXCLUSIONS = {"header_footer", "out_of_scope", "extraction_artifact"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read_json(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def inside(root, relative):
    require(isinstance(relative, str) and bool(relative.strip()), "empty project path")
    win = PureWindowsPath(relative)
    require(not Path(relative).is_absolute() and not win.drive and not win.root,
            f"project path must be relative: {relative}")
    require(".." not in win.parts and ".." not in Path(relative).parts,
            f"parent traversal is forbidden: {relative}")
    path = (root / relative).resolve()
    require(within(path, root), f"project path escapes root: {relative}")
    return path


def write_json(root, relative, value):
    path = inside(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, pending = tempfile.mkstemp(prefix=".translation-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


def strings(value, label, nonempty=False):
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value),
            f"{label} must be a list of nonempty strings")
    require(not nonempty or bool(value), f"{label} must not be empty")
    require(len(value) == len(set(value)), f"duplicate {label}")
    return value


def validate_spec(root, spec):
    require(isinstance(spec, dict) and type(spec.get("version")) is int and
            spec["version"] == VERSION, "unsupported spec version")
    require(spec.get("mode") in {"book", "slide"}, "mode must be book or slide")
    require(isinstance(spec.get("source"), dict) and isinstance(spec["source"].get("path"), str),
            "source.path is required")
    source = Path(spec["source"]["path"])
    source = (root / source).resolve() if not source.is_absolute() else source.resolve()
    require(source.is_file(), f"original source not found: {source}")
    require(source not in {inside(root, MANIFEST), inside(root, STATE)} and
            not within(source, root / "state"), "original source conflicts with generated state")
    chars = spec.get("context_chars", 400)
    require(type(chars) is int and chars >= 0, "context_chars must be a nonnegative integer")
    reads = [inside(root, spec.get("glossary", "glossary.json"))]
    for key in ("translation_inputs", "build_inputs"):
        for name in strings(spec.get(key, []), key):
            reads.append(inside(root, name))
    chunks = spec.get("chunks")
    require(isinstance(chunks, list) and bool(chunks), "chunks must be a nonempty list")
    ids, owned, outputs, page_ids, output_page_ids = set(), set(), [], set(), set()
    for chunk in chunks:
        require(isinstance(chunk, dict), "chunk must be an object")
        key = chunk.get("id")
        require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]+", key), "unsafe chunk id")
        require(key not in ids, f"duplicate chunk id: {key}")
        ids.add(key)
        source_ids = strings(chunk.get("source_ids"), f"{key}.source_ids", True)
        require(not owned.intersection(source_ids), f"source ID assigned to several chunks: {key}")
        owned.update(source_ids)
        require(isinstance(chunk.get("scope", "global"), str) and chunk.get("scope", "global").strip(),
                f"invalid scope: {key}")
        reads.append(inside(root, chunk.get("source")))
        outputs.append(inside(root, chunk.get("output")))
        if spec["mode"] == "slide":
            pages = chunk.get("source_pages")
            require(isinstance(pages, list) and pages and all(type(p) is int and p > 0 for p in pages),
                    "slide chunks require positive source_pages")
            require(len(set(pages)) == len(pages) and not page_ids.intersection(pages),
                    "slide source pages must have one owner")
            page_ids.update(pages)
            output_pages = chunk.get("output_pages", pages)
            require(isinstance(output_pages, list) and len(output_pages) == len(pages) and
                    all(type(p) is int and p > 0 for p in output_pages) and len(set(output_pages)) == len(output_pages),
                    "slide output_pages must map one-to-one to source_pages")
            require(not output_page_ids.intersection(output_pages), "slide output pages must have one owner")
            output_page_ids.update(output_pages)
    require(len(set(outputs)) == len(outputs), "duplicate output paths")
    reserved = {inside(root, MANIFEST), inside(root, STATE), source, *reads}
    for output in outputs:
        require(output not in reserved, f"output would overwrite an input/state file: {output}")
        require(not within(output, root / "state"), "outputs cannot overwrite state/briefs")
        require(not any(output in p.parents or p in output.parents for p in reserved | set(outputs) if p != output),
                f"conflicting input/output paths: {output}")
    for path in reads:
        require(path not in {inside(root, MANIFEST), inside(root, STATE)} and
                not within(path, root / "state"), f"input conflicts with generated state: {path}")
        require(path.is_file(), f"required project input not found: {path}")
    return source


def init(project, spec_path):
    root = Path(project).resolve()
    root.mkdir(parents=True, exist_ok=True)
    require(not inside(root, MANIFEST).exists() and not inside(root, STATE).exists(),
            "project state already exists; refusing to overwrite")
    spec = read_json(Path(spec_path))
    source = validate_spec(root, spec)
    spec["source"] = {"path": str(source), "sha256": file_hash(source)}
    load_terms(root, spec)
    write_json(root, MANIFEST, spec)
    write_json(root, STATE, {"version": VERSION, "manifest_fingerprint": digest(spec), "chunks": {}})
    return {"stage": "initialized", "chunks": len(spec["chunks"])}


def load(project):
    root = Path(project).resolve()
    spec = read_json(inside(root, MANIFEST))
    state = read_json(inside(root, STATE))
    require(isinstance(state, dict) and state.get("version") == VERSION and
            isinstance(state.get("chunks"), dict), "invalid run state")
    require(state.get("manifest_fingerprint") == digest(spec),
            "manifest identity changed; scope/order/path changes require a new project lineage")
    source = validate_spec(root, spec)
    require(file_hash(source) == spec["source"].get("sha256"),
            "original source bytes changed; use a new project lineage")
    require(set(state["chunks"]).issubset({c["id"] for c in spec["chunks"]}),
            "run state contains unknown chunks")
    return root, spec, state


def load_terms(root, spec):
    glossary = read_json(inside(root, spec.get("glossary", "glossary.json")))
    require(isinstance(glossary, dict) and glossary.get("version") == VERSION and
            isinstance(glossary.get("terms"), list), "invalid glossary v1")
    terms, term_ids = [], set()
    for item in glossary["terms"]:
        require(isinstance(item, dict), "glossary term must be an object")
        term = {key: item.get(key) for key in ("id", "source", "target")}
        require(all(isinstance(v, str) and v.strip() for v in term.values()), "term fields must be nonempty")
        require(term["id"] not in term_ids, f"duplicate term id: {term['id']}")
        term_ids.add(term["id"])
        term["aliases"] = sorted(strings(item.get("aliases", []), "term aliases"))
        term["scope"] = item.get("scope", "global")
        require(isinstance(term["scope"], str) and term["scope"].strip(), "invalid term scope")
        term["always"] = item.get("always", False)
        require(type(term["always"]) is bool, "term.always must be boolean")
        terms.append(term)
    # A global surface collides with any same-surface scoped term; distinct
    # non-global scopes may deliberately use different meanings.
    surfaces = {}
    for term in terms:
        for surface in {term["source"], *term["aliases"]}:
            key = surface.casefold()
            for other in surfaces.get(key, []):
                require(other["id"] == term["id"] or
                        (other["scope"] != term["scope"] and "global" not in {other["scope"], term["scope"]}),
                        f"ambiguous glossary surface: {surface}")
            surfaces.setdefault(key, []).append(term)
    return terms


def matches(surface, text):
    # CJK has no whitespace word boundary. Other terms use Unicode-aware
    # boundaries, so cat does not match category and foo does not match foo_bar.
    pattern = re.escape(surface)
    if not re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", surface):
        pattern = r"(?<!\w)" + pattern + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def snapshot(root, spec, chunk_id):
    index = next((i for i, c in enumerate(spec["chunks"]) if c["id"] == chunk_id), None)
    require(index is not None, f"unknown chunk: {chunk_id}")
    chunk = spec["chunks"][index]
    text = inside(root, chunk["source"]).read_text(encoding="utf-8-sig")
    require(text.strip(), f"blank source chunk: {chunk_id}")
    size = spec.get("context_chars", 400)
    context = {"prev_excerpt": "", "next_excerpt": "", "read_only": True}
    if size and index:
        context["prev_excerpt"] = inside(root, spec["chunks"][index - 1]["source"]).read_text(encoding="utf-8-sig")[-size:]
    if size and index + 1 < len(spec["chunks"]):
        context["next_excerpt"] = inside(root, spec["chunks"][index + 1]["source"]).read_text(encoding="utf-8-sig")[:size]
    combined = text + "\n" + context["prev_excerpt"] + "\n" + context["next_excerpt"]
    selected = sorted((term for term in load_terms(root, spec)
                       if term["scope"] in {"global", chunk.get("scope", "global")} and
                       (term["always"] or any(matches(s, combined) for s in [term["source"], *term["aliases"]]))),
                      key=lambda term: term["id"])
    translation_inputs = {name: file_hash(inside(root, name)) for name in spec.get("translation_inputs", [])}
    build_inputs = {name: file_hash(inside(root, name)) for name in spec.get("build_inputs", [])}
    payload = {"protocol": VERSION, "runtime_sha256": file_hash(Path(__file__)),
               "mode": spec["mode"], "source_sha256": spec["source"]["sha256"],
               "chunk": chunk, "source_text": text, "context": context,
               "terms": selected, "translation_inputs": translation_inputs}
    translation_fp = digest(payload)
    payload.update({"translation_fingerprint": translation_fp,
                    "build_inputs": build_inputs,
                    "build_fingerprint": digest({"translation": translation_fp, "inputs": build_inputs}),
                    "worker_write_only": chunk["output"],
                    "proof_boundary": "Scheduling and provenance only; no semantic, visual or PDF acceptance."})
    return payload


def brief(project, chunk_id):
    root, spec, _ = load(project)
    data = snapshot(root, spec, chunk_id)
    name = f"state/briefs/{chunk_id}.json"
    write_json(root, name, data)
    return {"brief": str(inside(root, name)), **data}


def source_refs(items, label):
    refs, ids = set(), set()
    for item in items:
        require(isinstance(item, dict), f"{label} item must be an object")
        key = item.get("id")
        require(isinstance(key, str) and key.strip() and key not in ids, f"invalid/duplicate {label} id")
        ids.add(key)
        refs.update(strings(item.get("source_ids"), f"{label}.source_ids", True))
    return refs


def validate_output(root, spec, chunk):
    output = read_json(inside(root, chunk["output"]))
    require(isinstance(output, dict), "output must be a JSON object")
    require(isinstance(output.get("unresolved", []), list) and not output.get("unresolved", []),
            "output unresolved must be an empty list before record")
    exclusions = output.get("exclusions", [])
    require(isinstance(exclusions, list), "exclusions must be a list")
    excluded = set()
    for item in exclusions:
        require(isinstance(item, dict) and item.get("category") in EXCLUSIONS and
                isinstance(item.get("reason"), str) and item["reason"].strip(), "invalid exclusion")
        ref = item.get("source_id")
        require(isinstance(ref, str) and ref.strip() and ref not in excluded, "invalid/duplicate exclusion source ID")
        excluded.add(ref)
    if spec["mode"] == "book":
        require("unresolved" in output, "book output requires unresolved list")
        blocks = output.get("blocks")
        require(isinstance(blocks, list) and bool(blocks), "book blocks must be nonempty")
        covered = source_refs(blocks, "block")
        for block in blocks:
            kind = block.get("kind")
            require(kind in BOOK_KINDS, f"unsupported book kind: {kind}")
            if kind in {"code", "console"}:
                require(not (set(block) - {"id", "kind", "source_ids", "text"}),
                        "literal block has unsupported fields; code/console accepts raw text, not tex/language")
                raw = block.get("text")
                require(isinstance(raw, str) and raw.strip(), "code/console requires nonempty raw text")
                require(not any((ord(ch) < 32 and ch not in "\t\n\r") or ord(ch) == 127 for ch in raw),
                        "literal text contains unsupported control characters")
                raw.encode("utf-8")
                continue
            field = "asset" if kind == "figure" else "tex"
            require(isinstance(block.get(field), str) and block[field].strip(), f"{kind} requires {field}")
            if kind == "figure_native":
                require(not set(block).intersection({"asset", "caption", "number", "width"}),
                        "figure_native puts its figure content in tex, not asset/caption/number/width")
            if kind == "figure":
                require(not block.get("tex"), "figure uses a registered asset, not tex")
        expectations = output.get("expectations")
        require(isinstance(expectations, dict), "source-derived expectations required")
        for key in ("equation_tags", "required_strings"):
            strings(expectations.get(key), f"expectations.{key}")
        for key in ("table_count", "figure_count"):
            require(type(expectations.get(key)) is int and expectations[key] >= 0, f"invalid expectations.{key}")
    else:
        require(output.get("source_sha256") == spec["source"]["sha256"], "slide source hash mismatch")
        pages = output.get("pages")
        require(isinstance(pages, list) and pages, "slide output requires pages")
        require([page.get("source_page") for page in pages if isinstance(page, dict)] == chunk["source_pages"],
                "slide source page order/ownership mismatch")
        objects, output_pages = [], set()
        require([page.get("output_page") for page in pages] == chunk.get("output_pages", chunk["source_pages"]),
                "slide output page mapping differs from assigned scope")
        for page in pages:
            number = page.get("output_page")
            require(type(number) is int and number > 0 and number not in output_pages, "invalid slide output page")
            output_pages.add(number)
            require(isinstance(page.get("unresolved"), list) and not page["unresolved"], "slide page unresolved")
            require(isinstance(page.get("objects"), list), "slide objects must be a list")
            if not page["objects"] or page.get("blank") is True:
                require(not page["objects"] and page.get("blank") is True and page.get("checked") is True and
                        isinstance(page.get("reason"), str) and page["reason"].strip(),
                        "empty slide requires blank:true, checked:true and a nonempty reason")
            objects.extend(page["objects"])
        covered = source_refs(objects, "slide object")
        for item in objects:
            require(isinstance(item.get("kind"), str) and item["kind"].strip(), "slide object requires kind")
            require(any(isinstance(item.get(key), str) and item[key].strip()
                        for key in ("latex", "tex", "text", "asset")), "slide object lacks native content/asset")
    require(not covered.intersection(excluded), "source ID both included and excluded")
    require(covered | excluded == set(chunk["source_ids"]), "output source ID coverage differs from assigned scope")
    return output


def record(project, chunk_id):
    root, spec, state = load(project)
    current = snapshot(root, spec, chunk_id)
    previous = read_json(inside(root, f"state/briefs/{chunk_id}.json"))
    require(previous == current,
            "brief is stale or modified; regenerate the brief and inspect the affected output")
    chunk = current["chunk"]
    validate_output(root, spec, chunk)
    entry = {key: current[key] for key in ("translation_fingerprint", "build_fingerprint")}
    entry.update({"output_sha256": file_hash(inside(root, chunk["output"])), "stage": "draft_recorded"})
    state["chunks"][chunk_id] = entry
    write_json(root, STATE, state)
    return {"chunk": chunk_id, **entry, "review_valid": False}


def plan(project):
    root, spec, state = load(project)
    rows = []
    for chunk in spec["chunks"]:
        now = snapshot(root, spec, chunk["id"])
        old = state["chunks"].get(chunk["id"])
        path = inside(root, chunk["output"])
        action, reasons = "reuse", []
        if old is None:
            action, reasons = ("inspect", ["untracked_output"]) if path.exists() else ("translate", ["not_recorded"])
        elif not isinstance(old, dict):
            raise ValueError(f"invalid chunk record: {chunk['id']}")
        elif old.get("stage") != "draft_recorded":
            raise ValueError(f"invalid chunk record stage: {chunk['id']}")
        elif not path.is_file():
            action, reasons = "translate", ["output_missing"]
        elif file_hash(path) != old.get("output_sha256"):
            action, reasons = "inspect", ["output_changed"]
        elif old.get("translation_fingerprint") != now["translation_fingerprint"]:
            action, reasons = "translate", ["translation_dependencies_changed"]
        elif old.get("build_fingerprint") != now["build_fingerprint"]:
            action, reasons = "rebuild", ["build_dependencies_changed"]
        else:
            try:
                validate_output(root, spec, chunk)
            except (ValueError, KeyError, TypeError) as exc:
                action, reasons = "inspect", [f"invalid_output: {exc}"]
        rows.append({"id": chunk["id"], "action": action, "reasons": reasons, "output": chunk["output"]})
    return {"stage": "planned", "chunks": rows,
            "ordered_outputs": [str(inside(root, c["output"])) for c in spec["chunks"]],
            "needs_rebuild": any(row["action"] == "rebuild" for row in rows),
            "review_valid": False}


def verify(project):
    result = plan(project)
    require(all(row["action"] in {"reuse", "rebuild"} for row in result["chunks"]),
            "draft verification blocked: " + "; ".join(f"{r['id']}:{','.join(r['reasons'])}" for r in result["chunks"]
                                                        if r["action"] not in {"reuse", "rebuild"}))
    result["stage"] = "draft_verified"
    result["proof_boundary"] = "Draft set provenance only; run engine and full content/visual/rebuild gates."
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "plan", "brief", "record", "verify"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--spec")
    parser.add_argument("--chunk")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            require(bool(args.spec), "init requires --spec")
            result = init(args.project, args.spec)
        elif args.command in {"brief", "record"}:
            require(bool(args.chunk), f"{args.command} requires --chunk")
            result = {"brief": brief, "record": record}[args.command](args.project, args.chunk)
            if args.command == "brief":
                result = {key: result[key] for key in ("brief", "translation_fingerprint", "build_fingerprint")}
        else:
            result = {"plan": plan, "verify": verify}[args.command](args.project)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"translation state blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
