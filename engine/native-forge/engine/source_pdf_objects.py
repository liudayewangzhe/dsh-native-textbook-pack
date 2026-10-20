"""Source-copied figure objects with deterministic native-label localization.

This draft helper is independent of the shared Native Forge engine. The enclosing
engine remains responsible for source SHA256, figure classification, RAM, coverage,
and release gates. Both extraction and verification use this same source recipe.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import math
import re


FIGURE_KINDS = {"plot", "schematic", "photograph", "mixed", "qr_code"}
_SMASK = re.compile(r"^(\d+)\s+\d+\s+R$")

_SOURCE_FORM_METHOD = "source-page-form+vector-bbox-clip"
_REF = re.compile(r"(\d+)\s+\d+\s+R")
_BI_TOKEN = re.compile(rb"(?:^|\s)BI(?=\s)")


def image_occurrences(doc, page, clip=None) -> list[dict]:
    import fitz
    result = []
    clip = page.rect if clip is None else fitz.Rect(clip)
    for info in page.get_image_info(xrefs=True):
        rect = fitz.Rect(info["bbox"])
        if (rect & clip).is_empty:
            continue
        xref = info.get("xref", 0)
        if not xref:
            raise ValueError("source has an inline image without a verifiable encoded stream")
        stream = doc.xref_stream_raw(xref)
        if stream is None:
            raise ValueError("source image has no addressable encoded stream")
        _, mask = doc.xref_get_key(xref, "SMask")
        match = _SMASK.fullmatch(mask)
        mask_stream = doc.xref_stream_raw(int(match[1])) if match else None
        result.append({"bbox": list(rect), "width": info["width"], "height": info["height"],
                       "pixel_digest": info["digest"].hex(),
                       "stream_sha256": hashlib.sha256(stream).hexdigest(),
                       "smask_stream_sha256": hashlib.sha256(mask_stream).hexdigest() if mask_stream else None})
    return result


def image_counter(records) -> Counter:
    return Counter((r["width"], r["height"], r["pixel_digest"], r["stream_sha256"],
                    r["smask_stream_sha256"]) for r in records)


def _rect(values, bounds, name):
    import fitz
    if not isinstance(values, (list, tuple)) or len(values) != 4 or not all(
            isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in values):
        raise ValueError(f"{name} needs four finite coordinates")
    rect = fitz.Rect(values)
    if rect.is_empty or not bounds.contains(rect):
        raise ValueError(f"{name} must be nonempty and contained by the source region")
    return rect


def _same_text(a, b):
    return " ".join(a.split()) == " ".join(b.split())


def _resource_proof(doc, field) -> dict:
    cache, active, raw_images = {}, set(), []
    counts = {"Image": 0, "Shading": 0, "Type3": 0, "Form": 0, "BI": 0}
    def node(xref):
        if xref in cache: return cache[xref]
        if xref in active: raise ValueError("resource graph cycle cannot be certified")
        active.add(xref)
        obj = doc.xref_object(xref, compressed=True); sub = doc.xref_get_key(xref, "Subtype")[1]
        counts["Image"] += sub == "/Image"; counts["Type3"] += sub == "/Type3"; counts["Form"] += sub == "/Form"
        counts["Shading"] += "ShadingType" in doc.xref_get_keys(xref)
        norm = _REF.sub(lambda m: "<" + node(int(m[1])) + ">", obj)
        raw = doc.xref_stream_raw(xref) if doc.xref_is_stream(xref) else None
        if sub == "/Image": raw_images.append({"stream_sha256": hashlib.sha256(raw).hexdigest(), "encoded_length": len(raw)})
        if doc.xref_is_stream(xref) and sub not in ("/Image", "/Type1C", "/CIDFontType0C", "/OpenType"):
            counts["BI"] += len(_BI_TOKEN.findall(doc.xref_stream(xref)))
        digest = hashlib.sha256((norm + (hashlib.sha256(raw).hexdigest() if raw is not None else "")).encode()).hexdigest()
        active.remove(xref); cache[xref] = digest; return digest
    match = _REF.fullmatch(field.strip())
    value = node(int(match[1])) if match else hashlib.sha256(_REF.sub(lambda m: "<" + node(int(m[1])) + ">", field).encode()).hexdigest()
    return {"sha256": value, "counts": counts, "image_streams":
            sorted(raw_images, key=lambda a: (a["stream_sha256"], a["encoded_length"]))}


def _pixel_records(page, clip) -> list:
    import fitz
    return sorted([i["width"], i["height"], i["digest"].hex()] for i in page.get_image_info(hashes=True)
                  if not (fitz.Rect(i["bbox"]) & clip).is_empty)


def _find_source_form(out, page, want_sha) -> int:
    found = [xref for xref, name, _, _ in page.get_xobjects()
             if name == "fullpage" and out.xref_get_key(xref, "Subtype")[1] == "/Form"
             and hashlib.sha256(out.xref_stream(xref)).hexdigest() == want_sha]
    if len(found) != 1: raise ValueError("payload does not carry exactly one verified fullpage form")
    return found[0]


def _build_source_form(doc, page_number, source_page, clip, *, figure_kind, allow_vector):
    import fitz
    ckind, cvalue = doc.xref_get_key(source_page.xref, "Contents")
    cxrefs = [int(cvalue.split()[0])] if ckind == "xref" else [int(n) for n in _REF.findall(cvalue)]
    if ckind not in ("xref", "array") or not cxrefs:
        raise ValueError("source page has no decodable Contents stream")
    contents = b"".join(doc.xref_stream(x) for x in cxrefs); contents_sha = hashlib.sha256(contents).hexdigest()
    source_tree = _resource_proof(doc, doc.xref_get_key(source_page.xref, "Resources")[1])
    raster = source_tree["counts"]["Image"] > 0 or source_tree["counts"]["BI"] + len(_BI_TOKEN.findall(contents)) > 0
    if raster and allow_vector: raise ValueError("vector_pdf source-page-form cannot contain real Image resources or inline BI")
    if not raster and not allow_vector: raise ValueError("source-page-form figure requires vector_pdf kind or raster")
    if raster:
        expanded = fitz.Rect(clip.x0-.001, clip.y0-.001, clip.x1+.001, clip.y1+.001)
        if any(not expanded.contains(fitz.Rect(i["bbox"])) for i in source_page.get_image_info(hashes=True)
               if not (fitz.Rect(i["bbox"]) & clip).is_empty):
            raise ValueError("source bitmap crosses crop boundary; widen reviewed bbox")
    out = fitz.open()
    try:
        page = out.new_page(width=clip.width, height=clip.height)
        full_xref = page.show_pdf_page(page.rect, doc, page_number - 1, clip=clip, keep_proportion=False)
        if hashlib.sha256(out.xref_stream(full_xref)).hexdigest() != contents_sha: raise ValueError("form bytes differ from source Contents")
        payload = out.tobytes(garbage=4, deflate=False, deflate_images=False, no_new_id=True)
        path_count, native_text = len(page.get_drawings()), page.get_text()
    finally:
        out.close()
    check = fitz.open(stream=payload, filetype="pdf")
    try:
        form_xref = _find_source_form(check, check[0], contents_sha)
        if check.xref_stream(form_xref) != contents: raise ValueError("reopened form bytes differ from source Contents")
        output_tree = _resource_proof(check, check.xref_get_key(form_xref, "Resources")[1])
        pixel_source, pixel_output = _pixel_records(source_page, clip), _pixel_records(check[0], check[0].rect)
    finally:
        check.close()
    if output_tree != source_tree: raise ValueError("payload resource graph differs from source resources")
    if raster:
        if pixel_source != pixel_output: raise ValueError("source-page-form pixel occurrences differ")
        source_images, proxy_source, proxy_output = source_tree["image_streams"], 0, 0
    elif len(pixel_source) != len(pixel_output) or (pixel_source and source_tree["counts"]["Shading"] == 0):
        raise ValueError("runtime pixel proxies without shading evidence cannot be certified")
    else:
        source_images, proxy_source, proxy_output = [], len(pixel_source), len(pixel_output)
    payload_sha = hashlib.sha256(payload).hexdigest()
    proof = {"crop_method": _SOURCE_FORM_METHOD, "source_page": page_number, "bbox": list(clip), "figure_kind": figure_kind,
             "source_contents_sha256": contents_sha, "resource_tree": source_tree, "output_resource_tree": output_tree,
             "source_images": source_images, "pixel_source": pixel_source, "pixel_output": pixel_output,
             "runtime_proxy_source_count": proxy_source, "runtime_proxy_output_count": proxy_output,
             "path_count": path_count, "native_text": native_text, "payload_sha256": payload_sha}
    provenance = {"source_page": page_number, "bbox": list(clip), "figure_kind": figure_kind,
                  "crop_method": _SOURCE_FORM_METHOD, "source_images": source_images,
                  "path_count": path_count, "native_text": native_text,
                  "sha256": payload_sha, "source_form": proof}
    return payload, provenance


def build_source_pdf(doc, page_number: int, bbox, *, figure_kind: str,
                     localization=None, allow_vector=False,
                     crop_method: str = "insert-source-page+clip_to_rect+cropbox") -> tuple[bytes, dict]:
    """Build only source objects; no rendered image or user TeX enters this path.

    Localization coordinates use original page coordinates. Both source and target
    rectangles must stay inside the approved figure crop. Source text is verified
    before erasure, and only native text is erased (images=0, graphics=0).
    """
    import fitz
    if figure_kind not in FIGURE_KINDS:
        raise ValueError("source_pdf is only for reviewed plot/schematic/photograph/mixed/qr_code figures")
    if not isinstance(page_number, int) or isinstance(page_number, bool) or not 1 <= page_number <= len(doc):
        raise ValueError("physical source page outside PDF")
    source_page = doc[page_number - 1]
    if source_page.rotation:
        raise ValueError("rotated source page requires an explicit coordinate recipe")
    clip = _rect(bbox, source_page.rect, "figure bbox")
    if all(abs(x - y) < .01 for x, y in zip(clip, source_page.rect)):
        raise ValueError("whole-page source_pdf is prohibited")
    if crop_method not in (_SOURCE_FORM_METHOD, "insert-source-page+clip_to_rect+cropbox"):
        raise ValueError("unknown source object crop_method")
    if crop_method == _SOURCE_FORM_METHOD:
        if localization is not None and (not isinstance(localization, list) or localization):
            raise ValueError("source-page-form variant only accepts empty localization")
        return _build_source_form(doc, page_number, source_page, clip, figure_kind=figure_kind, allow_vector=allow_vector)
    original_images = image_occurrences(doc, source_page, clip)
    if not original_images and not allow_vector:
        raise ValueError("source_pdf requires actual source raster occurrences; use vector_pdf otherwise")
    for info in original_images:
        # PDF coordinate arithmetic is single precision; tolerate only its noise.
        expanded = fitz.Rect(clip.x0 - .001, clip.y0 - .001, clip.x1 + .001, clip.y1 + .001)
        if not expanded.contains(fitz.Rect(info["bbox"])):
            raise ValueError("source bitmap crosses crop boundary; widen reviewed bbox")
    localization = [] if localization is None else localization
    if not isinstance(localization, list):
        raise ValueError("localization must be a list")
    recipes = []
    for item in localization:
        if not isinstance(item, dict):
            raise ValueError("label localization must be an object")
        allowed = {"source_bbox", "target_bbox", "source_text", "Chinese_text", "font", "fontsize", "color", "align"}
        if set(item) - allowed:
            raise ValueError("unknown localization fields")
        src = _rect(item.get("source_bbox"), clip, "source label bbox")
        dst = _rect(item.get("target_bbox", item.get("source_bbox")), clip, "Chinese label bbox")
        original = item.get("source_text")
        chinese = item.get("Chinese_text")
        if not isinstance(original, str) or not original.strip() or not _same_text(source_page.get_textbox(src), original):
            raise ValueError("source label text does not match source rectangle")
        if not isinstance(chinese, str) or not chinese.strip() or any(ord(c) < 32 for c in chinese):
            raise ValueError("Chinese label needs native printable text")
        if item.get("font", "china-s") != "china-s":
            raise ValueError("draft native localization only permits fixed built-in china-s font")
        size = item.get("fontsize")
        if not isinstance(size, (int, float)) or isinstance(size, bool) or not math.isfinite(size) or size <= 0:
            raise ValueError("localized font size must be explicit and positive")
        color = item.get("color", [0, 0, 0])
        if not isinstance(color, (list, tuple)) or len(color) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in color):
            raise ValueError("label color must be RGB values in [0,1]")
        align = item.get("align", 0)
        if type(align) is not int or align not in (0, 1, 2):
            raise ValueError("label alignment must be left/center/right (0/1/2)")
        recipes.append((src, dst, chinese, size, color, align))
    out = fitz.open()
    try:
        # Original link destinations are reconstructed separately by the engine.
        # Figure assets carry visual source objects, without PDF action objects.
        out.insert_pdf(doc, from_page=page_number - 1, to_page=page_number - 1,
                       links=False, annots=False, widgets=False)
        out[0].clip_to_rect(clip)
        out[0].set_cropbox(clip)
        page = out[0]
        offset = fitz.Point(clip.x0, clip.y0)
        for src, _, _, _, _, _ in recipes:
            local = fitz.Rect(src.x0 - offset.x, src.y0 - offset.y, src.x1 - offset.x, src.y1 - offset.y)
            page.add_redact_annot(local, fill=False, cross_out=False)
        if recipes:
            page.apply_redactions(images=0, graphics=0, text=0)
        for _, dst, chinese, size, color, align in recipes:
            local = fitz.Rect(dst.x0 - offset.x, dst.y0 - offset.y, dst.x1 - offset.x, dst.y1 - offset.y)
            remaining = page.insert_textbox(local, chinese, fontname="china-s", fontsize=size, color=color, align=align)
            if remaining < 0:
                raise ValueError("Chinese label does not fit target bbox; revise explicit layout")
        observed_images = image_occurrences(out, page)
        if image_counter(original_images) != image_counter(observed_images):
            raise ValueError("source image encoded streams/pixel digests/occurrence counts changed")
        payload = out.tobytes(garbage=4, deflate=False, deflate_images=False, no_new_id=True)
        provenance = {"source_page": page_number, "bbox": list(clip), "figure_kind": figure_kind,
                      "crop_method": "insert-source-page+clip_to_rect+cropbox",
                      "source_images": original_images, "localization": localization,
                      "path_count": len(page.get_drawings()), "native_text": page.get_text(),
                      "sha256": hashlib.sha256(payload).hexdigest()}
        return payload, provenance
    finally:
        out.close()


def verify_source_pdf(doc, asset_bytes: bytes, entry: dict) -> dict:
    """Recreate from the immutable source, preventing digest-manifest forgery.

    The caller must first verify doc's path SHA256 equals project.source.sha256 and
    entry.source_sha256. This helper also checks the original stream occurrence list.
    """
    if entry.get("crop_method") == _SOURCE_FORM_METHOD:
        expected, proof = build_source_pdf(doc, entry["source_page"], entry["bbox"], figure_kind=entry["figure_kind"],
                                           localization=entry.get("localization"), crop_method=_SOURCE_FORM_METHOD,
                                           allow_vector=entry.get("kind") == "vector_pdf")
        if asset_bytes != expected or entry.get("sha256") != proof["sha256"]:
            raise ValueError("asset sha256 differs from deterministic source-page-form recipe")
        if entry.get("source_form") != proof["source_form"]:
            raise ValueError("declared source_form proof differs from verified source recipe")
        if entry.get("source_images") != proof["source_images"] or entry.get("path_count") != proof["path_count"] \
                or entry.get("native_text") != proof["native_text"]:
            raise ValueError("declared source images/text/paths differ from verified source recipe")
        return proof

    if entry.get("crop_method") != "insert-source-page+clip_to_rect+cropbox":
        raise ValueError("crop_method differs from approved source object recipe")
    expected, proof = build_source_pdf(doc, entry["source_page"], entry["bbox"],
                                       figure_kind=entry["figure_kind"], localization=entry.get("localization"),
                                       allow_vector=entry.get("kind") == "vector_pdf")
    if asset_bytes != expected:
        raise ValueError("asset differs from deterministic source crop/localization recipe")
    if image_counter(entry.get("source_images", [])) != image_counter(proof["source_images"]):
        raise ValueError("declared source image encoded streams/pixel digests/counts differ")
    if entry.get("sha256") != proof["sha256"]:
        raise ValueError("asset SHA256 differs from verified source recipe")
    if entry.get("path_count") != proof["path_count"] or entry.get("native_text") != proof["native_text"]:
        raise ValueError("declared native text/path evidence differs from source recipe")
    return proof

