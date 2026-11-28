"""Issue #26, first item only: plan, collect originals, freeze and verify.

No cue screening, rewriting, reviewer evaluation or comparison is performed here.
Only `collect --live` makes requests, and those requests generate original drafts.
"""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = 'data/generated_rewrite_prompts_v1.jsonl'
PROTOCOL = 'rubric/generated_rewrite_protocol_v1.json'
PRIOR = 'data/wording_pairs_v1.jsonl'
PRIOR_MANIFEST = 'data/wording_pairs_v1.manifest.json'
ISSUE1_SOURCE = 'issue1_flagged_originals'
ISSUE1_STATUS_SHA256 = '4c0c19c5496d5011fe0dde70614533ee759f948b9a336aff21fe57a6881699b4'
ISSUE1_FLAGGED_COUNT = 33
DEPENDENCIES = (PROMPTS, PROTOCOL, PRIOR, PRIOR_MANIFEST,
    'rubric/generated_rewrite_review_v1.md', 'rubric/cue_rubric_v1.md',
    'rubric/cue_output_schema_v1.json', 'rubric/oa_protocol.json',
    'data/REVIEWER_GUIDE.md', 'evaluation/cue_output.py',
    'evaluation/cue_routing.py', 'evaluation/pair_judge.py',
    'evaluation/run.py', 'evaluation/judges.py', 'evaluation/data.py',
    'docs/GENERATED_REWRITE_FREEZE.md', 'evaluation/rewrite_freeze.py')
FIELDS = {'draft_id', 'prompt_group_id', 'sampling_stratum',
          'current_user_message', 'visible_history'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('Duplicate JSON key: ' + k)
        result[k] = v
    return result


def invalid_constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def loads(text):
    return json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)


def load(path):
    return loads(path.read_text(encoding='utf-8'))


def rows(path):
    return decode_rows(path.read_bytes())


def decode_rows(data):
    return [loads(line) for line in data.decode('utf-8').split('\n') if line.strip()]


def write(path, data):
    with path.open('xb') as f:
        f.write(canonical(data) + b'\n')


def write_rows(path, data):
    with path.open('xb') as f:
        for row in data:
            f.write(canonical(row) + b'\n')


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def normalized(s):
    return ' '.join(s.casefold().split())


def validate_prompts(prompts, prior, config):
    spec = config['cohort']
    if len(prompts) != spec['families'] or not prompts:
        raise ValueError('Unexpected cohort size')
    ids, families, messages = set(), set(), set()
    counts = Counter()
    prior_groups = {r['prompt_group_id'] for r in prior}
    prior_messages = {normalized(r['current_user_message']) for r in prior}
    for row in prompts:
        if not isinstance(row, dict) or set(row) != FIELDS or not all(
                nonempty(row[k]) for k in FIELDS - {'visible_history'}):
            raise ValueError('Invalid prompt row')
        ident, family = row['draft_id'], row['prompt_group_id']
        msg = normalized(row['current_user_message'])
        if ident in ids or family in families or family in prior_groups or msg in messages:
            raise ValueError('Duplicate or reused draft/family/message')
        if any(SequenceMatcher(None, msg, p).ratio() >= spec['lexical_overlap_threshold']
               for p in prior_messages):
            raise ValueError('Prior-cohort lexical overlap: ' + ident)
        ids.add(ident); families.add(family); messages.add(msg)
        counts[row['sampling_stratum']] += 1
        history = row['visible_history']
        if not isinstance(history, list):
            raise ValueError('Invalid visible history')
        refs = {'current_user_message'}
        for turn in history:
            if (not isinstance(turn, dict) or set(turn) != {'turn_id', 'role', 'content'}
                    or not all(nonempty(v) for v in turn.values())
                    or turn['role'] not in ('user', 'assistant') or turn['turn_id'] in refs):
                raise ValueError('Invalid history turn')
            refs.add(turn['turn_id'])
    if dict(counts) != spec['strata']:
        raise ValueError('Sampling strata changed')


def original_request(row, config):
    settings = config['original_generation']
    return {**settings, 'input': [
        *({'role': t['role'], 'content': t['content']} for t in row['visible_history']),
        {'role': 'user', 'content': row['current_user_message']}]}



def flagged_feedback(assessment, config):
    """Use only the checked output of the existing single-candidate assessment.

    An unresolved assessment never qualifies, even if another cue is unsupported.
    This helper does not run a detector or validate raw provider output itself.
    """
    if assessment.get('classification') != config['flagging']['classification']:
        return None
    cues = assessment.get('checked_cues')
    if assessment.get('status') != 'ok' or not isinstance(cues, list) or any(
            c.get('evidence_status') == 'unclear' for c in cues):
        raise ValueError('Inconsistent resolved detector assessment')
    feedback = [{k: c[k] for k in config['flagging']['feedback_fields']}
                for c in cues if c['evidence_status'] == 'unsupported']
    if not feedback:
        raise ValueError('Correction assessment has no validated unsupported cue')
    return feedback


def rewrite_request(record, config, arm, assessment, *, state_builder=None):
    """Build, but never send, a matched rewrite request for later Issue #26 work."""
    if arm not in ('cue_specific', 'generic'):
        raise ValueError('Unknown rewrite arm')
    feedback = flagged_feedback(assessment, config)
    if feedback is None:
        raise ValueError('Only flagged drafts can receive rewrites')
    if state_builder is None:
        from .cue_output import state as state_builder
    state = state_builder(record, record['draft'], config['capabilities'])
    settings = config['rewrite_generation']
    if arm == 'cue_specific':
        state[settings['cue_specific_extra_field']] = feedback
    request = {k: settings[k] for k in ('model', 'reasoning', 'max_output_tokens',
                                       'store', 'instructions', 'text')}
    request['input'] = [{'role': 'user', 'content': canonical(state).decode('utf-8')}]
    return request


def build_plan(root, cohort_note):
    if not nonempty(cohort_note):
        raise ValueError('Record the independent overlap/cohort review reference')
    config = load(root / PROTOCOL)
    if config['capabilities'] != load(root / PRIOR_MANIFEST)['system_capabilities']:
        raise ValueError('Study capabilities differ from existing harness')
    prompts = rows(root / PROMPTS)
    validate_prompts(prompts, rows(root / PRIOR), config)
    body = {'version': 1, 'cohort_note': cohort_note, 'config': config,
            'files_sha256': {p: sha((root / p).read_bytes()) for p in DEPENDENCIES},
            'jobs': [{'prompt': row, 'request': original_request(row, config)} for row in prompts]}
    return {'body': body, 'plan_sha256': sha(canonical(body))}


def check_plan(plan, root):
    if plan != build_plan(root, plan['body']['cohort_note']):
        raise ValueError('Plan, code, cohort or protocol changed')
    return plan['body']


def prepare(root, out, cohort_note):
    plan = build_plan(root, cohort_note)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    write(out / 'plan.json', plan)
    return plan


def parse_original(raw):
    if not isinstance(raw, dict) or raw.get('status') != 'completed' or not nonempty(raw.get('model')):
        raise ValueError('Incomplete result or missing returned model')
    texts = []
    for message in raw['output']:
        if message.get('type') != 'message' or message.get('phase') not in (None, 'final_answer'):
            continue
        if message.get('role') != 'assistant':
            raise ValueError('Unexpected message role')
        for part in message['content']:
            if part.get('type') == 'refusal':
                raise ValueError('Provider refusal')
            if part.get('type') == 'output_text':
                texts.append(part['text'])
    if len(texts) != 1 or not nonempty(texts[0]):
        raise ValueError('Expected one nonempty original response')
    return texts[0], raw['model']


def collect(root, plan_dir, out, key, max_calls, transport):
    plan = load(plan_dir / 'plan.json')
    body = check_plan(plan, root)
    jobs = body['jobs']
    if type(max_calls) is not int or max_calls != len(jobs):
        raise ValueError('Original-draft call budget must equal the frozen cohort size')
    if not nonempty(key):
        raise ValueError('Missing API key')
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    stopped = False
    with (out / 'attempts.jsonl').open('xb') as stream:
        for job in jobs:
            entry = {'draft_id': job['prompt']['draft_id'], 'request': job['request'],
                     'request_sha256': sha(canonical(job['request']))}
            start = time.monotonic()
            try:
                raw, request_id = transport('openai', job['request'], key)
                entry.update(raw=raw, request_id=request_id)
            except urllib.error.HTTPError as exc:
                entry['http_status'] = exc.code
                stopped = exc.code in (401, 403, 429)
                exc.close()
            except (OSError, TypeError, ValueError):
                entry['error'] = 'transport_failure'
            entry['latency_seconds'] = time.monotonic() - start
            stream.write(canonical(entry) + b'\n'); stream.flush()
            if stopped:
                break
    meta = {'plan_sha256': plan['plan_sha256'], 'complete': not stopped,
            'attempts_sha256': sha((out / 'attempts.jsonl').read_bytes())}
    write(out / 'collection.json', meta)
    return meta


def reconstruct(plan, attempts, collection, attempt_bytes):
    if collection != {'plan_sha256': plan['plan_sha256'], 'complete': True,
                      'attempts_sha256': sha(attempt_bytes)}:
        raise ValueError('Incomplete, mismatched or altered original collection')
    jobs = plan['body']['jobs']
    if len(attempts) != len(jobs):
        raise ValueError('Expected exactly one recorded original attempt per planned draft')
    drafts, failures = [], []
    for job, attempt in zip(jobs, attempts):
        row = job['prompt']
        if (attempt.get('draft_id') != row['draft_id'] or attempt.get('request') != job['request']
                or attempt.get('request_sha256') != sha(canonical(job['request']))):
            raise ValueError('Attempt differs from frozen request')
        if attempt.get('http_status') in (401, 403, 429):
            raise ValueError('Terminal collection failure')
        try:
            text, model = parse_original(attempt.get('raw'))
        except (ValueError, TypeError, KeyError, AttributeError):
            failures.append(row['draft_id'])
            continue
        drafts.append({**{k: row[k] for k in FIELDS - {'sampling_stratum'}},
                       'draft_model': model, 'draft': text})
    if not drafts:
        raise ValueError('No valid original drafts; do not run a comparison')
    # A changing provider snapshot could confound screening; do not pool it silently.
    if len({d['draft_model'] for d in drafts}) != 1:
        raise ValueError('Provider returned different original model IDs; stop before screening')
    return drafts, failures


def freeze(root, plan_dir, collection_dir, out):
    plan = load(plan_dir / 'plan.json')
    check_plan(plan, root)
    collection = load(collection_dir / 'collection.json')
    attempt_bytes = (collection_dir / 'attempts.jsonl').read_bytes()
    attempts = decode_rows(attempt_bytes)
    drafts, failures = reconstruct(plan, attempts, collection, attempt_bytes)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    write(out / 'plan.json', plan)
    write(out / 'collection.json', collection)
    (out / 'attempts.jsonl').write_bytes(attempt_bytes)
    write_rows(out / 'drafts.jsonl', drafts)
    manifest = {'plan_sha256': plan['plan_sha256'], 'planned': len(attempts),
                'valid_drafts': len(drafts), 'failed_original_ids': failures,
                'draft_model_returned': drafts[0]['draft_model'],
                'drafts_sha256': sha((out / 'drafts.jsonl').read_bytes()),
                'attempts_sha256': sha(attempt_bytes)}
    seal = {'manifest': manifest, 'freeze_sha256': sha(canonical(manifest))}
    write(out / 'freeze.json', seal)
    return seal


def issue1_plan(root):
    config = load(root / PROTOCOL)
    if config['capabilities'] != load(root / PRIOR_MANIFEST)['system_capabilities']:
        raise ValueError('Study capabilities differ from the original harness')
    config['cohort'] = {'drafts': ISSUE1_FLAGGED_COUNT, 'selection': ISSUE1_SOURCE}
    body = {
        'version': 1, 'source_kind': ISSUE1_SOURCE,
        'issue1_status_sha256': ISSUE1_STATUS_SHA256,
        'config': config,
        'files_sha256': {p: sha((root / p).read_bytes()) for p in
                         (*DEPENDENCIES, 'evaluation/run_wording.py')},
    }
    return {'body': body, 'plan_sha256': sha(canonical(body))}


def issue1_seal(plan, drafts, draft_bytes):
    from . import cue_output, cue_routing

    config = plan['body']['config']
    if len(drafts) != ISSUE1_FLAGGED_COUNT or len({d['draft_id'] for d in drafts}) != len(drafts):
        raise ValueError(f'Expected exactly {ISSUE1_FLAGGED_COUNT} unique flagged originals')
    for row in drafts:
        if set(row) != (FIELDS - {'sampling_stratum'}) | {'draft', 'draft_model', 'saved_assessment'}:
            raise ValueError('Unexpected saved draft fields')
        assessment = row['saved_assessment']
        state = cue_output.state(row, row['draft'], config['capabilities'])
        checked = cue_routing.validate_evidence(assessment['result'], state)
        if assessment['checked_cues'] != checked or not flagged_feedback(assessment, config):
            raise ValueError('Saved evidence differs from the original context')
    manifest = {
        'source_kind': ISSUE1_SOURCE, 'issue1_status_sha256': ISSUE1_STATUS_SHA256,
        'plan_sha256': plan['plan_sha256'], 'valid_drafts': len(drafts),
        'drafts_sha256': sha(draft_bytes),
    }
    return {'manifest': manifest, 'freeze_sha256': sha(canonical(manifest))}


def reuse_issue1(root, prior_study, source, run, out):
    from .run_wording import load_cases, verify_run

    if sha((run / 'status.json').read_bytes()) != ISSUE1_STATUS_SHA256:
        raise ValueError('Not the completed Issue #1 held-out run')
    outcomes, calls = verify_run(prior_study, source, run)
    if len(outcomes) != 80 or len(calls) != 611:
        raise ValueError('Unexpected Issue #1 replay coverage')
    originals = {pair['review_id']: record for record, pair, _ in load_cases(prior_study, source)}
    plan = issue1_plan(root)
    drafts = []
    for outcome in outcomes:
        full = outcome['traces']['full']
        assessment = full['assessments'][outcome['original_position']]
        if assessment['classification'] != 'correction':
            continue
        row = originals[outcome['review_id']]
        drafts.append({
            'draft_id': outcome['review_id'], 'draft_model': 'wording-v1-authored',
            'prompt_group_id': row['prompt_group_id'], 'draft': row['original'],
            'current_user_message': row['current_user_message'],
            'visible_history': row['visible_history'], 'saved_assessment': assessment,
        })
    data = b''.join(canonical(row) + b'\n' for row in drafts)
    seal = issue1_seal(plan, drafts, data)
    if sha((run / 'status.json').read_bytes()) != ISSUE1_STATUS_SHA256:
        raise ValueError('Issue #1 run changed during import')
    out.mkdir(parents=True, mode=0o700)
    write(out / 'plan.json', plan)
    (out / 'drafts.jsonl').write_bytes(data)
    write(out / 'freeze.json', seal)
    return seal


def verify(root, study):
    saved = load(study / 'freeze.json')
    if saved['manifest'].get('source_kind') == ISSUE1_SOURCE:
        plan = issue1_plan(root)
        data = (study / 'drafts.jsonl').read_bytes()
        if load(study / 'plan.json') != plan or issue1_seal(plan, decode_rows(data), data) != saved:
            raise ValueError('Imported cohort, evidence or rewrite protocol changed')
        return saved
    plan = load(study / 'plan.json'); check_plan(plan, root)
    collection = load(study / 'collection.json')
    attempt_bytes = (study / 'attempts.jsonl').read_bytes()
    attempts = decode_rows(attempt_bytes)
    drafts, failures = reconstruct(plan, attempts, collection, attempt_bytes)
    saved_bytes = (study / 'drafts.jsonl').read_bytes()
    if saved_bytes != b''.join(canonical(d) + b'\n' for d in drafts):
        raise ValueError('Frozen original text or cohort changed')
    manifest = {'plan_sha256': plan['plan_sha256'], 'planned': len(attempts),
                'valid_drafts': len(drafts), 'failed_original_ids': failures,
                'draft_model_returned': drafts[0]['draft_model'],
                'drafts_sha256': sha(saved_bytes), 'attempts_sha256': sha(attempt_bytes)}
    seal = {'manifest': manifest, 'freeze_sha256': sha(canonical(manifest))}
    if load(study / 'freeze.json') != seal:
        raise ValueError('Freeze manifest changed')
    return seal


def private_path(path):
    path = path.resolve()
    if not path.is_relative_to((ROOT / 'private').resolve()) or path == (ROOT / 'private').resolve():
        raise ValueError('Use a subdirectory of the repository ignored private/ directory')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan')
    plan.add_argument('--out', type=Path, required=True)
    plan.add_argument('--cohort-note', required=True)
    collection = commands.add_parser('collect')
    collection.add_argument('--plan', type=Path, required=True)
    collection.add_argument('--out', type=Path, required=True)
    collection.add_argument('--live', action='store_true', required=True)
    collection.add_argument('--max-calls', type=int, required=True)
    collection.add_argument('--env-file', type=Path, default=ROOT / '.env')
    frozen = commands.add_parser('freeze')
    frozen.add_argument('--plan', type=Path, required=True)
    frozen.add_argument('--collection', type=Path, required=True)
    frozen.add_argument('--out', type=Path, required=True)
    check = commands.add_parser('verify')
    check.add_argument('--study', type=Path, required=True)
    reuse = commands.add_parser('reuse-issue1')
    for name in ('study', 'source', 'run', 'out'):
        reuse.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            result = prepare(ROOT, private_path(args.out), args.cohort_note)
            print('Planned originals:', len(result['body']['jobs']), 'Plan SHA-256:', result['plan_sha256'])
        elif args.command == 'collect':
            from .run import load_env, post
            load_env(args.env_file)
            result = collect(ROOT, private_path(args.plan), private_path(args.out),
                             os.environ.get('OPENAI_API_KEY'), args.max_calls, post)
            if not result['complete']:
                parser.exit(1, 'Collection stopped; partial logs saved. Do not freeze or compare.\n')
            print('Original collection complete; verify and freeze before screening.')
        elif args.command == 'reuse-issue1':
            result = reuse_issue1(ROOT, private_path(args.study), private_path(args.source),
                                 private_path(args.run), private_path(args.out))
            print('Verified original drafts:', result['manifest']['valid_drafts'],
                  'Freeze SHA-256:', result['freeze_sha256'])
        else:
            result = (freeze(ROOT, private_path(args.plan), private_path(args.collection), private_path(args.out))
                      if args.command == 'freeze' else verify(ROOT, private_path(args.study)))
            print('Verified original drafts:', result['manifest']['valid_drafts'],
                  'Freeze SHA-256:', result['freeze_sha256'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
