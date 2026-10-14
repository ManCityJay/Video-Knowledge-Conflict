"""Question-only provenance and optional question-scoped report filters.

Report gate checks are read-only; task_execution.py owns standalone requests
and merges. Shared questions reuse one scope; variant questions are isolated
by their video scope. Target QA never depends on these report filters.
"""
from __future__ import annotations


from .common import PipelineError, question_only_records, video_case_context
from .integrity import digest, question_content
from .result_rules import (
    canonical_verdict,
    filter_field,
    qa_result_matches,
)


def scope_id(video):
    return video['video_id'] if video and video.get('variant_context') is not None else 'case'


def question_filter_fingerprint(case, video, question):
    context = video_case_context(case, video) if video else case
    payload = {'version': 1, 'scope': scope_id(video), 'stage': 'question_only',
               'question': question_content(question), 'facts': context['conflict_spec']}
    return digest(payload)


def _latest(results):
    return max(results, key=lambda r: (str(r.get('timestamp', '')), str(r.get('run_id', ''))),
               default=None)


def question_filter_state(case, video, question, model, effort):
    try:
        fingerprint = question_filter_fingerprint(case, video, question)
    except (PipelineError, OSError) as exc:
        reason = str(exc)
        return {'status': 'unavailable', 'reason': reason, 'result': None}
    result = _latest(r for r in question_only_records(question)
                     if r.get('question_id') == question['question_id']
                     and qa_result_matches(r, input_selection='question_only', model=model, efforts={effort}))
    if result is None:
        return {'status': 'missing', 'result': None, 'fingerprint': fingerprint}
    status = 'stale'
    current = (filter_field(result, 'fingerprint') == fingerprint
               and result.get('question') == question['text_en'])
    if current and result.get('final_answer'):
        judgment = result.get('judgment')
        if not isinstance(judgment, dict):
            status = 'unjudged'
        elif filter_field(result, 'stage') and filter_field(judgment, 'fingerprint') != digest(
                {'input': fingerprint, 'final_answer': result['final_answer']}):
            status = 'unjudged'
        else:
            status = ('passed' if canonical_verdict(judgment.get('verdict', '')) == 'context_grounded'
                      else 'failed')
    return {'status': status, 'result': result, 'fingerprint': fingerprint}


def question_gate(case, video, question, model, effort):
    state = question_filter_state(case, video, question, model, effort)
    reason = 'passed' if state['status'] == 'passed' else 'question_only_' + state['status']
    return {'passed': reason == 'passed', 'reason': reason,
            'question_only': state['status'],
            'case_id': case['case_id'], 'question_scope': scope_id(video),
            'question_id': question['question_id'], 'model': model,
            'thinking_effort': effort}
