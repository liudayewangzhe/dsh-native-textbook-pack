#!/usr/bin/env python3
"""native_forge.py -- deterministic rebuild engine for the Native Forge workflow (docs/design.md).

Commands: doctor | prepare --source --pages --project --title | asset --project --page
--bbox x0 y0 x1 y1 --name [--kind] | build | qa | release  (--project DIR).

A project directory holds project.json, content.json, assets.json, review.json,
packet/, assets/, build/, qa/, deliverable/ and a deliverable zip.  Only the stdlib and
PyMuPDF are used; the source PDF is opened read-only and never modified.  All JSON is
canonical and timestamp-free so reruns are byte-identical.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
ENGINE_SOURCE_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
RAM_MINIMUM = 1 << 30
# Optional operator override for hosts whose free-page reading sits near the default floor
# while total memory is ample.  It can only relax the floor between 512 MiB and the default
# 1 GiB, never below; heavy work still halts and no process is ever terminated.
RAM_MINIMUM_FLOOR = 512 << 20


def configured_ram_minimum(default=RAM_MINIMUM):
    raw = os.environ.get("NF_RAM_FLOOR_MIB")
    if not raw:
        return default
    try:
        value = int(str(raw).strip()) << 20
    except (TypeError, ValueError):
        return default
    return max(RAM_MINIMUM_FLOOR, min(default, value))
XELATEX_TIMEOUT = 1800
XELATEX_FLAGS = ("--no-shell-escape", "--interaction=nonstopmode", "--halt-on-error")
# 可选兜底：仅当 PATH 上没有 xelatex 且显式设置了 NF_XELATEX_LEGACY 时才使用。
# 不内置任何作者机器上的绝对路径，保证移植后行为可预期。
_XELATEX_LEGACY_ENV = os.environ.get("NF_XELATEX_LEGACY", "").strip()
XELATEX_LEGACY = Path(_XELATEX_LEGACY_ENV) if _XELATEX_LEGACY_ENV else None
TEMPLATE_FILES = ("elegantbook.cls", "nativeforge.sty")
BLOCK_KINDS = ("chapter", "section", "subsection", "paragraph", "equation", "table",
               "figure", "figure_native", "code", "console", "note")
FIGURE_LAYOUTS = ("float", "inline")
EXCLUSION_CATEGORIES = ("header_footer", "out_of_scope", "extraction_artifact")
ASSET_KINDS = ("vector_pdf", "native_pdf", "source_raster", "source_pdf", "page_raster")
ASSET_CROP_KINDS = ("vector_pdf", "source_raster", "source_pdf", "page_raster")
SOURCE_FORM_CROP_METHOD = "source-page-form+vector-bbox-clip"
RASTER_SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpeg"), (b"II*\x00", "tiff"),
                     (b"MM\x00*", "tiff"), (b"BM", "bmp"), (b"GIF8", "gif"),
                     (b"\x00\x00\x00\x0cjP", "jpx"))
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:_-]*$")
WIDTH_RE = re.compile(r"^\d+(?:\.\d+)?\\(?:linewidth|textwidth|columnwidth)$")
# Inline resource boxes (figure.layout "inline") render at a fixed compact millimetre
# width within (0, INLINE_WIDTH_MAX_MM]; the box reserves capped vertical room so the
# source anchors and graphic stay together.  The float width rule is untouched.
INLINE_WIDTH_RE = re.compile(r"^\d+(?:\.\d+)?mm$")
INLINE_WIDTH_MAX_MM = 45.0
INLINE_TEXT_HEIGHT_MM = 247.0
INLINE_NEED_CAP_MM = round(INLINE_TEXT_HEIGHT_MM / 3)
INLINE_CAPTION_MM = 9.0
INLINE_PAD_MM = 4.0
BANNED_MACROS = re.compile(
    r"""\\includegraphics|\\write|\\read
      | \\(?:input|include|includeonly|openout|closeout|openin|newread|immediate|special|shell
          |directlua|latelua|luadirect|luaexec|catcode|everyjob|usepackage|RequirePackage
          |documentclass|graphicspath|DeclareGraphicsRule|pgfimage|pdfximage|XeTeXpicfile
          |XeTeXpdffile|NFfigure|csname|scantokens)\b""", re.VERBOSE)
TABLE_ENVIRONMENT = re.compile(r"\\begin\{(?:tabular|longtable|tabularx|array)\*?\}")
DISPLAY_ENVIRONMENT = re.compile(
    r"\\begin\{(?:equation|align|gather|multline|eqnarray|displaymath|math)\*?\}|(?<!\\)\\\[|\$\$")
EQUATION_TAG = re.compile(r"\\tag\{([^{}]*)\}")
NOTE_MARK = re.compile(r"\\nfnotemark\{([A-Za-z0-9][A-Za-z0-9.:_-]*)\}\{([A-Za-z0-9][A-Za-z0-9.:_-]*)\}")
LAYOUT_DEFAULTS = {"paper_width_mm": 210, "paper_height_mm": 297,
                   "text_width_mm": 164, "inner_mm": 23, "outer_mm": 23,
                   "top_mm": 23, "bottom_mm": 23, "margin_note_width_mm": 0,
                   "margin_note_sep_mm": 0, "note_font_pt": 9, "note_leading_pt": 13,
                   "notes": "footnote", "chapter_open": "any"}
LOG_PATTERNS = {
    "fatal": (re.compile(r"^!\s"), re.compile(r"Fatal error occurred")),
    "missing_character": (re.compile(r"Missing character:"),),
    "overfull": (re.compile(r"Overfull \\[hv]box"),),
    "undefined": (re.compile(r"(?:Reference|Citation) `[^']*' .*undefined"),
                  re.compile(r"There were undefined (?:references|citations)")),
    "rerun": (re.compile(r"Rerun to get"), re.compile(r"Rerun LaTeX"), re.compile(r"Please rerun")),
    "margin": (re.compile(r"lost some margin notes"), re.compile(r"NFNOTE-OVERSIZE"),
               re.compile(r"NF-MARGIN-QUEUE-NOT-EMPTY")),
}


class EngineError(Exception):
    """Fatal, user-facing contract violation."""


# ------------------------------------------------------------------------- utilities

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sha256(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise EngineError(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise EngineError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(obj), encoding="utf-8", newline="\n")


def write_text(path, text) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def round3(values):
    return [round(float(v), 3) for v in values]


def hash_or_missing(path):
    path = Path(path)
    return sha256_file(path) if path.is_file() else None


def visible_bbox(bbox) -> bool:
    return (bbox[2] - bbox[0]) > 0.01 and (bbox[3] - bbox[1]) > 0.01


def sniff_raster(path):
    head = Path(path).read_bytes()[:16]
    for signature, kind in RASTER_SIGNATURES:
        if head.startswith(signature):
            return kind
    return None


def _scan_forbidden(node, where, problems) -> None:
    if isinstance(node, str):
        hit = BANNED_MACROS.search(node)
        if hit:
            problems.append(f"{where}: forbidden macro {hit.group(0)!r}; content may not include "
                            "graphics or touch files (figure macros are engine-only)")
    elif isinstance(node, dict):
        for key, value in node.items():
            # Literal code data is emitted only through engine-owned VerbatimInput.
            if key == "text" and node.get("kind") in ("code", "console"):
                continue
            _scan_forbidden(value, f"{where}.{key}", problems)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _scan_forbidden(value, f"{where}[{index}]", problems)


# ---------------------------------------------------------------------- environment

_FITZ = None


def load_fitz():
    global _FITZ
    if _FITZ is None:
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise EngineError("PyMuPDF (fitz) is required for this command") from exc
        _FITZ = fitz
    return _FITZ


def find_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_xelatex():
    found = shutil.which("xelatex")
    if found:
        return [found]
    if XELATEX_LEGACY and XELATEX_LEGACY.is_file():
        return [str(XELATEX_LEGACY)]
    return None


def available_physical_memory():
    """Available physical RAM in bytes, or None when undeterminable."""
    if os.name == "nt":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except OSError:
            return None
        return None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    try:
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError):
        return None


def ensure_ram(reader=None, minimum=None):
    """Halt heavy work below `minimum` free RAM.  Never terminates any process."""
    minimum = configured_ram_minimum() if minimum is None else minimum
    available = (reader or available_physical_memory)()
    if available is None:
        raise EngineError("cannot determine available physical RAM; refusing heavy work")
    if available < minimum:
        raise EngineError(f"available physical RAM {available >> 20} MiB is below the required "
                          f"{minimum >> 20} MiB; halting")
    return available


# -------------------------------------------------------------------------- project

def parse_pages(spec, page_count=None):
    pages = set()
    for part in str(spec).split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part) or re.fullmatch(r"(\d+)", part)
        if not match:
            raise EngineError(f"invalid page range {spec!r}")
        start, end = (int(match.group(1)), int(match.group(1))) if match.lastindex == 1 \
            else (int(match.group(1)), int(match.group(2)))
        if start < 1 or end < start:
            raise EngineError(f"invalid page range {part!r}")
        if page_count is not None and end > page_count:
            raise EngineError(f"page {end} exceeds source page count {page_count}")
        pages.update(range(start, end + 1))
    return sorted(pages)


_LATEX_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                  "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
                  "^": r"\textasciicircum{}"}


def latex_escape(text) -> str:
    return "".join(_LATEX_ESCAPES.get(ch, ch) for ch in str(text))


def resolve_templates_dir(project=None, override=None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    recorded = (project or {}).get("templates") or {}
    parents = {Path(v["path"]).parent for v in recorded.values()
               if isinstance(v, dict) and v.get("path")}
    return parents.pop() if len(parents) == 1 else find_repo_root() / "templates"


def template_hashes(templates_dir) -> dict:
    templates_dir = Path(templates_dir)
    hashes = {}
    for name in TEMPLATE_FILES:
        path = templates_dir / name
        if not path.is_file():
            raise EngineError(f"template missing: {path}")
        hashes[name] = {"path": str(path.resolve()), "sha256": sha256_file(path)}
    return hashes


def load_project(project_dir) -> dict:
    path = Path(project_dir) / "project.json"
    if not path.is_file():
        raise EngineError(f"no project.json in {Path(project_dir)}; run prepare first")
    project = read_json(path)
    if project.get("schema_version") != SCHEMA_VERSION:
        raise EngineError(f"unsupported project schema_version {project.get('schema_version')!r}")
    missing = [k for k in ("title", "source", "pages", "templates") if k not in project]
    if missing:
        raise EngineError(f"project.json is missing {missing}")
    validate_layout(project)
    return project


def validate_layout(project) -> dict:
    """Resolve optional, explicit page geometry without changing legacy projects."""
    supplied = project.get("layout", {})
    if not isinstance(supplied, dict):
        raise EngineError("project.layout must be an object")
    unknown = set(supplied) - set(LAYOUT_DEFAULTS)
    if unknown:
        raise EngineError(f"project.layout has unknown fields: {sorted(unknown)}")
    layout = {**LAYOUT_DEFAULTS, **supplied}
    for key, value in layout.items():
        if key in ("notes", "chapter_open"):
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise EngineError(f"project.layout.{key} must be a finite number")
        if value < 0 or (value == 0 and key not in ("margin_note_width_mm", "margin_note_sep_mm")):
            raise EngineError(f"project.layout.{key} must be positive (only unused note dimensions may be zero)")
    if layout["notes"] not in ("footnote", "outer"):
        raise EngineError("project.layout.notes must be footnote or outer")
    if layout["chapter_open"] not in ("any", "right"):
        raise EngineError("project.layout.chapter_open must be any or right")
    if layout["notes"] == "outer" and min(layout["margin_note_width_mm"], layout["margin_note_sep_mm"]) <= 0:
        raise EngineError("outer notes require positive margin_note_width_mm and margin_note_sep_mm")
    if layout["notes"] == "footnote" and (layout["margin_note_width_mm"] or layout["margin_note_sep_mm"]):
        raise EngineError("nonzero note dimensions require project.layout.notes=outer")
    occupied = sum(layout[k] for k in ("inner_mm", "text_width_mm", "margin_note_sep_mm", "margin_note_width_mm", "outer_mm"))
    if abs(occupied - layout["paper_width_mm"]) > 0.01:
        raise EngineError(f"project.layout horizontal dimensions sum to {occupied:g}mm, paper is {layout['paper_width_mm']:g}mm")
    if layout["top_mm"] + layout["bottom_mm"] >= layout["paper_height_mm"]:
        raise EngineError("project.layout top and bottom margins leave no text height")
    if layout["note_leading_pt"] < layout["note_font_pt"]:
        raise EngineError("project.layout note_leading_pt must be at least note_font_pt")
    return layout


def validate_preamble(project) -> list:
    """Project-level preamble additions, applied after the layout settings.

    The engine supplies a book-class preamble and a declared layout; some books still need
    document-wide typography that is neither content nor geometry (numbering style, heading
    shapes, caption fonts).  Keeping one reviewed preamble block per project stops that from
    being re-invented or smuggled into individual blocks.  Structural commands that could
    escape the generated document are refused.
    """
    if "preamble" not in project:
        return []
    value = project["preamble"]
    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        raise EngineError("project.preamble must be a list of TeX lines")
    forbidden = (r"\begin{document}", r"\end{document}", r"\input", r"\include",
                 r"\write", r"\openout", r"\read", r"\catcode", r"\usepackage{geometry}")
    for line in value:
        if "\n" in line or "\r" in line:
            raise EngineError("project.preamble entries must be single lines")
        if any(token in line for token in forbidden):
            raise EngineError(f"project.preamble entry uses a structural command: {line.strip()!r}")
    return list(value)


def render_layout(project) -> list:
    if "layout" not in project:
        return []
    layout = validate_layout(project)
    outer = layout["outer_mm"] + layout["margin_note_width_mm"] + layout["margin_note_sep_mm"]
    dimensions = {"paperwidth": layout["paper_width_mm"], "paperheight": layout["paper_height_mm"],
                  "inner": layout["inner_mm"], "outer": outer, "top": layout["top_mm"],
                  "bottom": layout["bottom_mm"], "marginparwidth": layout["margin_note_width_mm"],
                  "marginparsep": layout["margin_note_sep_mm"]}
    options = ",".join(f"{key}={value:g}mm" for key, value in dimensions.items())
    if layout["notes"] == "outer":
        options += ",twoside"
    lines = [rf"\renewcommand{{\NFGeometrySettings}}{{{options},headsep=5mm,footskip=10mm}}",
             rf"\renewcommand{{\NFNoteFontSize}}{{{layout['note_font_pt']:g}}}",
             rf"\renewcommand{{\NFNoteLeading}}{{{layout['note_leading_pt']:g}}}",
             r"\expandafter\geometry\expandafter{\NFGeometrySettings}",
             r"\setlength{\headwidth}{\textwidth}",
             r"\makeatletter\@openright" + ("false" if layout["chapter_open"] == "any" else "true") + r"\makeatother"]
    if layout["notes"] == "outer":
        lines += [r"\fancyhead{}", r"\fancyhead[EL]{\color{structurecolor}\cnormal\leftmark}",
                  r"\fancyhead[OR]{\color{structurecolor}\cnormal\rightmark}"]
    return lines


def check_template_bindings(project, templates) -> None:
    recorded = project.get("templates") or {}
    changed = sorted(n for n in TEMPLATE_FILES
                     if recorded.get(n, {}).get("sha256") != templates[n]["sha256"])
    if changed:
        raise EngineError(f"template(s) changed since prepare: {', '.join(changed)}; re-run prepare")


# ---------------------------------------------------------------- packet & prepare

def extract_page(doc, page_no: int) -> dict:
    page = doc[page_no - 1]
    raw = page.get_text("dict", sort=False)
    blocks = []
    for index, block in enumerate(b for b in raw.get("blocks", []) if b.get("type") == 0):
        lines = ["".join(span.get("text", "") for span in line.get("spans", []))
                 for line in block.get("lines", [])]
        blocks.append({"id": f"p{page_no:04d}-b{index:04d}", "page": page_no,
                       "bbox": round3(block.get("bbox", (0, 0, 0, 0))), "text": "\n".join(lines)})
    images = []
    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox", (0, 0, 0, 0))
        images.append({"number": info.get("number"), "bbox": round3(bbox), "width": info.get("width"),
                       "height": info.get("height"), "xref": info.get("xref", 0),
                       "visible": visible_bbox(bbox)})
    fonts = sorted({(f[3], f[2], f[1]) for f in page.get_fonts(full=True)})
    data = {"page": page_no, "width": round3([page.rect.width])[0],
            "height": round3([page.rect.height])[0], "mediabox": round3(tuple(page.mediabox)),
            "rotation": page.rotation, "blocks": blocks, "images": images,
            "raster_occurrences": len(images),
            "visible_raster_occurrences": sum(1 for i in images if i["visible"]),
            "vector_path_count": len(page.get_drawings()),
            "fonts": [{"basefont": b, "type": t, "ext": e} for b, t, e in fonts]}
    data["page_sha256"] = stable_sha256(data)
    return data


def packet_cache_valid(packet_dir, source_sha256: str, pages: list) -> bool:
    index_path = Path(packet_dir) / "packet.json"
    if not index_path.is_file():
        return False
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except ValueError:
        return False
    if index.get("source_sha256") != source_sha256:
        return False
    recorded = index.get("pages") or {}
    if sorted(int(k) for k in recorded) != list(pages):
        return False
    for page_no in pages:
        entry = recorded.get(str(page_no)) or {}
        json_path = Path(packet_dir) / "pages" / f"p{page_no:04d}.json"
        png_path = Path(packet_dir) / "pages" / f"p{page_no:04d}.png"
        if not json_path.is_file() or sha256_file(json_path) != entry.get("json_sha256"):
            return False
        if not png_path.is_file() or sha256_file(png_path) != entry.get("png_sha256"):
            return False
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except ValueError:
            return False
        if data.pop("page_sha256", None) != stable_sha256(data):
            return False
    return True


def prepare(source, pages_spec, project_dir, title, templates_dir=None) -> dict:
    ensure_ram()
    fitz = load_fitz()
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise EngineError(f"source PDF not found: {source}")
    if not str(title).strip():
        raise EngineError("title must be a non-empty string")
    project_dir = Path(project_dir).expanduser().resolve()
    templates = template_hashes(resolve_templates_dir(None, templates_dir))
    source_sha = sha256_file(source)
    previous = read_json(project_dir / "project.json") if (project_dir / "project.json").is_file() else None
    doc = fitz.open(source)
    try:
        pages = parse_pages(pages_spec, doc.page_count)
        packet_dir = project_dir / "packet"
        cached = bool(previous and previous.get("source", {}).get("sha256") == source_sha
                      and previous.get("pages") == pages
                      and packet_cache_valid(packet_dir, source_sha, pages))
        if not cached:
            pages_dir = packet_dir / "pages"
            pages_dir.mkdir(parents=True, exist_ok=True)
            index = {"schema_version": SCHEMA_VERSION, "source_sha256": source_sha, "pages": {}}
            for page_no in pages:
                ensure_ram()
                json_path = pages_dir / f"p{page_no:04d}.json"
                png_path = pages_dir / f"p{page_no:04d}.png"
                write_json(json_path, extract_page(doc, page_no))
                doc[page_no - 1].get_pixmap(dpi=120).save(str(png_path))
                index["pages"][str(page_no)] = {"json_sha256": sha256_file(json_path),
                                                "png_sha256": sha256_file(png_path)}
            write_json(packet_dir / "packet.json", index)
    finally:
        doc.close()
    if sha256_file(source) != source_sha:
        raise EngineError("source PDF changed while preparing; refusing to continue")
    # Preparing never certifies an existing build or its human review, but it must not
    # discard hand-authored project configuration such as the declared layout.
    status = "draft"
    recorded = {"schema_version": SCHEMA_VERSION, "title": str(title),
                "source": {"path": str(source), "sha256": source_sha}, "pages": pages,
                "templates": templates, "status": status}
    for key in ("layout", "preamble"):
        if previous and key in previous:
            recorded[key] = previous[key]
    write_json(project_dir / "project.json", recorded)
    scaffold = "exists"
    if not (project_dir / "content.json").is_file():
        write_json(project_dir / "content.json",
                   {"title": str(title), "blocks": [], "exclusions": [], "unresolved": [],
                    "expectations": {"equation_tags": [], "table_count": 0, "figure_count": 0,
                                     "required_strings": []}})
        scaffold = "created"
    if not (project_dir / "assets.json").is_file():
        write_json(project_dir / "assets.json", {})
    return {"command": "prepare", "project": str(project_dir), "source": str(source),
            "source_sha256": source_sha, "pages": pages, "cached": cached, "content": scaffold}


def load_packet(project_dir, project) -> dict:
    blocks = {}
    inventory_path = Path(project_dir) / "source_inventory.json"
    inventory = read_json(inventory_path) if inventory_path.is_file() else None
    if inventory is not None:
        if not isinstance(inventory, dict) or inventory.get("schema_version") != SCHEMA_VERSION \
                or inventory.get("source_sha256") != project["source"]["sha256"] \
                or not isinstance(inventory.get("pages"), dict):
            raise EngineError("source_inventory.json must have schema_version=1, current source_sha256 and pages object")
    for page_no in project["pages"]:
        path = Path(project_dir) / "packet" / "pages" / f"p{page_no:04d}.json"
        if not path.is_file():
            raise EngineError(f"packet page missing: {path}; re-run prepare")
        data = read_json(path)
        if data.pop("page_sha256", None) != stable_sha256(data):
            raise EngineError(f"packet page corrupt: {path}; re-run prepare")
        if data.get("page") != page_no:
            raise EngineError(f"packet page number does not match {path}")
        for block in data.get("blocks", []):
            if block["id"] in blocks:
                raise EngineError(f"duplicate packet block id {block['id']}")
            blocks[block["id"]] = {"page": data["page"], "text": block.get("text", "")}
        manual = inventory["pages"].get(str(page_no)) if inventory else None
        if not data.get("blocks") and manual is None:
            raise EngineError(f"source page {page_no} has zero text evidence: write hash-bound "
                              "source_inventory.json with manually read objects or an explicitly checked blank-page reason")
        if manual is None:
            continue
        if not isinstance(manual, dict):
            raise EngineError(f"source_inventory page {page_no} must be an object")
        objects = manual.get("objects", [])
        if manual.get("blank") is True:
            if data.get("blocks") or objects or manual.get("checked") is not True \
                    or not isinstance(manual.get("reason"), str) or not manual["reason"].strip():
                raise EngineError(f"source_inventory page {page_no}: blank page needs checked:true, reason and no objects/text")
            continue
        if not isinstance(objects, list) or not objects:
            raise EngineError(f"source_inventory page {page_no} needs nonempty manually read objects")
        for obj in objects:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), str) or not obj["id"] \
                    or obj.get("page") != page_no or obj.get("kind") not in \
                    ("paragraph", "equation", "table", "figure", "heading", "header_footer") \
                    or not isinstance(obj.get("text"), str) or not obj["text"].strip():
                raise EngineError(f"source_inventory page {page_no}: every object needs id/page/kind/text")
            bbox = obj.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4 \
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in bbox) \
                    or not (0 <= bbox[0] < bbox[2] <= data["width"] and 0 <= bbox[1] < bbox[3] <= data["height"]):
                raise EngineError(f"source_inventory object {obj['id']}: bbox must stay inside source page {page_no}")
            if obj["id"] in blocks:
                raise EngineError(f"source_inventory duplicate evidence id {obj['id']}")
            blocks[obj["id"]] = {"page": page_no, "text": obj["text"], "kind": obj["kind"], "bbox": bbox,
                                 "origin": "agent_manual_inventory"}
    return blocks


# ------------------------------------------------------------------------- assets

def load_assets(project_dir) -> dict:
    path = Path(project_dir) / "assets.json"
    if not path.is_file():
        return {}
    assets = read_json(path)
    if not isinstance(assets, dict):
        raise EngineError("assets.json must be a JSON object mapping asset id -> entry")
    return assets


def inspect_native_pdf(path, where, fitz) -> list:
    problems = []
    try:
        doc = fitz.open(path)
    except Exception as exc:  # pragma: no cover - defensive
        return [f"{where}: cannot open {path}: {exc}"]
    try:
        if doc.page_count == 0:
            return [f"{where}: {Path(path).name} has no pages"]
        for page in doc:
            rasters = [i for i in page.get_image_info(xrefs=True) if visible_bbox(i["bbox"])]
            if rasters:
                problems.append(f"{where}: page {page.number + 1} of {Path(path).name} contains "
                                f"{len(rasters)} visible raster occurrence(s); declare source_raster")
            if not page.get_drawings() and not page.get_text().strip():
                problems.append(f"{where}: page {page.number + 1} of {Path(path).name} has neither "
                                "vector paths nor text")
    finally:
        doc.close()
    return problems


def _verified_vector_source_form(asset_id, target, proof) -> tuple[list, dict]:
    """Certify a byte-verified source-page-form vector asset against its actual payload.

    The helper rebuild already proves the candidate bytes; this pass re-scans the payload
    so the false raster verdict of runtime shading proxies is bypassed only for a form
    with zero real Image resources, zero actual inline-image tokens, no uncertified Type3
    font content, native shading evidence, and proxy counts matching its pixel rows.
    """
    where = f"assets[{asset_id}]"
    problems = []
    module = native_shading_qa_helper()
    if module is None:
        return [f"{where}: native_shading_qa.py is required to certify source-page-form assets"], {}
    if proof.get("source_images"):
        problems.append(f"{where}: source-page-form holds source images; raster forms require kind source_pdf")
    source_counts = (proof.get("resource_tree") or {}).get("counts") or {}
    output_counts = (proof.get("output_resource_tree") or {}).get("counts") or {}
    for label, counts in (("source", source_counts), ("output", output_counts)):
        for key in ("Image", "BI"):
            if counts.get(key) != 0:
                problems.append(f"{where}: verified {label} resource graph holds "
                                f"{counts.get(key)} {key} object(s)")
    shading = source_counts.get("Shading")
    if not (type(shading) is int and shading > 0 and output_counts.get("Shading") == shading):
        problems.append(f"{where}: verified source-page-form lacks matching native shading evidence")
    proxy_source = proof.get("runtime_proxy_source_count")
    proxy_output = proof.get("runtime_proxy_output_count")
    if not (type(proxy_source) is int and type(proxy_output) is int
            and proxy_source > 0 and proxy_output > 0):
        problems.append(f"{where}: runtime shading proxy counts must be positive")
    elif not (len(proof.get("pixel_source") or []) == proxy_source
              and len(proof.get("pixel_output") or []) == proxy_output):
        problems.append(f"{where}: runtime proxy counts differ from their pixel occurrence rows")
    require_type3 = bool(source_counts.get("Type3") or output_counts.get("Type3"))
    ok, scan_problems, evidence = module.certify_payload(target.read_bytes(), proof,
                                                         require_type3=require_type3)
    problems += [f"{where}: {problem}" for problem in scan_problems]
    return problems, (evidence if ok and not problems else {})


def validate_assets(project_dir, assets, fitz=None) -> list:
    problems = []
    _VERIFIED_SOURCE_FORMS.clear()
    project_dir = Path(project_dir)
    project = load_project(project_dir)
    for asset_id in sorted(assets):
        where, entry = f"assets[{asset_id}]", assets[asset_id]
        if not isinstance(asset_id, str) or not asset_id:
            problems.append("asset ids must be non-empty strings")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{where}: must be an object")
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            problems.append(f"{where}: path must be a relative path inside the project")
            continue
        target = project_dir / rel
        if not target.resolve().is_relative_to(project_dir.resolve()):
            problems.append(f"{where}: asset path resolves outside the project")
            continue
        if not target.is_file():
            problems.append(f"{where}: file missing: {rel}")
            continue
        if entry.get("sha256") != sha256_file(target):
            problems.append(f"{where}: sha256 does not match {rel}")
        if entry.get("kind") not in ASSET_KINDS:
            problems.append(f"{where}: kind {entry.get('kind')!r} not one of {ASSET_KINDS}")
            continue
        if entry.get("role") != "figure":
            problems.append(f"{where}: role must be 'figure'")
        bbox = entry.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox)
                and bbox[0] < bbox[2] and bbox[1] < bbox[3]):
            problems.append(f"{where}: bbox must be [x0, y0, x1, y1] with x0<x1 and y0<y1")
        if not (isinstance(entry.get("source_page"), int)
                and not isinstance(entry.get("source_page"), bool) and entry["source_page"] >= 1):
            problems.append(f"{where}: source_page must be a positive integer")
        elif entry["source_page"] not in project["pages"]:
            problems.append(f"{where}: source_page is outside the selected project pages")
        if not (isinstance(entry.get("rationale"), str) and entry["rationale"].strip()):
            problems.append(f"{where}: rationale must be a non-empty string")
        if entry.get("kind") in ("vector_pdf", "native_pdf"):
            if target.suffix.lower() != ".pdf":
                problems.append(f"{where}: kind {entry['kind']} requires a .pdf asset")
            # Source-page-form vector assets are byte-verified against the immutable
            # source further below; their runtime shading proxies are not raster verdicts.
            elif fitz is not None and not (entry.get("kind") == "vector_pdf"
                                           and entry.get("crop_method") == SOURCE_FORM_CROP_METHOD):
                problems += inspect_native_pdf(target, where, fitz)
        elif entry.get("kind") == "source_raster" and sniff_raster(target) is None:
            problems.append(f"{where}: {rel} is not a recognised raster image")
        elif entry.get("kind") == "source_pdf" and target.suffix.lower() != ".pdf":
            problems.append(f"{where}: source_pdf requires a PDF asset")
        redraw = entry.get("redraw")
        if redraw is not None:
            if not isinstance(redraw, dict):
                problems.append(f"{where}: redraw provenance must be an object")
                continue
            for path_key, hash_key in (("spec_path", "spec_sha256"), ("tex_path", "tex_sha256")):
                input_path = redraw.get(path_key)
                if not isinstance(input_path, str) or not input_path or Path(input_path).is_absolute() \
                        or ".." in Path(input_path).parts:
                    problems.append(f"{where}: redraw.{path_key} must stay inside the project")
                elif hash_or_missing(project_dir / input_path) != redraw.get(hash_key):
                    problems.append(f"{where}: redraw.{hash_key} does not match its current input")
            if redraw.get("source_sha256") != project["source"]["sha256"]:
                problems.append(f"{where}: redraw source hash differs from the project source")
            if redraw.get("engine_sha256") != hash_or_missing(Path(__file__).with_name("redraw.py")):
                problems.append(f"{where}: redraw engine hash changed; regenerate this asset")
    source_crops = {k: e for k, e in assets.items() if isinstance(e, dict)
                    and (e.get("kind") == "source_pdf" or e.get("source_pdf_recipe") is True
                         or e.get("crop_method") == SOURCE_FORM_CROP_METHOD)}
    if source_crops:
        source_path = Path(project["source"]["path"])
        if not source_path.is_file() or sha256_file(source_path) != project["source"]["sha256"]:
            problems.append("source_pdf assets require the unchanged original source PDF")
        elif fitz is None:
            problems.append("source_pdf verification requires PyMuPDF")
        else:
            helper = source_pdf_helper()
            with fitz.open(source_path) as source_doc:
                for asset_id, entry in source_crops.items():
                    target = project_dir / entry.get("path", "")
                    if not target.resolve().is_relative_to(project_dir.resolve()) or not target.is_file():
                        continue
                    if entry.get("source_sha256") != project["source"]["sha256"]:
                        problems.append(f"assets[{asset_id}]: source_pdf source hash differs")
                        continue
                    try:
                        ensure_ram()
                        proof = helper.verify_source_pdf(source_doc, target.read_bytes(), entry)
                    except (ValueError, KeyError, TypeError) as exc:
                        problems.append(f"assets[{asset_id}]: {exc}")
                        continue
                    if proof.get("crop_method") != SOURCE_FORM_CROP_METHOD:
                        continue
                    proof = proof.get("source_form")
                    if not isinstance(proof, dict):
                        problems.append(f"assets[{asset_id}]: verified source-page-form proof is missing")
                        continue
                    if entry.get("kind") == "source_pdf":
                        _VERIFIED_SOURCE_FORMS[asset_id] = {"kind": "source_pdf", "proof": proof}
                    elif entry.get("kind") == "vector_pdf":
                        vector_problems, evidence = _verified_vector_source_form(asset_id, target, proof)
                        problems += vector_problems
                        if not vector_problems:
                            _VERIFIED_SOURCE_FORMS[asset_id] = {"kind": "vector_pdf", "proof": proof,
                                                                "evidence": evidence}
                    else:
                        problems.append(f"assets[{asset_id}]: the source-page-form method needs kind "
                                        "vector_pdf (no source bitmaps) or source_pdf (original bitmaps kept)")
    return problems


def source_pdf_helper():
    import importlib.util
    path = Path(__file__).with_name("source_pdf_objects.py")
    spec = importlib.util.spec_from_file_location("native_forge_source_pdf", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_VERIFIED_SOURCE_FORMS: dict[str, dict] = {}


def native_shading_qa_helper():
    import importlib.util
    path = Path(__file__).with_name("native_shading_qa.py")
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("native_forge_shading_qa", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verified_source_form(asset_id):
    record = _VERIFIED_SOURCE_FORMS.get(asset_id)
    if not record:
        raise EngineError(f"assets[{asset_id}]: no verified source-page-form proof is available; "
                          "byte verification against the immutable source must succeed first")
    return record


def clip_page(page, rect, fitz) -> str:
    """Remove everything outside `rect`, preferring true content clipping over redaction."""
    if hasattr(page, "clip_to_rect"):
        page.clip_to_rect(rect)
        page.set_cropbox(rect)
        return "clip_to_rect+cropbox"
    raise EngineError("PyMuPDF Page.clip_to_rect is required: cropbox alone does not remove outside content")


def extract_raster(doc, rasters, clip, assets_dir, name, page, fitz) -> dict:
    if not rasters:
        raise EngineError("no raster occurrence inside bbox; use the default vector crop")
    if len(rasters) > 1:
        raise EngineError(f"{len(rasters)} raster occurrences inside bbox; narrow the bbox")
    info = rasters[0]
    image_rect = fitz.Rect(info["bbox"])
    if (image_rect & clip).get_area() < image_rect.get_area() - 1.0:
        raise EngineError("raster occurrence extends beyond bbox; widen the bbox to include it whole")
    xref = int(info.get("xref") or 0)
    if xref <= 0:
        raise EngineError("raster occurrence is an inline image without an addressable stream; "
                          "its original bitmap cannot be preserved")
    extracted = doc.extract_image(xref)
    ext = extracted.get("ext") or "bin"
    target = assets_dir / f"{name}.{ext}"
    if target.exists():
        raise EngineError(f"{target.name} already exists; refusing to overwrite")
    target.write_bytes(extracted["image"])
    if sniff_raster(target) is None:
        target.unlink(missing_ok=True)
        raise EngineError(f"extracted data for {name!r} is not a recognised raster image")
    return {"path": f"assets/{target.name}", "kind": "source_raster", "role": "figure",
            "source_page": page, "bbox": round3(info["bbox"]),
            "rationale": f"original {ext} raster occurrence of source page {page}",
            "sha256": sha256_file(target),
            "image": {"width": extracted.get("width"), "height": extracted.get("height"),
                      "colorspace": extracted.get("colorspace"), "bpc": extracted.get("bpc")}}


def render_page_raster(doc, clip, assets_dir, name, page, figure_kind, fitz, dpi=300) -> dict:
    """Keep a figure as a bitmap by rendering the source page region as it actually appears.

    Some source figures are stored as raw image streams that the page composites through a
    soft mask, a transparency group or a flipped image matrix, so ``extract_image`` returns
    bytes that do not match the printed appearance (for example a black plate carrying white
    line art).  Rendering the page region preserves the reviewer-visible result.
    """
    target = assets_dir / f"{name}.png"
    if target.exists():
        raise EngineError(f"{target.name} already exists; refusing to overwrite")
    pix = doc[page - 1].get_pixmap(dpi=dpi, clip=clip, alpha=False)
    pix.save(str(target))
    if sniff_raster(target) is None:
        target.unlink(missing_ok=True)
        raise EngineError(f"rendered region for {name!r} is not a recognised raster image")
    return {"path": f"assets/{target.name}", "kind": "page_raster", "role": "figure",
            "source_page": page, "bbox": round3(tuple(clip)),
            "rationale": f"source page {page} region rendered at {dpi} dpi as printed "
                         "(composited soft mask / transparency group / flipped matrix)",
            "sha256": sha256_file(target),
            "render_dpi": dpi, "figure_kind": figure_kind,
            "image": {"width": pix.width, "height": pix.height,
                      "colorspace": "DeviceRGB", "bpc": 8}}


def asset(project_dir, page, bbox, name, kind="vector_pdf", figure_kind="mixed", localization=None) -> dict:
    ensure_ram()
    fitz = load_fitz()
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir)
    if not NAME_RE.match(name or ""):
        raise EngineError(f"invalid asset name {name!r}; use letters, digits, '.', '-', '_'")
    if kind not in ASSET_CROP_KINDS:
        raise EngineError(f"--kind must be one of {ASSET_CROP_KINDS}; native_pdf assets are produced "
                          "outside the engine and registered in assets.json by hand")
    if page not in project["pages"]:
        raise EngineError(f"page {page} is not among the prepared pages {project['pages']}")
    x0, y0, x1, y1 = (float(v) for v in bbox)
    if not all(v == v and v not in (float("inf"), float("-inf")) for v in (x0, y0, x1, y1)):
        raise EngineError("bbox values must be finite")
    if not (x0 < x1 and y0 < y1):
        raise EngineError("bbox must satisfy x0 < x1 and y0 < y1")
    source = Path(project["source"]["path"])
    if not source.is_file() or sha256_file(source) != project["source"]["sha256"]:
        raise EngineError("source PDF changed since prepare; re-run prepare")
    assets = load_assets(project_dir)
    if name in assets:
        raise EngineError(f"asset id {name!r} already declared in assets.json; refusing to overwrite")
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(source)
    try:
        clip = fitz.Rect(x0, y0, x1, y1) & doc[page - 1].rect
        if clip.is_empty or clip.is_infinite:
            raise EngineError("bbox does not intersect the source page")
        rasters = [info for info in doc[page - 1].get_image_info(xrefs=True)
                   if visible_bbox(info["bbox"]) and not (fitz.Rect(info["bbox"]) & clip).is_empty]
        if kind == "source_pdf":
            try:
                payload, entry = source_pdf_helper().build_source_pdf(doc, page, tuple(clip),
                                      figure_kind=figure_kind, localization=localization)
            except ValueError as exc:
                raise EngineError(str(exc)) from exc
            target = assets_dir / f"{name}.pdf"
            if target.exists():
                raise EngineError(f"{target.name} already exists; refusing to overwrite")
            target.write_bytes(payload)
            entry.update(path=f"assets/{target.name}", kind=kind, role="figure",
                         source_sha256=project["source"]["sha256"],
                         rationale="Reviewed graphical source region; original image streams and native paths retained")
        elif kind == "source_raster":
            entry = extract_raster(doc, rasters, clip, assets_dir, name, page, fitz)
        elif kind == "page_raster":
            entry = render_page_raster(doc, clip, assets_dir, name, page, figure_kind, fitz)
        else:
            if rasters:
                raise EngineError(f"bbox covers {len(rasters)} visible raster occurrence(s); a raster "
                                  "cannot be declared vector_pdf (pass --kind source_raster to keep "
                                  "the original bitmap)")
            target = assets_dir / f"{name}.pdf"
            if target.exists():
                raise EngineError(f"{target.name} already exists; refusing to overwrite")
            out = fitz.open()
            try:
                out.insert_pdf(doc, from_page=page - 1, to_page=page - 1)
                clip_page(out[0], clip, fitz)
                out.save(str(target), garbage=4, deflate=True, no_new_id=True)
            finally:
                out.close()
            problems = inspect_native_pdf(target, f"asset {name}", fitz)
            if problems:
                target.unlink(missing_ok=True)
                raise EngineError("cropped asset failed vector verification: " + "; ".join(problems))
            entry = {"path": f"assets/{target.name}", "kind": kind, "role": "figure",
                     "source_page": page, "bbox": round3(tuple(clip)),
                     "rationale": f"clipped rectangle of source page {page}",
                     "sha256": sha256_file(target)}
    finally:
        doc.close()
    assets[name] = entry
    write_json(project_dir / "assets.json", assets)
    return {"command": "asset", "asset": name, "entry": entry}


# -------------------------------------------------------------------- content rules


def safe_link_uri(uri):
    if not isinstance(uri, str) or not uri or any(ord(c) <= 32 or ord(c) == 127 or c in "{}\\" for c in uri):
        raise EngineError("link_uri must be a printable URI without TeX braces/backslashes")
    try:
        parsed = urlsplit(uri)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("only public http/https hyperlinks are supported")
        parsed.port
    except ValueError as exc:
        raise EngineError(f"unsafe link_uri: {exc}") from exc
    return uri


def href_uri_tex(uri):
    uri = safe_link_uri(uri)
    for char in ("%", "#", "&", "_"):
        uri = uri.replace(char, "\\" + char)
    return uri


def inline_width_mm(width):
    """The millimetre value of an inline figure width string, else None (syntax only)."""
    if not isinstance(width, str):
        return None
    match = INLINE_WIDTH_RE.fullmatch(width)
    return float(match.group(0)[:-2]) if match else None


def validate_content(content, packet_ids, asset_ids) -> dict:
    if not isinstance(content, dict):
        raise EngineError("content.json must be a JSON object")
    problems = [f"missing top-level key {k!r}" for k in
                ("title", "blocks", "exclusions", "unresolved", "expectations") if k not in content]
    if problems:
        raise EngineError("content.json invalid:\n- " + "\n- ".join(problems))
    if not isinstance(content["title"], str) or not content["title"].strip():
        problems.append("title must be a non-empty string")
    for key in ("blocks", "exclusions", "unresolved"):
        if not isinstance(content[key], list):
            problems.append(f"{key} must be a list")
    if content.get("blocks") == []:
        problems.append("blocks must contain native content; empty content cannot be built or published")
    expectations = content["expectations"]
    if not isinstance(expectations, dict):
        problems.append("expectations must be an object")
        expectations = {}
    for key in ("equation_tags", "table_count", "figure_count", "required_strings"):
        if key not in expectations:
            problems.append(f"expectations.{key} is mandatory")
    _scan_forbidden(content, "content", problems)
    if problems:
        raise EngineError("content.json invalid:\n- " + "\n- ".join(problems))

    counts = {kind: 0 for kind in BLOCK_KINDS}
    seen_ids, used_sources, tags = set(), {}, []
    for index, block in enumerate(content["blocks"]):
        where = f"blocks[{index}]"
        if not isinstance(block, dict):
            problems.append(f"{where}: must be an object")
            continue
        block_id, kind, tex = block.get("id"), block.get("kind"), block.get("tex")
        if not isinstance(block_id, str) or not block_id:
            problems.append(f"{where}: id must be a non-empty string")
        elif block_id in seen_ids:
            problems.append(f"{where}: duplicate block id {block_id!r}")
        else:
            seen_ids.add(block_id)
        if isinstance(block_id, str) and block_id:
            where = f"{where} ({block_id})"
        if kind not in BLOCK_KINDS:
            problems.append(f"{where}: kind {kind!r} not one of {BLOCK_KINDS}")
            continue
        counts[kind] += 1
        if "keep_with_next" in block:
            if kind != "equation" or not isinstance(block["keep_with_next"], bool):
                problems.append(f"{where}: keep_with_next must be a boolean on an equation block")
            elif block["keep_with_next"]:
                following = content["blocks"][index + 1] if index + 1 < len(content["blocks"]) else None
                if not isinstance(following, dict) or following.get("kind") != "equation":
                    problems.append(f"{where}: keep_with_next requires an immediately following equation")
        if "join_next" in block:
            if kind != "paragraph" or not isinstance(block["join_next"], bool):
                problems.append(f"{where}: join_next must be a boolean on a paragraph block")
            elif block["join_next"]:
                following = content["blocks"][index + 1] if index + 1 < len(content["blocks"]) else None
                if not isinstance(following, dict) or following.get("kind") != "paragraph":
                    problems.append(f"{where}: join_next requires an immediately following paragraph")
                else:
                    boundary = re.compile(r"\\(?:par|chapter|section|subsection|part|clearpage|newpage|pagebreak)\b|\\begin\{(?:figure|table|equation|align|gather|multline|eqnarray)\*?\}")
                    if any(isinstance(value, str) and boundary.search(value)
                           for value in (tex, following.get("tex"))):
                        problems.append(f"{where}: join_next cannot cross explicit paragraph, heading, page or floating/display boundaries")
        span = block.get("span", "body")
        if span not in ("body", "full"):
            problems.append(f"{where}: span must be body or full")
        if span == "full" and kind not in ("equation", "table", "figure", "figure_native"):
            problems.append(f"{where}: full span is only supported for equations, tables and figures")
        if span == "full" and isinstance(tex, str) and re.search(r"\\begin\{(?:figure|table)\}", tex):
            problems.append(f"{where}: full span must not contain a floating figure/table environment")
        source_ids = block.get("source_ids")
        if not (isinstance(source_ids, list) and source_ids
                and all(isinstance(s, str) and s for s in source_ids)):
            problems.append(f"{where}: source_ids must be a non-empty list of packet block ids")
        else:
            if len(set(source_ids)) != len(source_ids):
                problems.append(f"{where}: source_ids contains duplicates")
            for source_id in source_ids:
                if source_id not in packet_ids:
                    problems.append(f"{where}: source id {source_id!r} is not a packet block id")
                else:
                    # Extraction can merge several semantic paragraphs/equations.
                    used_sources.setdefault(source_id, []).append(block_id)
        if kind in ("code", "console"):
            try:
                literal_payload(block)
            except EngineError as exc:
                problems.append(f"{where}: {exc}")
        elif kind == "figure":
            if not (isinstance(block.get("asset"), str) and block["asset"] in asset_ids):
                problems.append(f"{where}: asset {block.get('asset')!r} is not declared in assets.json")
            if not isinstance(block.get("caption"), str) or (block.get("number") and not block["caption"].strip()):
                problems.append(f"{where}: caption must be a string, non-empty for numbered figures")
            if block.get("number") is not None and not (isinstance(block["number"], str) and LABEL_RE.fullmatch(block["number"])):
                problems.append(f"{where}: number must be a label-safe string")
            width = block.get("width", "0.8\\linewidth")
            layout = block.get("layout", "float")
            if layout == "inline":
                width_mm = inline_width_mm(width)
                if width_mm is None:
                    problems.append(f"{where}: inline layout requires a fixed millimetre width greater than 0 and at most 45mm")
                elif not 0 < width_mm <= INLINE_WIDTH_MAX_MM:
                    problems.append(f"{where}: inline width must be within (0, {INLINE_WIDTH_MAX_MM:g}mm]")
            elif not ((isinstance(width, (int, float)) and not isinstance(width, bool) and 0 < width <= 1)
                      or (isinstance(width, str) and WIDTH_RE.fullmatch(width))):
                problems.append(f"{where}: width must be a TeX dimension such as 0.8\\linewidth")
            if tex:
                problems.append(f"{where}: figure must not carry tex; the engine emits figure macros")
            if block.get("placement", "htbp") not in ("htbp", "H"):
                problems.append(f"{where}: placement must be 'htbp' or 'H'")
            if layout not in FIGURE_LAYOUTS:
                problems.append(f"{where}: layout must be one of {FIGURE_LAYOUTS}")
            # Optional registration hints carried by the author: the source page and the
            # region to crop, so the supervisor can register the asset without guessing.
            if "source_page" in block and not (isinstance(block["source_page"], int)
                                               and not isinstance(block["source_page"], bool)
                                               and block["source_page"] > 0):
                problems.append(f"{where}: source_page must be a positive integer")
            if "bbox" in block:
                bbox = block["bbox"]
                if not (isinstance(bbox, list) and len(bbox) == 4
                        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox)
                        and bbox[2] > bbox[0] and bbox[3] > bbox[1]):
                    problems.append(f"{where}: bbox must be [x0,y0,x1,y1] in PDF points with x1>x0, y1>y0")
            if "asset_kind" in block and block["asset_kind"] not in ASSET_CROP_KINDS:
                problems.append(f"{where}: asset_kind must be one of {ASSET_CROP_KINDS}")
            if "figure_kind" in block and block["figure_kind"] not in (
                    "photograph", "plot", "schematic", "mixed", "qr_code"):
                problems.append(f"{where}: figure_kind must be photograph, plot, schematic, mixed or qr_code")
            if "link_uri" in block:
                try:
                    safe_link_uri(block["link_uri"])
                except EngineError as exc:
                    problems.append(f"{where}: {exc}")
        elif kind == "figure_native":
            if not (isinstance(tex, str) and tex.strip()):
                problems.append(f"{where}: figure_native requires non-empty tex")
            for key in ("asset", "caption", "number", "width"):
                if key in block:
                    problems.append(f"{where}: figure_native must not carry {key!r}; put it in tex")
            figure_number = block.get("figure_number")
            if figure_number is not None and not (isinstance(figure_number, str) and
                                                  LABEL_RE.fullmatch(figure_number)):
                problems.append(f"{where}: figure_number must be a label-safe string")
        elif kind == "note":
            if not isinstance(block_id, str) or not LABEL_RE.fullmatch(block_id):
                problems.append(f"{where}: note id must be label-safe")
            if not isinstance(block.get("number"), str) or not LABEL_RE.fullmatch(block["number"]):
                problems.append(f"{where}: note number must be a label-safe display string")
            if block.get("placement") not in ("margin", "block"):
                problems.append(f"{where}: note placement must be margin or block")
            if block.get("anchor", "mark") not in ("mark", "position"):
                problems.append(f"{where}: note anchor must be mark or position")
            if block.get("anchor") == "position" and block.get("placement") not in ("margin", "block"):
                problems.append(f"{where}: note anchor=position requires placement margin or block")
            if not isinstance(tex, str) or not tex.strip():
                problems.append(f"{where}: note requires non-empty tex")
            elif re.search(r"\\(?:nfnotemark|footnote|marginpar)\b|\\begin\{(?:figure|table)\}", tex):
                problems.append(f"{where}: notes cannot nest notes or floating environments")
        elif not (isinstance(tex, str) and tex.strip()):
            problems.append(f"{where}: {kind} requires non-empty tex")
        elif kind == "equation":
            found = EQUATION_TAG.findall(tex)
            if block.get("numbered") is False:
                if found:
                    problems.append(f"{where}: numbered:false equation must not carry \\tag")
                if re.search(r"\\begin\{(?:equation|align|gather|multline|eqnarray)\}", tex):
                    problems.append(f"{where}: numbered:false requires a starred or unnumbered display environment")
            elif len(found) < 1:
                problems.append(f"{where}: equation tex needs exactly one \\tag{{...}} "
                                f"(found {len(found)})")
            else:
                tags.extend(found)
        elif kind == "table":
            if not TABLE_ENVIRONMENT.search(tex):
                problems.append(f"{where}: table tex must contain a native "
                                "tabular/longtable/tabularx/array environment")
        elif kind == "paragraph":
            match = TABLE_ENVIRONMENT.search(tex) or DISPLAY_ENVIRONMENT.search(tex)
            if match:
                problems.append(f"{where}: paragraph tex must not claim table or display math "
                                f"environments; found {match.group(0)!r}")

    notes = {b["id"]: b for b in content["blocks"] if isinstance(b, dict)
             and b.get("kind") == "note" and isinstance(b.get("id"), str)}
    marks = []
    for block in content["blocks"]:
        if not isinstance(block, dict) or block.get("kind") in ("code", "console"):
            continue
        tex = block.get("tex", "")
        if not isinstance(tex, str):
            continue
        found = NOTE_MARK.findall(tex)
        if len(found) != len(re.findall(r"\\nfnotemark\b", tex)):
            problems.append(f"{block.get('id')}: malformed nfnotemark; expected {{note-id}}{{display-number}}")
        marks.extend(found)
        for note_id, _ in found:
            if note_id in notes and notes[note_id].get("placement") == "margin" and block.get("kind") != "paragraph":
                problems.append(f"{block.get('id')}: margin note marks require a body paragraph; use placement=block here")
    marked = Counter(note_id for note_id, _ in marks)
    # A margin note whose evidence block already carries its own text can be placed at the
    # note block's own list position; such a note needs no nfnotemark in a body paragraph.
    # Everything else still needs exactly one mark.
    markless_margin = {note_id for note_id, note in notes.items()
                       if marked[note_id] == 0 and note.get("anchor") == "position"}
    for note_id, number in marks:
        if note_id not in notes:
            problems.append(f"note mark {note_id!r} has no note block")
        elif notes[note_id].get("number") != number:
            problems.append(f"note mark {note_id!r} number does not match its note block")
    for note_id in notes:
        if marked[note_id] != 1 and note_id not in markless_margin:
            problems.append(f"note {note_id!r} must have exactly one mark (found {marked[note_id]})")

    excluded = set()
    for index, exclusion in enumerate(content["exclusions"]):
        where = f"exclusions[{index}]"
        if not isinstance(exclusion, dict):
            problems.append(f"{where}: must be an object")
            continue
        source_id = exclusion.get("source_id")
        if source_id not in packet_ids:
            problems.append(f"{where}: source_id {source_id!r} is not a packet block id")
        elif source_id in used_sources:
            problems.append(f"{where}: source id {source_id!r} is already covered by block "
                            f"{used_sources[source_id]!r}")
        elif source_id in excluded:
            problems.append(f"{where}: source id {source_id!r} is excluded twice")
        else:
            excluded.add(source_id)
        if exclusion.get("category") not in EXCLUSION_CATEGORIES:
            problems.append(f"{where}: category {exclusion.get('category')!r} not one of "
                            f"{EXCLUSION_CATEGORIES}")
        if not (isinstance(exclusion.get("reason"), str) and exclusion["reason"].strip()):
            problems.append(f"{where}: reason must be a non-empty string")
    missing = sorted(set(packet_ids) - set(used_sources) - excluded)
    # Long books are authored chunk by chunk.  `pending_pages` declares, per page, that its
    # evidence is deliberately not written yet, so a partial draft can be compiled and
    # reviewed; release() refuses while any page is still pending.
    pending = content.get("pending_pages")
    pending_pages = set()
    if pending is not None:
        if not isinstance(pending, list) or not all(isinstance(p, int) and not isinstance(p, bool)
                                                    for p in pending):
            problems.append("pending_pages must be a list of integers")
        else:
            pending_pages = set(pending)
    missing = [m for m in missing if int(m[1:5]) not in pending_pages]
    if missing:
        shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        problems.append(f"{len(missing)} packet text block(s) neither covered nor excluded: {shown}")
    if pending_pages:
        touched = {int(s[1:5]) for s in used_sources if re.match(r"^p(\d{4})-[bs]\d+$", s)} | \
                  {int(s[1:5]) for s in excluded if re.match(r"^p(\d{4})-[bs]\d+$", s)}
        contradicted = sorted(pending_pages & touched)
        if contradicted:
            problems.append(f"pending_pages declares pages that already have coverage: {contradicted[:8]}")

    equation_tags = expectations.get("equation_tags")
    if not (isinstance(equation_tags, list) and all(isinstance(t, str) and t for t in equation_tags)):
        problems.append("expectations.equation_tags must be a list of non-empty strings")
    elif len(set(equation_tags)) != len(equation_tags):
        problems.append("expectations.equation_tags contains duplicates")
    elif sorted(tags) != sorted(equation_tags):
        problems.append(f"equation \\tag set must match expectations exactly: content has "
                        f"{sorted(tags)}, expectations declare {sorted(equation_tags)}")
    for key, actual in (("table_count", counts["table"]),
                        ("figure_count", counts["figure"] + counts["figure_native"])):
        declared = expectations.get(key)
        if not (isinstance(declared, int) and not isinstance(declared, bool) and declared >= 0):
            problems.append(f"expectations.{key} must be a non-negative integer")
        elif declared != actual:
            problems.append(f"expectations.{key} is {declared} but content has {actual}")
    if not (isinstance(expectations.get("required_strings"), list)
            and all(isinstance(s, str) and s for s in expectations["required_strings"])):
        problems.append("expectations.required_strings must be a list of non-empty strings")
    for key in ("tex_strings", "asset_ids", "link_targets", "heading_source_ids"):
        values = expectations.get(key)
        if values is not None:
            if not (isinstance(values, list) and all(isinstance(s, str) and s.strip() for s in values)):
                problems.append(f"expectations.{key} must be a list of non-empty strings")
            elif len(set(values)) != len(values):
                problems.append(f"expectations.{key} contains duplicates")
    heading_sources = expectations.get("heading_source_ids")
    if isinstance(heading_sources, list) and all(isinstance(s, str) and s for s in heading_sources):
        expected_headings = set(heading_sources)
        unknown = expected_headings - set(packet_ids)
        if unknown:
            problems.append(f"expectations.heading_source_ids are not packet block ids: {sorted(unknown)}")
        heading_order = []
        for block in content["blocks"]:
            if not isinstance(block, dict) or block.get("kind") not in ("chapter", "section", "subsection"):
                continue
            sources = block.get("source_ids")
            if not isinstance(sources, list):
                continue
            matched = [s for s in sources if isinstance(s, str) and s in expected_headings]
            if len(matched) > 1:
                problems.append(f"{block.get('id')}: one heading block cannot represent multiple independent heading_source_ids: {matched}")
            heading_order.extend(matched)
        heading_counts = Counter(heading_order)
        for source_id in heading_sources:
            if heading_counts[source_id] != 1:
                problems.append(f"heading source {source_id!r} must bind exactly one chapter/section/subsection (found {heading_counts[source_id]})")
        if heading_order != heading_sources:
            problems.append("heading block order must match expectations.heading_source_ids exactly")
    link_uris = expectations.get("link_uris")
    if link_uris is not None:
        if not (isinstance(link_uris, list) and all(isinstance(u, str) and u for u in link_uris)):
            problems.append("expectations.link_uris must be a list of non-empty strings")
        elif len(set(link_uris)) != len(link_uris):
            problems.append("expectations.link_uris contains duplicates")
        else:
            for uri in link_uris:
                try:
                    safe_link_uri(uri)
                except EngineError as exc:
                    problems.append(f"expectations.link_uris: {exc}")
    if content["unresolved"]:
        problems.append(f"unresolved must be empty before build ({len(content['unresolved'])} left)")
    if problems:
        raise EngineError("content.json invalid:\n- " + "\n- ".join(problems[:25]))
    return counts


# --------------------------------------------------------------------------- build


def literal_payload(block):
    unexpected = set(block) - {"id", "kind", "source_ids", "text"}
    if unexpected:
        raise EngineError("literal block has unsupported fields: " + ", ".join(sorted(unexpected)))
    raw = block.get("text")
    if not isinstance(raw, str) or not raw.strip():
        raise EngineError("code/console requires nonempty raw text")
    if any((ord(ch) < 32 and ch not in "\t\n\r") or ord(ch) == 127 for ch in raw):
        raise EngineError("literal text contains unsupported control characters")
    try:
        data = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise EngineError("literal text must be valid UTF-8") from exc
    digest = hashlib.sha256(data).hexdigest()
    return f"literal/{digest}.txt", data


def literal_files(content):
    return dict(literal_payload(block) for block in content.get("blocks", [])
                if isinstance(block, dict) and block.get("kind") in ("code", "console"))


def write_literal_files(build_dir, content):
    build_dir = Path(build_dir).resolve()
    for rel, data in literal_files(content).items():
        path = build_dir / rel
        if not path.resolve().is_relative_to(build_dir):
            raise EngineError("literal output resolves outside build directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def validate_literal_files(build_dir, content):
    problems = []
    build_dir = Path(build_dir).resolve()
    for rel, data in literal_files(content).items():
        path = build_dir / rel
        if not path.resolve().is_relative_to(build_dir):
            problems.append(f"{rel}: resolves outside build directory")
        elif not path.is_file() or path.read_bytes() != data:
            problems.append(f"{rel}: differs from authoritative raw UTF-8 content")
    return problems


def caption_optional_arg(caption_tex) -> str:
    # caption's anchor preparation accepts no paragraph token in the short title.
    # Keep the full native caption intact and flatten only its moving argument.
    if not re.search(r"\\par\b", caption_tex):
        return ""
    return "[{" + re.sub(r"\\par\b", " ", caption_tex) + "}]"


def protect_native_links(tex) -> str:
    return re.sub(r"(?<!\\protect)\\(hyperlink|href|url|nolinkurl)\b", r"\\protect\\\1", tex)


def break_native_urls(tex) -> str:
    def canonical(text):
        if text.startswith(r"\texttt{") and text.endswith("}"):
            text = text[8:-1]
        text = re.sub(r"\\textasciitilde\s?", "~", text)
        return re.sub(r"\\([_%&#])", r"\1", text)

    def replace(match):
        uri, display = match.groups()
        plain = canonical(uri)
        if canonical(display) != plain or re.search(r"\s|[{}\\]", plain):
            return match[0]
        return r"\href{" + uri + r"}{\nolinkurl{" + uri + "}}"

    # Only an equivalent, literal URL display changes; targets and API labels stay.
    tex = re.sub(r"\\href\{(https?://[^{}]*)\}\{(\\texttt\{[^{}]*\}|[^{}]*)\}", replace, tex)
    return re.sub(r"\\texttt\{((?:https?://)[^/\s{}][^\s{}]*)\}",
                  lambda m: r"\nolinkurl{" + m[1] + "}", tex)


# Note ids that have an explicit \nfnotemark in the content, refreshed once per build.
# Margin notes not in this set carry their own evidence text and are placed at their own
# list position (see render_block / build).
_MARKED_NOTE_IDS = [set()]


def render_block(block, assets, anchor_lines=None) -> str:
    """Render one content block.  A margin note without an ``\\nfnotemark`` in the body is
    placed at its own list position when it declares ``anchor: position`` (see build)."""
    marked_note_ids = _MARKED_NOTE_IDS[0]
    kind, tex = block["kind"], block.get("tex", "")
    if block.get("span") == "full":
        local = {**block, "span": "body"}
        if kind == "figure":
            width = block.get("width", "0.8\\linewidth")
            if isinstance(width, (int, float)):
                width = f"{width:g}\\linewidth"
            graphic = rf"\includegraphics[width={width},height=0.78\textheight,keepaspectratio]{{{assets[block['asset']]['path']}}}"
            if block.get("link_uri"):
                graphic = rf"\href{{{href_uri_tex(block['link_uri'])}}}{{{graphic}}}"
            caption = protect_native_links(break_native_urls(block["caption"]))
            number = block.get("number")
            body = [r"\noindent\begin{minipage}{\linewidth}\centering", *(anchor_lines or []), graphic]
            if number:
                body.extend([rf"\renewcommand{{\thefigure}}{{{number}}}",
                             rf"\captionof{{figure}}{caption_optional_arg(caption)}{{{caption}}}", rf"\label{{fig:{number}}}"])
            elif caption.strip():
                body.append(rf"\captionof*{{figure}}{{{caption}}}")
            body.append(r"\end{minipage}")
            rendered = "\n".join(body)
        elif kind == "figure_native":
            rendered = "\n".join([r"\begingroup\centering", *(anchor_lines or []), protect_native_links(tex), r"\par\endgroup"])
        else:
            rendered = render_block(local, assets, anchor_lines)
        return "\n".join([r"\begin{nfFullWidth}", rendered, r"\end{nfFullWidth}"])
    if kind not in ("code", "console", "equation"):
        tex = break_native_urls(tex)
    if kind == "note":
        if block["placement"] == "margin":
            if block["id"] in marked_note_ids:
                return "% Margin note emitted at its nfnotemark: " + block["id"]
            if block.get("anchor") != "position":
                return "% Margin note: no mark found; declare anchor=position to place it here"
            # Evidence block already carries the note text: place it in the outer lane here.
            return rf"\nopagebreak[2]\nfPositionMarginNote{{{block['id']}}}{{{block['number']}}}{{{tex}}}"
        return rf"\nfBlockNote{{{block['id']}}}{{{block['number']}}}{{{tex}}}"
    if kind in ("code", "console"):
        path, _ = literal_payload(block)
        keep_lines = min(10, max(3, len(block["text"].splitlines()) + 1))
        return "\\par\\needspace{" + str(keep_lines) + rf"\baselineskip}}\VerbatimInput[fontsize=\small]{{{path}}}" + "\n\\par\n"
    if kind in ("chapter", "section", "subsection"):
        if re.match(r"\s*\\" + kind + r"\*?\s*(?:\[|\{)", tex):
            return tex
        return f"\\{kind}{{{tex}}}"
    if kind == "paragraph":
        if block.get("join_next"):
            return tex.rstrip()
        return tex + "\n\\par\n"
    if kind == "equation":
        tex = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)*", "\n", tex)
        if DISPLAY_ENVIRONMENT.search(tex):
            return tex
        env = "equation*" if block.get("numbered") is False else "equation"
        return f"\\begin{{{env}}}\n" + tex + f"\n\\end{{{env}}}"
    if kind == "table":
        return "\\par\\begingroup\\centering\n" + protect_native_links(tex) + "\n\\par\\endgroup\n"
    if kind == "figure_native":
        tex = protect_native_links(tex)
        if anchor_lines and re.search(r"\\begin\{figure\}(?:\[[^\]]*\])?", tex):
            return re.sub(r"(\\begin\{figure\}(?:\[[^\]]*\])?)", lambda m: m[0]+"\n"+"\n".join(anchor_lines), tex, count=1)
        if re.search(r"\\begin\{figure\}", tex):
            return tex
        return "\n".join(["\\begin{figure}[htbp]", "\\centering", *(anchor_lines or []),
                          "\\begin{minipage}{\\linewidth}", tex,
                          "\\end{minipage}", "\\end{figure}"])
    width = block.get("width", "0.8\\linewidth")
    if isinstance(width, (int, float)):
        width = f"{width:g}\\linewidth"
    number = block.get("number")
    caption_tex = protect_native_links(break_native_urls(block["caption"]))
    caption = (f"\\renewcommand{{\\thefigure}}{{{number}}}\n\\caption{caption_optional_arg(caption_tex)}{{{caption_tex}}}"
               if number else f"\\caption*{{{caption_tex}}}" if block["caption"].strip() else "")
    label = f"\\label{{fig:{number}}}" if number else ""
    options = f"width={width}" if block.get("layout") == "inline" else f"width={width},height=0.78\\textheight,keepaspectratio"
    graphic = f"\\includegraphics[{options}]{{{assets[block['asset']]['path']}}}"
    if block.get("link_uri"):
        graphic = f"\\href{{{href_uri_tex(block['link_uri'])}}}{{{graphic}}}"
    if block.get("layout") == "inline":
        return render_inline_figure(block, assets[block["asset"]], width, caption_tex, number,
                                    anchor_lines, graphic)
    return "\n".join([f"\\begin{{figure}}[{block.get('placement', 'htbp')}]", "\\centering",
                      *(anchor_lines or []),
                      graphic,
                      caption, label, "\\end{figure}"])


def inline_needspace_mm(block, width, asset) -> int:
    """Reserve a conservative small box height; actual caption layout still requires QA."""
    match = INLINE_WIDTH_RE.fullmatch(str(width))
    if not match or not 0 < float(width[:-2]) <= 45:
        raise EngineError("inline figure width must be >0 and <=45mm")
    bbox = asset.get("bbox") if isinstance(asset, dict) else None
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise EngineError("inline figure requires its verified source bbox")
    span_x, span_y = float(bbox[2])-float(bbox[0]), float(bbox[3])-float(bbox[1])
    if span_x <= 0 or span_y <= 0:
        raise EngineError("inline figure bbox must have positive dimensions")
    image_height = float(width[:-2]) * span_y / span_x
    caption = block.get("caption", "").strip()
    caption_mm = 5 * max(1, math.ceil(len(caption) / 32)) if caption else 0
    need = math.ceil(image_height + caption_mm + 8)
    if need > INLINE_NEED_CAP_MM:
        raise EngineError("inline resource exceeds one third of the A4 text height; use a float")
    return need


def render_inline_figure(block, asset, width, caption_tex, number, anchor_lines, graphic) -> str:
    """Keep the graphic and native caption in one local, non-floating minipage."""
    lines = ["\\par", f"\\needspace{{{inline_needspace_mm(block, width, asset)}mm}}",
             "\\noindent\\begin{minipage}{\\linewidth}", "\\centering"]
    lines.extend(anchor_lines or [])
    lines.append(graphic)
    if number:
        lines.append(f"\\renewcommand{{\\thefigure}}{{{number}}}\n\\captionof{{figure}}{caption_optional_arg(caption_tex)}{{{caption_tex}}}")
        lines.append(f"\\label{{fig:{number}}}")
    elif block["caption"].strip():
        lines.append(f"\\captionof*{{figure}}{{{caption_tex}}}")
    lines.extend(["\\end{minipage}", "\\par"])
    return "\n".join(lines)


def matrix_column_capacity(content) -> int:
    """Use the actual matrix rows to raise amsmath's default ten-column limit."""
    capacity, stack = 10, []
    matrix = re.compile(r"^(?:[pbBvV]?matrix|smallmatrix)\*?$")
    tokens = re.compile(r"(\\(?:begin|end))\{([^}]+)\}|(\\\\)|(?<!\\)(&)")
    for block in content["blocks"]:
        if block["kind"] in ("code", "console"):
            continue
        tex = re.sub(r"\\begin\{(verbatim\*?|Verbatim)\}.*?\\end\{\1\}", "", block.get("tex", ""), flags=re.S)
        for token in tokens.finditer(tex):
            command, env, row_end, column = token.groups()
            if command == r"\begin":
                stack.append([env, 1])
            elif command == r"\end":
                if stack and stack[-1][0] == env:
                    if matrix.fullmatch(env):
                        capacity = max(capacity, stack[-1][1])
                    stack.pop()
            elif stack and matrix.fullmatch(stack[-1][0]):
                if column:
                    stack[-1][1] += 1
                elif row_end:
                    capacity = max(capacity, stack[-1][1])
                    stack[-1][1] = 1
    return capacity


def render_main_tex(project, content, assets) -> str:
    layout = validate_layout(project)
    if any(b["kind"] == "note" and b["placement"] == "margin" for b in content["blocks"]) and layout["notes"] != "outer":
        raise EngineError("margin notes require project.layout.notes=outer")
    lines = ["% Generated by native_forge. Do not edit by hand.",
             "\\documentclass[lang=cn,11pt,math=cm]{elegantbook}", "\\usepackage{nativeforge}",
             *render_layout(project),
             *validate_preamble(project),
             f"\\setcounter{{MaxMatrixCols}}{{{matrix_column_capacity(content)}}}",
             f"\\title{{{latex_escape(project['title'])}}}", "\\author{}", "\\date{}",
             "\\begin{document}"]
    declarations = []
    marked_note_ids = set()
    for _block in content["blocks"]:
        if isinstance(_block, dict) and isinstance(_block.get("tex"), str):
            marked_note_ids.update(m[0] for m in NOTE_MARK.findall(_block["tex"]))
    _MARKED_NOTE_IDS[0] = marked_note_ids
    anchored_pages = set()
    anchored_ids = set()
    excluded_by_page = {}
    for exclusion in content.get("exclusions", []):
        match = re.match(r"^p(\d{4})-[bs]\d+$", exclusion["source_id"])
        if match:
            excluded_by_page.setdefault(match[1], []).append(exclusion["source_id"])
    for index, block in enumerate(content["blocks"]):
        lines.append("% Source block: " + block["id"].replace("\n", " ").replace("\r", " "))
        anchor_lines = []
        for source_id in block.get("source_ids", []):
            if source_id not in anchored_ids:
                anchor_lines.append(rf"\hypertarget{{src-{source_id}}}{{}}")
                anchor_lines.append(rf"\label{{src-{source_id}}}")
                anchored_ids.add(source_id)
            match = re.match(r"^p(\d{4})-[bs]\d+$", source_id)
            if match and match[1] not in anchored_pages:
                anchor_lines.append(rf"\hypertarget{{src-p{match[1]}}}{{}}")
                anchor_lines.append(rf"\label{{src-p{match[1]}}}")
                for excluded_id in excluded_by_page.get(match[1], []):
                    if excluded_id not in anchored_ids:
                        anchor_lines.append(rf"\hypertarget{{src-{excluded_id}}}{{}}")
                        anchor_lines.append(rf"\label{{src-{excluded_id}}}")
                        anchored_ids.add(excluded_id)
                anchored_pages.add(match[1])
        anchor_number = block.get("number") if block["kind"] == "figure" else None
        if block["kind"] == "figure_native":
            user_tex = block.get("tex") or ""
            if isinstance(block.get("figure_number"), str) \
                    and f"\\hypertarget{{fig-anchor-{block['figure_number']}}}" not in user_tex:
                anchor_number = block["figure_number"]
        if anchor_number:
            anchor_lines.append(rf"\hypertarget{{fig-anchor-{anchor_number}}}{{}}")
        floating = block["kind"] in ("figure", "figure_native")
        margin_note = block["kind"] == "note" and block["placement"] == "margin" \
            and block["id"] in marked_note_ids
        # A margin note that carries its own evidence text is positioned where it appears
        # in the block list instead of at a mark in a body paragraph.
        position_note = block["kind"] == "note" and block["placement"] == "margin" \
            and block.get("anchor") == "position"
        if margin_note:
            body = "\n".join([*anchor_lines, break_native_urls(block["tex"])])
            declarations.append(rf"\nfDeclareMarginNote{{{block['id']}}}{{{block['number']}}}{{{body}}}")
        inline = block["kind"] == "figure" and block.get("layout") == "inline"
        anchors_after_block = block["kind"] in ("chapter", "section", "subsection") \
                or (block["kind"] == "paragraph" and (block.get("tex") or "").strip() == "\\clearpage")
        if not floating and not inline and not anchors_after_block and not margin_note and not position_note:
            lines.extend(anchor_lines)
        rendered = render_block(block, assets, anchor_lines if floating or inline else None)
        if index > 0 and content["blocks"][index - 1].get("join_next"):
            rendered = rendered.lstrip()
        keep_equation = block["kind"] == "equation" and block.get("keep_with_next")
        if keep_equation:
            lines.append(r"\begingroup\postdisplaypenalty=10000")
        lines.append(rendered)
        if anchors_after_block:
            lines.extend(anchor_lines)
        if keep_equation or \
                (block["kind"] == "paragraph" and index + 1 < len(content["blocks"]) \
                 and content["blocks"][index + 1]["kind"] == "equation"):
            lines.append("\\nopagebreak[4]")
        if keep_equation:
            lines.append(r"\endgroup")
    lines.append("\\end{document}")
    if declarations:
        at = lines.index("\\begin{document}")
        lines[at:at] = declarations
    return "\n".join(lines) + "\n"


def fingerprint_files(project_dir, project, templates_dir) -> dict:
    project_dir, build_dir = Path(project_dir), Path(project_dir) / "build"
    assets = load_assets(project_dir)
    return {"source": hash_or_missing(project["source"]["path"]),
            "engine": sha256_file(__file__),
            "source_pdf_engine": hash_or_missing(Path(__file__).with_name("source_pdf_objects.py")),
            "native_shading_qa_engine": hash_or_missing(Path(__file__).with_name("native_shading_qa.py")),
            "project": stable_sha256({k: project[k] for k in
                                       ("schema_version", "title", "source", "pages", "templates",
                                        "layout", "preamble") if k in project}),
            "packet": {str(p): hash_or_missing(project_dir / "packet" / "pages" / f"p{p:04d}.json")
                       for p in project["pages"]},
            "source_inventory": hash_or_missing(project_dir / "source_inventory.json"),
            "content": hash_or_missing(project_dir / "content.json"),
            "assets_manifest": hash_or_missing(project_dir / "assets.json"),
            "assets": {i: hash_or_missing(project_dir / e.get("path", ""))
                       for i, e in sorted(assets.items()) if isinstance(e, dict)},
            "build_assets": {i: hash_or_missing(build_dir / e.get("path", ""))
                             for i, e in sorted(assets.items()) if isinstance(e, dict)},
            "redraw_inputs": {i: {k: hash_or_missing(project_dir / e["redraw"][k])
                                  for k in ("spec_path", "tex_path") if isinstance(e["redraw"].get(k), str)}
                              for i, e in sorted(assets.items()) if isinstance(e, dict)
                              and isinstance(e.get("redraw"), dict)},
            "templates": {n: hash_or_missing(Path(templates_dir) / n) for n in TEMPLATE_FILES},
            "build_templates": {n: hash_or_missing(build_dir / n) for n in TEMPLATE_FILES},
            "literal_files": {rel: hash_or_missing(build_dir / rel)
                              for rel in literal_files(read_json(project_dir / "content.json"))},
            "tex": hash_or_missing(build_dir / "main.tex"),
            "log": hash_or_missing(build_dir / "main.log"),
            "layout_positions": hash_or_missing(build_dir / "main.aux"),
            "pdf": hash_or_missing(build_dir / "main.pdf")}


def diff_fingerprint(recorded, current, prefix="") -> list:
    problems = []
    for key in sorted(set(recorded) | set(current)):
        old, new = recorded.get(key), current.get(key)
        if isinstance(old, dict) or isinstance(new, dict):
            if isinstance(old, dict) and isinstance(new, dict):
                problems += diff_fingerprint(old, new, prefix=f"{prefix}{key}.")
            else:
                problems.append(f"{prefix}{key}: changed")
        elif old != new:
            problems.append(f"{prefix}{key}: {old} -> {new}")
    return problems


def log_tail(path, limit=30) -> str:
    if not Path(path).is_file():
        return "(no compile log was produced)"
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-limit:])


def build(project_dir, templates_dir=None, xelatex_cmd=None) -> dict:
    ensure_ram()
    if sha256_file(__file__) != ENGINE_SOURCE_HASH:
        raise EngineError("engine source changed after import; restart the command before building")
    fitz = load_fitz()
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir)
    project["status"] = "draft"
    write_json(project_dir / "project.json", project)
    templates_dir = resolve_templates_dir(project, templates_dir)
    check_template_bindings(project, template_hashes(templates_dir))
    source = Path(project["source"]["path"])
    if not source.is_file() or sha256_file(source) != project["source"]["sha256"]:
        raise EngineError("source PDF changed since prepare; re-run prepare")
    packet = load_packet(project_dir, project)
    assets = load_assets(project_dir)
    asset_problems = validate_assets(project_dir, assets, fitz)
    if asset_problems:
        raise EngineError("assets.json invalid:\n- " + "\n- ".join(asset_problems[:25]))
    if not (project_dir / "content.json").is_file():
        raise EngineError("content.json missing; run prepare to scaffold it")
    content = read_json(project_dir / "content.json")
    counts = validate_content(content, set(packet), set(assets))
    project["status"] = "draft"
    write_json(project_dir / "project.json", project)
    input_keys = ("engine", "source_pdf_engine", "native_shading_qa_engine", "source", "project", "packet", "content", "assets_manifest", "assets",
                  "redraw_inputs", "templates", "source_inventory")
    before = fingerprint_files(project_dir, project, templates_dir)
    if stable_sha256(content) != stable_sha256(read_json(project_dir / "content.json")):
        raise EngineError("content changed while validating; rerun build")

    build_dir = project_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_FILES:
        shutil.copyfile(templates_dir / name, build_dir / name)
    (build_dir / "assets").mkdir(exist_ok=True)
    for entry in assets.values():
        (build_dir / entry["path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_dir / entry["path"], build_dir / entry["path"])
    write_literal_files(build_dir, content)
    write_text(build_dir / "main.tex", render_main_tex(project, content, assets))
    for stale in ("main.log", "main.pdf", "fingerprint.json"):
        (build_dir / stale).unlink(missing_ok=True)

    command = list(xelatex_cmd) if xelatex_cmd else resolve_xelatex()
    if not command:
        raise EngineError("xelatex not found on PATH"
                          " (install TeX Live, or set NF_XELATEX_LEGACY to an explicit xelatex.exe)")
    returncode = 0
    compile_env = os.environ.copy()
    compile_env.update({"SOURCE_DATE_EPOCH": "946684800", "FORCE_SOURCE_DATE": "1", "TZ": "UTC"})
    for pass_no in range(1, 5):
        ensure_ram()
        try:
            proc = subprocess.run([*command, *XELATEX_FLAGS, "main.tex"], cwd=str(build_dir),
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=XELATEX_TIMEOUT, env=compile_env)
        except subprocess.TimeoutExpired:
            raise EngineError(f"xelatex timed out after {XELATEX_TIMEOUT}s; log preserved at "
                              f"{build_dir / 'main.log'}")
        except OSError as exc:
            raise EngineError(f"cannot run xelatex ({command[0]}): {exc}")
        returncode = proc.returncode
        write_text(build_dir / f"pass-{pass_no}.stdout.txt", proc.stdout + "\n" + proc.stderr)
        if returncode != 0:
            break
        if pass_no >= 2 and not scan_compile_log(build_dir / "main.log")["rerun"]:
            break
    log_path, pdf_path = build_dir / "main.log", build_dir / "main.pdf"
    if returncode != 0 or not pdf_path.is_file():
        raise EngineError(f"xelatex failed (exit {returncode}); log preserved at {log_path}\n"
                          + log_tail(log_path))
    literal_problems = validate_literal_files(build_dir, content)
    if literal_problems:
        raise EngineError("literal build files changed:\n- " + "\n- ".join(literal_problems))
    files = fingerprint_files(project_dir, project, templates_dir)
    changes = diff_fingerprint({k: before[k] for k in input_keys}, {k: files[k] for k in input_keys})
    if changes:
        raise EngineError("build inputs changed during compilation; rerun build:\n- " + "\n- ".join(changes))
    fingerprint = {"schema_version": SCHEMA_VERSION, "build_fingerprint": stable_sha256(files),
                   "files": files}
    write_json(build_dir / "fingerprint.json", fingerprint)
    return {"command": "build", "project": str(project_dir), "content_blocks": len(content["blocks"]),
            "block_counts": counts, "assets": sorted(assets),
            "build_fingerprint": fingerprint["build_fingerprint"]}


# ------------------------------------------------------------------------------ qa

def review_scaffold(project, build_fingerprint, output_pages) -> dict:
    return {"schema_version": SCHEMA_VERSION, "build_fingerprint": build_fingerprint,
            "source_pages": [{"page": p, "checked": False} for p in project["pages"]],
            "output_pages": [{"page": p, "checked": False} for p in range(1, output_pages + 1)],
            "translation_checked": False, "formula_table_checked": False, "issues": [],
            "reviewer": ""}


def scan_compile_log(path) -> dict:
    diagnostics = {category: [] for category in LOG_PATTERNS}
    if not Path(path).is_file():
        return diagnostics
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), 1):
        for category, patterns in LOG_PATTERNS.items():
            if len(diagnostics[category]) >= 20:
                continue
            for pattern in patterns:
                if pattern.search(line):
                    diagnostics[category].append(f"{line_no}: {line.strip()[:160]}")
                    break
    return diagnostics


def audit_layout(project, content, build_dir, page_sizes) -> dict:
    """Check measurable note geometry; keep drift data distinct from visual review."""
    layout = validate_layout(project)
    report = {"configured": "layout" in project, "notes": [], "findings": []}
    findings = report["findings"]
    if "layout" in project:
        report["resolved"] = layout
        for page, width, height in page_sizes:
            if abs(width - layout["paper_width_mm"]) > 0.2 or abs(height - layout["paper_height_mm"]) > 0.2:
                findings.append(f"page {page}: actual paper {width:.2f}x{height:.2f}mm differs from configured paper")
    notes = [b for b in (content or {}).get("blocks", []) if b.get("kind") == "note"]
    if not notes:
        return report
    auxiliary = Path(build_dir) / "main.aux"
    aux = auxiliary.read_text(encoding="utf-8", errors="replace") if auxiliary.is_file() else ""
    positions = {}
    for line in aux.splitlines():
        label = re.match(r"\\zref@newlabel\{(nf-(?:mark|note-start|note-end)-[^{}]+)\}\{(.*)\}", line)
        if label:
            values = dict(re.findall(r"\\(posx|posy|abspage)\{(-?\d+)\}", label[2]))
            if all(k in values for k in ("posx", "posy", "abspage")):
                positions[label[1]] = {k: int(v) for k, v in values.items()}
    sp_mm = 25.4 / (72.27 * 65536)
    log_path = Path(build_dir) / "main.log"
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    metrics = {note_id: {"height_mm": int(height) * sp_mm, "width_mm": int(width) * sp_mm}
               for note_id, height, width in re.findall(r"NFNOTE-METRIC (\S+) height=(\d+)\s+width=(\d+)", log)}
    intervals = {}
    for block in notes:
        note_id = block["id"]
        entry = {"id": note_id, "number": block["number"], "placement": block["placement"]}
        for name, prefix in (("mark", "nf-mark-"), ("start", "nf-note-start-"), ("end", "nf-note-end-")):
            position = positions.get(prefix + note_id)
            if position:
                entry[name] = {"page": position["abspage"], "x_mm": round(position["posx"] * sp_mm, 3),
                               "y_mm": round(layout["paper_height_mm"] - position["posy"] * sp_mm, 3)}
            elif name == "mark" and block.get("anchor", "mark") == "position":
                # A position-anchored note is placed where it appears in the block list and
                # therefore has no in-text mark to drift from.
                entry["anchor"] = "position"
            else:
                findings.append(f"note {note_id}: missing {name} position")
        if "mark" in entry and "start" in entry:
            entry["page_drift"] = entry["start"]["page"] - entry["mark"]["page"]
            entry["vertical_drift_mm"] = round(entry["start"]["y_mm"] - entry["mark"]["y_mm"], 3)
        if block["placement"] == "margin":
            if note_id not in metrics:
                findings.append(f"note {note_id}: missing box metric")
            else:
                entry.update({k: round(v, 3) for k, v in metrics[note_id].items()})
            if entry.get("page_drift", 0):
                findings.append(f"note {note_id}: margin note moved {entry['page_drift']} page(s) from mark")
            if "start" in entry and "end" in entry and note_id in metrics:
                start, end = entry["start"], entry["end"]
                if start["page"] != end["page"]:
                    findings.append(f"note {note_id}: margin note crosses pages")
                top, bottom = end["y_mm"] - metrics[note_id]["height_mm"], end["y_mm"]
                entry["box_top_mm"], entry["box_bottom_mm"] = round(top, 3), round(bottom, 3)
                expected_x = (layout["inner_mm"] + layout["text_width_mm"] + layout["margin_note_sep_mm"]
                              if start["page"] % 2 else layout["outer_mm"])
                if abs(start["x_mm"] - expected_x) > 1:
                    findings.append(f"note {note_id}: note is not in the expected outer column")
                if top < layout["top_mm"] - 1 or bottom > layout["paper_height_mm"] - layout["bottom_mm"] + 1:
                    findings.append(f"note {note_id}: margin note extends beyond the text-height boundary")
                if metrics[note_id]["width_mm"] > layout["margin_note_width_mm"] + 0.2:
                    findings.append(f"note {note_id}: note box exceeds configured column width")
                intervals.setdefault(start["page"], []).append((top, bottom, note_id))
        report["notes"].append(entry)
    for page, spans in intervals.items():
        previous = None
        for top, bottom, note_id in sorted(spans):
            if previous and top < previous[1] - 0.2:
                findings.append(f"page {page}: margin notes {previous[2]} and {note_id} overlap")
            if previous is None or bottom > previous[1]:
                previous = (top, bottom, note_id)
    return report


def allowed_raster_occurrences(project_dir, content, assets, fitz):
    """Account for each actual use of an explicitly declared original bitmap."""
    allowed = Counter()
    for block in content.get("blocks", []):
        if not isinstance(block, dict) or block.get("kind") != "figure":
            continue
        entry = assets.get(block.get("asset"), {})
        if entry.get("kind") == "source_pdf":
            if entry.get("crop_method") == SOURCE_FORM_CROP_METHOD:
                proof = verified_source_form(block.get("asset"))["proof"]
                for width, height, digest in proof["pixel_source"]:
                    allowed[(width, height, digest)] += 1
            else:
                for image in entry["source_images"]:
                    allowed[(image["width"], image["height"], image["pixel_digest"])] += 1
            continue
        if entry.get("kind") not in ("source_raster", "page_raster"):
            continue
        pix = fitz.Pixmap(str(Path(project_dir) / entry["path"]))
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        allowed[(pix.width, pix.height, pix.digest.hex())] += 1
    return allowed


def native_runtime_proxy_exemption(doc, page, proxies):
    """Decide whether a page's xref-0 runtime shading proxies may be reported separately.

    Refused by default: the page must carry no real Image resource and no actual
    inline-image token (Contents, nested forms, Type3 charprocs), and must embed exactly
    one form whose payload fingerprint and recursive resource graph match an already
    verified vector source-page-form with the exact recorded proxy occurrence count.
    """
    module = native_shading_qa_helper()
    if module is None:
        return False, (f"output page {page.number + 1}: {len(proxies)} xref-0 runtime proxy "
                       "occurrence(s) cannot be certified (native_shading_qa.py missing); counted as bitmaps")
    candidates = [{"asset": asset_id, "source_contents_sha256": record["proof"]["source_contents_sha256"],
                   "graph_sha256": record["evidence"]["graph_sha256"],
                   "runtime_proxy_output_count": record["proof"]["runtime_proxy_output_count"],
                   "resource_counts": record["evidence"]["counts"]}
                  for asset_id, record in sorted(_VERIFIED_SOURCE_FORMS.items())
                  if record.get("kind") == "vector_pdf" and record.get("evidence")]
    if not candidates:
        return False, (f"output page {page.number + 1}: {len(proxies)} xref-0 runtime proxy occurrence(s) "
                       "without an authorized verified vector source-page-form; counted as bitmaps")
    ok, detail = module.exempt_runtime_proxies(doc, page, len(proxies), candidates)
    if ok:
        return True, detail
    return False, (f"output page {page.number + 1}: {len(proxies)} xref-0 runtime proxy occurrence(s) "
                   f"not exempted ({detail}); counted as bitmaps")


def qa(project_dir, templates_dir=None) -> dict:
    ensure_ram()
    fitz = load_fitz()
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir)
    build_dir = project_dir / "build"
    if not (build_dir / "fingerprint.json").is_file():
        project["status"] = "draft"
        write_json(project_dir / "project.json", project)
        raise EngineError("no build fingerprint; run build first")
    fingerprint = read_json(build_dir / "fingerprint.json")
    recorded = fingerprint.get("build_fingerprint")
    templates_dir = resolve_templates_dir(project, templates_dir)
    mismatches = diff_fingerprint(fingerprint.get("files") or {},
                                  fingerprint_files(project_dir, project, templates_dir))
    findings = [{"check": "fingerprint", "detail": d} for d in mismatches]
    if recorded != stable_sha256(fingerprint.get("files") or {}):
        findings.append({"check": "fingerprint", "detail": "build fingerprint record is corrupt"})

    if not (build_dir / "main.log").is_file():
        findings.append({"check": "log", "detail": "compile log missing: build/main.log"})
    diagnostics = scan_compile_log(build_dir / "main.log")
    for category, hits in sorted(diagnostics.items()):
        if hits:
            findings.append({"check": f"log.{category}",
                             "detail": f"{len(hits)} hit(s); first: {hits[0]}"})

    assets = load_assets(project_dir)
    findings += [{"check": "assets", "detail": p} for p in validate_assets(project_dir, assets, fitz)]

    content = None
    packet = {}
    try:
        content = read_json(project_dir / "content.json")
        packet = load_packet(project_dir, project)
        validate_content(content, set(packet), set(assets))
        findings += [{"check": "literal.content", "detail": problem}
                     for problem in validate_literal_files(build_dir, content)]
    except EngineError as exc:
        findings.append({"check": "content", "detail": str(exc)})

    expectations_checks = {"required_strings_missing": [], "equation_tags_missing_in_pdf": [],
                           "equation_tags_missing_in_tex": [], "equation_tags_missing_in_source": []}
    preview_pages = output_pages = 0
    page_sizes = []
    observed_rasters = Counter()
    allowed_rasters = Counter()
    native_runtime_exempt, native_runtime_refused = [], []
    try:
        if isinstance(content, dict):
            allowed_rasters = allowed_raster_occurrences(project_dir, content, assets, fitz)
    except Exception as exc:
        findings.append({"check": "raster.assets", "detail": str(exc)})
    pdf_text = ""
    pdf_link_uris = set()
    pdf_named_destinations = set()
    pdf_path = build_dir / "main.pdf"
    if not pdf_path.is_file():
        findings.append({"check": "pdf", "detail": "output PDF missing: build/main.pdf"})
    else:
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            findings.append({"check": "pdf", "detail": f"invalid output PDF: {exc}"})
            doc = None
        if doc is not None:
            try:
                output_pages = doc.page_count
                pdf_named_destinations.update(doc.resolve_names())
                texts = []
                preview_dir = build_dir / "preview"
                preview_dir.mkdir(parents=True, exist_ok=True)
                for stale in preview_dir.glob("page-*.png"):
                    match = re.fullmatch(r"page-(\d{4})\.png", stale.name)
                    if match and int(match.group(1)) > output_pages:
                        stale.unlink()
                for page in doc:
                    ensure_ram()
                    page_sizes.append((page.number + 1, page.rect.width * 25.4 / 72, page.rect.height * 25.4 / 72))
                    texts.append(page.get_text())
                    for link in page.get_links():
                        uri = link.get("uri")
                        if link.get("kind") == fitz.LINK_URI and isinstance(uri, str) and uri:
                            pdf_link_uris.add(uri)
                    infos = [info for info in page.get_image_info(xrefs=True) if visible_bbox(info["bbox"])]
                    for info in infos:
                        if int(info.get("xref") or 0) > 0:
                            observed_rasters[(info["width"], info["height"], info["digest"].hex())] += 1
                    proxies = [info for info in infos if int(info.get("xref") or 0) <= 0]
                    if proxies:
                        exempt, detail = native_runtime_proxy_exemption(doc, page, proxies)
                        if exempt:
                            native_runtime_exempt.append(detail)
                        else:
                            native_runtime_refused.append(detail)
                            findings.append({"check": "raster.native_proxy", "detail": detail})
                            for info in proxies:
                                observed_rasters[(info["width"], info["height"], info["digest"].hex())] += 1
                    page.get_pixmap(dpi=120).save(str(preview_dir / f"page-{page.number + 1:04d}.png"))
                    preview_pages += 1
                pdf_text = re.sub(r"\s+", "", "\n".join(texts))
            finally:
                doc.close()
            if observed_rasters != allowed_rasters:
                findings.append({"check": "raster.output", "detail":
                                 f"output bitmap occurrences differ from declared source_raster figure uses: "
                                 f"observed={sum(observed_rasters.values())}, allowed={sum(allowed_rasters.values())}; "
                                 "pixel digests and dimensions must match; xref-0 runtime proxies without an "
                                 "authorized verified source-page-form are counted here as bitmaps"})
        if isinstance(content, dict) and isinstance(content.get("expectations"), dict):
            for required in content["expectations"].get("required_strings") or []:
                if isinstance(required, str) and re.sub(r"\s+", "", required) not in pdf_text:
                    expectations_checks["required_strings_missing"].append(required)
            expectations_checks["required_link_uris_missing"] = []
            for uri in content["expectations"].get("link_uris") or []:
                if isinstance(uri, str) and uri not in pdf_link_uris:
                    expectations_checks["required_link_uris_missing"].append(uri)
        tex_path = build_dir / "main.tex"
        tex = tex_path.read_text(encoding="utf-8") if tex_path.is_file() else ""
        if isinstance(content, dict) and isinstance(content.get("expectations"), dict):
            expected = content["expectations"]
            normalized_tex = re.sub(r"\s+", "", tex.replace(r"\protect", ""))
            expectations_checks["required_tex_strings_missing"] = [s for s in expected.get("tex_strings", [])
                if re.sub(r"\s+", "", s.replace(r"\protect", "")) not in normalized_tex]
            used_assets = {b.get("asset") for b in content["blocks"] if b.get("kind") == "figure"}
            expectations_checks["required_asset_ids_missing"] = [s for s in expected.get("asset_ids", [])
                if s not in used_assets or s not in assets]
            expectations_checks["required_link_targets_missing"] = [s for s in expected.get("link_targets", [])
                if s not in pdf_named_destinations]
        if isinstance(content, dict) and isinstance(content.get("blocks"), list):
            for block in content["blocks"]:
                if not isinstance(block, dict) or block.get("kind") != "equation":
                    continue
                for tag in EQUATION_TAG.findall(block.get("tex") or ""):
                    if f"\\tag{{{tag}}}" not in tex:
                        expectations_checks["equation_tags_missing_in_tex"].append(tag)
                    if tag not in pdf_text:
                        expectations_checks["equation_tags_missing_in_pdf"].append(tag)
                    source_text = "".join(re.sub(r"\s+", "", packet[s]["text"])
                                          for s in block.get("source_ids") or [] if s in packet)
                    if tag not in source_text:
                        expectations_checks["equation_tags_missing_in_source"].append(tag)
    for key, missing in sorted(expectations_checks.items()):
        if missing:
            findings.append({"check": f"expectations.{key}",
                             "detail": f"missing {sorted(set(missing))}"})

    layout_report = audit_layout(project, content, build_dir, page_sizes)
    findings += [{"check": "layout", "detail": issue} for issue in layout_report["findings"]]
    write_json(project_dir / "qa" / "layout_report.json", layout_report)
    review_path = project_dir / "review.json"
    review_current = None
    if review_path.is_file():
        review_status = "existing"
        try:
            review_current = read_json(review_path).get("build_fingerprint") == recorded
        except EngineError as exc:
            review_status = "unreadable"
            findings.append({"check": "review", "detail": str(exc)})
    else:
        write_json(review_path, review_scaffold(project, recorded, output_pages))
        review_status, review_current = "created", True
    write_json(project_dir / "review-template.json", review_scaffold(project, recorded, output_pages))
    if findings or not review_current:
        project["status"] = "draft"
        write_json(project_dir / "project.json", project)

    report = {"schema_version": SCHEMA_VERSION, "command": "qa",
              "status": "pass" if not findings else "fail",
              "project_status": project.get("status"), "build_fingerprint": recorded,
              "fingerprint_mismatches": mismatches, "log_diagnostics": diagnostics,
              "expectations": expectations_checks, "preview_pages": preview_pages,
              "output_pages": output_pages,
              "raster_occurrences": {"output": sum(observed_rasters.values()),
                                     "explicit_source_raster_uses": sum(allowed_rasters.values())},
              "native_runtime_proxy": {"occurrences": sum(d["occurrences"] for d in native_runtime_exempt),
                                       "source_form_ids": sorted({d["asset"] for d in native_runtime_exempt}),
                                       "pages": native_runtime_exempt,
                                       "refused": native_runtime_refused},
              "review": {"status": review_status, "fingerprint_current": review_current},
              "layout": layout_report,
              "findings": findings}
    write_json(project_dir / "qa" / "qa_report.json", report)
    if findings:
        raise EngineError(f"qa failed with {len(findings)} finding(s); report: "
                          f"{project_dir / 'qa' / 'qa_report.json'}")
    return report


# ------------------------------------------------------------------------- release

def check_page_list(entries, expected, label) -> list:
    if not isinstance(entries, list):
        return [f"{label} must be a list of {{page, checked}} entries"]
    problems, seen = [], []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("page"), int) \
                or isinstance(item.get("page"), bool):
            problems.append(f"{label}: every entry needs an integer page")
            continue
        seen.append(item["page"])
        if item.get("checked") is not True:
            problems.append(f"{label}: page {item['page']} is not checked")
    if len(seen) != len(set(seen)):
        problems.append(f"{label}: duplicate page entries")
    if sorted(set(expected) - set(seen)):
        problems.append(f"{label}: missing pages {sorted(set(expected) - set(seen))}")
    if sorted(set(seen) - set(expected)):
        problems.append(f"{label}: unexpected pages {sorted(set(seen) - set(expected))}")
    return problems


def check_review(review, build_fingerprint, project, output_pages) -> list:
    if not isinstance(review, dict):
        return ["review.json must be a JSON object"]
    problems = []
    if review.get("build_fingerprint") != build_fingerprint:
        problems.append("review is bound to a different build fingerprint; the project was rebuilt, "
                        "so a fresh human review is required")
    problems += check_page_list(review.get("source_pages"), project["pages"], "source_pages")
    problems += check_page_list(review.get("output_pages"), list(range(1, output_pages + 1)),
                                "output_pages")
    if review.get("translation_checked") is not True:
        problems.append("translation_checked must be true")
    if review.get("formula_table_checked") is not True:
        problems.append("formula_table_checked must be true")
    if not isinstance(review.get("issues"), list):
        problems.append("issues must be a list")
    elif review["issues"]:
        problems.append(f"issues must be empty ({len(review['issues'])} unresolved)")
    if not (isinstance(review.get("reviewer"), str) and review["reviewer"].strip()):
        problems.append("reviewer must name the human reviewer")
    return problems


def zip_deliverable(deliverable: Path, zip_path: Path) -> None:
    entries = sorted(p for p in deliverable.rglob("*") if p.is_file())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in entries:
            info = zipfile.ZipInfo(path.relative_to(deliverable).as_posix(),
                                   date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def release(project_dir, templates_dir=None) -> dict:
    ensure_ram()
    fitz = load_fitz()
    project_dir = Path(project_dir).expanduser().resolve()
    project = load_project(project_dir)
    templates_dir = resolve_templates_dir(project, templates_dir)
    report = qa(project_dir, templates_dir=templates_dir)  # release always re-runs qa

    # A partial draft may compile, but it must never be released: pending pages are exactly
    # the evidence that has not been authored yet.
    content = read_json(project_dir / "content.json")
    pending = content.get("pending_pages") or []
    if pending:
        project["status"] = "draft"
        write_json(project_dir / "project.json", project)
        shown = ", ".join(str(p) for p in sorted(pending)[:20])
        raise EngineError(f"release blocked (project stays draft): {len(pending)} page(s) still "
                          f"declared pending and unauthored: {shown}"
                          + (" ..." if len(pending) > 20 else ""))

    recorded = report["build_fingerprint"]
    output_pages = report["output_pages"]
    review_path = project_dir / "review.json"
    if not review_path.is_file():
        raise EngineError("review.json missing; run qa to scaffold it, then complete the review")
    problems = check_review(read_json(review_path), recorded, project, output_pages)
    if problems:
        project["status"] = "draft"
        write_json(project_dir / "project.json", project)
        raise EngineError("release blocked (project stays draft):\n- " + "\n- ".join(problems))

    previous_status = project.get("status")
    project["status"] = "completed"
    write_json(project_dir / "project.json", project)
    try:
        deliverable = project_dir / "deliverable"
        if deliverable.exists():
            if not deliverable.resolve().is_relative_to(project_dir):
                raise EngineError("deliverable resolves outside the project; refusing recursive deletion")
            shutil.rmtree(deliverable)
        for sub in ("assets", "qa", "packet/pages"):
            (deliverable / sub).mkdir(parents=True)
        assets = load_assets(project_dir)
        shutil.copyfile(project_dir / "build" / "main.pdf", deliverable / "main.pdf")
        shutil.copyfile(project_dir / "build" / "main.tex", deliverable / "main.tex")
        for name in TEMPLATE_FILES:
            shutil.copyfile(templates_dir / name, deliverable / name)
        for rel in literal_files(read_json(project_dir / "content.json")):
            (deliverable / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_dir / "build" / rel, deliverable / rel)
        for entry in assets.values():
            (deliverable / entry["path"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_dir / entry["path"], deliverable / entry["path"])
            if isinstance(entry.get("redraw"), dict):
                for key in ("spec_path", "tex_path"):
                    path = entry["redraw"][key]
                    (deliverable / path).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(project_dir / path, deliverable / path)
                code_dir = deliverable / "engine"
                code_dir.mkdir(exist_ok=True)
                shutil.copyfile(Path(__file__).with_name("redraw.py"), code_dir / "redraw.py")
        if any(e.get("kind") == "source_pdf" or e.get("source_pdf_recipe") is True
               or e.get("crop_method") == SOURCE_FORM_CROP_METHOD for e in assets.values()):
            code_dir = deliverable / "engine"
            code_dir.mkdir(exist_ok=True)
            shutil.copyfile(Path(__file__).with_name("source_pdf_objects.py"), code_dir / "source_pdf_objects.py")
            if any(isinstance(entry, dict) and entry.get("crop_method") == SOURCE_FORM_CROP_METHOD
                   for entry in assets.values()):
                shutil.copyfile(Path(__file__).with_name("native_shading_qa.py"), code_dir / "native_shading_qa.py")
        for page_no in project["pages"]:
            name = f"p{page_no:04d}.json"
            shutil.copyfile(project_dir / "packet" / "pages" / name, deliverable / "packet" / "pages" / name)
        for name in ("assets.json",):
            shutil.copyfile(project_dir / name, deliverable / name)
        if (project_dir / "source_inventory.json").is_file():
            shutil.copyfile(project_dir / "source_inventory.json", deliverable / "source_inventory.json")
        shutil.copyfile(project_dir / "build" / "fingerprint.json", deliverable / "build_fingerprint.json")
        shutil.copyfile(project_dir / "build" / "main.log", deliverable / "qa" / "main.log")
        if (project_dir / "build" / "main.aux").is_file():
            shutil.copyfile(project_dir / "build" / "main.aux", deliverable / "qa" / "layout_positions.aux")
        shutil.copyfile(project_dir / "qa" / "layout_report.json", deliverable / "qa" / "layout_report.json")
        shutil.copyfile(project_dir / "content.json", deliverable / "content.json")
        shutil.copyfile(project_dir / "qa" / "qa_report.json", deliverable / "qa" / "qa_report.json")
        shutil.copyfile(review_path, deliverable / "review.json")
        shutil.copyfile(project_dir / "project.json", deliverable / "project.json")
        write_json(deliverable / "manifest.json",
                   {"schema_version": SCHEMA_VERSION, "build_fingerprint": recorded,
                    "files": [{"path": p.relative_to(deliverable).as_posix(), "sha256": sha256_file(p)}
                              for p in sorted(f for f in deliverable.rglob("*") if f.is_file())]})
        zip_path = project_dir / "deliverable.zip"
        zip_deliverable(deliverable, zip_path)
        write_text(project_dir / "deliverable.zip.sha256", f"{sha256_file(zip_path)}  deliverable.zip\n")
    except BaseException:
        project["status"] = previous_status
        write_json(project_dir / "project.json", project)
        raise
    return {"command": "release", "project": str(project_dir), "status": "completed",
            "build_fingerprint": recorded, "output_pages": output_pages,
            "deliverable": str(project_dir / "deliverable"), "zip": str(project_dir / "deliverable.zip"),
            "zip_sha256": sha256_file(project_dir / "deliverable.zip")}


# -------------------------------------------------------------------------- doctor

def doctor(templates_dir=None) -> dict:
    report = {"schema_version": SCHEMA_VERSION, "command": "doctor",
              "python": {"executable": sys.executable, "version": sys.version.split()[0]}}
    try:
        import fitz as fitz_module
        report["pymupdf"] = {"available": True, "version": getattr(fitz_module, "__version__", "unknown"),
                             "clip_to_rect": hasattr(fitz_module.Page, "clip_to_rect"),
                             "set_cropbox": hasattr(fitz_module.Page, "set_cropbox")}
    except ImportError as exc:  # pragma: no cover - environment dependent
        report["pymupdf"] = {"available": False, "error": str(exc), "clip_to_rect": False,
                             "set_cropbox": False}
    xelatex = resolve_xelatex()
    report["xelatex"] = {"found": bool(xelatex), "command": xelatex,
                         "legacy_path": str(XELATEX_LEGACY) if XELATEX_LEGACY else None}
    try:
        available = available_physical_memory()
    except OSError:  # pragma: no cover - defensive
        available = None
    report["memory"] = {"available_bytes": available, "required_bytes": RAM_MINIMUM,
                        "ok": available is not None and available >= RAM_MINIMUM}
    try:
        directory = resolve_templates_dir(None, templates_dir)
        report["templates"] = {"directory": str(directory), "files": template_hashes(directory), "ok": True}
    except EngineError as exc:
        report["templates"] = {"directory": str(templates_dir or find_repo_root() / "templates"),
                               "files": {}, "ok": False, "error": str(exc)}
    report["ok"] = bool(report["pymupdf"]["available"] and report["xelatex"]["found"]
                        and report["memory"]["ok"] and report["templates"]["ok"]
                        and report["pymupdf"]["clip_to_rect"])
    return report


# ----------------------------------------------------------------------------- cli

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="native-forge", description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="report environment state")
    prepare_parser = subparsers.add_parser("prepare", help="extract a read-only source packet")
    prepare_parser.add_argument("--source", required=True)
    prepare_parser.add_argument("--pages", required=True)
    prepare_parser.add_argument("--project", required=True)
    prepare_parser.add_argument("--title", required=True)
    asset_parser = subparsers.add_parser("asset", help="register a figure asset from the source")
    asset_parser.add_argument("--project", required=True)
    asset_parser.add_argument("--page", type=int, required=True)
    asset_parser.add_argument("--bbox", nargs=4, type=float, required=True,
                              metavar=("X0", "Y0", "X1", "Y1"))
    asset_parser.add_argument("--name", required=True)
    asset_parser.add_argument("--kind", choices=ASSET_CROP_KINDS, default="vector_pdf")
    asset_parser.add_argument("--figure-kind", choices=("photograph", "plot", "schematic", "mixed", "qr_code"), default="mixed")
    redraw_parser = subparsers.add_parser("redraw", help="rebuild a figure as native vector graphics")
    redraw_parser.add_argument("--project", required=True)
    redraw_parser.add_argument("--spec", required=True)
    redraw_parser.add_argument("--name", required=True)
    for name in ("build", "qa", "release"):
        subparsers.add_parser(name, help=f"run {name}").add_argument("--project", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = doctor()
            print(canonical_json(report), end="")
            return 0 if report["ok"] else 1
        if args.command == "prepare":
            result = prepare(args.source, args.pages, args.project, args.title)
        elif args.command == "asset":
            result = asset(args.project, args.page, args.bbox, args.name, args.kind, args.figure_kind)
        elif args.command == "redraw":
            return subprocess.call([sys.executable, str(Path(__file__).with_name("redraw.py")),
                                    "--project", args.project, "--spec", args.spec, "--name", args.name])
        elif args.command == "build":
            result = build(args.project)
        elif args.command == "qa":
            result = qa(args.project)
        else:
            result = release(args.project)
    except EngineError as exc:
        print(f"native-forge: ERROR: {exc}", file=sys.stderr)
        return 1
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
