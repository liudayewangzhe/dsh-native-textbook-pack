"""Create the exact scan inventory shape without overwriting authored work."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project', type=Path, required=True)
args = parser.parse_args()
project_dir = args.project.resolve()
target = project_dir / 'source_inventory.json'
if target.exists():
    parser.exit(0, f'Existing authored inventory preserved: {target}\n')
project = json.loads((project_dir / 'project.json').read_text(encoding='utf-8'))
pages = {}
for n in project['pages']:
    packet = json.loads((project_dir / 'packet' / 'pages' / f'p{n:04d}.json').read_text(encoding='utf-8'))
    if not packet['blocks']:
        pages[str(n)] = {'objects': []}
if not pages:
    parser.exit(0, 'No zero-text pages; no manual inventory required.\n')
target.write_text(json.dumps({'schema_version': 1, 'source_sha256': project['source']['sha256'],
                             'pages': pages}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(target)
print('Fill each objects array from the whole source page; empty arrays cannot publish.')
