"""Question-scoped knowledge filters shared by execution and reporting.

Gate checks are read-only; scheduler.py owns all filter requests and commits.
Private variant questions own their own records and matched control video.
"""
from __future__ import annotations


from .core import (
    FILTER_RESULT_FIELDS, PipelineError, canonical_verdict, filter_field,
    qa_result_input_mode, resolve_video_path, video_case_context,
)
from .evidence import observed_summary, video_sha256
from .integrity import digest, judgment_is_current, qa_is_current, question_content
from .settings import FAIRY_TALE_GROUP


def scope_id(video):
    return video['video_id'] if video.get('variant_context') is not None else 'case'


def control_video(case, video):
    if video.get('variant_context') is not None:
        path = video['variant_context'].get('matched_control_path')
        if not path:
            raise PipelineError('control_unmapped')
        control = next((v for v in case['videos']
                        if v['role'] == 'control' and v['local_path'] == path), None)
        # This explicit per-variant mapping is never replaced by the shared control.
        if control is None:
            control = {'video_id': 'control_' + video['video_id'], 'role': 'control',
                       'local_path': path, 'status': 'ready', 'qa_results': []}
    else:
        controls = [v for v in case['videos'] if v['role'] == 'control']
        if len(controls) != 1:
            raise PipelineError('control_unmapped')
        control = controls[0]
    if control['status'] != 'ready' or control.get('human_review') == 'rejected':
        raise PipelineError('control_unavailable')
    if control.get('qualification_pending'):
        raise PipelineError('control_unavailable')
    resolve_video_path(control['local_path'], must_exist=True)
    observed_summary(control)
    return control


def effective_prefix(group, prefix):
    # Groups can reuse another group's video paths. The command's group, not
    # the media directory, determines the experiment's prompt condition.
    if group == FAIRY_TALE_GROUP:
        return bool(prefix)
    return None


def stage_fingerprint(case, video, question, stage, prefix):
    context = video_case_context(case, video)
    payload = {'version': 1, 'scope': scope_id(video), 'stage': stage,
               'question': question_content(question), 'facts': context['conflict_spec']}
    if stage == 'control_video':
        control = control_video(case, video)
        payload.update(control_path=control['local_path'], control_sha256=video_sha256(control),
                       work_title_prefix=prefix,
                       title=context['title'].split(':', 1)[0].strip() if prefix else None)
    return digest(payload)


def _matches(result, question, model, effort, mode, prefix=None):
    from .qa import qa_result_thinking_effort
    return (result.get('question_id') == question['question_id']
            and result.get('model') == model
            and qa_result_thinking_effort(result) == effort
            and qa_result_input_mode(result) == mode
            and (mode != 'video' or result.get('based', False) is False)
            and (mode != 'video' or prefix is None
                 or result.get('work_title_prefix') is prefix))


def _latest(results):
    return max(results, key=lambda r: (str(r.get('timestamp', '')), str(r.get('run_id', ''))),
               default=None)


def stage_result(case, video, question, stage, model, effort, prefix):
    mode = 'question_only' if stage == 'question_only' else 'video'
    candidates = [r for field in FILTER_RESULT_FIELDS for r in question.get(field, [])
                  if filter_field(r, 'stage') == stage
                  and _matches(r, question, model, effort, mode, prefix)]
    if stage == 'question_only':
        candidates.extend(r for r in question.get('question_only_results', [])
                          if _matches(r, question, model, effort, mode))
    else:
        try:
            control = control_video(case, video)
        except (PipelineError, OSError):
            return _latest(candidates)
        # Reuse shared control QA only when it really asked this same question.
        cq = next((q for q in video_case_context(case, control)['questions']
                   if q['question_id'] == question['question_id']), None)
        if cq is not None and question_content(cq) == question_content(question):
            candidates.extend(r for r in control.get('qa_results', [])
                              if _matches(r, question, model, effort, mode, prefix))
    return _latest(candidates)


def stage_state(case, video, question, stage, model, effort, prefix):
    try:
        fingerprint = stage_fingerprint(case, video, question, stage, prefix)
    except (PipelineError, OSError) as exc:
        reason = str(exc)
        return {'status': 'unavailable', 'reason': reason, 'result': None}
    result = stage_result(case, video, question, stage, model, effort, prefix)
    if result is None:
        return {'status': 'missing', 'result': None, 'fingerprint': fingerprint}
    status = 'stale'
    current = (filter_field(result, 'fingerprint') == fingerprint
               and result.get('question') == question['text_en'])
    # Existing control results already carry the pipeline's video/question provenance.
    legacy_control = stage == 'control_video' and not filter_field(result, 'stage')
    if legacy_control:
        current = qa_is_current(case, control_video(case, video), result)
    if current and result.get('final_answer'):
        judgment = result.get('judgment')
        if not isinstance(judgment, dict):
            status = 'unjudged'
        elif legacy_control and not judgment_is_current(case, control_video(case, video), result):
            status = 'unjudged'
        elif filter_field(result, 'stage') and filter_field(judgment, 'fingerprint') != digest(
                {'input': fingerprint, 'final_answer': result['final_answer']}):
            status = 'unjudged'
        else:
            status = ('passed' if canonical_verdict(judgment.get('verdict', '')) == 'context_grounded'
                      else 'failed')
    return {'status': status, 'result': result, 'fingerprint': fingerprint}


def question_gate(case, video, question, model, effort, prefix=None):
    first = stage_state(case, video, question, 'question_only', model, effort, None)
    second = stage_state(case, video, question, 'control_video', model, effort, prefix)
    reason = ('passed' if first['status'] == second['status'] == 'passed' else
              'question_only_' + first['status'] if first['status'] != 'passed' else
              'control_video_' + second['status'])
    return {'passed': reason == 'passed', 'reason': reason,
            'question_only': first['status'], 'control_video': second['status'],
            'case_id': case['case_id'], 'question_scope': scope_id(video),
            'question_id': question['question_id'], 'model': model,
            'thinking_effort': effort, 'work_title_prefix': prefix}


def qa_allowed(case, video, question, model, effort, prefix, input_mode='video'):
    if input_mode not in ('video', 'description'):
        return True
    if input_mode == 'video' and video['role'] == 'control':
        return stage_state(case, video, question, 'question_only', model, effort, None)['status'] == 'passed'
    return question_gate(case, video, question, model, effort, prefix)['passed']
