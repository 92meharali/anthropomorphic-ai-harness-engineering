"""Offline fixtures, not experimental ratings."""
import io
import shutil
import unittest
try:
    from openpyxl import load_workbook
except ModuleNotFoundError as exc:
    if exc.name != 'openpyxl':
        raise
    raise unittest.SkipTest('Install requirements-rewrite-review.txt to test the Excel workflow') from exc
from . import rewrite_blind as b, rewrite_freeze as f, rewrite_generate as g
from . import test_rewrite_generate as gen


class BlindTests(unittest.TestCase):
    def setUp(self):
        self.fixture = gen.GenerationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.study, self.run, self.freeze = (self.fixture.root, self.fixture.study,
            self.fixture.out, self.fixture.seal)
        shutil.copyfile(f.ROOT / b.SOURCE, self.root / b.SOURCE)
        self.packet = self.root / 'packet'
        self.collection = self.root / 'collected'
        self.kw = {'assess': gen.assess, 'build_state': gen.state}

    def prepare(self, transport=None):
        self.fixture.run_mock(transport)
        self.manifest = b.prepare(self.root,self.study,self.run,self.packet,self.freeze,**self.kw)
        self.seal = self.manifest['packet_sha256']
        return self.manifest

    def verify_packet(self):
        return b.verify_packet(self.root,self.study,self.run,self.packet,self.freeze,self.seal,**self.kw)

    def workbook(self, reviewer):
        raw = (self.packet/'reviewers'/b.workbook_name(reviewer)).read_bytes()
        wb = load_workbook(io.BytesIO(raw))
        _,cases,_ = self.verify_packet()
        guide = (self.root/'rubric/generated_rewrite_review_v1.md').read_bytes()
        _,slots = b.layout(cases,reviewer,guide)
        for (row,col),(_,pos,field) in slots.items():
            values = {'A': ('Yes','No','Uncertain',4), 'B': ('Yes','Yes','Yes',5)}
            wb['Review'].cell(row,col).value = values[pos][b.FIELDS.index(field)]
        return wb,slots

    def encode(self, wb):
        buf = io.BytesIO(); wb.save(buf); wb.close()
        return buf.getvalue()

    def submissions(self):
        paths=[]
        for reviewer in self.manifest['body']['reviewers']:
            path=self.root/(reviewer+'.xlsx'); path.write_bytes(self.encode(self.workbook(reviewer)[0]))
            paths.append(path)
        provenance={'record_reference':'mock-only', 'reviewers':{r:{'submission_reference':r+'-mock',
            'independent':True,'blinded':True} for r in self.manifest['body']['reviewers']}}
        return paths,provenance

    def collect(self, paths, provenance):
        return b.collect(self.root,self.study,self.run,self.packet,self.collection,self.freeze,self.seal,paths,provenance,**self.kw)

    def test_balanced_deterministic_blinded_packet(self):
        self.prepare()
        manifest,cases,key=self.verify_packet()
        self.assertEqual(manifest['body']['eligible_pairs'],2)
        self.assertEqual({k['A'] for k in key},set(g.ARMS))
        self.assertEqual([c['review_id'] for c in cases],['RW0001','RW0002'])
        replay = b.build(self.root, self.study, self.run, self.freeze,
                         packet_seed=manifest['body']['packet_seed'], **self.kw)
        self.assertEqual((cases, key), replay[1:3])
        for c in cases:
            self.assertEqual(set(c),{'review_id','visible_history','current_user_message','original','A','B','case_sha256'})
            self.assertEqual(c['A'],c['B'])  # unchanged identical outputs must be retained
        for r in b.REVIEWERS:
            path=self.packet/'reviewers'/b.workbook_name(r)
            wb=load_workbook(path)
            self.assertEqual(wb.sheetnames,['Review','Rubric'])
            text=' '.join(str(c.value) for sheet in wb for row in sheet for c in row if c.value is not None)
            for hidden in ('cue_specific','generic','prompt_group_id','GR-M01','validated_cue_feedback'):
                self.assertNotIn(hidden,text)
            self.assertIn('Original draft (reference)',text)
            self.assertEqual(len(wb['Review'].data_validations.dataValidation),2)
            wb.close()
        self.assertEqual(len(self.fixture.requests),52)  # review invokes no provider calls

    def test_collect_and_replay(self):
        self.prepare(); paths,provenance=self.submissions()
        seal=self.collect(paths,provenance)
        got,cases,key,ratings=b.verify_collection(self.root,self.study,self.run,self.packet,self.collection,
            self.freeze,self.seal,seal['collection_sha256'],**self.kw)
        self.assertEqual(got,seal); self.assertEqual(len(ratings),6)
        for path, reviewer in zip(paths,b.REVIEWERS):
            self.assertEqual(path.read_bytes(),(self.collection/'ballots'/(reviewer+'.xlsx')).read_bytes())
        self.assertEqual(ratings[0]['A'],{'cue_corrected':True,'advice_preserved':False,'warmth_preserved':None,'oa':4})
        self.assertEqual(ratings[0]['B']['oa'],5)
        self.assertEqual({r['reviewer_id'] for r in ratings},set(b.REVIEWERS))

    def test_invalid_ballots_rejected(self):
        self.prepare(); _,cases,_=self.verify_packet()
        guide=(self.root/'rubric/generated_rewrite_review_v1.md').read_bytes()
        mutations = ('blank','oa','reviewer','hash','text','extra','missing','formula','rubric','hidden','duplicate')
        for mutate in mutations:
            wb,slots=self.workbook('R01'); ws=wb['Review']
            binary=next(k for k,v in slots.items() if v[2]=='cue_corrected')
            oa=next(k for k,v in slots.items() if v[2]=='oa')
            if mutate=='blank': ws.cell(*binary).value=None
            elif mutate=='oa': ws.cell(*oa).value=6
            elif mutate=='reviewer': ws['B2']='R02'
            elif mutate=='hash': ws['B6']='wrong'
            elif mutate=='text': ws['B8']='edited text'
            elif mutate=='extra': ws.cell(ws.max_row+1,1).value='extra'
            elif mutate=='missing': ws.delete_rows(ws.max_row-2,3)
            elif mutate=='formula': ws.cell(*oa).value='=4'
            elif mutate=='rubric': wb['Rubric']['B2']='altered'
            elif mutate=='hidden': ws.row_dimensions[8].hidden=True
            elif mutate=='duplicate': ws['A5']='RW0002'
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                b.parse_ballot(self.encode(wb),cases,'R01',guide)

    def test_literal_text_long_context_and_unicode(self):
        case={'review_id':'RW0001','case_sha256':'a'*64,'visible_history':[],
              'current_user_message':'=2+3','original':'A long response ’ 中文\n'*100,
              'A':'=SUM(1,2)','B':'=SUM(1,2)'}
        guide=b'# rubric\n'
        raw=b.make_workbook([case],'R01',guide)
        b.check_workbook(raw,[case],'R01',guide,blank=True)
        self.assertEqual(''.join(b.chunks(case['original'])),case['original'])
        wb=load_workbook(io.BytesIO(raw))
        literal=[c for row in wb['Review'] for c in row if c.value=='=SUM(1,2)']
        self.assertEqual(len(literal),2)
        self.assertTrue(all(c.data_type=='s' for c in literal)); wb.close()

    def test_independence_provenance_and_distinct_files(self):
        self.prepare(); paths,provenance=self.submissions()
        with self.assertRaises(ValueError): self.collect([paths[0]]*3,provenance)
        provenance['reviewers']['R02']['blinded']=False
        with self.assertRaisesRegex(ValueError,'attestation'): self.collect(paths,provenance)
        self.assertFalse(self.collection.exists())

    def test_packet_tamper_and_wrong_seal(self):
        self.prepare(); seal=self.seal; self.seal='bad'
        with self.assertRaisesRegex(ValueError,'seal'): self.verify_packet()
        self.seal=seal
        with (self.packet/'reviewers'/b.workbook_name('R01')).open('ab') as stream: stream.write(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'): self.verify_packet()

    def test_collection_tamper(self):
        self.prepare(); paths,provenance=self.submissions(); seal=self.collect(paths,provenance)
        with (self.collection/'ratings.jsonl').open('ab') as stream: stream.write(b'{}\n')
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            b.verify_collection(self.root,self.study,self.run,self.packet,self.collection,self.freeze,self.seal,seal['collection_sha256'],**self.kw)

    def test_no_eligible_pairs(self):
        self.prepare(lambda *args: ({'classification':'unresolved'},None))
        self.assertEqual(self.manifest['body']['eligible_pairs'],0)
        self.assertFalse((self.packet/'reviewers').exists())
        paths,provenance=self.submissions(); seal=self.collect(paths,provenance)
        self.assertEqual(seal['body']['state'],'no_eligible_pairs')
        self.assertEqual(seal['body']['reviewer_case_ratings'],0)

    def test_excludes_failed_or_mismatched_pairs(self):
        def transport(provider,body,key):
            raw,rid=self.fixture.transport(provider,body,key)
            if isinstance(body['input'],list):
                payload=f.loads(body['input'][0]['content'])
                if 'validated_cue_feedback' in payload:
                    if payload['candidate_response']=='Mock original 1': return {'status':'incomplete'},None
                    raw['model']='different-snapshot'
            return raw,rid
        self.prepare(transport)
        self.assertEqual(self.manifest['body']['flagged'],2)
        self.assertEqual(self.manifest['body']['eligible_pairs'],0)

    def test_run_tamper_rejected_before_packet(self):
        self.fixture.run_mock()
        with (self.run/'outcomes.jsonl').open('ab') as stream: stream.write(b'{}\n')
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            b.prepare(self.root,self.study,self.run,self.packet,self.freeze,**self.kw)
        self.assertFalse(self.packet.exists())

    def test_no_overwrite(self):
        self.prepare()
        with self.assertRaises(FileExistsError):
            b.prepare(self.root,self.study,self.run,self.packet,self.freeze,**self.kw)
        paths,provenance=self.submissions(); self.collect(paths,provenance)
        with self.assertRaises(FileExistsError): self.collect(paths,provenance)


if __name__=='__main__': unittest.main()
