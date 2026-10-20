"""Merge ordered, independently authored semantic chunks, then validate coverage."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('native_forge', ROOT / 'engine' / 'native_forge.py')
nf = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(nf)


def merge(project_dir: Path, chunks: list[Path]) -> dict:
    project = nf.read_json(project_dir / 'project.json')
    merged = {'title': project['title'], 'blocks': [], 'exclusions': [], 'source_notes': [],
              'unresolved': [], 'expectations': {'equation_tags': [], 'table_count': 0,
              'figure_count': 0, 'required_strings': []}}
    ledger = {'chunks': [], 'boundary_exclusions_resolved': [], 'duplicate_headers_coalesced': []}
    exclusions = {}
    for index, path in enumerate(chunks, 1):
        data = nf.read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get('blocks'), list):
            raise nf.EngineError(f'invalid semantic chunk: {path}')
        ledger['chunks'].append({'path': str(path.resolve()), 'sha256': nf.sha256_file(path)})
        for block in data['blocks']:
            block = dict(block)
            block['id'] = f'chunk{index:04d}:{block["id"]}'
            merged['blocks'].append(block)
        for key in ('unresolved',):
            merged[key].extend(data.get(key, []))
        notes = data.get('source_notes', [])
        merged['source_notes'].extend(notes if isinstance(notes, list) else [notes])
        exp = data.get('expectations')
        if not isinstance(exp, dict):
            raise nf.EngineError(f'chunk has no source-derived expectations: {path}')
        for key in ('equation_tags', 'required_strings'):
            merged['expectations'][key].extend(exp[key])
        for key in ('table_count', 'figure_count'):
            merged['expectations'][key] += exp[key]
        for exclusion in data.get('exclusions', []):
            source_id = exclusion['source_id']
            if source_id in exclusions:
                existing = exclusions[source_id]
                if existing['category'] != exclusion['category']:
                    raise nf.EngineError(f'conflicting exclusions for {source_id}')
                ledger['duplicate_headers_coalesced'].append(source_id)
            else:
                exclusions[source_id] = exclusion
    covered = {s for b in merged['blocks'] for s in b.get('source_ids', [])}
    for source_id, exclusion in exclusions.items():
        if source_id in covered:
            if exclusion['category'] != 'out_of_scope':
                raise nf.EngineError(f'included content conflicts with exclusion for {source_id}')
            ledger['boundary_exclusions_resolved'].append(source_id)
        else:
            merged['exclusions'].append(exclusion)
    merged['expectations']['required_strings'] = list(dict.fromkeys(merged['expectations']['required_strings']))
    packet = nf.load_packet(project_dir, project)
    assets = nf.load_assets(project_dir)
    nf.validate_content(merged, set(packet), set(assets))
    # Only a fully validated merge may replace the current working manuscript.
    target = project_dir / 'content.json'
    pending = project_dir / 'content.merge.pending.json'
    nf.write_json(pending, merged)
    pending.replace(target)
    project['status'] = 'draft'
    nf.write_json(project_dir / 'project.json', project)
    nf.write_json(project_dir / 'merge-ledger.json', ledger)
    return {'blocks': len(merged['blocks']), 'chunks': len(chunks), 'content': str(target)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--chunks', required=True, type=Path, nargs='+', help='Explicit files in reading order')
    args = parser.parse_args()
    try:
        print(json.dumps(merge(args.project.resolve(), args.chunks), ensure_ascii=False))
    except (nf.EngineError, KeyError, TypeError) as exc:
        parser.exit(1, f'merge blocked: {exc}\n')
