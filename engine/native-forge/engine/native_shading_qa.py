"""Native-shading QA scanner for the Native Forge engine (candidate helper module).

Engine-side certification for `source-page-form+vector-bbox-clip` assets and for the
xref-0 runtime shading proxies that MuPDF reports for them (runtime gradient pixmaps of
native shading objects, not inline images).  The engine loads this module from its own
directory, next to native_forge.py.  It is deliberately standalone: stdlib only plus the
PyMuPDF handle the engine already loads; it never opens the immutable source PDF.

Every public entry point fails closed: when a stream, resource graph or embedded form
cannot be certified, the caller must treat the occurrences as unsupported evidence.
"""
from __future__ import annotations

import hashlib
import re

SOURCE_FORM_METHOD = "source-page-form+vector-bbox-clip"
MAX_PAYLOAD_BYTES = 512 << 20
MAX_STREAM_BYTES = 256 << 20
MAX_GRAPH_NODES = 4096
_FONT_PROGRAM_SUBTYPES = ("/Type1C", "/CIDFontType0C", "/OpenType")
_REF = re.compile(r"(\d+)\s+\d+\s+R")
_WS = b"\x00\t\n\x0c\r "
_DELIMS = b"()<>[]{}/%"


class _Uncertified(Exception):
    """Raised when a stream or resource graph cannot be certified."""


def scan_bi_tokens(data):
    """Count actual BI operators in one decoded content stream; (count, certified).

    Comments, literal strings, hex strings and names are skipped, so stream data such as
    `(BI)`, `<4249>`, `/BI` or `% BI` can never be reported as an inline image, while a
    real `BI` operator is found even when it follows a delimiter instead of whitespace.
    `certified` is False when the stream cannot be tokenised safely (unbalanced
    constructs or size guard); callers must then refuse rather than assume no BI.
    """
    if not isinstance(data, (bytes, bytearray)):
        return 0, False
    if len(data) > MAX_STREAM_BYTES:
        return 0, False
    count, index, size = 0, 0, len(data)
    while index < size:
        char = data[index]
        if char == 0x25:                                   # comment up to end of line
            index += 1
            while index < size and data[index] not in (0x0A, 0x0D):
                index += 1
        elif char == 0x28:                                 # literal string, nesting depth
            depth, index = 1, index + 1
            while depth:
                if index >= size:
                    return count, False
                inner = data[index]
                if inner == 0x5C:                          # backslash escape
                    index += 2
                elif inner == 0x28:
                    depth, index = depth + 1, index + 1
                elif inner == 0x29:
                    depth, index = depth - 1, index + 1
                else:
                    index += 1
        elif char == 0x3C:                                 # dict open or hex string
            if index + 1 < size and data[index + 1] == 0x3C:
                index += 2
            else:
                end = data.find(b">", index + 1)
                if end < 0:
                    return count, False
                index = end + 1
        elif char == 0x2F:                                 # name token
            index += 1
            while index < size and data[index] not in _DELIMS and data[index] not in _WS:
                index += 1
        elif char in _DELIMS or char in _WS:
            index += 1
        else:
            end = index
            while end < size and data[end] not in _DELIMS and data[end] not in _WS:
                end += 1
            if data[index:end] == b"BI":
                count += 1
            index = end
    return count, True


def _field_ref(doc, xref, key):
    kind, value = doc.xref_get_key(xref, key)
    if kind == "xref":
        return ("xref", int(value.split()[0]))
    if kind == "dict":
        return ("dict", value)
    return None


def _dict_refs(doc, xref, key):
    kind, value = doc.xref_get_key(xref, key)
    if kind == "dict":
        return {int(number) for number in _REF.findall(value)}
    if kind == "xref":
        return {int(value.split()[0])}
    return set()


def _page_contents_streams(doc, page):
    kind, value = doc.xref_get_key(page.xref, "Contents")
    if kind == "xref":
        return [int(value.split()[0])]
    if kind == "array":
        return [int(number) for number in _REF.findall(value)]
    return None


def _scan_resource_closure(doc, resources):
    """Walk one Resources value: recursive counts, actual BI tokens, forms, graph digest.

    Only content-bearing streams (Form XObjects, Type3 charprocs, pattern streams) are
    BI-scanned; image data and font programs (Type1C/CIDFontType0C/OpenType) are not
    content and are never tokenised.  Every /Form XObject reached anywhere in the graph
    is recorded as (xref, sha256 of its decoded stream) so callers can match an embedded
    form against a verified source Contents fingerprint.  Cycles and oversized graphs
    raise _Uncertified.
    """
    counts = {"Image": 0, "Shading": 0, "Type3": 0, "Form": 0, "BI": 0}
    state = {"certified": True, "type3_charprocs": 0, "type3_charprocs_bi": 0, "forms": []}
    cache, active, charprocs = {}, set(), set()

    def node(xref):
        if xref in cache:
            return cache[xref]
        if xref in active:
            raise _Uncertified("resource graph cycle cannot be certified")
        if len(cache) >= MAX_GRAPH_NODES:
            raise _Uncertified("resource graph exceeds the certification node budget")
        active.add(xref)
        try:
            subtype = doc.xref_get_key(xref, "Subtype")[1]
            keys = doc.xref_get_keys(xref)
            if subtype == "/Type3":
                charprocs.update(_dict_refs(doc, xref, "CharProcs"))
            obj = _REF.sub(lambda match: "<" + node(int(match.group(1))) + ">",
                           doc.xref_object(xref, compressed=True))
            stream = doc.xref_stream_raw(xref) if doc.xref_is_stream(xref) else None
            counts["Image"] += subtype == "/Image"
            counts["Type3"] += subtype == "/Type3"
            counts["Form"] += subtype == "/Form"
            if "ShadingType" in keys:
                counts["Shading"] += 1
            is_content = subtype == "/Form" or xref in charprocs or "PatternType" in keys
            if stream is not None and subtype != "/Image" and is_content \
                    and subtype not in _FONT_PROGRAM_SUBTYPES:
                decoded = doc.xref_stream(xref)
                if decoded is None:
                    state["certified"] = False
                else:
                    found, ok = scan_bi_tokens(bytes(decoded))
                    counts["BI"] += found
                    state["certified"] = state["certified"] and ok
                    if subtype == "/Form":
                        state["forms"].append((xref, hashlib.sha256(bytes(decoded)).hexdigest()))
                    if xref in charprocs:
                        state["type3_charprocs"] += 1
                        state["type3_charprocs_bi"] += found
            stream_sha = hashlib.sha256(stream).hexdigest() if stream is not None else ""
            digest = hashlib.sha256((obj + "|" + stream_sha).encode("utf-8")).hexdigest()
            cache[xref] = digest
            return digest
        finally:
            active.discard(xref)

    kind, value = resources or ("", "")
    if kind == "xref":
        digest = node(value)
    elif kind == "dict":
        digest = hashlib.sha256(_REF.sub(lambda match: "<" + node(int(match.group(1))) + ">",
                                         value).encode("utf-8")).hexdigest()
    else:
        raise _Uncertified("resources cannot be located for certification")
    return {"digest": digest, "counts": counts, "certified": state["certified"],
            "type3_charprocs": state["type3_charprocs"],
            "type3_charprocs_bi": state["type3_charprocs_bi"], "forms": state["forms"]}


def _certify_page_contents(doc, page):
    """(problem or None): actual BI tokens in the page Contents streams."""
    contents = _page_contents_streams(doc, page)
    if not contents:
        return "page Contents cannot be located"
    for xref in contents:
        data = doc.xref_stream(xref)
        if data is None:
            return "page Contents cannot be decoded"
        found, ok = scan_bi_tokens(bytes(data))
        if not ok:
            return "page Contents cannot be certified free of inline images"
        if found:
            return f"page Contents hold {found} actual inline image token(s)"
    return None


def certify_payload(asset_bytes, proof, require_type3=False):
    """Re-scan a byte-verified source-page-form payload; (ok, problems, evidence).

    Locates the embedded fullpage form by the verified source Contents fingerprint and
    certifies with actual tokens that neither the payload page Contents nor the
    recursive form resources (nested forms, Type3 charprocs, patterns) hold real Image
    objects or inline-image operators, that native shading evidence exists, and that the
    resource graph can be digested.  require_type3 demands certified Type3 charproc
    content instead of trusting the recorded Type3 count.
    """
    try:
        if not isinstance(asset_bytes, (bytes, bytearray)):
            return False, ["asset payload bytes are missing"], {}
        if len(asset_bytes) > MAX_PAYLOAD_BYTES:
            return False, ["asset payload exceeds the certification size guard"], {}
        import fitz
        with fitz.open(stream=bytes(asset_bytes), filetype="pdf") as doc:
            if doc.page_count != 1:
                return False, ["source-page-form payload must hold exactly one page"], {}
            page = doc[0]
            want = proof.get("source_contents_sha256")
            if not isinstance(want, str) or not want:
                return False, ["verified proof lacks the source Contents fingerprint"], {}
            problem = _certify_page_contents(doc, page)
            if problem:
                return False, [problem], {}
            page_graph = _scan_resource_closure(doc, _field_ref(doc, page.xref, "Resources"))
            if not page_graph["certified"] or page_graph["counts"]["BI"]:
                return False, ["payload content cannot be certified free of inline images"], {}
            matches = [xref for xref, sha in page_graph["forms"] if sha == want]
            if len(matches) != 1:
                return False, [f"payload carries {len(matches)} form(s) matching the verified "
                               "source Contents fingerprint"], {}
            graph = _scan_resource_closure(doc, _field_ref(doc, matches[0], "Resources"))
            counts = graph["counts"]
            if not graph["certified"] or counts["BI"]:
                return False, ["the form resource graph cannot be certified free of inline images"], {}
            if counts["Image"]:
                return False, [f"the form resource graph holds {counts['Image']} real Image object(s)"], {}
            if counts["Shading"] < 1:
                return False, ["the form resource graph holds no native shading objects"], {}
            if require_type3 and (counts["Type3"] < 1 or graph["type3_charprocs"] < 1
                                  or graph["type3_charprocs_bi"]):
                return False, ["Type3 font content is not certified free of inline images"], {}
            evidence = {"source_contents_sha256": want, "graph_sha256": graph["digest"],
                        "counts": counts, "type3_charprocs": graph["type3_charprocs"],
                        "payload_sha256": hashlib.sha256(bytes(asset_bytes)).hexdigest()}
            return True, [], evidence
    except _Uncertified as exc:
        return False, [str(exc)], {}
    except Exception as exc:  # fail closed: certification must never pass on error
        return False, [f"payload certification failed: {exc}"], {}


def exempt_runtime_proxies(doc, page, occurrences, candidates):
    """(ok, detail): may this page's xref-0 runtime proxies be reported separately?

    Strict page level: the whole page must be free of real Image resources and actual
    inline-image tokens (page Contents, nested forms, Type3 charprocs), must embed
    exactly one form matching a candidate's verified source Contents fingerprint with an
    identical recursive resource graph, and must show exactly the recorded proxy count.
    Output pixel digests may legitimately differ from the source when the CTM differs.
    """
    try:
        if not isinstance(occurrences, int) or isinstance(occurrences, bool) or occurrences <= 0:
            return False, "no runtime proxy occurrences to exempt"
        if not candidates:
            return False, "no verified vector source-page-form is available"
        problem = _certify_page_contents(doc, page)
        if problem:
            return False, problem
        page_graph = _scan_resource_closure(doc, _field_ref(doc, page.xref, "Resources"))
        if not page_graph["certified"] or page_graph["counts"]["BI"]:
            return False, "nested form/Type3 content cannot be certified free of inline images"
        if page_graph["counts"]["Image"]:
            return False, f"page resources hold {page_graph['counts']['Image']} real Image object(s)"
        matches = [(xref, candidate) for xref, sha in page_graph["forms"] for candidate in candidates
                   if sha == candidate.get("source_contents_sha256")]
        if len(matches) != 1:
            return False, (f"page carries {len(matches)} embedded form(s) matching verified "
                           "source-page-form payloads; exactly one is required")
        form_xref, candidate = matches[0]
        if occurrences != candidate.get("runtime_proxy_output_count"):
            return False, (f"{occurrences} runtime proxy occurrence(s) differ from the verified "
                           f"count {candidate.get('runtime_proxy_output_count')}")
        form_graph = _scan_resource_closure(doc, _field_ref(doc, form_xref, "Resources"))
        if not form_graph["certified"] or form_graph["counts"]["BI"]:
            return False, "embedded form content cannot be certified free of inline images"
        if form_graph["digest"] != candidate.get("graph_sha256"):
            return False, "embedded form resource graph differs from the verified source-page-form"
        return True, {"page": page.number + 1, "occurrences": occurrences,
                      "asset": candidate.get("asset"),
                      "source_contents_sha256": candidate.get("source_contents_sha256"),
                      "resource_counts": candidate.get("resource_counts"),
                      "graph_sha256": form_graph["digest"]}
    except _Uncertified as exc:
        return False, str(exc)
    except Exception as exc:  # fail closed
        return False, f"runtime proxy certification failed: {exc}"
