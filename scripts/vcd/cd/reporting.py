"""Reports rebuilt from selected, current case records only."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from vconflict_pipeline.common import utc_now
from vconflict_pipeline.reporting import aggregate_video_verdict
from . import PROTOCOL_VERSION, SCHEMA_VERSION
from .storage import (
    atomic_json, atomic_text, bind_target, current_judgment, current_qa, matching_records,
    read_json, records_for, result_path,
)

DIAGNOSTICS = ('max_tokens_truncated', 'final_answer_continuation_max_tokens_truncated',
               'missing_final_answer', 'final_answer_retries',
               'final_answer_retry_recovered', 'final_answer_retry_failed')


def summarize(rows):
    answers, videos = Counter(), defaultdict(list)
    statuses = Counter(row['status'] for row in rows)
    for row in rows:
        if row['status'] != 'judged':
            continue
        answers[row['verdict']] += 1
        videos[(row['group'], row['case_id'], row['video_id'])].append(row['verdict'])
    video_counts = Counter(aggregate_video_verdict(v) for v in videos.values())
    def counts(values):
        total = sum(values.values())
        return {'total': total, 'context_grounded': values['context_grounded'],
                'knowledge_trapped': values['knowledge_trapped'],
                'ambiguous_or_unjudgeable': values['ambiguous_or_unjudgeable'],
                'grounded_rate': round(values['context_grounded'] / total, 6) if total else None,
                'trapped_rate': round(values['knowledge_trapped'] / total, 6) if total else None}
    a, v = counts(answers), counts(video_counts)
    a['grounded_answer_rate'], a['trapped_answer_rate'] = a.pop('grounded_rate'), a.pop('trapped_rate')
    v['grounded_video_rate'], v['trapped_video_rate'] = v.pop('grounded_rate'), v.pop('trapped_rate')
    return {'required': len(rows), 'qa_valid': sum(r['qa_valid'] for r in rows),
            'judge_valid': statuses['judged'], 'states': dict(statuses), 'answers': a, 'videos': v}


def write_report(output, targets, config, *, run_id, counts=None, run_error=None):
    cases = {}
    rows, diagnostics = [], Counter({k: 0 for k in DIAGNOSTICS})
    for target in targets:
        path = result_path(output, target['group'], target['case_id'])
        if path not in cases:
            cases[path] = read_json(path)
        case = cases[path]
        binding = bind_target(target, config)
        result = current_qa(case, target, binding)
        attempts = matching_records(case, target, binding, 'qa_attempts')
        history = [r for r in records_for(case, target) if all(
            r.get(key) == binding[key] for key in ('question_scope', 'question_id', 'model', 'method'))]
        if result:
            judged = current_judgment(target, result)
            status = 'judged' if judged else 'judge_failed' if result.get('judge_error') else (
                'judge_stale' if result.get('judgment') else 'judge_missing')
        else:
            status = ('qa_failed' if attempts and attempts[-1].get('status') == 'failed' else
                      'qa_interrupted' if attempts else 'qa_stale' if history else 'qa_missing')
        row = {key: target[key] for key in ('group', 'case_id', 'video_id', 'question_scope')}
        row.update(question_id=target['question']['question_id'], method='cd',
                   status=status, qa_valid=bool(result),
                   verdict=result['judgment']['verdict'] if status == 'judged' else None,
                   result_path=str(path.relative_to(output)))
        if status == 'qa_failed':
            row['error'] = attempts[-1].get('error')
        elif status == 'judge_failed':
            row['error'] = result['judge_error']
        rows.append(row)
        # Diagnostics reflect this execution; history stays auditable in cases.
        for record in [*attempts, *matching_records(case, target, binding)]:
            if record.get('run_id') != run_id:
                continue
            for phase in record.get('phases', []):
                reason = phase.get('diagnostic')
                if reason in diagnostics:
                    diagnostics[reason] += 1
            if record.get('final_answer_retry_count'):
                diagnostics['final_answer_retries'] += 1
                if record.get('status') in ('ok', 'failed', 'interrupted'):
                    key = ('final_answer_retry_recovered' if record['status'] == 'ok'
                           else 'final_answer_retry_failed')
                    diagnostics[key] += 1
    groups = list(dict.fromkeys(t['group'] for t in targets))
    summary = {'protocol_version': config['generation_protocols']['cd'],
               'overall': summarize(rows), 'groups': {
        group: summarize([r for r in rows if r['group'] == group]) for group in groups}}
    incomplete = [{k: v for k, v in row.items() if k not in ('qa_valid', 'verdict')}
                  for row in rows if row['status'] != 'judged']
    failed = len(incomplete)
    parameters = {k: v for k, v in config.items() if k != 'selection'}
    report = {'vcd_schema_version': SCHEMA_VERSION, 'protocol_version': PROTOCOL_VERSION,
              'run_id': run_id, 'updated_at': utc_now(), 'selection': config['selection'],
              'parameters': parameters, 'methods': {'cd': summary}, 'incomplete_tasks': incomplete,
              'incomplete': failed, 'run_error': run_error, 'this_run': counts or {},
              'diagnostics': {'cd': dict(diagnostics)}}
    atomic_json(output / 'report.json', report)
    def rate(value):
        return 'null' if value is None else f'{value:.6f}'
    lines = ['# VCD QA / Judge', '', f'Run: {run_id}; incomplete QA/Judge targets: {failed}.', '',
             'Only current results matching this selection and generation protocol are counted.', '',
             '| method | group | answers | grounded answer | trapped answer | videos | grounded video | trapped video |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for group, metrics in [('overall', summary['overall']), *summary['groups'].items()]:
        a, v = metrics['answers'], metrics['videos']
        lines.append(f"| cd | {group} | {a['total']} | {rate(a['grounded_answer_rate'])} | "
                     f"{rate(a['trapped_answer_rate'])} | {v['total']} | {rate(v['grounded_video_rate'])} | "
                     f"{rate(v['trapped_video_rate'])} |")
    lines += ['', f"cd generation protocol: {summary['protocol_version']}", '',
              f"cd states: {summary['overall']['states']}",
              f"cd diagnostics: {dict(diagnostics)}", '']
    lines += ['Configuration and selection:', '', '```json',
              json.dumps({'parameters': parameters, 'selection': config['selection']}, ensure_ascii=False, indent=2), '```', '',
              f'This run: {counts or {}}', '', f'Run error: {run_error}', '']
    if incomplete:
        lines += ['Incomplete tasks:', '']
        lines += [f"- {r['group']}/{r['case_id']}/{r['video_id']}/{r['question_id']} "
                  f"({r['method']}): {r['status']}" for r in incomplete]
        lines.append('')
    atomic_text(output / 'report.md', '\n'.join(lines))
    return report
