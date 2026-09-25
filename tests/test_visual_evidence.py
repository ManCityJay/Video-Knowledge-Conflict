"""Offline regressions for pixel-bound annotations and reference selection."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from vconflict_pipeline import evidence as e, authoring as a
from vconflict_pipeline import generation as g
from vconflict_pipeline import deletion as deletion
from vconflict_pipeline.core import PipelineError, sha256_text

class EvidenceTests(unittest.TestCase):
    def video(self, path):
        return {'video_id':'v001','role':'conflict','status':'ready',
                'local_path':str(path),'seedance_prompt_en':'Intended outcome is A.'}

    def test_replaced_bytes_invalidate_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'video.mp4';p.write_bytes(b'old')
            v=self.video(p);v['video_observation']={'summary_en':'Actual outcome is B.','source_sha256':hashlib.sha256(b'old').hexdigest()}
            with patch.object(e,'resolve_video_path',return_value=p):
                self.assertEqual(e.observed_summary(v),'Actual outcome is B.')
                p.write_bytes(b'new')
                with self.assertRaisesRegex(PipelineError,'changed since visual review'):e.observed_summary(v)

    def test_required_review_cannot_fall_back_to_intended_prompt(self):
        v=self.video('unused');v['require_video_observation']=True
        with self.assertRaisesRegex(PipelineError,'Review the generated pixels'):e.observed_summary(v)

    def test_legacy_prompt_description_still_uses_prompt_hash(self):
        v=self.video('unused');v['description']={'source':'seedance_prompt_en'}
        self.assertEqual(e.description_source_hash(v),sha256_text(v['seedance_prompt_en']))

    def test_video_description_uses_file_hash_not_prompt_hash(self):
        v=self.video('unused');v['description']={'source':'video'}
        with patch.object(e,'observed_summary',return_value='Observed.'),patch.object(e,'video_sha256',return_value='FILE_HASH'):
            self.assertEqual(e.description_source_hash(v),'FILE_HASH')

    def test_reviewed_video_cannot_use_old_prompt_description(self):
        v=self.video('unused');v['description']={'source':'seedance_prompt_en'}
        v['require_video_observation']=True
        with self.assertRaisesRegex(PipelineError,'reviewed pixels'):e.description_source_hash(v)

    def test_qualified_reference_variant_cannot_generate_without_first_frame(self):
        v=self.video('unused');v['qualified_reference']={'video_id':'v001'}
        with self.assertRaisesRegex(PipelineError,'first_frame_path'):g.seedance_content(v)

    def test_question_context_uses_pixels_and_retains_control(self):
        conflict=self.video('unused');control={'role':'control','seedance_prompt_en':'Normal control A.'}
        c={'case_id':'test','title':'Sorting','conflict_spec':{},'videos':[conflict,control]}
        with patch.object(a,'observed_summary',return_value='Actual outcome B.'):
            context=a.question_case_context(c)
        self.assertNotIn('seedance_prompt_en',context['videos'][0])
        self.assertEqual(context['videos'][0]['observed_video_content_en'],'Actual outcome B.')
        self.assertEqual(context['videos'][1]['seedance_prompt_en'],'Normal control A.')

    def test_only_verified_existing_conflicts_can_be_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'g').mkdir();(root/'g/c.json').touch();p=root/'movie.mp4';p.write_bytes(b'test')
            videos=[]
            for i,(review,role,bucket) in enumerate([('verified','conflict','qualified'),('pending','conflict','qualified'),('verified','control','qualified'),('verified','conflict','unqualified')]):
                v=self.video(p);v.update(video_id=f'v{i}',human_review=review,role=role,local_path=f'videos/{bucket}/v{i}.mp4');videos.append(v)
            with patch.object(e,'load_case',return_value={'videos':videos}),patch.object(e,'resolve_video_path',return_value=p),patch.object(e,'reference_frames',return_value='PIXELS'):
                refs=e.qualified_references('g','c',root=root)
            self.assertEqual([r['video_id'] for r in refs],['v0'])
            self.assertEqual(refs[0]['chronological_frames'],'PIXELS')

class WithdrawalTests(unittest.TestCase):
    def test_deleting_variant_preserves_other_videos_in_shared_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'shared_case';directory.mkdir()
            selected=directory/'m12.mp4';selected.write_bytes(b'delete')
            retained=directory/'m11.mp4';retained.write_bytes(b'keep')
            case_path=Path(tmp)/'case.json';case_path.write_text('{}')
            with patch.object(deletion,'_validated_local_video_path',side_effect=Path):
                result=deletion._remove_entire_case(case_path=case_path,case={'videos':[{'local_path':str(selected)}]},video_directories=[directory])
            self.assertEqual(result,0)
            self.assertFalse(selected.exists())
            self.assertEqual(retained.read_bytes(),b'keep')
            self.assertFalse(case_path.exists())

    def test_withdrawn_variant_is_not_recreated_or_run(self):
        spec=importlib.util.spec_from_file_location('batch_evidence_test',ROOT/'artifacts/math_expansion_20260923/run_batch.py')
        b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
        rows=[{'label':'M09','case_id':'merge'}]
        with tempfile.TemporaryDirectory() as tmp:
            here=Path(tmp);(here/'excluded_variants.json').write_text(json.dumps({'M09':{'reason':'deleted'}}))
            with patch.object(b,'HERE',here),patch.object(b,'prepare',return_value=rows),patch.object(b,'author') as author,patch.object(sys,'argv',['batch','author','--variant','M09']):
                with self.assertRaisesRegex(RuntimeError,'withdrawn'):b.main()
                author.assert_not_called()

if __name__=='__main__':unittest.main()
