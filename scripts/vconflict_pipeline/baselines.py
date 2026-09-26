"""Question-scoped knowledge baselines shared by execution and reporting.

No model calls occur while checking a gate. Only prepare_baselines makes requests.
Private variant questions own their own records and matched control video.
"""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter

from .core import (PipelineError, atomic_write_json, canonical_verdict,
                   qa_result_input_mode, resolve_video_path, utc_now, video_case_context)
from .evidence import observed_summary, video_sha256
from .integrity import digest, judgment_is_current, qa_is_current, question_content
from .settings import COSMOS_QA_MODEL, FAIRY_TALE_GROUP, AUTHOR_JUDGE_MODEL


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
            and (mode != 'video' or prefix is None
                 or result.get('work_title_prefix') is prefix))


def _latest(results):
    return max(results, key=lambda r: (str(r.get('timestamp', '')), str(r.get('run_id', ''))),
               default=None)


def stage_result(case, video, question, stage, model, effort, prefix):
    mode = 'question_only' if stage == 'question_only' else 'video'
    candidates = [r for r in question.get('baseline_results', [])
                  if r.get('baseline_stage') == stage
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
    current = (result.get('baseline_fingerprint') == fingerprint
               and result.get('question') == question['text_en'])
    # Existing control results already carry the pipeline's video/question provenance.
    legacy_control = stage == 'control_video' and not result.get('baseline_stage')
    if legacy_control:
        current = qa_is_current(case, control_video(case, video), result)
    if current and result.get('final_answer'):
        judgment = result.get('judgment')
        if not isinstance(judgment, dict):
            status = 'unjudged'
        elif legacy_control and not judgment_is_current(case, control_video(case, video), result):
            status = 'unjudged'
        elif result.get('baseline_stage') and judgment.get('baseline_fingerprint') != digest(
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
    if input_mode != 'video':
        return True
    if video['role'] == 'control':
        return stage_state(case, video, question, 'question_only', model, effort, None)['status'] == 'passed'
    return question_gate(case, video, question, model, effort, prefix)['passed']


def prepare_baselines(args, loaded, efforts):
    """Run both stages in order; incorrect answers are exclusions, errors are failures.

Saves after each answer/judgment so an interrupted invocation resumes safely.
No force flag on a conflict run clears baseline or historical conflict results.
"""
    from .evaluation import _eligible_videos, _selected_questions, JUDGE_SYSTEM_PROMPT
    from .core import JUDGMENT_SCHEMA
    from .qa import (get_backend, preflight_qa_backend, run_qa_batch,
                     work_title_prefix_condition)
    from .transport import (RequestLimiter, make_request_limiter, make_openrouter_limiter,
                            openrouter_json, require_openrouter_api_key)
    from .integrity import qa_fingerprint, judgment_fingerprint

    prefix = work_title_prefix_condition(args.group, 'video', args.with_work_title_prefix)
    qa_limiter = (RequestLimiter(args.cosmos_workers) if args.qa_model == COSMOS_QA_MODEL
                  else make_request_limiter(args))
    judge_limiter = make_openrouter_limiter(args)
    backend_ready = False
    served = None
    failures = 0
    counts = Counter()
    for path, case in loaded:
        videos = _eligible_videos(case, input_mode='video',
                                  selected_video_ids=set(args.video_id or []),
                                  video_scope=getattr(args, 'video_scope', None))
        seen = set()
        for video in videos:
            context = video_case_context(case, video)
            for question in _selected_questions(context, set(args.question_id or [])):
                for effort in efforts:
                    key = (scope_id(video), question['question_id'], effort)
                    if key in seen:
                        continue
                    seen.add(key)
                    for stage in ('question_only', 'control_video'):
                        stage_prefix = None if stage == 'question_only' else prefix
                        state = stage_state(case, video, question, stage, args.qa_model, effort, stage_prefix)
                        force_qa = getattr(args, 'baselines_only', False) and args.force_qa
                        force_judge = getattr(args, 'baselines_only', False) and args.force_judge
                        if state['status'] in ('passed', 'failed') and not (force_qa or force_judge):
                            if state['status'] == 'failed':
                                break
                            continue
                        if state['status'] == 'unavailable':
                            print(f"Baseline unavailable {case['case_id']}/{scope_id(video)}/{question['question_id']}: {state['reason']}")
                            failures += 1
                            break
                        try:
                            result = state['result']
                            control = control_video(case, video) if stage == 'control_video' else None
                            control_input = (qa_fingerprint(case, control, question, 'video', prefix)
                                             if control is not None and scope_id(video) == 'case' else None)
                            if force_qa or state['status'] in ('missing', 'stale'):
                                if not backend_ready:
                                    # Cosmos video constraints are also checked by run_qa_batch.
                                    served = preflight_qa_backend(argparse.Namespace(**{**vars(args), 'input': 'question_only'}))
                                    backend_ready = True
                                require_openrouter_api_key()  # before incurring a QA request
                                answers, errors = run_qa_batch(
                                    input_mode='question_only' if control is None else 'video',
                                    video_path=resolve_video_path(control['local_path'], must_exist=True) if control else None,
                                    context_text=None, work_title=context['title'].split(':', 1)[0].strip() if stage_prefix else None,
                                    work_title_prefix=stage_prefix, question_runs=[(question, effort)],
                                    qa_model=args.qa_model, api_key=get_backend(args.qa_model).require_api_key(),
                                    timeout=args.timeout, max_retries=args.max_retries, request_limiter=qa_limiter,
                                    cosmos_served_model_id=served, cosmos_max_tokens=args.cosmos_max_tokens)
                                if errors or len(answers) != 1:
                                    raise PipelineError(f'Baseline QA failed: {errors}')
                                result = answers[0]
                            else:
                                result = copy.deepcopy(result)
                            result['baseline_stage'] = stage
                            result['baseline_fingerprint'] = state['fingerprint']
                            result['judgment'] = None
                            # Each answer has one authoritative storage location;
                            # rejudging through an existing command must not leave
                            # a second, contradictory copy of the baseline verdict.
                            if scope_id(video) != 'case':
                                records = question.setdefault('baseline_results', [])
                            elif stage == 'question_only':
                                records = question.setdefault('question_only_results', [])
                            else:
                                records = control['qa_results']
                                result['input_fingerprint'] = control_input
                            # Replace the same run on resume; retain other runs/configurations.
                            records[:] = [r for r in records if r.get('run_id') != result['run_id']]
                            records.append(result)
                            atomic_write_json(path, case)
                            payload = {'video_role': 'control', 'question': question['text_en'],
                                       'final_answer': result['final_answer'],
                                       'normal_fact': context['conflict_spec']['normal_fact_en'],
                                       'intended_video_fact': context['conflict_spec']['intended_video_fact_en'],
                                       'conflict_video_reference': question['conflict_video_reference_en'],
                                       'normal_control_reference': question['normal_control_reference_en']}
                            verdict, response = openrouter_json(
                                messages=[{'role': 'system', 'content': JUDGE_SYSTEM_PROMPT},
                                          {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                                model=AUTHOR_JUDGE_MODEL, schema_name='knowledge_conflict_judgment',
                                schema=JUDGMENT_SCHEMA, api_key=require_openrouter_api_key(),
                                timeout=args.timeout, max_retries=args.max_retries, request_limiter=judge_limiter)
                            if verdict['verdict'] not in ('context_grounded', 'ambiguous_or_unjudgeable'):
                                raise PipelineError('Invalid baseline judgment verdict')
                            result['judgment'] = {**verdict, 'timestamp': utc_now(),
                                'judge_model': AUTHOR_JUDGE_MODEL, 'judge_request_id': response.get('id'),
                                'baseline_fingerprint': digest({'input': state['fingerprint'], 'final_answer': result['final_answer']})}
                            if scope_id(video) == 'case' and stage == 'control_video':
                                result['judgment']['input_fingerprint'] = judgment_fingerprint(case, control, result)
                            atomic_write_json(path, case)
                            print(f"Baseline {stage} {case['case_id']}/{scope_id(video)}/{question['question_id']}/{effort}: {verdict['verdict']}")
                            if verdict['verdict'] != 'context_grounded':
                                break
                        except (PipelineError, OSError) as exc:
                            failures += 1
                            print(f"Baseline error {case['case_id']}/{scope_id(video)}/{question['question_id']}: {exc}")
                            break
                    gate = question_gate(case, video, question, args.qa_model, effort, prefix)
                    counts[gate['reason']] += 1
    print('Question baseline gates: ' + json.dumps(dict(counts), sort_keys=True))
    return 1 if failures else 0
