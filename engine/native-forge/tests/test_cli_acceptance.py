"""Independent command-level regressions for provenance/cropping/preservation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

ENGINE = Path(__file__).resolve().parents[1] / 'engine' / 'native_forge.py'


class CommandAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.pdf'
        doc = fitz.open()
        page = doc.new_page(width=400, height=300)
        page.insert_text((20, 30), 'OUTSIDE_TEXT')
        page.insert_text((170, 180), 'INSIDE_TEXT')
        page.draw_rect(fitz.Rect(150, 150, 300, 250), color=(1, 0, 0))
        doc.save(self.source)
        doc.close()
        self.project = self.root / 'project'
        result = self.command('prepare', '--source', str(self.source), '--pages', '1', '--project', str(self.project), '--title', 'Test')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args):
        return subprocess.run([sys.executable, str(ENGINE), *args], text=True, encoding='utf-8', capture_output=True)

    def read(self, name):
        return json.loads((self.project / name).read_text(encoding='utf-8-sig'))

    def write(self, name, value):
        (self.project / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def test_crop_physically_removes_outside_text_and_retains_paths(self):
        result = self.command('asset', '--project', str(self.project), '--page', '1', '--bbox', '140', '140', '310', '260', '--name', 'diagram')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        asset = self.read('assets.json')['diagram']
        path = Path(asset['path'])
        if not path.is_absolute():
            path = self.project / path
        with fitz.open(path) as doc:
            self.assertIn('INSIDE_TEXT', doc[0].get_text())
            self.assertNotIn('OUTSIDE_TEXT', doc[0].get_text())
            self.assertTrue(doc[0].get_drawings())
            self.assertEqual(len(doc[0].get_image_info(xrefs=True)), 0)

    def test_existing_asset_is_not_overwritten(self):
        args = ('asset', '--project', str(self.project), '--page', '1', '--bbox', '140', '140', '310', '260', '--name', 'diagram')
        first = self.command(*args)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        manifest = (self.project / 'assets.json').read_bytes()
        second = self.command(*args)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(manifest, (self.project / 'assets.json').read_bytes())

    def test_prepare_preserves_authored_content_and_asset_manifest(self):
        content = {'title': 'Authored', 'blocks': [], 'exclusions': [], 'unresolved': ['keep'], 'expectations': {'equation_tags': [], 'table_count': 0, 'figure_count': 0, 'required_strings': []}}
        assets = {'external': {'sentinel': 'preserve me'}}
        self.write('content.json', content)
        self.write('assets.json', assets)
        result = self.command('prepare', '--source', str(self.source), '--pages', '1', '--project', str(self.project), '--title', 'Test')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read('content.json'), content)
        self.assertEqual(self.read('assets.json'), assets)

    def test_source_raster_cannot_masquerade_as_vector_pdf(self):
        raster_source = self.root / 'raster.pdf'
        doc = fitz.open()
        page = doc.new_page(width=400, height=300)
        page.insert_text((20, 30), 'Caption')
        pix = fitz.Pixmap(fitz.csRGB, fitz.Rect(0, 0, 4, 4), False)
        pix.clear_with(255)
        page.insert_image(fitz.Rect(100, 100, 300, 250), stream=pix.tobytes('png'))
        doc.save(raster_source)
        doc.close()
        project = self.root / 'raster-project'
        result = self.command('prepare', '--source', str(raster_source), '--pages', '1', '--project', str(project), '--title', 'Raster')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rejected = self.command('asset', '--project', str(project), '--page', '1', '--bbox', '90', '90', '310', '260', '--name', 'wrong-vector')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn('wrong-vector', json.loads((project / 'assets.json').read_text(encoding='utf-8-sig')))


if __name__ == '__main__':
    unittest.main()
