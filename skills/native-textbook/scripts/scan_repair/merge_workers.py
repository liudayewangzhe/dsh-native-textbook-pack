"""Merge per-page worker transcriptions into source_inventory.json + content.json.

Worker shards live in D:\\native-forge-work\\inbox\\pNNNN.json (see WORKER_CONTRACT.md).
Everything else in the project is derived from them, so this script is the single
place where page evidence becomes engine input.

Usage:  python merge_workers.py [--pages 23-27] [--allow-pending]
"""
import argparse
import json
import re
import sys
from pathlib import Path

PROJECT = Path(r"E:\PDF\_ZH\native-forge\projects\cpp-zh")
INBOX = Path(r"D:\native-forge-work\inbox")
OBJECT_KINDS = ("paragraph", "equation", "table", "figure", "heading", "header_footer", "code")
BLOCK_KINDS = ("chapter", "section", "subsection", "paragraph", "equation", "table",
               "figure", "figure_native", "code", "console")
CJK = r"\u3000-\u303f\u4e00-\u9fff\uff00-\uffef"
TAG_RE = re.compile(r"\\tag\{([^}]*)\}")


def parse_pages(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def normalize_tex(tex: str) -> str:
    """Chinese typography cleanup: no hand-typed space at CJK<->Latin/number boundaries."""
    if not isinstance(tex, str):
        return tex
    tex = re.sub(r"(?<=[" + CJK + r"])[ \t]+(?=[0-9A-Za-z\\$])", "", tex)
    tex = re.sub(r"(?<=[0-9A-Za-z\)\]\}])[ \t]+(?=[" + CJK + r"])", "", tex)
    tex = re.sub(r"[ \t]{2,}", " ", tex)
    # A control word immediately followed by a CJK character is swallowed as part of the
    # control sequence name under some catcode setups ("\quad三角" -> undefined \quad三角).
    tex = re.sub(r"(\\[a-zA-Z]+)(?=[" + CJK + r"])", r"\1{}", tex)
    return tex.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", default="", help="override page list, e.g. 23-27")
    ap.add_argument("--allow-pending", action="store_true",
                    help="write pending_pages for shards that do not exist yet")
    args = ap.parse_args()

    project = json.loads((PROJECT / "project.json").read_text(encoding="utf-8"))
    pages = parse_pages(args.pages) if args.pages else project["pages"]
    sha = project["source"]["sha256"]

    inventory_pages, blocks, exclusions, pending, unresolved = {}, [], [], [], []
    figure_requests, table_requests = [], []
    missing_shards = []

    for pno in pages:
        packet_path = PROJECT / "packet" / "pages" / f"p{pno:04d}.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        W, H = packet["width"], packet["height"]
        shard_path = INBOX / f"p{pno:04d}.json"
        if not shard_path.is_file():
            missing_shards.append(pno)
            pending.append(pno)
            continue
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        if shard.get("blank"):
            inventory_pages[str(pno)] = {"blank": True, "checked": True,
                                         "reason": shard.get("notes", "空白页")[:200]}
            continue
        objects = shard.get("objects") or []
        described = {}
        for fig in shard.get("figures") or []:
            described[fig.get("source_id")] = fig.get("description") or fig.get("caption") or ""
        for tab in shard.get("tables") or []:
            described.setdefault(tab.get("source_id"), tab.get("caption") or "表格")
        used = set()
        inv_objects = []
        for obj in objects:
            oid, kind, text = obj.get("id"), obj.get("kind"), obj.get("text", "")
            if not str(text).strip():
                text = described.get(oid, "")
            if not oid or kind not in OBJECT_KINDS or not str(text).strip():
                unresolved.append(f"p{pno:04d}: invalid object {obj!r}"[:200])
                continue
            bbox = obj.get("bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                unresolved.append(f"p{pno:04d} {oid}: missing bbox")
                continue
            x0, y0, x1, y1 = (float(v) for v in bbox)
            pts = [round(min(x0, x1) * W, 2), round(min(y0, y1) * H, 2),
                   round(max(x0, x1) * W, 2), round(max(y0, y1) * H, 2)]
            pts[0] = max(0.0, min(pts[0], W - 0.5))
            pts[2] = max(pts[0] + 0.5, min(pts[2], W))
            pts[1] = max(0.0, min(pts[1], H - 0.5))
            pts[3] = max(pts[1] + 0.5, min(pts[3], H))
            entry = {"id": oid, "page": pno, "kind": kind, "text": str(text), "bbox": pts}
            for key in ("continues_next", "continues_prev"):
                if obj.get(key):
                    entry[key] = True
            inv_objects.append(entry)
        inventory_pages[str(pno)] = {"objects": inv_objects}
        obj_by_id = {o["id"]: o for o in inv_objects}

        for blk in shard.get("blocks") or []:
            kind = blk.get("kind")
            if kind not in BLOCK_KINDS:
                unresolved.append(f"p{pno:04d} {blk.get('id')}: bad kind {kind!r}")
                continue
            sids = [s for s in (blk.get("source_ids") or []) if s in obj_by_id]
            if not sids:
                unresolved.append(f"p{pno:04d} {blk.get('id')}: no valid source_ids")
                continue
            used.update(sids)
            new = {"id": blk["id"], "kind": kind, "source_ids": sids}
            for key in ("tex", "text", "numbered", "asset", "caption", "number", "width",
                        "placement", "layout", "span", "join_next", "keep_with_next",
                        "asset_kind", "figure_kind", "figure_number", "link_uri",
                        "continues_next", "continues_prev"):
                if key in blk:
                    new[key] = normalize_tex(blk[key]) if key == "tex" else blk[key]
            fk = new.get("figure_kind")
            if isinstance(fk, str) and fk not in ("photograph", "plot", "schematic",
                                                  "mixed", "qr_code"):
                new["figure_kind"] = {"diagram": "schematic", "line_art": "schematic",
                                      "flowchart": "schematic", "chart": "plot",
                                      "graph": "plot", "circuit": "schematic",
                                      "photo": "photograph", "image": "photograph",
                                      "code": "mixed", "listing": "mixed"}.get(fk.lower(), "mixed")
            blocks.append(new)

        for obj in inv_objects:
            if obj["id"] not in used:
                exclusions.append({"source_id": obj["id"],
                                   "category": "header_footer" if obj["kind"] == "header_footer"
                                   else "out_of_scope",
                                   "reason": f"{obj['kind']}：{obj['text'][:40]}"})

        for fig in shard.get("figures") or []:
            fig["page"] = pno
            figure_requests.append(fig)
        for tab in shard.get("tables") or []:
            tab["page"] = pno
            table_requests.append(tab)

    # ---- join paragraphs that continue across a page break -------------------
    merged = []
    for blk in blocks:
        if merged and blk["kind"] == "paragraph" and merged[-1]["kind"] == "paragraph":
            prev_objs = merged[-1].get("_src_objs") or []
            cur_first = blk["source_ids"][0]
            prev_next = (any(o.get("continues_next") for o in prev_objs)
                         or bool(merged[-1].get("continues_next")))
            cur_prev = any(o.get("continues_prev") for o in
                           (inventory_pages.get(str(int(cur_first[1:5])), {}).get("objects") or [])
                           if o["id"] == cur_first) or bool(blk.get("continues_prev"))
            if prev_next and cur_prev:
                merged[-1]["tex"] = merged[-1]["tex"].rstrip() + blk["tex"].lstrip()
                merged[-1]["source_ids"] = merged[-1]["source_ids"] + blk["source_ids"]
                merged[-1]["_src_objs"] = prev_objs + [o for o in
                    (inventory_pages.get(str(int(cur_first[1:5])), {}).get("objects") or [])
                    if o["id"] in blk["source_ids"]]
                continue
        blk["_src_objs"] = [o for o in
                            (inventory_pages.get(str(int(blk["source_ids"][0][1:5])), {}).get("objects") or [])
                            if o["id"] in blk["source_ids"]]
        merged.append(blk)
    for blk in merged:
        blk.pop("_src_objs", None)
    blocks = merged

    # ---- expectations -------------------------------------------------------
    tags = []
    for blk in blocks:
        if blk["kind"] == "equation":
            tags.extend(TAG_RE.findall(blk.get("tex", "")))
    table_count = sum(1 for b in blocks if b["kind"] == "table")
    figure_count = sum(1 for b in blocks if b["kind"] in ("figure", "figure_native"))
    required = []
    for blk in blocks:
        if blk["kind"] in ("chapter", "section") and blk.get("tex"):
            name = re.sub(r"\\[a-zA-Z]+\*?", "", blk["tex"]).strip("{} ")
            name = name.strip()
            if 2 <= len(name) <= 30:
                required.append(name)
    required = list(dict.fromkeys(required))[:40]
    for blk in blocks[:6]:
        if blk["kind"] == "paragraph":
            plain = re.sub(r"\$[^$]*\$", "", blk.get("tex", ""))
            if len(plain) > 14:
                required.append(plain[:14])
    required = list(dict.fromkeys(required))

    content = {
        "title": project["title"],
        "blocks": blocks,
        "exclusions": exclusions,
        "unresolved": unresolved,
        "expectations": {"equation_tags": tags, "table_count": table_count,
                         "figure_count": figure_count, "required_strings": required},
    }
    if pending:
        content["pending_pages"] = sorted(pending)

    (PROJECT / "source_inventory.json").write_text(
        json.dumps({"schema_version": 1, "source_sha256": sha, "pages": inventory_pages},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (PROJECT / "content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (PROJECT / "work" / "figure_requests.json").write_text(
        json.dumps({"figures": figure_requests, "tables": table_requests},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(json.dumps({
        "pages": len(pages), "missing_shards": missing_shards,
        "inventory_pages": len(inventory_pages), "blocks": len(blocks),
        "exclusions": len(exclusions), "unresolved": len(unresolved),
        "equations": len(tags), "tables": table_count, "figures": figure_count,
        "figure_requests": len(figure_requests),
    }, ensure_ascii=False))
    if unresolved:
        print("UNRESOLVED:", *unresolved[:10], sep="\n  ")
    if figure_requests and not args.allow_pending:
        print("NOTE: figure requests must be registered in assets.json before build:")
        for fig in figure_requests:
            print("   ", fig)
    return 0


if __name__ == "__main__":
    sys.exit(main())
