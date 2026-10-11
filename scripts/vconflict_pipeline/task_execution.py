"""Single-task QA/Judge requests and provenance-checked result merging."""
from __future__ import annotations

import argparse
import json
import os

from .common import PipelineError, utc_now
from .filters import control_video, scope_id
from .integrity import digest, judgment_fingerprint, qa_fingerprint
from .qa import get_backend, local_qa_max_tokens, preflight_qa_backend, run_qa_once
from .result_rules import filter_field, set_filter_field
from .schema import JUDGMENT_SCHEMA
from .settings import AUTHOR_JUDGE_MODEL, VERDICTS
from .transport import openrouter_json


JUDGE_SYSTEM_PROMPT = """Evaluate the supplied final_answer against the context
references. Treat final_answer as the complete answer to judge. Do not infer,
reconstruct, or consider any reasoning or other response text that is not in
final_answer.

For video_role=conflict:
- context_grounded means final_answer clearly reports the conflict-context fact.
- knowledge_trapped means final_answer substitutes the normal-control answer for the
  conflict-context fact.
- ambiguous_or_unjudgeable covers irrelevant, unresolved, mixed, contradictory,
  hedged, or otherwise unclassifiable final answers.

For video_role=control:
- context_grounded means final_answer clearly reports the normal-control fact.
- never use knowledge_trapped; an answer matching the conflict reference or
  neither reference is ambiguous_or_unjudgeable.

Return only the requested structured result."""


class TaskExecutor:
    def __init__(self, args, planner, diagnostics):
        self.args, self.planner, self.diagnostics = args, planner, diagnostics
        self.backend = get_backend(args.qa_model)
        self.api_key = os.environ.get(self.backend.api_key_variable, '').strip() if self.backend.api_key_variable else ''
        self.judge_key = os.environ.get('OPENROUTER_API_KEY', '').strip()
        self.served = None
        self.backend_ready = False

    def ensure_backend(self):
        if not self.backend_ready:
            preflight = argparse.Namespace(**{**vars(self.args), 'input': 'question_only'})
            self.served = preflight_qa_backend(preflight)
            self.api_key = self.backend.require_api_key()
            self.backend_ready = True

    def normalize_filter(self, case, task, result):
        video, _, q = self.planner.owners(case, task)
        set_filter_field(result, 'stage', task.stage)
        set_filter_field(result, 'fingerprint', task.fingerprint)
        if task.stage == 'control_video' and scope_id(video) == 'case':
            result['input_fingerprint'] = qa_fingerprint(case, control_video(case, video), q, 'video', task.prefix)
        records = self.planner.records(case, task, result)
        records[:] = [r for r in records if r.get('run_id') != result['run_id']]
        records.append(result)

    def request(self, task, media):
        if task.kind == 'qa':
            return run_qa_once(
                input_mode=task.mode, video_path=task.video_path, context_text=task.context_text,
                work_title=task.context['title'].split(':', 1)[0].strip() if task.prefix else None,
                work_title_prefix=task.prefix, question=task.question, thinking_effort=task.effort,
                qa_model=self.args.qa_model, api_key=self.api_key, timeout=self.args.timeout,
                local_served_model_id=self.served,
                local_max_tokens=local_qa_max_tokens(self.args), based=task.based,
                diagnostics=self.diagnostics, prepared_video_input=media,
                diagnostic_stage=('question_only filter' if task.stage == 'question_only' else
                                  'control filter' if task.stage == 'control_video' else 'main'))
        q, facts = task.question, task.context['conflict_spec']
        final_answer = task.result.get('final_answer')
        if not isinstance(final_answer, str) or not final_answer.strip():
            raise PipelineError('Selected QA has no final_answer; run --force-qa')
        payload = {'video_role': task.context['role'], 'question': q['text_en'], 'final_answer': final_answer,
                   'normal_fact': facts['normal_fact_en'], 'intended_video_fact': facts['intended_video_fact_en'],
                   'conflict_video_reference': q['conflict_video_reference_en'],
                   'normal_control_reference': q['normal_control_reference_en']}
        verdict, response = openrouter_json(
            messages=[{'role': 'system', 'content': JUDGE_SYSTEM_PROMPT},
                      {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            model=AUTHOR_JUDGE_MODEL, schema_name='knowledge_conflict_judgment', schema=JUDGMENT_SCHEMA,
            api_key=self.judge_key, timeout=self.args.timeout, single_attempt=True)
        if verdict.get('verdict') not in VERDICTS:
            raise PipelineError('Invalid judgment verdict')
        if task.context['role'] == 'control' and verdict['verdict'] == 'knowledge_trapped':
            raise PipelineError('Judge returned knowledge_trapped for a control input')
        if task.stage and verdict['verdict'] not in ('context_grounded', 'ambiguous_or_unjudgeable'):
            raise PipelineError('Invalid filter judgment verdict')
        confidence = float(verdict['confidence'])
        if not 0 <= confidence <= 1:
            raise PipelineError('Invalid judgment confidence')
        return {**verdict, 'confidence': confidence, 'timestamp': utc_now(),
                'judge_model': AUTHOR_JUDGE_MODEL, 'judge_request_id': response.get('id')}

    def merge(self, case, task, output):
        video, _, q = self.planner.owners(case, task)
        _, binding = self.planner.fingerprint(case, video, q, task.stage, task.mode, task.prefix, task.based)
        if binding != task.binding:
            raise PipelineError('Inputs changed during request; refusing stale result')
        if task.kind == 'qa':
            if task.stage:
                self.normalize_filter(case, task, output)
            else:
                if task.mode != 'question_only':
                    output['input_fingerprint'] = task.fingerprint
                else:
                    # Same request as the shared question-only filter: persist its
                    # existing provenance fields so another command can reuse it.
                    set_filter_field(output, 'stage', 'question_only')
                    set_filter_field(output, 'fingerprint', task.fingerprint)
                self.planner.records(case, task).append(output)
            return
        records = self.planner.records(case, task, task.result)
        result = next((r for r in records if r.get('run_id') == task.result['run_id']), None)
        if result is None or result.get('final_answer') != task.result.get('final_answer'):
            raise PipelineError('QA changed during judging; refusing stale judgment')
        if task.stage:
            output['filter_fingerprint'] = digest({'input': task.fingerprint, 'final_answer': result['final_answer']})
            if task.stage == 'control_video' and scope_id(video) == 'case':
                output['input_fingerprint'] = judgment_fingerprint(case, control_video(case, video), result)
        elif task.mode != 'question_only':
            output['input_fingerprint'] = judgment_fingerprint(case, video, result)
        if not task.stage and filter_field(result, 'stage'):
            output['filter_fingerprint'] = digest({'input': filter_field(result, 'fingerprint'),
                                                   'final_answer': result['final_answer']})
        result['judgment'] = output
