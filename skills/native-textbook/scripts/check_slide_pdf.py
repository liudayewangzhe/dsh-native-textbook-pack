#!/usr/bin/env python3
"""Check observable properties of an actual slide PDF; not semantic/visual QA.

Requires PyMuPDF. Coordinates in config are PDF points, top-left origin.
Run: python check_slide_pdf.py --pdf main.pdf --config checks.json --out qa.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

try:
    import fitz
except ImportError:
    raise SystemExit("PyMuPDF is required; use the bundled Python with fitz installed.")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def is_private(ch: str) -> bool:
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def rect(value, label):
    if not isinstance(value, list) or len(value) != 4 or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in value):
        raise ValueError(f"{label} must be [x0,y0,x1,y1] in PDF points")
    result = fitz.Rect(value)
    if result.is_empty or result.is_infinite:
        raise ValueError(f"{label} must have positive width and height")
    return result


def page_value(config, plural, single, number):
    return config.get(plural, {}).get(str(number), config.get(single))


def validate_config(config, page_count):
    if not isinstance(config, dict):
        raise ValueError("config must be a JSON object")
    for key in ("page_titles", "title_regions_pt", "required_strings", "body_regions_pt", "content_bounds_by_page_pt"):
        value = config.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object keyed by one-based page number")
        for number in value:
            if not str(number).isdigit() or not 1 <= int(number) <= page_count:
                raise ValueError(f"{key}: page {number!r} is outside the actual PDF")
    if "expected_pages" in config and (not isinstance(config['expected_pages'], int) or config['expected_pages'] < 1):
        raise ValueError("expected_pages must be a positive integer")
    for key in ("width_mm", "height_mm", "size_tolerance_pt", "bbox_tolerance_pt"):
        if key in config and (not isinstance(config[key], (int, float)) or not math.isfinite(config[key]) or config[key] < 0):
            raise ValueError(f"{key} must be finite and nonnegative")
    for number, title in config.get("page_titles", {}).items():
        if not isinstance(title, str) or not title:
            raise ValueError(f"page_titles[{number}] must be a nonempty string; omit intentionally untitled pages")
    for number, values in config.get("required_strings", {}).items():
        if not isinstance(values, list):
            raise ValueError(f"required_strings[{number}] must be a list")
        for value in values:
            if isinstance(value, str) and value:
                continue
            if (isinstance(value, dict) and isinstance(value.get("text"), str) and value["text"]
                    and isinstance(value.get("min_count", 1), int) and value.get("min_count", 1) > 0):
                continue
            raise ValueError(f"required_strings[{number}] entries must be strings or text/min_count objects")
    for key in ("title_region_pt", "body_region_pt", "content_bounds_pt"):
        if key in config:
            rect(config[key], key)
    for key in ("title_regions_pt", "body_regions_pt", "content_bounds_by_page_pt"):
        for number, value in config.get(key, {}).items():
            rect(value, f"{key}[{number}]")


def check_pdf(path: Path, config: dict):
    issues = []
    observations = []
    font_records = {}
    doc = fitz.open(path)
    validate_config(config, len(doc))

    def issue(code, message, page=None, details=None):
        entry = dict(code=code, message=message)
        if page is not None:
            entry['page'] = page
        if details is not None:
            entry['details'] = details
        issues.append(entry)

    if doc.is_encrypted:
        issue('encrypted', 'PDF is encrypted; successful opening does not prove full content access.')
    if config.get('expected_pages') is not None and len(doc) != config['expected_pages']:
        issue('page_count', f"Expected {config['expected_pages']} pages, found {len(doc)}.")
    expected_width = config.get('width_mm')
    expected_height = config.get('height_mm')
    size_tolerance = config.get('size_tolerance_pt', 0.5)
    bbox_tolerance = config.get('bbox_tolerance_pt', 0.5)
    unique_image_xrefs = set()
    total_runtime_images = 0
    allowed_private = set(config.get('allowed_private_characters', []))

    for number, page in enumerate(doc, 1):
        # Default page clipping can silently drop the very off-page glyphs this
        # check needs to observe. Title-region checks below intentionally clip.
        text = page.get_text(clip=fitz.INFINITE_RECT())
        rect_page = page.rect
        if expected_width is not None and abs(rect_page.width - expected_width * 72 / 25.4) > size_tolerance:
            issue('page_width', 'Page width differs from the configured width.', number, rect_page.width)
        if expected_height is not None and abs(rect_page.height - expected_height * 72 / 25.4) > size_tolerance:
            issue('page_height', 'Page height differs from the configured height.', number, rect_page.height)
        if len(compact(text)) < config.get('min_text_characters_per_page', 1):
            issue('little_extractable_text', 'Page has less extractable text than configured.', number)

        bad_chars = sorted({ch for ch in text if ch == '\ufffd' or (is_private(ch) and ch not in allowed_private)
                            or (ord(ch) < 32 and ch not in '\n\r\t\f')})
        if bad_chars:
            issue('suspicious_characters', 'Replacement, private-use or unexpected control characters were extracted.', number,
                  [dict(character=ch, codepoint=f'U+{ord(ch):04X}') for ch in bad_chars])

        spans = []
        for block in page.get_text('dict', clip=fitz.INFINITE_RECT())['blocks']:
            for line in block.get('lines', []):
                spans.extend(span for span in line.get('spans', []) if span.get('text', '').strip())
        body_value = page_value(config, 'body_regions_pt', 'body_region_pt', number)
        bounds_value = page_value(config, 'content_bounds_by_page_pt', 'content_bounds_pt', number)
        body_rect = rect(body_value, 'body_region') if body_value else None
        bounds_rect = rect(bounds_value, 'content_bounds') if bounds_value else None
        outside_page = []
        outside_body = []
        body_boxes = []
        for span in spans:
            box = fitz.Rect(span['bbox'])
            if (box.x0 < rect_page.x0 - bbox_tolerance or box.y0 < rect_page.y0 - bbox_tolerance
                    or box.x1 > rect_page.x1 + bbox_tolerance or box.y1 > rect_page.y1 + bbox_tolerance):
                outside_page.append(dict(text=span['text'], bbox=list(box)))
            centre = fitz.Point((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
            if body_rect is None or centre in body_rect:
                body_boxes.append(box)
                if bounds_rect is not None and (box.x0 < bounds_rect.x0 - bbox_tolerance
                        or box.y0 < bounds_rect.y0 - bbox_tolerance or box.x1 > bounds_rect.x1 + bbox_tolerance
                        or box.y1 > bounds_rect.y1 + bbox_tolerance):
                    outside_body.append(dict(text=span['text'], bbox=list(box)))
        if outside_page:
            issue('text_outside_page', 'Extracted text span bounds extend beyond the page.', number, outside_page)
        if outside_body:
            issue('body_text_outside_bounds', 'Body text spans extend beyond configured content bounds.', number, outside_body)

        title = config.get('page_titles', {}).get(str(number))
        title_region = page_value(config, 'title_regions_pt', 'title_region_pt', number)
        title_text = page.get_text(clip=rect(title_region, 'title_region')) if title_region else text
        if title and compact(title) not in compact(title_text):
            issue('missing_title', f'Configured title not found: {title}', number)
        for entry in config.get('required_strings', {}).get(str(number), []):
            needle = entry if isinstance(entry, str) else entry['text']
            required_count = 1 if isinstance(entry, str) else entry.get('min_count', 1)
            count = compact(text).count(compact(needle))
            if count < required_count:
                issue('missing_required_string', f'Required {needle!r} at least {required_count} time(s), found {count}.', number)

        resource_images = page.get_images(full=True)
        unique_image_xrefs.update(item[0] for item in resource_images if item[0] > 0)
        runtime_images = page.get_image_info(xrefs=True)
        total_runtime_images += len(runtime_images)
        for font in page.get_fonts(full=True):
            xref = font[0]
            if xref in font_records:
                font_records[xref]['pages'].append(number)
                continue
            try:
                name, extension, kind, data = doc.extract_font(xref)
                embedded = bool(data)
            except Exception as exc:
                name, extension, kind, embedded = font[3], font[1], font[2], False
                issue('font_inspection_failed', str(exc), number, dict(xref=xref))
            font_records[xref] = dict(xref=xref, name=name, extension=extension, type=kind,
                                     embedded=embedded, pages=[number])
        body_union = None
        if body_boxes:
            body_union = fitz.Rect(body_boxes[0])
            for box in body_boxes[1:]:
                body_union |= box
        observations.append(dict(page=number, size_pt=[rect_page.width, rect_page.height], rotation=page.rotation,
                                 extracted_characters=len(text), text_spans=len(spans),
                                 min_font_pt=min((span['size'] for span in spans), default=None),
                                 body_text_bbox_pt=list(body_union) if body_union else None,
                                 resource_image_count=len(resource_images), runtime_image_count=len(runtime_images),
                                 vector_drawing_count=len(page.get_drawings())))

    max_images = config.get('max_raster_images')
    if max_images is not None and total_runtime_images > max_images:
        issue('raster_image_count', f'Found {total_runtime_images} runtime image appearances, configured maximum is {max_images}.')
    if config.get('require_embedded_fonts', False):
        for record in font_records.values():
            if not record['embedded']:
                issue('unembedded_font', 'Font has no extracted embedded font program.', details=record)
    if not font_records:
        issue('no_fonts', 'No PDF font resources found; native text is not established.')

    report = dict(schema_version=1, pdf=str(path.resolve()), pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  actual_page_count=len(doc), technical_pass=not issues, issues=issues, pages=observations,
                  fonts=list(font_records.values()), unique_resource_image_count=len(unique_image_xrefs),
                  runtime_image_appearance_count=total_runtime_images, config=config,
                  semantic_review='not_performed', visual_review='not_performed',
                  limitations=['Text presence and bounding boxes do not prove mathematical or translation correctness.',
                               'Text bounding boxes do not detect every clipping mask, occlusion or overlap.',
                               'Image counts do not establish vector asset provenance or native-source editability.',
                               'Font embedding is technical evidence, not confirmation of visible glyph fidelity.',
                               'This report cannot grant Native Forge book release status.'])
    doc.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True, type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else {}
        report = check_pdf(args.pdf, config)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Check failed: {exc}', file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"technical_pass={str(report['technical_pass']).lower()} pages={report['actual_page_count']} "
          f"issues={len(report['issues'])} report={args.out.resolve()}")
    return 0 if report['technical_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
