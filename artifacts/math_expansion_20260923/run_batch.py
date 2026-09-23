"""Run only the 25 source-defined September 23 conflict variants."""
import argparse
import copy
import fcntl
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GROUP = 'mathematics_algorithm_conflicts'
sys.path.insert(0, str(ROOT / 'scripts'))
from vconflict_pipeline import authoring
from vconflict_pipeline.cli import build_parser
from vconflict_pipeline.core import atomic_write_json, load_case, validate_case


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def prepare():
    rows = []
    for path in sorted((ROOT / 'dataset/source_cases' / GROUP).glob('*.md')):
        text = path.read_text(encoding='utf-8-sig')
        if '<!-- math-expansion-20260923-start -->' not in text:
            continue
        section = text.split('<!-- math-expansion-20260923-start -->', 1)[1].split('<!-- math-expansion-20260923-end -->', 1)[0]
        common = '**本批次共用画面要求**' + section.split('**本批次共用画面要求**', 1)[1]
        matches = re.findall(r'##### 新增变体 (M\d{2})\n(.*?)(?=##### 新增变体 |\*\*本批次共用画面要求\*\*)', section, re.S)
        for label, description in matches:
            source = text.splitlines()[0] + '\n\n' + description.strip() + '\n\n' + common.strip() + '\n'
            source += '\n本文件仅描述一个指定的新 conflict；只为此输入和结果生成一条 conflict prompt，不增加其他数字变体。生成一个同输入正常 control 草稿用于问题参考，本批次不生成 control 视频。\n'
            source_path = HERE / 'sources' / label / GROUP / path.name
            rows.append({'label': label, 'case_id': path.stem, 'video_id': 'exp20260923_' + label.lower(),
                         'source_path': str(source_path.relative_to(ROOT)), 'source_sha256': digest(source),
                         'duration': 8, '_source': source})
    rows.sort(key=lambda x: x['label'])
    require([r['label'] for r in rows] == [f'M{i:02}' for i in range(1, 26)], 'Expected exactly M01-M25')
    require(len({r['case_id'] for r in rows}) == 13, 'Expected 13 parent cases')
    manifest = {'group': GROUP, 'count': 25, 'variants': [{k:v for k,v in r.items() if k != '_source'} for r in rows]}
    manifest_path = HERE / 'manifest.json'
    if manifest_path.exists():
        require(json.loads(manifest_path.read_text()) == manifest, 'Sources changed since preparation; refusing to alter the running batch')
    for row in rows:
        p = ROOT / row['source_path']
        if p.exists():
            require(p.read_text(encoding='utf-8') == row['_source'], 'Prepared source changed: ' + str(p))
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(row['_source'], encoding='utf-8')
    atomic_write_json(manifest_path, manifest)
    return manifest['variants']


def dataset(row):
    return ROOT / 'dataset/variant_cases/math_expansion_20260923' / row['label']


def runtime_path(row):
    return dataset(row) / GROUP / (row['case_id'] + '.json')


def expected_path(row, control=False):
    name = ('control_' if control else '') + row['video_id']
    return f"videos/seedance/{GROUP}/{row['case_id']}/{name}.mp4"


def checked_case(row):
    case = load_case(runtime_path(row))
    require(case['case_id'] == row['case_id'], 'Case mismatch')
    require(len(case['videos']) == 2, 'Expected one conflict and one control draft')
    conflicts = [v for v in case['videos'] if v['role'] == 'conflict']
    controls = [v for v in case['videos'] if v['role'] == 'control']
    require(len(conflicts) == len(controls) == 1, 'Role mismatch')
    v = conflicts[0]
    require(v['video_id'] == row['video_id'] and v['local_path'] == expected_path(row), 'Conflict target mismatch')
    require(controls[0]['local_path'] == expected_path(row, True), 'Control path mismatch')
    require(controls[0]['status'] == 'pending' and not controls[0]['task_id'], 'Control is no longer a draft')
    if v['status'] in ('pending', 'failed'):
        require(not (ROOT / v['local_path']).exists(), 'Refusing to overwrite existing output')
    return case


def pipeline(arguments):
    args = build_parser().parse_args(arguments)
    require(args.func(args) == 0, 'Pipeline failed: ' + ' '.join(arguments))


def author(row):
    if runtime_path(row).exists():
        checked_case(row)
        print(row['label'] + ': authored record already exists', flush=True)
        return
    staging = HERE / 'authored' / row['label']
    pipeline(['author', '--source-dir', str(HERE / 'sources' / row['label']), '--output-dir', str(staging),
              '--group', GROUP, '--case-id', row['case_id'], '--case-workers', '1', '--openrouter-workers', '1'])
    case = load_case(staging / GROUP / (row['case_id'] + '.json'))
    require(len(case['videos']) == 2, 'Author must return exactly one conflict; no videos have been submitted')
    for v in case['videos']:
        control = v['role'] == 'control'
        v['video_id'] = ('control_' if control else '') + row['video_id']
        v['local_path'] = expected_path(row, control)
        require(v['status'] == 'pending' and not v['task_id'], 'Unexpected generated state')
        require(not (ROOT / v['local_path']).exists(), 'Output path already exists')
    validate_case(case)
    atomic_write_json(runtime_path(row), case)
    checked_case(row)


def constrain_author():
    # These changes affect only this process, never the shared pipeline source.
    def restrict(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == 'conflict_video_prompts_en' and isinstance(value, dict):
                    value['minItems'] = value['maxItems'] = 1
                restrict(value)
        elif isinstance(obj, list):
            for value in obj:
                restrict(value)
    authoring.AUTHOR_OUTPUT_SCHEMA = copy.deepcopy(authoring.AUTHOR_OUTPUT_SCHEMA)
    authoring.AUTHOR_VERIFY_SCHEMA = copy.deepcopy(authoring.AUTHOR_VERIFY_SCHEMA)
    restrict(authoring.AUTHOR_OUTPUT_SCHEMA)
    restrict(authoring.AUTHOR_VERIFY_SCHEMA)
    original = authoring.author_prompts_for_group
    supplement = '\nThis batch requires exactly ONE conflict prompt for the precise source-defined input, action, and result, and one matched normal control draft. Do not invent further variants. Preserve all numbers, counts, and temporal evidence. Use one continuous 8-second shot: establish the input, execute the full specified trace, then hold the completed state with neutral DONE during seconds 6-8. Source-defined counts of 6 or 7 are permitted when required.\n'
    authoring.author_prompts_for_group = lambda group: tuple(p + supplement for p in original(group))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'check', 'author', 'questions', 'generate'])
    args = parser.parse_args()
    with (HERE / '.batch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = prepare()
        if args.stage in ('prepare', 'check'):
            ready = sum(runtime_path(r).exists() for r in rows)
            for row in rows:
                if runtime_path(row).exists():
                    checked_case(row)
            print(json.dumps({'source_variants': 25, 'parent_cases': 13, 'authored_variants': ready,
                              'control_videos_selected': 0, 'api_calls': 0}, indent=2))
            return
        if args.stage == 'author':
            constrain_author()
            for row in rows:
                author(row)
            return
        # Preflight the full batch before any question/video API calls.
        for row in rows:
            require(runtime_path(row).exists(), 'Run author first: ' + row['label'])
            case = checked_case(row)
            if args.stage == 'generate':
                require(bool(case['questions']), 'Run questions first: ' + row['label'])
        def run(row):
            command = [args.stage, '--dataset-dir', str(dataset(row)), '--group', GROUP,
                       '--case-id', row['case_id'], '--case-workers', '1']
            if args.stage == 'generate':
                command += ['--video-id', row['video_id'], '--duration', str(row['duration']), '--ratio', '16:9',
                            '--resolution', '720p', '--seedance-workers', '1', '--seedance-total-workers', '1', '--retry-failed']
            else:
                command += ['--openrouter-workers', '1']
            pipeline(command)
            if args.stage == 'questions':
                require(bool(checked_case(row)['questions']), 'Questions missing: ' + row['label'])
        if args.stage == 'generate':
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(run, rows))
        else:
            failures = []
            for row in rows:
                print(f"Questions: {row['label']} / {row['case_id']}", flush=True)
                try:
                    run(row)
                except RuntimeError as exc:
                    failures.append(row['label'])
                    print(f"FAILED {row['label']}: {exc}", file=sys.stderr, flush=True)
            require(not failures, 'Questions failed for: ' + ', '.join(failures)
                    + '. Other successful variants were saved; rerun questions to retry only missing ones.')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
