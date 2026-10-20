#!/usr/bin/env python3
"""redraw.py -- native vector figure redraw module for the Native Forge workflow.

CLI: redraw.py --project DIR --spec spec.json --name ID   (--spec also takes an inline JSON object)

Validates an agent-authored figure spec (type xy_plot | flowchart | tikz | chemfig) against the
project contract (docs/design.md), renders it into a standalone Chinese-capable XeLaTeX document,
compiles it with two shell-escape-free passes, verifies the PDF contains no raster objects and
neither missing glyphs nor overfull boxes, and registers it in assets.json as a native_pdf asset
bound to the source page, bbox and full spec/tex/code/source provenance.  Only the standard
library, PyMuPDF and the native_forge helpers are used; no Python from the spec is ever evaluated.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import native_forge as nf

REDRAW_TYPES = ("xy_plot", "flowchart", "tikz", "chemfig")
SERIES_TYPES = ("line", "scatter")
FUNCTION_KINDS = ("sin", "cos")
SHAPES = ("rectangle", "ellipse", "diamond")
MARKS = ("o", "*", "square*", "triangle*")
COLORS = ("blue", "red", "green", "black", "orange", "purple", "cyan", "gray")
COLOR_MIX = re.compile("^(?:" + "|".join(COLORS) + r")!(?:100|[1-9]?\d)$")
NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
PT_WIDTH_RE = re.compile(r"^(\d+(?:\.\d+)?)pt$")
DOCUMENT_ENV = re.compile(r"\\(?:begin|end)\{document\}")
MIN_CM, MAX_CM = 1.0, 30.0
MIN_PT, MAX_PT = 0.1, 10.0
DEFAULT_SAMPLES, MIN_SAMPLES, MAX_SAMPLES = 201, 10, 1000
DEFAULT_WIDTH_CM, DEFAULT_HEIGHT_CM = 10.0, 7.0
BLOCKING_DIAGNOSTICS = ("fatal", "missing_character", "overfull", "undefined")


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number(value, low, high) -> bool:
    return _finite(value) and low <= value <= high


def fmt_num(value) -> str:
    """Deterministic finite decimal for TeX output; scientific notation is never emitted."""
    text = f"{float(value):.10g}"
    if "e" in text or "E" in text:
        text = f"{float(value):.10f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0", "-0.0") else text


# --------------------------------------------------------------------------- validation

def validate_xy_plot(spec) -> list:
    problems = []
    for key in ("xlim", "ylim"):
        value = spec.get(key)
        if not (isinstance(value, list) and len(value) == 2 and all(_finite(v) for v in value)
                and value[0] < value[1]):
            problems.append(f"spec.{key} must be [lo, hi] with finite numbers and lo < hi")
    for key in ("xlabel", "ylabel"):
        if not (isinstance(spec.get(key), str) and spec[key].strip()):
            problems.append(f"spec.{key} must be a non-empty TeX string")
    for key, fallback in (("width_cm", DEFAULT_WIDTH_CM), ("height_cm", DEFAULT_HEIGHT_CM)):
        if not _number(spec.get(key, fallback), MIN_CM, MAX_CM):
            problems.append(f"spec.{key} must be a number within [{MIN_CM:g}, {MAX_CM:g}]")
    if "grid" in spec and not isinstance(spec["grid"], bool):
        problems.append("spec.grid must be true or false")
    series = spec.get("series")
    if not (isinstance(series, list) and series):
        problems.append("spec.series must be a non-empty list")
        return problems
    for index, item in enumerate(series):
        problems += validate_series(item, index)
    return problems


def validate_series(item, index) -> list:
    where = f"spec.series[{index}]"
    if not isinstance(item, dict):
        return [f"{where} must be an object"]
    problems = []
    if item.get("type") not in SERIES_TYPES:
        problems.append(f"{where}.type {item.get('type')!r} must be one of {SERIES_TYPES}")
    has_points, has_function = "points" in item, "function" in item
    if has_points == has_function:
        problems.append(f"{where} must carry exactly one of points or function")
    elif has_points:
        points = item["points"]
        if not (isinstance(points, list) and points):
            problems.append(f"{where}.points must be a non-empty list of [x, y] pairs")
        else:
            for pair_index, pair in enumerate(points):
                if not (isinstance(pair, list) and len(pair) == 2 and all(_finite(v) for v in pair)):
                    problems.append(f"{where}.points[{pair_index}] must be [x, y] with finite numbers")
    else:
        if item.get("type") != "line":
            problems.append(f"{where}: function series must be a line; scatter needs source points")
        problems += validate_function(item["function"], where)
    color = item.get("color", "black")
    if not (isinstance(color, str) and (color in COLORS or COLOR_MIX.fullmatch(color))):
        problems.append(f"{where}.color must be one of {COLORS} or a NAME!0-100 mix")
    if "label" in item and not (isinstance(item["label"], str) and item["label"].strip()):
        problems.append(f"{where}.label must be a non-empty TeX string")
    width = item.get("line_width", "1pt")
    if isinstance(width, str):
        match = PT_WIDTH_RE.fullmatch(width)
        ok = bool(match) and _number(float(match.group(1)), MIN_PT, MAX_PT)
    else:
        ok = _number(width, MIN_PT, MAX_PT)
    if not ok:
        problems.append(f"{where}.line_width must be a width in pt within [{MIN_PT:g}, {MAX_PT:g}]")
    if item.get("mark", item.get("scattermark", "o")) not in MARKS:
        problems.append(f"{where}.mark must be one of {MARKS}")
    return problems


def validate_function(function, where) -> list:
    where = f"{where}.function"
    if not isinstance(function, dict):
        return [f"{where} must be an object"]
    problems = []
    if function.get("kind") not in FUNCTION_KINDS:
        problems.append(f"{where}.kind must be one of {FUNCTION_KINDS}")
    for key in ("amplitude", "angular_frequency", "phase", "offset"):
        if not _finite(function.get(key)):
            problems.append(f"{where}.{key} must be a finite number")
    samples = function.get("samples", DEFAULT_SAMPLES)
    if not (isinstance(samples, int) and not isinstance(samples, bool)
            and MIN_SAMPLES <= samples <= MAX_SAMPLES):
        problems.append(f"{where}.samples must be an integer within [{MIN_SAMPLES}, {MAX_SAMPLES}]")
    return problems


def validate_flowchart(spec) -> list:
    problems = []
    nodes = spec.get("nodes")
    if not (isinstance(nodes, list) and nodes):
        problems.append("spec.nodes must be a non-empty list")
        nodes = []
    ids = []
    for index, node in enumerate(nodes):
        where = f"spec.nodes[{index}]"
        if not isinstance(node, dict):
            problems.append(f"{where} must be an object")
            continue
        node_id = node.get("id")
        if not (isinstance(node_id, str) and NODE_ID_RE.fullmatch(node_id)):
            problems.append(f"{where}.id must use letters, digits, '_' or '-'")
        elif node_id in ids:
            problems.append(f"{where}.id {node_id!r} is a duplicate node id")
        else:
            ids.append(node_id)
        if not (isinstance(node.get("label"), str) and node["label"].strip()):
            problems.append(f"{where}.label must be a non-empty TeX string")
        for key in ("x", "y"):
            if not _number(node.get(key), -100.0, 100.0):
                problems.append(f"{where}.{key} must be a finite number within [-100, 100]")
        if node.get("shape") not in SHAPES:
            problems.append(f"{where}.shape {node.get('shape')!r} must be one of {SHAPES}")
    edges = spec.get("edges", [])
    if not isinstance(edges, list):
        problems.append("spec.edges must be a list")
        edges = []
    for index, edge in enumerate(edges):
        where = f"spec.edges[{index}]"
        if not isinstance(edge, dict):
            problems.append(f"{where} must be an object")
            continue
        for key in ("from", "to"):
            if edge.get(key) not in ids:
                problems.append(f"{where}.{key} {edge.get(key)!r} does not reference a known node id")
        if edge.get("from") == edge.get("to") and edge.get("from") in ids:
            problems.append(f"{where} is a self-loop; an edge must join two nodes")
        if "label" in edge and not (isinstance(edge["label"], str) and edge["label"].strip()):
            problems.append(f"{where}.label must be a non-empty TeX string")
    return problems


def validate_raw_tex(spec, kind) -> list:
    tex = spec.get("tex")
    if not (isinstance(tex, str) and tex.strip()):
        return [f"spec.tex must be non-empty {kind} body TeX"]
    problems = []
    if DOCUMENT_ENV.search(tex):
        problems.append("spec.tex must be body-only: \\begin{document}/\\end{document} are forbidden")
    required = "\\begin{tikzpicture}" if kind == "tikz" else "\\chemfig"
    if required not in tex:
        problems.append(f"spec.tex must contain {required!r}")
    return problems


def validate_spec(spec, project) -> str:
    """Return the figure type, or raise EngineError listing every contract violation."""
    if not isinstance(spec, dict):
        raise nf.EngineError("spec must be a JSON object")
    problems = []
    nf._scan_forbidden(spec, "spec", problems)
    kind = spec.get("type")
    if kind not in REDRAW_TYPES:
        problems.append(f"spec.type {kind!r} must be one of {REDRAW_TYPES}")
    page = spec.get("source_page")
    if not (isinstance(page, int) and not isinstance(page, bool) and page >= 1):
        problems.append("spec.source_page must be a positive integer")
    elif page not in project["pages"]:
        problems.append(f"spec.source_page {page} is not among the prepared pages {project['pages']}")
    bbox = spec.get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(_finite(v) for v in bbox)):
        problems.append("spec.bbox must be [x0, y0, x1, y1] with four finite numbers")
    elif not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        problems.append("spec.bbox must satisfy x0 < x1 and y0 < y1")
    if not (isinstance(spec.get("rationale"), str) and spec["rationale"].strip()):
        problems.append("spec.rationale must be a non-empty string")
    if kind == "xy_plot":
        problems += validate_xy_plot(spec)
    elif kind == "flowchart":
        problems += validate_flowchart(spec)
    elif kind in ("tikz", "chemfig"):
        problems += validate_raw_tex(spec, kind)
    if problems:
        raise nf.EngineError("spec invalid:\n- " + "\n- ".join(problems[:25]))
    return kind


# ---------------------------------------------------------------------------- rendering

def series_points(item, xlim) -> list:
    """Finite [x, y] pairs; function series sample math.sin/math.cos over xlim (no eval)."""
    if "points" in item:
        return [(float(x), float(y)) for x, y in item["points"]]
    function = item["function"]
    low, high = float(xlim[0]), float(xlim[1])
    samples = function.get("samples", DEFAULT_SAMPLES)
    step = (high - low) / (samples - 1)
    trig = math.sin if function["kind"] == "sin" else math.cos
    points = []
    for index in range(samples):
        x = low + index * step
        angle = function["angular_frequency"] * x + function["phase"]
        value = trig(angle) if math.isfinite(angle) else math.nan
        y = function["offset"] + function["amplitude"] * value
        if not (math.isfinite(x) and math.isfinite(y)):
            raise nf.EngineError("function series produced a non-finite coordinate; "
                                 "amplitude/angular_frequency are too large")
        points.append((x, y))
    return points


def width_to_pt(value) -> str:
    if isinstance(value, str):
        return fmt_num(float(PT_WIDTH_RE.fullmatch(value).group(1)))
    return fmt_num(value)


def render_xy_plot(spec) -> str:
    xlim, ylim = spec["xlim"], spec["ylim"]
    options = [f"width={fmt_num(spec.get('width_cm', DEFAULT_WIDTH_CM))}cm",
               f"height={fmt_num(spec.get('height_cm', DEFAULT_HEIGHT_CM))}cm",
               f"xmin={fmt_num(xlim[0])}", f"xmax={fmt_num(xlim[1])}",
               f"ymin={fmt_num(ylim[0])}", f"ymax={fmt_num(ylim[1])}",
               f"xlabel={{{spec['xlabel']}}}", f"ylabel={{{spec['ylabel']}}}"]
    if spec.get("grid"):
        options.append("grid=major")
    lines = ["\\begin{tikzpicture}", "\\begin{axis}[" + ", ".join(options) + "]"]
    legend = any(item.get("label") for item in spec["series"])
    for item in spec["series"]:
        style = [f"color={item.get('color', 'black')}"]
        if item["type"] == "scatter":
            style += ["only marks", f"mark={item.get('mark', item.get('scattermark', 'o'))}"]
        else:
            style.append(f"line width={width_to_pt(item.get('line_width', '1pt'))}pt")
        coordinates = " ".join(f"({fmt_num(x)},{fmt_num(y)})" for x, y in series_points(item, xlim))
        lines.append("\\addplot[" + ", ".join(style) + "] coordinates {" + coordinates + "};")
        if legend:
            lines.append(f"\\addlegendentry{{{item.get('label', '')}}}")
    lines += ["\\end{axis}", "\\end{tikzpicture}"]
    return "\n".join(lines)


def render_flowchart(spec) -> str:
    lines = ["\\begin{tikzpicture}"]
    for node in spec["nodes"]:
        lines.append(f"\\node[draw, {node['shape']}] ({node['id']}) at "
                     f"({fmt_num(node['x'])}cm,{fmt_num(node['y'])}cm) {{{node['label']}}};")
    for edge in spec.get("edges", []):
        label = f" node[midway, above, font=\\small] {{{edge['label']}}}" if edge.get("label") else ""
        lines.append(f"\\draw[-{{Latex}}] ({edge['from']}) --{label} ({edge['to']});")
    lines.append("\\end{tikzpicture}")
    return "\n".join(lines)


def build_document(kind, spec, body) -> str:
    lines = ["% Generated by engine/redraw.py from the registered spec; do not edit by hand.",
             "\\documentclass[tikz,border=3pt,10pt]{standalone}",
             "\\usepackage[UTF8,fontset=windows]{ctex}",
             "\\usepackage{pgfplots}",
             "\\pgfplotsset{compat=1.18}",
             "\\pagestyle{empty}"]
    if kind in ("flowchart", "tikz"):
        lines.append("\\usetikzlibrary{shapes.geometric, arrows.meta}")
    if kind == "chemfig":
        lines.append("\\usepackage{chemfig}")
    lines += ["\\begin{document}", "\\noindent", body, "\\end{document}"]
    return "\n".join(lines) + "\n"


def render_figure(kind, spec) -> str:
    if kind == "xy_plot":
        body = render_xy_plot(spec)
    elif kind == "flowchart":
        body = render_flowchart(spec)
    else:
        body = spec["tex"]
    return build_document(kind, spec, body)


# ------------------------------------------------------------------------------ compile

def compile_figure(work_dir) -> None:
    command = nf.resolve_xelatex()
    if not command:
        raise nf.EngineError("xelatex not found on PATH and not at " + str(nf.XELATEX_LEGACY))
    work_dir, returncode = Path(work_dir), 0
    compile_env = os.environ.copy()
    compile_env.update({"SOURCE_DATE_EPOCH": "946684800", "FORCE_SOURCE_DATE": "1", "TZ": "UTC"})
    for pass_no in (1, 2):
        nf.ensure_ram()
        try:
            proc = subprocess.run([*command, *nf.XELATEX_FLAGS, "figure.tex"], cwd=str(work_dir),
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=nf.XELATEX_TIMEOUT, env=compile_env)
        except subprocess.TimeoutExpired as exc:
            raise nf.EngineError(f"xelatex timed out after {nf.XELATEX_TIMEOUT}s; log preserved at "
                                 f"{work_dir / 'figure.log'}") from exc
        except OSError as exc:
            raise nf.EngineError(f"cannot run xelatex ({command[0]}): {exc}") from exc
        returncode = proc.returncode
        nf.write_text(work_dir / f"pass-{pass_no}.stdout.txt", proc.stdout + "\n" + proc.stderr)
        if returncode != 0:
            break
    if returncode != 0 or not (work_dir / "figure.pdf").is_file():
        raise nf.EngineError(f"xelatex failed (exit {returncode}); log preserved at "
                             f"{work_dir / 'figure.log'}\n" + nf.log_tail(work_dir / "figure.log"))


def verify_figure(work_dir, fitz) -> None:
    """The PDF must be vector-only (no raster objects) and the log free of blocking diagnostics."""
    work_dir = Path(work_dir)
    pdf_path = work_dir / "figure.pdf"
    problems = nf.inspect_native_pdf(pdf_path, f"redraw {work_dir.name}", fitz)
    diagnostics = nf.scan_compile_log(work_dir / "figure.log")
    problems += [f"{category}: {diagnostics[category][0]}" for category in BLOCKING_DIAGNOSTICS
                 if diagnostics[category]]
    if problems:
        pdf_path.unlink(missing_ok=True)
        raise nf.EngineError("figure failed vector verification:\n- " + "\n- ".join(problems))


# ------------------------------------------------------------------------------- driver

def load_spec(spec_arg):
    """Accept a spec JSON file path, or the JSON object itself (--spec '{...}')."""
    text = str(spec_arg).strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except ValueError as exc:
            raise nf.EngineError(f"--spec is not valid JSON: {exc}") from exc
    path = Path(spec_arg)
    if path.is_file():
        return nf.read_json(path)
    raise nf.EngineError(f"spec file not found: {spec_arg}")


def redraw(project_dir, spec_path, name) -> dict:
    nf.ensure_ram()
    fitz = nf.load_fitz()
    project_dir = Path(project_dir).expanduser().resolve()
    project = nf.load_project(project_dir)
    code_hash = nf.sha256_file(__file__)
    if not nf.NAME_RE.match(name or ""):
        raise nf.EngineError(f"invalid asset name {name!r}; use letters, digits, '.', '-', '_'")
    spec = load_spec(spec_path)
    kind = validate_spec(spec, project)
    source = Path(project["source"]["path"])
    if not source.is_file() or nf.sha256_file(source) != project["source"]["sha256"]:
        raise nf.EngineError("source PDF changed since prepare; re-run prepare")
    with fitz.open(source) as source_doc:
        if not source_doc[spec["source_page"] - 1].rect.contains(fitz.Rect(spec["bbox"])):
            raise nf.EngineError("redraw source bbox lies outside its source page")
    assets = nf.load_assets(project_dir)
    work_dir = project_dir / "redraw" / name
    if name in assets:
        raise nf.EngineError(f"asset id {name!r} already declared in assets.json; refusing to overwrite")
    if (work_dir / "figure.pdf").exists():
        raise nf.EngineError(f"{work_dir / 'figure.pdf'} already exists; refusing to overwrite")
    work_dir.mkdir(parents=True, exist_ok=True)
    nf.write_json(work_dir / "spec.json", spec)
    nf.write_text(work_dir / "figure.tex", render_figure(kind, spec))
    compile_figure(work_dir)
    verify_figure(work_dir, fitz)
    if nf.sha256_file(source) != project["source"]["sha256"] or nf.sha256_file(__file__) != code_hash:
        raise nf.EngineError("redraw source or engine changed during compilation; rerun")
    metadata = {"type": kind,
                "spec_path": f"redraw/{name}/spec.json",
                "spec_sha256": nf.sha256_file(work_dir / "spec.json"),
                "tex_path": f"redraw/{name}/figure.tex",
                "tex_sha256": nf.sha256_file(work_dir / "figure.tex"),
                "engine_sha256": nf.sha256_file(Path(__file__)),
                "source_sha256": nf.sha256_file(source)}
    metadata["redraw_sha256"] = nf.stable_sha256(metadata)  # binds spec/tex/code/source
    entry = {"path": f"redraw/{name}/figure.pdf", "kind": "native_pdf", "role": "figure",
             "source_page": spec["source_page"], "bbox": nf.round3(spec["bbox"]),
             "rationale": spec["rationale"],
             "sha256": nf.sha256_file(work_dir / "figure.pdf"),
             "redraw": metadata}
    assets[name] = entry
    nf.write_json(project_dir / "assets.json", assets)
    return {"command": "redraw", "asset": name, "type": kind, "pdf": entry["path"],
            "sha256": entry["sha256"], **{k: metadata[k] for k in
                                          ("spec_path", "spec_sha256", "tex_path", "tex_sha256",
                                           "engine_sha256", "source_sha256", "redraw_sha256")}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="redraw", description=__doc__.splitlines()[0])
    parser.add_argument("--project", required=True, help="project directory (must be prepared)")
    parser.add_argument("--spec", required=True, help="path to the figure spec JSON (or inline JSON)")
    parser.add_argument("--name", required=True, help="asset id to register in assets.json")
    args = parser.parse_args(argv)
    try:
        result = redraw(args.project, args.spec, args.name)
    except nf.EngineError as exc:
        print(f"redraw: ERROR: {exc}", file=sys.stderr)
        return 1
    print(nf.canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
