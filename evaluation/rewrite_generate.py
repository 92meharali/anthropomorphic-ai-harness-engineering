"""Issue #26 Task 2: screen frozen originals and run matched rewrites.

No live calls without --live. No retries, reviewer judgments or outcome analysis.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import random
import time
import urllib.error

from . import rewrite_freeze as f

ARMS = ('cue_specific', 'generic')
TERMINAL = (401, 403, 429)
VERSION = 'generated-rewrite-task2-v1'
SOURCE = 'evaluation/rewrite_generate.py'


def assessment_fn():
    from .cue_routing import _assessment
    return _assessment


def state_fn():
    from .cue_output import state
    return state


def setup(root, study, expected):
    seal = f.verify(root, study)
    if seal['freeze_sha256'] != expected:
        raise ValueError('Freeze SHA-256 differs from the independently recorded seal')
    config = f.load(study / 'plan.json')['body']['config']
    drafts = f.rows(study / 'drafts.jsonl')
    uses_saved_cues = seal['manifest'].get('source_kind') == f.ISSUE1_SOURCE
    if (config['flagging']['implementation'] != 'evaluation.cue_routing._assessment'
            or config['flagging']['history_withheld'] is not False
            or config['flagging']['attempts_per_draft'] != 1
            or config['rewrite_generation']['attempts_per_arm'] != 1):
        raise ValueError('Unsupported frozen attempt or flagging configuration')
    # Assign balanced orders before screening, never based on detector results.
    orders = [list(ARMS if i % 2 == 0 else ARMS[::-1]) for i in range(len(drafts))]
    random.Random(config['review']['arm_order_seed']).shuffle(orders)
    manifest = {'version': VERSION, 'freeze_sha256': expected,
                'source_sha256': f.sha((root / SOURCE).read_bytes()),
                'valid_drafts': len(drafts), 'max_calls': (2 if uses_saved_cues else 3) * len(drafts),
                'screening_source': 'saved_issue1' if uses_saved_cues else 'live_detector',
                'orders': [{'draft_id': d['draft_id'], 'arms': order}
                           for d, order in zip(drafts, orders)]}
    return manifest, config, drafts


def parse_rewrite(raw):
    text, model = f.parse_original(raw)
    value = f.loads(text)
    if not isinstance(value, dict) or set(value) != {'response'} or not f.nonempty(value['response']):
        raise ValueError('Expected exactly one nonempty response field')
    return value['response'], model


def evaluate(draft, config, order, request, *, assess, build_state):
    # Task 1 revalidated saved assessments against the exact original context.
    assessment = draft.get('saved_assessment')
    if assessment is None:
        assessment = assess(config['detector_model'], draft, draft['draft'],
                            config['capabilities'], False, lambda body: request('detect', body))
    feedback = f.flagged_feedback(assessment, config)
    outcome = {'draft_id': draft['draft_id'], 'prompt_group_id': draft['prompt_group_id'],
               'current_user_message': draft['current_user_message'],
               'visible_history': draft['visible_history'], 'original': draft['draft'],
               'original_model': draft['draft_model'], 'assessment': assessment,
               'flagged': feedback is not None, 'rewrites': {}, 'pair_eligible': False}
    if feedback is None:
        return outcome
    for arm in order:
        body = f.rewrite_request(draft, config, arm, assessment, state_builder=build_state)
        raw = request(arm, body)
        try:
            response, model = parse_rewrite(raw)
            result = {'status': 'ok', 'response': response, 'returned_model': model,
                      'changed': response != draft['draft']}
        except (ValueError, KeyError, TypeError, AttributeError):
            result = {'status': 'failed', 'response': None,
                      'returned_model': raw.get('model') if isinstance(raw, dict) else None,
                      'changed': None}
        outcome['rewrites'][arm] = result
    a, b = (outcome['rewrites'][arm] for arm in ARMS)
    outcome['pair_eligible'] = (a['status'] == b['status'] == 'ok'
                                and a['returned_model'] == b['returned_model'])
    return outcome


def aggregate(outcomes, calls):
    flagged = [r for r in outcomes if r['flagged']]
    by_stage = {}
    for stage in ('detect', *ARMS):
        stage_calls = [c for c in calls if c['stage'] == stage]
        usage = [c['raw'].get('usage') for c in stage_calls if isinstance(c.get('raw'), dict)]
        totals = {}
        for field in ('input_tokens', 'output_tokens', 'total_tokens'):
            values = [u[field] for u in usage if isinstance(u, dict)
                      and type(u.get(field)) is int and u[field] >= 0]
            totals[field] = {'observed_sum': sum(values), 'calls_with_value': len(values)}
        by_stage[stage] = {'attempts': len(stage_calls), 'tokens': totals,
                           'latency_seconds': sum(c['latency_seconds'] for c in stage_calls),
                           'returned_models': dict(Counter(c['raw']['model'] for c in stage_calls
                              if isinstance(c.get('raw'), dict) and f.nonempty(c['raw'].get('model'))))}
    return {'screened': len(outcomes), 'screening': dict(Counter(r['assessment']['classification'] for r in outcomes)),
            'flagged': len(flagged), 'eligible_pairs': sum(r['pair_eligible'] for r in flagged),
            'model_mismatch_pairs': sum(all(r['rewrites'][a]['status'] == 'ok' for a in ARMS)
                and not r['pair_eligible'] for r in flagged),
            'arms': {a: {'valid': sum(r['rewrites'][a]['status'] == 'ok' for r in flagged),
                         'failed': sum(r['rewrites'][a]['status'] != 'ok' for r in flagged),
                         'unchanged': sum(r['rewrites'][a]['changed'] is False for r in flagged)} for a in ARMS},
            'calls': len(calls), 'usage': by_stage}


def run(root, study, out, expected, key, max_calls, transport, *, assess=None, build_state=None):
    manifest, config, drafts = setup(root, study, expected)
    if type(max_calls) is not int or max_calls != manifest['max_calls']:
        raise ValueError(f"Call budget must equal {manifest['max_calls']} (worst-case ceiling)")
    if not f.nonempty(key):
        raise ValueError('Missing API key')
    assess, build_state = assess or assessment_fn(), build_state or state_fn()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    f.write(out / 'manifest.json', manifest)
    calls, outcomes, terminal = [], [], None
    with (out / 'calls.jsonl').open('xb') as log, (out / 'outcomes.jsonl').open('xb') as results:
        for draft, item in zip(drafts, manifest['orders']):
            def request(stage, body):
                nonlocal terminal
                if terminal is not None:
                    return None  # no further paid attempts after an access/rate-limit error
                if len(calls) >= max_calls:
                    raise RuntimeError('Call ceiling exceeded')
                entry = {'draft_id': draft['draft_id'], 'stage': stage, 'request': deepcopy(body),
                         'request_sha256': f.sha(f.canonical(body))}
                start = time.monotonic()
                try:
                    raw, rid = transport('openai', deepcopy(body), key)
                    if not isinstance(raw, dict):
                        raise ValueError('Invalid provider envelope')
                    f.canonical(raw)  # refuse non-serializable/non-finite payloads
                    entry.update(raw=raw, request_id=rid if isinstance(rid, str) else None)
                except urllib.error.HTTPError as exc:
                    entry['http_status'] = exc.code
                    if exc.code in TERMINAL:
                        terminal = exc.code
                    exc.close()
                except (OSError, ValueError, TypeError):
                    entry['error'] = 'transport_failure'
                entry['latency_seconds'] = time.monotonic() - start
                log.write(f.canonical(entry) + b'\n'); log.flush()
                calls.append(entry)
                return entry.get('raw')
            result = evaluate(draft, config, item['arms'], request, assess=assess, build_state=build_state)
            results.write(f.canonical(result) + b'\n'); results.flush()
            outcomes.append(result)
            if terminal is not None:
                break
    summary = aggregate(outcomes, calls)
    f.write(out / 'summary.json', summary)
    status = {'state': 'complete' if terminal is None else 'stopped', 'terminal_http': terminal,
              'sha256': {name: f.sha((out / name).read_bytes()) for name in
                         ('manifest.json', 'calls.jsonl', 'outcomes.jsonl', 'summary.json')}}
    f.write(out / 'status.json', status)
    return status, summary


def verify(root, study, out, expected, *, assess=None, build_state=None):
    manifest, config, drafts = setup(root, study, expected)
    status = f.load(out / 'status.json')
    if status['state'] != 'complete' or status['terminal_http'] is not None:
        raise ValueError('Run incomplete; do not send to review')
    names = ('manifest.json', 'calls.jsonl', 'outcomes.jsonl', 'summary.json')
    if (status['sha256'] != {name: f.sha((out / name).read_bytes()) for name in names}
            or f.load(out / 'manifest.json') != manifest):
        raise ValueError('Run manifest or artifact changed')
    calls = f.rows(out / 'calls.jsonl')
    if len(calls) > manifest['max_calls']:
        raise ValueError('Call ceiling exceeded')
    for call in calls:
        latency = call.get('latency_seconds')
        if (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0
                or call.get('http_status') in TERMINAL
                or sum(k in call for k in ('raw', 'http_status', 'error')) != 1):
            raise ValueError('Invalid recorded call')
    iterator = iter(calls)
    outcomes = []
    assess, build_state = assess or assessment_fn(), build_state or state_fn()
    for draft, item in zip(drafts, manifest['orders']):
        mismatch = []
        def request(stage, body):
            call = next(iterator, {})
            if (call.get('draft_id') != draft['draft_id'] or call.get('stage') != stage
                    or call.get('request') != body or call.get('request_sha256') != f.sha(f.canonical(body))):
                mismatch.append(stage)
                return None
            return call.get('raw')
        outcomes.append(evaluate(draft, config, item['arms'], request, assess=assess, build_state=build_state))
        if mismatch:
            raise ValueError('Replay request mismatch: ' + draft['draft_id'])
    if next(iterator, None) is not None or outcomes != f.rows(out / 'outcomes.jsonl'):
        raise ValueError('Replay outcomes differ from saved outputs')
    summary = aggregate(outcomes, calls)
    if summary != f.load(out / 'summary.json'):
        raise ValueError('Replay summary differs from saved summary')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'run', 'verify'):
        sub = commands.add_parser(name)
        sub.add_argument('--study', type=Path, required=True)
        sub.add_argument('--freeze-sha256', required=True)
        if name != 'plan':
            sub.add_argument('--out', type=Path, required=True)
        if name == 'run':
            sub.add_argument('--live', action='store_true', required=True)
            sub.add_argument('--max-calls', type=int, required=True)
            sub.add_argument('--env-file', type=Path, default=f.ROOT / '.env')
    args = parser.parse_args()
    try:
        study = f.private_path(args.study)
        if args.command == 'plan':
            manifest, _, _ = setup(f.ROOT, study, args.freeze_sha256)
            print(json.dumps({k: manifest[k] for k in ('freeze_sha256', 'valid_drafts', 'max_calls')}, indent=2))
            return
        out = f.private_path(args.out)
        if args.command == 'run':
            from .run import load_env, post
            load_env(args.env_file)
            status, summary = run(f.ROOT, study, out, args.freeze_sha256,
                                  os.environ.get('OPENAI_API_KEY'), args.max_calls, post)
            if status['state'] != 'complete':
                parser.exit(1, 'Stopped on access/rate limit; partial logs retained; do not review.\n')
        else:
            summary = verify(f.ROOT, study, out, args.freeze_sha256)
        print(json.dumps(summary, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
