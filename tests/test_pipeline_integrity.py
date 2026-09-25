"""Offline regressions for canonical variants and content-bound evaluation."""
import argparse
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from vconflict_pipeline import core, integrity as i, evidence as e, authoring as a
from vconflict_pipeline import evaluation as ev, qa, reporting, descriptions
from vconflict_pipeline.cli import build_parser, _validate


def question():
    return {'question_id':'q001', 'text_en':'Starting with [1, 2], append 3 at the end. What is the final list?',
            'conflict_video_reference_en':'The final list is [3, 1, 2].',
            'normal_control_reference_en':'The final list is [1, 2, 3].'}


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(core, 'PROJECT_ROOT', self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.video = {'video_id':'v001','role':'conflict','status':'ready',
            'local_path':f'videos/seedance/{i.MATH_GROUP}/qualified/example/v001.mp4',
            'task_id':None,'seedance_prompt_en':'Append 3 at the front of the list.',
            'human_review':'verified','qa_results':[]}
        self.file=self.root/self.video['local_path'];self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'original movie')
        self.case={'schema_version':'4.0','case_id':'example','title':'Append: Add item',
            'conflict_spec':{'normal_fact_en':'The list is [1, 2, 3].','intended_video_fact_en':'The list is [3, 1, 2].'},
            'questions':[question()],'videos':[self.video]}
        control=copy.deepcopy(self.video);control.update(video_id='control',role='control',
            local_path=self.video['local_path'].replace('v001.mp4','control.mp4'),
            seedance_prompt_en='Append 3 after every item.')
        (self.root/control['local_path']).write_bytes(b'control movie')
        self.case['videos'].append(control)

    def result(self):
        return {'run_id':'test_run','timestamp':'2026-09-24T00:00:00Z','input_mode':'video',
            'question_id':'q001','question':question()['text_en'],'raw_answer':'Final answer: [3, 1, 2].',
            'final_answer':'[3, 1, 2].','model':'google/gemini-3.1-pro-preview',
            'thinking_effort':'default','judgment':None,
            'input_fingerprint':i.qa_fingerprint(self.case,self.video,question(),'video')}

    def test_replaced_movie_invalidates_result(self):
        r=self.result();self.assertTrue(i.qa_is_current(self.case,self.video,r))
        self.file.write_bytes(b'replacement movie')
        self.assertFalse(i.qa_is_current(self.case,self.video,r))

    def test_same_question_id_new_text_invalidates_result(self):
        r=self.result();self.case['questions'][0]['text_en']='Starting with [1, 2], append 4. What is the final list?'
        self.video['qa_results']=[r]
        core.validate_case(self.case)
        self.assertFalse(i.qa_is_current(self.case,self.video,r))

    def test_changed_reference_requires_rejudging_but_reuses_answer(self):
        r=self.result();r['judgment']={'verdict':'context_grounded','confidence':1,
            'input_fingerprint':i.judgment_fingerprint(self.case,self.video,r)}
        self.assertTrue(i.judgment_is_current(self.case,self.video,r))
        self.case['questions'][0]['conflict_video_reference_en']='The list reads [3, 1, 2], left to right.'
        self.assertTrue(i.qa_is_current(self.case,self.video,r))
        self.assertFalse(i.judgment_is_current(self.case,self.video,r))

    def test_legacy_math_qa_not_silently_certified(self):
        r=self.result();del r['input_fingerprint']
        self.assertFalse(i.qa_is_current(self.case,self.video,r))

    def test_math_default_selection_matches_curated_bucket(self):
        self.assertTrue(i.video_selected(self.video,'video'))
        self.video['local_path']=self.video['local_path'].replace('/qualified/','/unqualified/')
        self.assertFalse(i.video_selected(self.video,'video'))
        self.assertTrue(i.video_selected(self.video,'video','all'))

    def test_nonready_existing_file_not_promoted(self):
        for status in ['pending','submitted','failed']:
            self.video['status']=status
            self.assertEqual(ev._promote_existing_local_videos(self.case,selected_video_ids={'v001'}),[])
            self.assertEqual(self.video['status'],status)

    def test_regenerated_video_in_qualified_directory_requires_new_review(self):
        self.video['human_review']='pending'
        self.assertFalse(i.video_selected(self.video,'video'))
        control=self.case['videos'][1]
        control['human_review']='pending'
        self.assertTrue(i.video_selected(control,'video'))  # Historical qualified control.
        control['qualification_pending']=True
        self.assertFalse(i.video_selected(control,'video'))

    def test_variant_title_and_question_are_used(self):
        self.video['variant_context']={'title':'Variant Title','questions':[dict(question(),text_en='Variant question?')],
                                     'conflict_spec':self.case['conflict_spec']}
        context=core.video_case_context(self.case,self.video)
        self.assertEqual(context['title'],'Variant Title')
        self.assertEqual(context['questions'][0]['text_en'],'Variant question?')

    def test_description_tracks_review_text_as_well_as_movie(self):
        h=e.video_sha256(self.video)
        self.video['video_observation']={'source_sha256':h,'summary_en':'Three cards move.','context_en':'The row reads 3, 1, 2.'}
        self.video['description']={'source':'video','source_sha256':h,'context_en':'The row reads 3, 1, 2.'}
        self.assertTrue(i.description_is_current(self.video))
        self.video['video_observation']['context_en']='The row reads 3, 1, 2 after the card moves left.'
        self.assertFalse(i.description_is_current(self.video))

    def test_promoted_snapshot_cannot_mutate_qualified_file(self):
        self.case['canonical_case_path']='dataset/cases/math/example.json'
        with self.assertRaisesRegex(core.PipelineError,'canonical case'):
            i.require_writable_case(self.case,Path('snapshot.json'))

    def test_force_author_cannot_erase_qualified_variants(self):
        directory=self.root/'dataset/cases'/i.MATH_GROUP;directory.mkdir(parents=True)
        path=directory/'example.json';core.atomic_write_json(path,self.case)
        original=path.read_bytes()
        args=build_parser().parse_args(['author','--force','--group',i.MATH_GROUP,
                                       '--output-dir',str(directory.parent)])
        with patch.object(a,'require_openrouter_api_key',return_value='offline'), \
             patch.object(a,'make_openrouter_limiter',return_value=None), \
             patch.object(a,'iter_source_paths',return_value=[Path('example.md')]), \
             patch.object(a,'parse_source_case',return_value={'case_id':'example'}), \
             patch.object(a,'openrouter_json') as provider:
            self.assertEqual(a.command_author(args),1)
            provider.assert_not_called()
        self.assertEqual(path.read_bytes(),original)

    def test_summary_excludes_stale_judgment_and_unqualified_video(self):
        r=self.result();r['judgment']={'verdict':'context_grounded','confidence':1,
            'input_fingerprint':i.judgment_fingerprint(self.case,self.video,r)}
        self.video['qa_results']=[r]
        def summary():
            with patch.object(reporting,'load_case',return_value=self.case):
                return reporting.build_summary([Path('example.json')],qa_model=r['model'],
                    input_mode='video',effort='default',work_title_prefix=None)
        self.assertIn('example',summary()['cases'])
        self.case['conflict_spec']['normal_fact_en']='A changed normal fact.'
        self.assertEqual(summary()['cases'],{})
        r['judgment']['input_fingerprint']=i.judgment_fingerprint(self.case,self.video,r)
        self.video['human_review']='rejected'
        self.assertEqual(summary()['cases'],{})

    def test_qa_to_judge_to_summary_uses_same_current_scope(self):
        directory=self.root/'dataset/cases'/i.MATH_GROUP;directory.mkdir(parents=True)
        path=directory/'example.json';core.atomic_write_json(path,self.case)
        parser=build_parser();args=parser.parse_args(['qa-judge','--group',i.MATH_GROUP,
            '--dataset-dir',str(directory.parent),'--case-id','example','--video-id','v001',
            '--qa-model','gemini','--thinking-effort','default','--case-workers','1'])
        _validate(args,parser)
        calls=[]
        def batch(**kw):
            results=[]
            for q,effort in kw['question_runs']:
                r=self.result();r['question']=q['text_en'];r['thinking_effort']=effort
                r.pop('input_fingerprint');results.append(r)
            calls.append(kw)
            return results,[]
        backend=argparse.Namespace(require_api_key=lambda:'offline')
        with patch.object(qa,'get_backend',return_value=backend),patch.object(qa,'expand_thinking_efforts',return_value=('default',)), \
             patch.object(qa,'make_request_limiter',return_value=None),patch.object(qa,'run_qa_batch',side_effect=batch):
            self.assertEqual(qa.command_qa(args),0)
            self.assertEqual(qa.command_qa(args),0)
            self.assertEqual(len(calls),1)
            saved=core.load_case(path);saved['questions'][0]['text_en']='Starting with [1, 2], append 3 at the end. What list results?'
            core.atomic_write_json(path,saved)
            self.assertEqual(qa.command_qa(args),0)
            self.assertEqual(len(calls),2)
        with patch.object(ev,'require_openrouter_api_key',return_value='offline'), \
             patch.object(ev,'make_openrouter_limiter',return_value=None), \
             patch.object(ev,'openrouter_json',return_value=({'verdict':'context_grounded','confidence':1},{'id':'mock'})) as judge:
            self.assertEqual(ev.command_judge(args),0)
            self.assertEqual(judge.call_count,1)
            self.assertEqual(ev.command_judge(args),0)
            self.assertEqual(judge.call_count,1)
            saved=core.load_case(path);saved['questions'][0]['normal_control_reference_en']='The completed list reads [1, 2, 3].'
            core.atomic_write_json(path,saved)
            self.assertEqual(ev.command_judge(args),0)
            self.assertEqual(judge.call_count,2)
        summary=reporting.build_summary([path],qa_model=args.qa_model,input_mode='video',effort='default',work_title_prefix=None)
        self.assertIn('example',summary['cases'])
        self.assertEqual(ev._completion_counts(args,('default',)),(1,1,1,1))

    def test_existing_unchanged_questions_save_real_audit_without_clearing_qa(self):
        directory=self.root/'dataset/cases'/i.MATH_GROUP;directory.mkdir(parents=True)
        path=directory/'example.json'
        self.video['qa_results']=[self.result()]
        core.atomic_write_json(path,self.case)
        args=build_parser().parse_args(['questions','--audit-only','--group',i.MATH_GROUP,
            '--dataset-dir',str(directory.parent),'--case-id','example','--video-id','v001'])
        def api(**kw):
            data=json.loads(kw['messages'][1]['content'])
            if kw['schema_name']=='math_question_only_audit':
                return {'checks':[{'index':1,'self_contained':True,'answer_en':'[1, 2, 3]',
                                   'derivation_en':'Append at the end.','issues':[]}]},{'id':'blind'}
            return {'valid':True,'issues':[],'questions':data['questions']},{'id':'context'}
        with patch.object(a,'PROJECT_ROOT',self.root),patch.object(a,'require_openrouter_api_key',return_value='offline'), \
             patch.object(a,'make_openrouter_limiter',return_value=None),patch.object(a,'openrouter_json',side_effect=api):
            self.assertEqual(a.command_questions(args),0)
        saved=core.load_case(path)
        self.assertEqual(saved['questions'],self.case['questions'])
        self.assertEqual(saved['videos'][0]['qa_results'],self.video['qa_results'])
        self.assertEqual(saved['question_audit']['request_ids'],['blind','context'])
        self.assertEqual(saved['question_audit']['scope_fingerprint'],
                         i.question_scope_fingerprint(saved,a.question_case_context(saved)))


class AuditReceiptTests(unittest.TestCase):
    def test_check_only_saves_evidence_and_cannot_repair(self):
        q=question();authored=[{'question_en':q['text_en'], 'conflict_video_reference_en':q['conflict_video_reference_en'],
                               'normal_control_reference_en':q['normal_control_reference_en']}]
        receipt={}
        def api(**kw):
            data=json.loads(kw['messages'][1]['content'])
            if kw['schema_name']=='math_question_only_audit':
                self.assertEqual(set(data),{'questions'})
                return {'checks':[{'index':1,'self_contained':True,'answer_en':'[1, 2, 3]',
                                   'derivation_en':'Append to the end.','issues':[]}]},{'id':'blind'}
            self.assertEqual(data['validation_mode'],'check_only')
            return {'valid':True,'issues':[],'questions':data['questions']},{'id':'context'}
        kw=dict(case_context={'title':'Private case'},system_prompt='Validate.',api_key='offline',
                timeout=1,max_repairs=0,max_retries=0,request_limiter=None,
                require_self_contained=True,audit_only=True,audit_receipt=receipt)
        with patch.object(a,'openrouter_json',side_effect=api):
            self.assertEqual(a.verify_authored_questions(authored,**kw),authored)
        self.assertEqual(receipt['request_ids'],['blind','context'])
        self.assertEqual(receipt['method'],'independent_model')

    def test_check_only_rejects_model_rewriting(self):
        q={'question_en':question()['text_en'],'conflict_video_reference_en':'The list is [3, 1, 2].',
           'normal_control_reference_en':'The list is [1, 2, 3].'}
        def api(**kw):
            return {'valid':True,'issues':[],'questions':[dict(q,normal_control_reference_en='Changed reference.')]},{'id':'context'}
        receipt={}
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'PROJECT_ROOT',Path(tmp)),patch.object(a,'openrouter_json',side_effect=api):
            with self.assertRaisesRegex(core.PipelineError,'Check-only audit failed'):
                a.verify_authored_questions([q],case_context={},system_prompt='Validate.',api_key='offline',timeout=1,
                    max_repairs=0,max_retries=0,request_limiter=None,audit_only=True,audit_receipt=receipt)
        self.assertEqual(receipt,{})

    def test_cli_exposes_offline_audit_and_check_only(self):
        parser=build_parser()
        args=parser.parse_args(['audit','--group',i.MATH_GROUP,'--output','audit.json'])
        self.assertEqual(args.func.__name__,'command_audit')
        args=parser.parse_args(['questions','--audit-only','--group',i.MATH_GROUP])
        _validate(args,parser)
        self.assertTrue(args.audit_only)


if __name__=='__main__':unittest.main()
