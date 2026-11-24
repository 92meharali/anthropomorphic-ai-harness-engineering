"""Run the OA-only development pilot. --dry-run creates requests without network calls."""
import argparse
import datetime
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .data import ROOT, digest, read_jsonl, write_json, write_jsonl
from .judges import DEFAULT_MODELS, ENDPOINTS, KEY_NAMES, VERSION, parse_jev, parse_openai, parse_decision, request_body


def load_env(path):
    """Read simple KEY=value entries without shell evaluation or value logging."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not key.replace('_', '').isalnum():
            raise ValueError('Invalid .env line; use KEY=value')
        os.environ.setdefault(key, value.strip().strip('\"\''))


def plan(records, protocol, providers, models):
    jobs = []
    seen = set()
    for record in records:
        if not record.get('item_id') or record['item_id'] in seen:
            raise ValueError('Missing or duplicate item ID')
        seen.add(record['item_id'])
        for provider in providers:
            body = request_body(provider, models[provider], record, protocol)
            payload_hash = digest(json.dumps(body, sort_keys=True, ensure_ascii=False))
            jobs.append({'job_id': digest(provider + ':' + record['item_id'] + ':' + payload_hash),
                         'item_id': record['item_id'], 'provider': provider,
                         'payload_sha256': payload_hash, 'request': body})
    return jobs


def post(provider, body, key):
    request = urllib.request.Request(ENDPOINTS[provider], data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    # No implicit retries: each job makes at most one billed attempt in this invocation.
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read()), response.headers.get('x-request-id')


def execute(job, key, transport=post):
    start = time.monotonic()
    result = {k: job[k] for k in ('job_id', 'item_id', 'provider', 'payload_sha256')}
    result['requested_model'] = job['request']['model']
    result['request'] = job['request']
    try:
        raw, request_id = transport(job['provider'], job['request'], key)
        result.update(raw_response=raw, request_id=request_id,
                      returned_model=raw.get('model'), usage=raw.get('usage'))
        parse = {'jev': parse_jev, 'openai': parse_openai, 'decision': parse_decision}[job['provider']]
        result.update(parse(raw))
    except urllib.error.HTTPError as exc:
        # Server error bodies may echo source data. Keep status only in console-facing errors.
        result.update(status='api_error', rating=None, error=f'HTTP {exc.code}', http_status=exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        result.update(status='api_error', rating=None, error='Network failure or timeout')
    except (ValueError, KeyError, TypeError):
        result.update(status='invalid_output', rating=None, error='Invalid or incomplete response schema')
    result['latency_seconds'] = round(time.monotonic() - start, 3)
    result['timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('jev', 'openai', 'decision', 'both', 'comparison'), default='openai',
                        help='comparison runs OpenAI Decisions and the frozen OpenAI LLM; both retains Jev + OpenAI')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=ROOT / 'rubric/oa_protocol.json')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--limit', type=int, default=60,
                        help='Response records to score (default: 60, maximum: 200)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error('--limit must be between 1 and 200')
    if 'reserved' in args.input.parts:
        parser.error('Reserved examples are locked out of this development runner')
    load_env(args.env_file)
    providers = {'both': ('jev', 'openai'), 'comparison': ('decision', 'openai')}.get(args.provider, (args.provider,))
    model_keys = {'jev': 'JEV_MODEL', 'openai': 'OPENAI_MODEL', 'decision': 'OPENAI_DECISION_MODEL'}
    models = {p: os.environ.get(model_keys[p]) or DEFAULT_MODELS[p] for p in providers}
    records = read_jsonl(args.input)[:args.limit]
    if not records:
        parser.error('No input records')
    protocol = json.loads(args.protocol.read_text())
    if set(protocol['dimensions']) != {'OA'}:
        parser.error('This runner accepts an OA-only protocol')
    jobs = plan(records, protocol, providers, models)
    if not args.dry_run:
        missing = [KEY_NAMES[p] for p in providers if not os.environ.get(KEY_NAMES[p])]
        if missing:
            parser.error('Missing API credentials: ' + ', '.join(missing) + '. Set them in .env; do not put keys in prompts.')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_dir = args.run_dir or ROOT / 'outputs' / (('dry-run-' if args.dry_run else 'run-') + stamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'version': VERSION, 'dry_run': args.dry_run, 'models': models,
                'input_sha256': digest(args.input.read_bytes()), 'protocol_sha256': digest(args.protocol.read_bytes()),
                'responses': len(records), 'requests': len(jobs),
                'source_code_sha256': {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))},
                'jobs': [{k: j[k] for k in ('job_id', 'item_id', 'provider', 'payload_sha256')} for j in jobs]}
    manifest_path = run_dir / 'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        parser.error('Run configuration changed. Use a new --run-dir to keep runs separate.')
    write_json(manifest_path, manifest)
    write_jsonl(run_dir / 'requests.jsonl', jobs)
    if args.dry_run:
        print(f'Dry run: {len(records)} responses, {len(jobs)} requests prepared; no model calls.')
        print(run_dir)
        return
    result_path = run_dir / 'results.jsonl'
    # On resume, skip all recorded attempts, including failures. A fresh run retries deliberately.
    done = {r['job_id'] for r in read_jsonl(result_path)} if result_path.exists() else set()
    for index, job in enumerate(jobs, 1):
        if job['job_id'] in done:
            continue
        result = execute(job, os.environ[KEY_NAMES[job['provider']]])
        with result_path.open('a') as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
            stream.flush()
        print(f'{index}/{len(jobs)} {job["provider"]}: {result["status"]}', flush=True)
        if result.get('http_status') in (401, 403, 429):
            print('Stopping on authentication/access/rate-limit error. Recorded results are preserved.')
            break
    print(run_dir)


if __name__ == '__main__':
    main()
