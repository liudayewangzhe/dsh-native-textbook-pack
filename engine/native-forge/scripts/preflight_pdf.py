#!/usr/bin/env python3
"""Read-only source preflight. Observations and unconfirmed candidates are distinct.

No OCR, translation, asset replacement, or publication acceptance is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import gc
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys
import zipfile

RAM_FLOOR = 1 << 30
PT_MM = 25.4 / 72
HEURISTICS = {"large_image_area_ratio": 0.8, "low_text_characters": 80,
              "code_font_ratio": 0.12, "code_pattern_lines": 3,
              "math_font_or_symbol_ratio": 0.08, "column_min_lines_each": 6,
              "narrow_note_font_ratio": 0.9, "qr_square_aspect_tolerance": 0.2,
              "reference_body_width_mm": 164}
MATH_FONT = re.compile(r"math|symbol|cmsy|cmmi|cmex|mtsy|mtmi|mtex|msam|msbm|eufm", re.I)
MONO_FONT = re.compile(r"courier|mono|consolas|cmtt|typewriter", re.I)
MATH_CHAR = re.compile(r"[\u0370-\u03ff\u2200-\u22ff\u27c0-\u27ef]")
CODE_LINE = re.compile(r"^\s*(?:>>>|\.\.\.|In\s*\[\d*\]:|Out\s*\[\d*\]:|def\s|class\s|import\s|from\s\S+\simport|for\s.+:|while\s.+:|if\s.+:)")


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(path.suffix + ".tmp")
    staging.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    staging.replace(path)


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def free_memory():
    if sys.platform != "win32":
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
                    ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong),
                    ("extended", ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("cannot read free physical memory")
    return status.available


def ensure_memory():
    available = free_memory()
    if available is not None and available < RAM_FLOOR:
        raise MemoryError(f"physical memory below 1.00 GiB ({available / (1 << 30):.3f} GiB); checkpoint preserved")


def input_route(path):
    path = Path(path)
    if path.suffix.lower() == ".pptx":
        try:
            with zipfile.ZipFile(path) as package:
                if "ppt/presentation.xml" in package.namelist():
                    return {"kind": "editable_presentation", "route": "presentations",
                            "book_conversion": False, "evidence": "PPTX presentation.xml exists"}
        except zipfile.BadZipFile:
            pass
        raise ValueError(".pptx is not a valid editable presentation container")
    with path.open("rb") as stream:
        signature = stream.read(1024)
    if b"%PDF-" in signature:
        return {"kind": "pdf", "route": "pdf-source-preflight", "book_conversion": None,
                "evidence": "PDF signature; page features still need inspection"}
    raise ValueError("unsupported source; no automatic conversion to a book")


def page_observations(page):
    import fitz
    # Excluding image payloads is essential for scanned books: retain coordinates only.
    raw = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES, sort=False)
    width, height = page.rect.width, page.rect.height
    text_parts, lines, fonts = [], [], Counter()
    mono_chars = math_chars = math_font_chars = replacement_chars = private_chars = 0
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans)
            if not text.strip():
                continue
            sizes = []
            for span in spans:
                count = len(span.get("text", "").strip())
                font = span.get("font", "")
                size = float(span.get("size", 0))
                fonts[round(size * 2) / 2] += count
                sizes.extend([size] * min(count, 40))
                if span.get("flags", 0) & 8 or MONO_FONT.search(font):
                    mono_chars += count
                if MATH_FONT.search(font):
                    math_font_chars += count
            text_parts.append(text)
            math_chars += len(MATH_CHAR.findall(text))
            replacement_chars += text.count("\ufffd")
            private_chars += sum(0xE000 <= ord(char) <= 0xF8FF for char in text)
            lines.append({"bbox": [round(v, 2) for v in line["bbox"]],
                          "size": statistics.median(sizes) if sizes else 0, "chars": len(text),
                          "code_pattern": bool(CODE_LINE.match(text))})
    text = "\n".join(text_parts)
    characters = len(re.sub(r"\s", "", text))
    body_font = fonts.most_common(1)[0][0] if fonts else 0
    body_lines = [line for line in lines if height * .10 < line["bbox"][1] < height * .90]
    left = [line for line in body_lines if line["bbox"][0] < width * .45 and line["bbox"][2] < width * .55]
    right = [line for line in body_lines if line["bbox"][0] > width * .45]
    narrow_outer = [line for line in body_lines if line["bbox"][2] - line["bbox"][0] < width * .30
                    and (line["bbox"][2] < width * .33 or line["bbox"][0] > width * .67)
                    and 0 < line["size"] <= body_font * HEURISTICS["narrow_note_font_ratio"]]
    images, square_images = [], []
    for info in page.get_image_info(hashes=False, xrefs=False):
        rect = fitz.Rect(info["bbox"]) & page.rect
        if rect.is_empty or rect.is_infinite:
            continue
        ratio = rect.get_area() / page.rect.get_area()
        item = {"bbox": [round(v, 2) for v in rect], "pixels": [info["width"], info["height"]],
                "area_ratio": round(ratio, 4)}
        images.append(item)
        aspect = rect.width / rect.height
        if (abs(aspect - 1) <= HEURISTICS["qr_square_aspect_tolerance"]
                and rect.width < width * .35 and rect.height < height * .35 and min(item["pixels"]) >= 35):
            square_images.append(item)
    # Compact tuples avoid millions of Point/Rect wrapper objects on dense plots.
    drawings = page.get_cdrawings()
    horizontal_rules = vertical_rules = rectangles = 0
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] == "l":
                a, b = item[1], item[2]
                horizontal_rules += abs(a[1]-b[1]) < 1 and abs(a[0]-b[0]) > 20
                vertical_rules += abs(a[0]-b[0]) < 1 and abs(a[1]-b[1]) > 20
            elif item[0] == "re":
                rectangles += 1
    link_list = page.get_links()
    uris = sorted({link["uri"] for link in link_list if isinstance(link.get("uri"), str)})
    image_ratio = max((image["area_ratio"] for image in images), default=0)
    observation = {"page": page.number + 1, "width_mm": round(width * PT_MM, 2),
        "height_mm": round(height * PT_MM, 2), "rotation": page.rotation,
        "mediabox": list(page.mediabox), "cropbox": list(page.cropbox),
        "text_characters": characters, "text_lines": len(lines), "body_font_pt": body_font,
        "monospace_characters": mono_chars, "math_font_characters": math_font_chars,
        "math_symbol_characters": math_chars, "replacement_characters": replacement_chars,
        "private_use_characters": private_chars, "code_pattern_lines": sum(line["code_pattern"] for line in lines),
        "max_text_line_width_mm": round(max((line["bbox"][2]-line["bbox"][0] for line in body_lines), default=0) * PT_MM, 2),
        "left_short_lines": len(left), "right_short_lines": len(right), "smaller_outer_lines": len(narrow_outer),
        "image_count": len(images), "max_image_area_ratio": image_ratio,
        "max_image_width_mm": round(max((image["bbox"][2]-image["bbox"][0] for image in images), default=0) * PT_MM, 2),
        "max_nonpage_image_width_mm": round(max((image["bbox"][2]-image["bbox"][0] for image in images
            if image["area_ratio"] < HEURISTICS["large_image_area_ratio"]), default=0) * PT_MM, 2),
        "vector_paths": len(drawings), "horizontal_rules": horizontal_rules, "vertical_rules": vertical_rules,
        "rectangles": rectangles, "link_count": len(link_list), "external_uris": uris,
        "square_image_candidates": square_images[:5],
        "evidence_excerpt": text[:700]}
    observation["candidates"] = candidate_flags(observation)
    return observation


def candidate_flags(observation):
    o, flags = observation, []
    chars = max(o["text_characters"], 1)
    if o["max_image_area_ratio"] >= HEURISTICS["large_image_area_ratio"]:
        flags.append("large_page_image_low_text" if o["text_characters"] < HEURISTICS["low_text_characters"] else "large_page_image_with_text_layer")
    if o["replacement_characters"] or o["private_use_characters"]:
        flags.append("text_encoding_needs_inspection")
    if o["monospace_characters"] / chars >= HEURISTICS["code_font_ratio"] or o["code_pattern_lines"] >= HEURISTICS["code_pattern_lines"]:
        flags.append("code_or_literal")
    if max(o["math_font_characters"], o["math_symbol_characters"]) / chars >= HEURISTICS["math_font_or_symbol_ratio"]:
        flags.append("mathematical_typography")
    if o["horizontal_rules"] >= 3 and (o["vertical_rules"] >= 2 or o["text_lines"] >= 15):
        flags.append("ruled_table_or_diagram")
    if min(o["left_short_lines"], o["right_short_lines"]) >= HEURISTICS["column_min_lines_each"]:
        flags.append("multiple_text_bands")
    if o["smaller_outer_lines"] >= 3:
        flags.append("margin_text_or_figure_labels")
    if o["square_image_candidates"]:
        flags.append("square_image_not_yet_qr")
    if o["width_mm"] > o["height_mm"]:
        flags.append("landscape_or_presentation_pdf")
    if max(o["max_text_line_width_mm"], o["max_nonpage_image_width_mm"]) > HEURISTICS["reference_body_width_mm"]:
        flags.append("source_object_wider_than_reference_body")
    if o["rotation"]:
        flags.append("rotated_page_requires_coordinate_review")
    if o["text_characters"] == 0 and not o["image_count"] and not o["vector_paths"]:
        flags.append("no_observed_content")
    return flags


def summarize(pages):
    features = Counter(flag for page in pages for flag in page["candidates"])
    sizes = Counter(f"{page['width_mm']}x{page['height_mm']}mm" for page in pages)
    sample_pages = {}
    for field in ("monospace_characters", "math_font_characters", "vector_paths", "horizontal_rules", "link_count", "smaller_outer_lines"):
        winner = max(pages, key=lambda page: page[field], default=None)
        if winner and winner[field] > 0:
            sample_pages[field] = winner["page"]
    for flag in features:
        sample_pages[flag] = next(page["page"] for page in pages if flag in page["candidates"])
    return {"pages_scanned": len(pages), "page_sizes": dict(sizes), "candidate_page_counts": dict(features),
            "pages_with_extractable_text": sum(page["text_characters"] > 0 for page in pages),
            "pages_with_images": sum(page["image_count"] > 0 for page in pages),
            "pages_with_vector_paths": sum(page["vector_paths"] > 0 for page in pages),
            "text_characters": sum(page["text_characters"] for page in pages),
            "external_link_count": sum(len(page["external_uris"]) for page in pages),
            "representative_candidates": sample_pages}


def scan_source(entry, output_dir):
    import fitz
    ensure_memory()
    source = Path(entry["path"]).expanduser().resolve(strict=True)
    identifier = entry["id"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identifier):
        raise ValueError("manifest id must be a safe unique filename")
    route = input_route(source)
    record = {"schema_version": 1, "id": identifier, "source": str(source), "source_sha256": file_hash(source),
              "source_bytes": source.stat().st_size, "analyzer_sha256": file_hash(__file__),
              "route": route, "heuristics": HEURISTICS, "status": "complete", "pages": []}
    destination = Path(output_dir) / f"{identifier}.json"
    if route["kind"] != "pdf":
        dump(destination, record)
        return record
    if destination.exists():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        if all(previous.get(key) == record[key] for key in ("source_sha256", "analyzer_sha256", "heuristics")):
            record["pages"] = previous.get("pages", [])
    with fitz.open(source) as document:
        if document.needs_pass:
            raise ValueError(f"encrypted PDF needs an authorized password: {identifier}")
        record["page_count"] = document.page_count
        record["toc_entries"] = len(document.get_toc())
        record["metadata"] = {key: document.metadata.get(key) for key in ("title", "author", "producer")}
        if (len(record["pages"]) > document.page_count or
                any(page.get("page") != index + 1 for index, page in enumerate(record["pages"]))):
            record["pages"] = []
        try:
            for page_number in range(len(record["pages"]), document.page_count):
                ensure_memory()
                record["pages"].append(page_observations(document[page_number]))
                if (page_number + 1) % 12 == 0:
                    record["status"] = "in_progress"
                    dump(destination, record)
                    fitz.TOOLS.store_shrink(100)
                    gc.collect()
            record["status"] = "complete"
        except MemoryError:
            record["status"] = "paused_low_memory"
            record["summary"] = summarize(record["pages"])
            dump(destination, record)
            raise
    record["summary"] = summarize(record["pages"])
    record["source_unchanged_after_scan"] = file_hash(source) == record["source_sha256"]
    if not record["source_unchanged_after_scan"]:
        record["status"] = "source_changed_during_scan"
        dump(destination, record)
        raise ValueError(f"source changed during preflight: {identifier}; rerun against a stable input")
    dump(destination, record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries or any(not isinstance(entry, dict) for entry in entries):
        parser.error("manifest must be a nonempty list of {id,path} objects")
    if len({entry.get("id") for entry in entries}) != len(entries):
        parser.error("manifest source IDs must be unique")
    summary = []
    for entry in entries:
        record = scan_source(entry, args.out)
        item = {key: record[key] for key in ("id", "source", "source_sha256", "source_bytes", "route", "status")}
        item["summary"] = record.get("summary", {})
        summary.append(item)
        dump(args.out / "corpus.json", {"documents": summary, "scope": "read-only features; no translation, OCR or acceptance"})
        print(json.dumps({"id": record["id"], "pages": record.get("page_count"), "status": record["status"]}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (MemoryError, ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
