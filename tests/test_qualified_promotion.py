import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from vconflict_pipeline.core import load_case, validate_case, PipelineError, AUTHOR_OUTPUT_SCHEMA

class PromotionTests(unittest.TestCase):
    def test_accumulated_variants_exceed_author_limit_without_changing_author_schema(self):
        case = load_case(ROOT/'dataset/cases/mathematics_algorithm_conflicts/append_inserts_at_front.json')
        video = copy.deepcopy(next(v for v in case['videos'] if v['role'] == 'conflict'))
        for n in range(90, 95):
            added = copy.deepcopy(video)
            added.update(video_id=f'v{n:03}', local_path=f"videos/seedance/mathematics_algorithm_conflicts/qualified/{case['case_id']}/v{n:03}.mp4")
            added['seedance_prompt_en'] += f' Test variant number {n}.'
            case['videos'].append(added)
        validate_case(case)
        self.assertEqual(AUTHOR_OUTPUT_SCHEMA['properties']['conflict_video_prompts_en']['maxItems'], 5)
        case['videos'].append(copy.deepcopy(case['videos'][-1]))
        with self.assertRaisesRegex(PipelineError, 'Duplicate video_id'):
            validate_case(case)

    def test_promoted_batch_cannot_regenerate_or_overwrite_questions(self):
        spec = importlib.util.spec_from_file_location('promotion_batch', ROOT/'artifacts/math_expansion_20260923/run_batch.py')
        batch = importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
        with tempfile.TemporaryDirectory() as temp:
            here = Path(temp); runtime = here/'case.json'; runtime.write_text('{}')
            rows = [{'label':'M01','case_id':'append','video_id':'exp20260923_m01'}]
            for stage in ('author','generate','questions'):
                with patch.object(batch,'HERE',here), patch.object(batch,'prepare',return_value=rows), \
                     patch.object(batch,'runtime_path',return_value=runtime), \
                     patch.object(batch,'checked_case',return_value={'qualified_promotion':{'video_id':'v006'}}), \
                     patch.object(batch,'pipeline') as pipeline, patch.object(batch,'author') as author, \
                     patch.object(sys,'argv',['batch',stage]):
                    batch.main()
                    pipeline.assert_not_called(); author.assert_not_called()

if __name__ == '__main__': unittest.main()
