"""Run fixed-pair OA, direct-judge and cue-harness comparisons."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error

from . import cue_output, cue_routing, pair_judge
from .data import digest, read_jsonl, write_json
from .held_out import cohort_for
from .judges import parse_openai
from .oa_history import MODEL, oa_jobs
from .run import load_env, post
from .wording_harness import FILES, indexed, signed_choice

MAX_CALLS_PER_PAIR = 9
TRACE_FILES = ('pairs.jsonl', 'requests_and_results.jsonl')
RUN_MODULES = ('cue_output', 'cue_routing', 'data', 'decision', 'held_out',
               'judges', 'oa_history', 'pair_judge', 'run', 'run_wording', 'wording_harness')


def load_cases(study, source):
    manifest = json.loads((study / 'manifest.json').read_text())
    if manifest['source_sha256'] != digest(source.read_bytes()):
        raise ValueError('Source does not match the frozen study')
    if any(digest((study / name).read_bytes()) != manifest['sha256'][name] for name in FILES):
        raise ValueError('Frozen study files changed')
    source_rows = indexed(read_jsonl(source), 'pair_id')
    keys = indexed(read_jsonl(study / 'pair_key.jsonl'), 'review_id')
    packets = indexed(read_jsonl(study / 'review_packet.jsonl'), 'review_id')
    if (not keys or keys.keys() != packets.keys()
            or len(keys) != len(source_rows)
            or set(v['pair_id'] for v in keys.values()) != source_rows.keys()):
        raise ValueError('Frozen cases do not match the source or packet')
    cases = []
    for rid, key in keys.items():
        record, pair = source_rows[key['pair_id']], packets[rid]
        pair_judge.verify_pair(pair)
        if any(pair[p] != record[key[p]] for p in ('A', 'B')):
            raise ValueError('Frozen mapping mismatch')
        jobs = oa_jobs(record, pair, study / 'protocol.json')
        cases.append((record, pair, jobs))
    return cases


def score_pair(record, pair, jobs, capabilities, detector_model, pair_model, request):
    """Use a transport callback so this workflow can be replayed offline."""
    oa = {}
    for position, job in zip(('A', 'B'), jobs):
        try:
            raw = request('oa_' + position, job['request'])
            if not isinstance(raw, dict):
                raise ValueError('Missing or invalid OA response')
            oa[position] = parse_openai(raw)
        except (TypeError, ValueError, KeyError, AttributeError):
            oa[position] = {'status': 'invalid_or_failed', 'rating': None}
    scores = {p: oa[p]['rating'] if oa[p]['status'] == 'ok' else None for p in ('A', 'B')}
    try:
        ballot = pair_judge.parse_openai(request('direct_pair', pair_judge.request_body(pair_model, pair)), pair)
    except (TypeError, ValueError, KeyError):
        ballot = None

    def evaluate_oa(prompt, response):
        if prompt != pair['prompt']:
            raise ValueError('OA gate must use the common full prompt')
        return next(oa[p] for p in ('A', 'B') if pair[p] == response)

    traces = {}
    for condition, masked in (('full', False), ('masked', True)):
        traces[condition] = cue_routing.route_pair(
            record, pair, detector_model=detector_model, pair_model=pair_model,
            detect=lambda body: request(condition + '_detector', body),
            judge_pair=lambda body: request(condition + '_guard', body),
            evaluate_oa=evaluate_oa, withhold_history=masked, capabilities=capabilities,
        )
    direct = ballot['preference'] if ballot and ballot['preference'] != 'cannot_judge' else 'unresolved'
    return {'review_id': pair['review_id'], 'pair_sha256': pair['pair_sha256'],
            'prompt_group_id': record['prompt_group_id'], 'cue': record['cue'],
            'original_position': traces['full']['original_position'],
            'oa': oa, 'direct_pair_judgment': ballot, 'traces': traces,
            'choices': {'keep_original': traces['full']['original_position'],
                        'frozen_oa': signed_choice(scores['A'], scores['B']),
                        'direct_pair': direct,
                        **{name: trace['cue_decision']['selected_position'] or 'hold'
                           for name, trace in traces.items()}}}


def configuration(study, source, cases, caps, detector_model, pair_model):
    root = Path(__file__).parent
    return {
        'version': 2, 'cohort': cohort_for(source), 'cases': len(cases),
        'max_requests_upper_bound': len(cases) * MAX_CALLS_PER_PAIR,
        'study_manifest_sha256': digest((study / 'manifest.json').read_bytes()),
        'source_sha256': digest(source.read_bytes()), 'capabilities': caps,
        'models': {'detector': detector_model, 'pair': pair_model, 'oa': MODEL},
        'code_sha256': {name: digest((root / (name + '.py')).read_bytes()) for name in RUN_MODULES},
        'rubric_sha256': {p.name: digest(p.read_bytes()) for p in (
            cue_output.RUBRIC_PATH, cue_output.SCHEMA_PATH,
            pair_judge.GUIDE_PATH, pair_judge.SCHEMA_PATH, study / 'protocol.json')},
    }


def configuration_hash(config):
    return digest(json.dumps(config, sort_keys=True, ensure_ascii=False))


def check_approval(config, approval):
    if config['cohort'] != 'held_out':
        return
    if (not isinstance(approval, dict)
            or approval.get('configuration_sha256') != configuration_hash(config)
            or any(not isinstance(approval.get(field), str) or not approval[field].strip()
                   for field in ('content_review_record', 'protocol_signoff_record'))):
        raise ValueError('Held-out scoring requires content review and protocol sign-off bound to this configuration')


def check_freeze(config, snapshot, approval):
    if snapshot.get('status') != 'dry_run' or snapshot.get('configuration') != config:
        raise ValueError('Configuration differs from the frozen dry run')
    if snapshot.get('configuration_sha256') != configuration_hash(config):
        raise ValueError('Frozen configuration hash mismatch')
    check_approval(config, approval)


def verify_run(study, source, run):
    manifest = json.loads((run / 'manifest.json').read_text())
    status = json.loads((run / 'status.json').read_text())
    if manifest.get('status') != 'live_requested' or status.get('status') != 'attempts_completed':
        raise ValueError('Comparison run is incomplete')
    if status.get('manifest_sha256') != digest((run / 'manifest.json').read_bytes()):
        raise ValueError('Run manifest changed after scoring')
    for name in TRACE_FILES:
        if status['files_sha256'][name] != digest((run / name).read_bytes()):
            raise ValueError(f'Completed run file changed: {name}')
    cases = load_cases(study, source)
    caps = cue_output.load_capabilities()
    models = manifest['configuration']['models']
    config = configuration(study, source, cases, caps, models['detector'], models['pair'])
    check_freeze(config, {'status':'dry_run', 'configuration':manifest['configuration'],
                          'configuration_sha256':manifest['configuration_sha256']}, manifest.get('approval'))
    logs = read_jsonl(run / 'requests_and_results.jsonl')
    if len(logs) != status['calls']:
        raise ValueError('Run call count disagrees with the completed log')
    logged = iter(logs)
    reconstructed = []
    for record, pair, jobs in cases:
        mismatch = []
        def request(stage, body):
            row = next(logged, None)
            if (row is None or row.get('review_id') != pair['review_id']
                    or row.get('stage') != stage or row.get('request') != body
                    or row.get('request_sha256') != cue_output.request_sha256(body)):
                mismatch.append(stage)
                return None
            raw = row.get('raw')
            if raw is not None and (not isinstance(raw, dict) or row.get('usage') != raw.get('usage')
                                    or row.get('returned_model') != raw.get('model')):
                mismatch.append(stage)
                return None
            return raw
        reconstructed.append(score_pair(record, pair, jobs, caps, models['detector'], models['pair'], request))
        if mismatch:
            raise ValueError(f'Missing or mismatched call trace for {pair["review_id"]}')
    if next(logged, None) is not None or reconstructed != read_jsonl(run / 'pairs.jsonl'):
        raise ValueError('Saved choices do not match the replayed provider outputs')
    return reconstructed, logs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--detector-model', default=MODEL)
    parser.add_argument('--pair-model', default=MODEL)
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--freeze-manifest', type=Path, help='Manifest from the offline dry run')
    parser.add_argument('--approval', type=Path, help='Required held-out sign-off record')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    cases = load_cases(args.study, args.source)
    upper = len(cases) * MAX_CALLS_PER_PAIR
    caps = cue_output.load_capabilities()
    config = configuration(args.study, args.source, cases, caps, args.detector_model, args.pair_model)
    approval = None
    # Validate the model request contracts before creating any run output.
    for record, pair, _ in cases:
        if pair['A'] == pair['B']:
            raise ValueError('Expected distinct candidates')
        pair_judge.request_body(args.pair_model, pair)
        for label in ('A', 'B'):
            for mask in (False, True):
                cue_output.request_body(args.detector_model, record, pair[label], caps, withhold_history=mask)
    if args.live:
        if args.max_calls is None or args.max_calls < upper:
            parser.error(f'--live requires --max-calls of at least {upper} to cover this cohort')
        if args.freeze_manifest is None:
            parser.error('--live requires --freeze-manifest')
        approval = json.loads(args.approval.read_text()) if args.approval else None
        try:
            check_freeze(config, json.loads(args.freeze_manifest.read_text()), approval)
        except ValueError as exc:
            parser.error(str(exc))
        load_env(args.env_file)
        key = os.environ.get('OPENAI_API_KEY')
        if not key:
            parser.error('OPENAI_API_KEY is required for live scoring')

    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'manifest.json', {
        'status': 'live_requested' if args.live else 'dry_run',
        'configuration': config, 'configuration_sha256': configuration_hash(config), 'approval': approval,
    })
    if not args.live:
        print(f'Checked request construction for {len(cases)} pairs, at most {upper} live calls. No API calls.')
        return

    calls = 0
    terminal = None
    with (args.out / 'requests_and_results.jsonl').open('a') as log, (args.out / 'pairs.jsonl').open('a') as out:
        for record, pair, jobs in cases:
            def request(stage, body):
                nonlocal calls, terminal
                if terminal is not None or calls >= args.max_calls:
                    return None
                calls += 1
                start = time.monotonic()
                entry = {'review_id': pair['review_id'], 'stage': stage, 'request': body,
                         'request_sha256': cue_output.request_sha256(body)}
                try:
                    raw, request_id = post('openai', body, key)
                    if not isinstance(raw, dict):
                        raise ValueError('Malformed provider response')
                    entry.update(raw=raw, request_id=request_id, usage=raw.get('usage'),
                                 returned_model=raw.get('model'))
                    return raw
                except urllib.error.HTTPError as exc:
                    entry['http_status'] = exc.code
                    if exc.code in (401, 403, 429):
                        terminal = exc.code
                    exc.close()
                except (OSError, ValueError, TypeError):
                    entry['error'] = 'transport_failure'
                finally:
                    entry['latency_seconds'] = time.monotonic() - start
                    log.write(json.dumps(entry, ensure_ascii=False) + '\n')
                    log.flush()
            result = score_pair(record, pair, jobs, caps, args.detector_model, args.pair_model, request)
            out.write(json.dumps(result, ensure_ascii=False) + '\n')
            out.flush()
            if terminal is not None:
                write_json(args.out / 'status.json', {'status': 'stopped', 'http_status': terminal, 'calls': calls})
                parser.exit(1, f'Stopped on HTTP {terminal}; partial records saved.\n')
    write_json(args.out / 'status.json', {
        'status': 'attempts_completed', 'calls': calls,
        'manifest_sha256': digest((args.out / 'manifest.json').read_bytes()),
        'files_sha256': {name: digest((args.out / name).read_bytes()) for name in TRACE_FILES},
    })
    print(f'Finished {len(cases)} pairs and {calls} calls. Review coverage before interpretation.')


if __name__ == '__main__':
    main()
