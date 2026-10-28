"""Single-task QA/Judge requests and provenance-checked result merging."""
from __future__ import annotations

import os

from .common import PipelineError
from .integrity import digest, judgment_fingerprint
from .qa import TruncatedAnswerError, get_backend, local_qa_max_tokens, preflight_qa_backend, run_qa_once
from .qa_truncation import split_truncated_response
from .result_rules import set_filter_field
from .judging import judge_answer


class TaskExecutor:
    def __init__(self, args, planner, diagnostics, max_token_log=None):
        self.args, self.planner, self.diagnostics = args, planner, diagnostics
        self.max_token_log = max_token_log
        self.backend = get_backend(args.qa_model)
        self.api_key = os.environ.get(self.backend.api_key_variable, '').strip() if self.backend.api_key_variable else ''
        self.judge_key = os.environ.get('OPENROUTER_API_KEY', '').strip()
        self.served = None
        self.backend_ready = False

    def ensure_backend(self, loaded):
        if not self.backend_ready:
            self.served = preflight_qa_backend(self.args, loaded)
            self.api_key = self.backend.require_api_key()
            self.backend_ready = True

    def normalize_filter(self, case, task, result):
        set_filter_field(result, 'stage', task.stage)
        set_filter_field(result, 'fingerprint', task.fingerprint)
        records = self.planner.records(case, task, result)
        records[:] = [r for r in records if r.get('run_id') != result['run_id']]
        records.append(result)

    def request(self, task, media):
        if task.kind == 'qa':
            try:
                return run_qa_once(
                    input_mode=task.mode, video_path=task.video_path, context_text=task.context_text,
                    work_title=task.context['title'].split(':', 1)[0].strip() if task.prefix else None,
                    work_title_prefix=task.prefix, question=task.question, thinking_effort=task.effort,
                    qa_model=self.args.qa_model, api_key=self.api_key, timeout=self.args.timeout,
                    local_served_model_id=self.served,
                    local_max_tokens=local_qa_max_tokens(self.args), based=task.based,
                    thinking_token_budget=self.args.thinking_token_budget,
                    diagnostics=self.diagnostics, prepared_video_input=media,
                    final_answer_continuation=task.final_answer_continuation,
                    diagnostic_stage=task.diagnostic_stage)
            except TruncatedAnswerError as exc:
                if self.max_token_log is not None:
                    self.log_truncated_answer(task, exc)
                raise
        return judge_answer(
            question=task.question, facts=task.context['conflict_spec'],
            role=task.context['role'], final_answer=task.result.get('final_answer'),
            api_key=self.judge_key, timeout=self.args.timeout)

    def log_truncated_answer(self, task, exc):
        response, parameters = exc.raw_response, exc.generation_parameters
        record = {
            'timestamp': exc.timestamp,
            'case_path': str(task.path.resolve()), 'case_id': task.path.stem,
            'group': self.args.group or task.path.parent.name,
            'video_id': task.video_id, 'video_role': task.context['role'],
            'question_id': task.question_id, 'question': task.question['text_en'],
            'model': self.args.qa_model, 'input': self.args.input, 'input_mode': task.mode,
            'thinking_effort': task.effort, 'based': task.based, 'work_title_prefix': task.prefix,
            'stage': task.diagnostic_stage, 'task_key': task.key,
            'final_answer_retry_count': task.final_answer_retry_count,
            'max_tokens': parameters.get('max_tokens'),
            'thinking_token_budget': parameters.get('thinking_token_budget'),
            'generation_parameters': parameters,
            'finish_reason': response['choices'][0]['finish_reason'],
            'request_id': response.get('id'), 'usage': response.get('usage'),
            **split_truncated_response(response, self.args.qa_model),
            'raw_response': response,
        }
        if exc.final_answer_continuation is not None:
            record['final_answer_continuation'] = exc.final_answer_continuation
        self.max_token_log.append(record)

    def merge(self, case, task, output):
        video, q = self.planner.owners(case, task)
        _, binding = self.planner.fingerprint(case, video, q, task.stage, task.mode, task.prefix, task.based)
        if binding != task.binding:
            raise PipelineError('Inputs changed during request; refusing stale result')
        if task.kind == 'qa':
            if task.stage:
                self.normalize_filter(case, task, output)
            else:
                output['input_fingerprint'] = task.fingerprint
                self.planner.records(case, task).append(output)
            return
        records = self.planner.records(case, task, task.result)
        result = next((r for r in records if r.get('run_id') == task.result['run_id']), None)
        if result is None or result.get('final_answer') != task.result.get('final_answer'):
            raise PipelineError('QA changed during judging; refusing stale judgment')
        if task.stage:
            output['filter_fingerprint'] = digest({'input': task.fingerprint, 'final_answer': result['final_answer']})
        else:
            output['input_fingerprint'] = judgment_fingerprint(case, video, result)
        result['judgment'] = output
