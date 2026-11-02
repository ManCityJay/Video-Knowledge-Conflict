"""Spawned workers, physical GPU isolation and FIFO scheduling for both CLIs."""
from __future__ import annotations

import importlib.metadata
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from vconflict_pipeline.common import utc_now
from .config import FAMILIES
from .storage import atomic_json, make_config, read_json


def add_queue_options(parser, *, required_models=False):
    parser.add_argument('--models', nargs='+', choices=FAMILIES, required=required_models,
                        default=None if required_models else list(FAMILIES),
                        help='One to three distinct models, queued in the given order')
    parser.add_argument('--gpus', choices=('0', '1', 'all'), default='all',
                        help='Physical GPU 0, 1, or both (default: all); one model per GPU')
    parser.add_argument('--disable-thinking', action='store_true',
                        help='Disable thinking; ignore the thinking token budget')
    parser.add_argument('--dry-run', action='store_true',
                        help='Read-only model order, initial GPU assignment and configuration preview')


def validate_models(models):
    if not 1 <= len(models) <= 3 or len(set(models)) != len(models):
        raise ValueError('--models requires one to three distinct models')


def gpu_indices(choice, model_count):
    # Both free cards are ordered physically. A single model always prefers 0.
    return ([0] if model_count == 1 else [0, 1]) if choice == 'all' else [int(choice)]


def validate_root(output):
    if any((output / name).exists() for name in ('config.json', 'cases', 'report.json', 'report.md')):
        raise ValueError('Legacy single-model output root is not moved or overwritten; '
                         'choose a separate output root containing model subdirectories')


def environment(gpu_uuid):
    return {'CUDA_VISIBLE_DEVICES': gpu_uuid or '', 'CUDA_DEVICE_ORDER': 'PCI_BUS_ID',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
            'TOKENIZERS_PARALLELISM': 'false', 'PYTHONUNBUFFERED': '1',
            'PYTHONDONTWRITEBYTECODE': '1'}


def preflight(configs, indices, *, require_judge=False):
    """Check only selected models and cards; never called for previews or reports."""
    if require_judge and not os.environ.get('OPENROUTER_API_KEY', '').strip():
        raise ValueError('OPENROUTER_API_KEY is required; its value is never logged')
    versions = {name: importlib.metadata.version(name) for name in ('transformers', 'vllm', 'torch')}
    if versions['transformers'] != '5.18.0' or versions['vllm'] != '0.29.0':
        raise ValueError(f'The environment does not match the experiment: {versions}')
    for config in configs:
        root = Path(config.model_path)
        index = root / 'model.safetensors.index.json'
        weights = set(read_json(index)['weight_map'].values()) if index.exists() else {'model.safetensors'}
        missing = sorted(name for name in weights if not (root / name).is_file())
        if missing:
            raise ValueError(f'Incomplete offline {config.model_family} model cache: {missing}')
    query = subprocess.run(
        ['nvidia-smi', '--query-gpu=index,uuid,name,memory.total,memory.used', '--format=csv,noheader,nounits'],
        capture_output=True, text=True, timeout=30)
    if query.returncode:
        raise ValueError('GPU preflight failed: ' + (query.stderr.strip() or query.stdout.strip()))
    devices = {}
    for line in query.stdout.splitlines():
        index, gpu_uuid, name, total, used = [v.strip() for v in line.split(',')]
        devices[int(index)] = {'uuid': gpu_uuid, 'name': name, 'memory_total_mib': int(total),
                               'memory_used_mib': int(used)}
    mapping = {}
    for index in indices:
        if index not in devices:
            raise ValueError(f'Physical GPU {index} is unavailable')
        device = devices[index]
        if not device['uuid'].startswith('GPU-'):
            raise ValueError(f'GPU {index} has no usable UUID')
        if device['memory_total_mib'] < 80000:
            raise ValueError(f'GPU {index} does not meet the planned 80 GB requirement')
        probe = subprocess.run(
            [sys.executable, '-B', '-c',
             'import torch; assert torch.cuda.device_count() == 1, "Expected one isolated GPU"; '
             'p = torch.cuda.get_device_properties(0); print(str(p.uuid)); print(p.name)'],
            env={**os.environ, **environment(device['uuid'])}, capture_output=True, text=True, timeout=60)
        if probe.returncode or device['uuid'].removeprefix('GPU-') not in probe.stdout:
            raise ValueError(f'GPU {index}: isolated CUDA mapping check failed: '
                             f'{probe.stdout.strip()} {probe.stderr.strip()}')
        mapping[index] = {'physical_index': index, **device}
    return {'versions': versions, 'gpus': mapping,
            'judge_key_present': bool(os.environ.get('OPENROUTER_API_KEY', '').strip())}


def preview(phases, indices):
    print('Model order: ' + ' -> '.join(c.model_family for c in phases[0][1]), flush=True)
    for phase, configs in phases:
        print(f'Phase: {phase}', flush=True)
        for position, config in enumerate(configs):
            assignment = ('GPU unused (report only)' if config.summarize_only else
                          f'physical GPU {indices[position]}' if position < len(indices) else
                          'waiting for a free GPU')
            print(f'{config.model_family}: {assignment}; output={config.output}', flush=True)
            print(json.dumps(make_config(config), ensure_ascii=False, indent=2), flush=True)


def worker(config, gpu_uuid, log_path):
    # The spawn import path contains no GPU imports. Isolate before importing
    # either the runtime or the worker implementation, including vLLM parsers.
    os.environ.update(environment(gpu_uuid))
    os.setsid()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    with open(log_path, 'a', encoding='utf-8', buffering=1) as stream:
        os.dup2(stream.fileno(), 1)
        os.dup2(stream.fileno(), 2)
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
        try:
            from .cli import run
            print(f'Model={config.model_family}; visible GPU={gpu_uuid}; device={config.device}', flush=True)
            code = run(config)
        except KeyboardInterrupt:
            code = 130
        except Exception as exc:
            print(f'Error: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
            code = 2
    raise SystemExit(code)


def report_status(config):
    path = config.output / 'report.json'
    if not path.is_file():
        return {'complete': False, 'error': 'Worker did not produce a report'}
    report = read_json(path)
    if report['run_id'] != config.run_id:
        return {'complete': False, 'error': 'Worker report belongs to another run'}
    metrics = {'cd': report['methods']['cd']['overall']}
    return {'complete': report['incomplete'] == 0 and not report['run_error'],
            'methods': metrics, 'incomplete': report['incomplete'], 'run_error': report['run_error']}


def supervise(phases, indices, checks, status, run, status_path):
    """Hold a slot until the entire QA/Judge process exits, even on failure."""
    context = multiprocessing.get_context('spawn')
    active, received = {}, []

    def save():
        run['updated_at'] = utc_now()
        atomic_json(status_path, status)

    def notify(child, sig):
        if child.is_alive():
            try:
                os.kill(child.pid, sig)
            except ProcessLookupError:
                pass

    def stop(signum, _frame):
        received.append(signum)
        for child, _, _, _ in tuple(active.values()):
            notify(child, signal.SIGINT if len(received) == 1 else signal.SIGTERM)

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for phase, configs in phases:
            run['phase'] = phase
            attempts = []
            for config in configs:
                attempt = {'phase': phase, 'status': 'queued', 'pid': None, 'gpu': None,
                           'exit_code': None, 'queued_at': utc_now()}
                run['models'][config.model_family]['attempts'].append(attempt)
                attempts.append(attempt)
            pending = list(zip(configs, attempts))
            save()
            while pending or active:
                for index, (child, config, attempt, stream) in list(active.items()):
                    if child.is_alive():
                        continue
                    child.join()
                    code = child.exitcode
                    try:
                        result = report_status(config)
                    except (OSError, ValueError, KeyError) as exc:
                        result = {'complete': False, 'error': str(exc)}
                    attempt.update(exit_code=code, finished_at=utc_now(), result=result,
                                   status='interrupted' if received else
                                   'complete' if code == 0 and result['complete'] else 'failed')
                    print(f'{phase}: {config.model_family} exit={code}; {attempt["status"]}', flush=True)
                    del active[index]
                    stream.close()
                    child.close()
                    save()
                if received:
                    for _, attempt in pending:
                        attempt.update(status='cancelled', finished_at=utc_now())
                    pending.clear()
                for index in sorted(indices):
                    if received or not pending:
                        break
                    if index in active:
                        continue
                    config, attempt = pending.pop(0)
                    config.run_id = uuid.uuid4().hex
                    gpu = None if config.summarize_only else checks['gpus'][index]
                    log_path = config.output / 'logs' / f'{run["run_id"]}_{phase}.log'
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    stream = log_path.open('x', encoding='utf-8')
                    attempt.update(status='starting', started_at=utc_now(), log=str(log_path),
                                   gpu=gpu, worker_run_id=config.run_id)
                    child = context.Process(target=worker,
                                            args=(config, gpu['uuid'] if gpu else None, str(log_path)),
                                            name=f'vcd-{config.model_family}')
                    try:
                        child.start()
                    except (OSError, RuntimeError) as exc:
                        stream.close()
                        child.close()
                        attempt.update(status='failed', error=str(exc), finished_at=utc_now())
                    else:
                        active[index] = (child, config, attempt, stream)
                        attempt.update(pid=child.pid, status='running')
                        print(f'{phase}: {config.model_family} PID={child.pid}; '
                              f'GPU={index if gpu else "unused"}; log={log_path}', flush=True)
                        if received:
                            notify(child, signal.SIGINT)
                    save()
                if active:
                    time.sleep(.2)
            # A smoke failure still runs every queued smoke model, but gates the full batch.
            if received or any(a['status'] != 'complete' for a in attempts):
                break
        complete = not received and all(
            model['attempts'] and model['attempts'][-1]['status'] == 'complete'
            and model['attempts'][-1]['phase'] == phases[-1][0] for model in run['models'].values())
        run.update(status='interrupted' if received else 'complete' if complete else 'failed',
                   finished_at=utc_now())
        save()
        return 128 + received[0] if received else 0 if complete else 1
    finally:
        # Do not release the root lock while QA or Judge is still running.
        remaining = list(active.values())
        for child, _, _, _ in remaining:
            notify(child, signal.SIGINT)
        for index, (child, _, attempt, stream) in list(active.items()):
            child.join()
            attempt.update(exit_code=child.exitcode, status='interrupted', finished_at=utc_now())
            del active[index]
            stream.close()
            child.close()
        if remaining or received:
            run.update(status='interrupted', finished_at=utc_now())
            save()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def new_run(models, checks, **metadata):
    return {'run_id': utc_now().replace(':', '').replace('-', '') + '_' + uuid.uuid4().hex[:8],
            'pid': os.getpid(), 'status': 'running', 'started_at': utc_now(),
            'model_order': list(models), 'preflight': checks,
            'models': {family: {'attempts': []} for family in models}, **metadata}


def load_status(path, format_name):
    status = read_json(path) if path.exists() else {'format': format_name, 'runs': []}
    if status.get('format') != format_name or not isinstance(status.get('runs'), list):
        raise ValueError(f'Incompatible queue status: {path}')
    for old in status['runs']:
        if old['status'] == 'running':
            old.update(status='interrupted', interruption_detected_at=utc_now())
    return status
