"""One shared final-answer-only Judge request for pipeline and local experiments."""
from __future__ import annotations

import json
import math

from .common import PipelineError, utc_now
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


def judge_payload(*, question, facts, role, final_answer):
    if not isinstance(final_answer, str) or not final_answer.strip():
        raise PipelineError('Selected QA has no final_answer; run --force-qa')
    return {
        'video_role': role, 'question': question['text_en'], 'final_answer': final_answer,
        'normal_fact': facts['normal_fact_en'],
        'intended_video_fact': facts['intended_video_fact_en'],
        'conflict_video_reference': question['conflict_video_reference_en'],
        'normal_control_reference': question['normal_control_reference_en'],
    }


def judge_answer(*, question, facts, role, final_answer, api_key, timeout):
    payload = judge_payload(question=question, facts=facts, role=role, final_answer=final_answer)
    verdict, response = openrouter_json(
        messages=[{'role': 'system', 'content': JUDGE_SYSTEM_PROMPT},
                  {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
        model=AUTHOR_JUDGE_MODEL, schema_name='knowledge_conflict_judgment',
        schema=JUDGMENT_SCHEMA, api_key=api_key, timeout=timeout, single_attempt=True)
    if verdict.get('verdict') not in VERDICTS:
        raise PipelineError('Invalid judgment verdict')
    if role == 'control' and verdict['verdict'] == 'knowledge_trapped':
        raise PipelineError('Judge returned knowledge_trapped for a control input')
    confidence = verdict.get('confidence')
    if (isinstance(confidence, bool) or not isinstance(confidence, (float, int))
            or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        raise PipelineError('Invalid judgment confidence')
    return {**verdict, 'confidence': float(confidence), 'timestamp': utc_now(),
            'judge_model': AUTHOR_JUDGE_MODEL, 'judge_request_id': response.get('id')}
