"""Scan/blank provenance guard regressions; source pages never disappear silently."""
import copy
import tempfile
import unittest
from pathlib import Path
import sys
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import native_forge as nf

class SourceInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/'source.pdf'
        doc=fitz.open(); page=doc.new_page(width=300,height=400)
        page.insert_text((20,40),'Original native body')
        scan=doc.new_page(width=300,height=400)
        pix=fitz.Pixmap(fitz.csRGB,fitz.Rect(0,0,8,8),False); pix.clear_with(123)
        scan.insert_image(fitz.Rect(20,80,280,300),stream=pix.tobytes('png'))
        doc.new_page(width=300,height=400); doc.save(self.source); doc.close()
        self.project=self.root/'project'
        nf.prepare(self.source,'1-2',self.project,'Scan evidence')
        self.config=nf.load_project(self.project)
        self.inventory={'schema_version':1,'source_sha256':self.config['source']['sha256'],'pages':{'2':{'objects':[{'id':'p0002-s0000','page':2,'bbox':[20,80,280,300],'kind':'figure','text':'Manually read original diagram'}]}}}

    def tearDown(self):
        self.temp.cleanup()

    def write(self,inventory=None):
        nf.write_json(self.project/'source_inventory.json',inventory or self.inventory)

    def load(self):
        return nf.load_packet(self.project,nf.load_project(self.project))

    def test_scan_without_manual_inventory_cannot_pass_as_empty_evidence(self):
        with self.assertRaisesRegex(nf.EngineError,'zero text evidence.*source_inventory'):
            self.load()

    def test_manual_scan_objects_join_coverage_ledger(self):
        self.write(); packet=self.load()
        self.assertEqual(packet['p0002-s0000']['origin'],'agent_manual_inventory')
        original_ids=[key for key in packet if key.startswith('p0001-')]
        content={'title':'Native text','blocks':[{'id':'body','kind':'paragraph','source_ids':original_ids,'tex':'原生中文正文。'}], 'exclusions':[], 'unresolved':[], 'expectations':{'equation_tags':[],'table_count':0,'figure_count':0,'required_strings':[]}}
        with self.assertRaisesRegex(nf.EngineError,'neither covered nor excluded'):
            nf.validate_content(content,set(packet),set())
        content['blocks'].append({'id':'diagram','kind':'figure','source_ids':['p0002-s0000'],'asset':'original','caption':''})
        content['expectations']['figure_count']=1
        nf.validate_content(content,set(packet),{'original'})

    def test_inventory_wrong_source_hash_is_rejected(self):
        self.inventory['source_sha256']='0'*64; self.write()
        with self.assertRaisesRegex(nf.EngineError,'current source_sha256'):
            self.load()

    def test_bad_bounds_ids_page_and_missing_text_are_rejected(self):
        cases=[{'bbox':[0,0,301,400]},{'bbox':[0,0,float('nan'),400]},{'page':1},{'id':''},{'kind':'arbitrary'},{'text':''}]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                inv=copy.deepcopy(self.inventory); inv['pages']['2']['objects'][0].update(mutation)
                self.write(inv)
                with self.assertRaises(nf.EngineError):
                    self.load()
        inv=copy.deepcopy(self.inventory); inv['pages']['2']['objects']*=2; self.write(inv)
        with self.assertRaisesRegex(nf.EngineError,'duplicate evidence'):
            self.load()

    def test_empty_manual_inventory_is_rejected(self):
        self.inventory['pages']['2']['objects']=[]; self.write()
        with self.assertRaisesRegex(nf.EngineError,'nonempty manually read objects'):
            self.load()

    def test_explicit_checked_blank_page_requires_reason(self):
        nf.prepare(self.source,'1,3',self.project,'Native and verified blank')
        inv={'schema_version':1,'source_sha256':self.config['source']['sha256'],'pages':{'3':{'blank':True,'checked':True,'reason':'Read entire page; genuinely blank'}}}
        self.write(inv); self.assertTrue(self.load())
        inv['pages']['3']['checked']=False; self.write(inv)
        with self.assertRaisesRegex(nf.EngineError,'blank page needs checked'):
            self.load()
        inv['pages']['3']['checked']=True; inv['pages']['3']['reason']=''; self.write(inv)
        with self.assertRaises(nf.EngineError):
            self.load()

    def test_empty_content_is_never_publishable_even_with_no_text_ids(self):
        content={'title':'Empty','blocks':[],'exclusions':[],'unresolved':[],'expectations':{'equation_tags':[],'table_count':0,'figure_count':0,'required_strings':[]}}
        with self.assertRaisesRegex(nf.EngineError,'empty content cannot be built'):
            nf.validate_content(content,set(),set())

if __name__=='__main__':
    unittest.main()
