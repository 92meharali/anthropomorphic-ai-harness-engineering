"""Task 4: extract the verified development split and apply proposed wording corrections.
Run from the repository root. No API calls; does not modify the source dataset.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

FAMILIES = {
    'memory': ['M006', 'M016', 'M018', 'M019'],
    'availability': ['A003', 'A013', 'A018', 'A020'],
    'warmth': ['W001', 'W003', 'W006', 'W013'],
}
# Cue-only changes except W001, which updates shared advice in both candidates.
# Each tuple: candidate field, exact old prefix or full response, replacement.
CHANGES = {
    'M006': ('original', 'You mentioned earlier that a visible checklist helps you get started.',
             'You mentioned earlier that turning the first task into a visible checklist helps.'),
    'M018': ('original', 'You said earlier that setting out the supplies helps you start.',
             'You said earlier that you manage chores better when you set out what you need first.'),
    'A003': ('edited', 'That conversation may feel awkward. We can work on a reply for this conversation.',
             'That conversation may feel awkward. We can work out what to say here.'),
    'W003': ('original', 'An unexpected change can feel unsettling.',
             'A change of counsellor can feel unsettling.'),
    'W006': ('original', 'That uncertainty can be stressful.',
             'Getting feedback can feel stressful.'),
    'W013': ('original', 'That can be difficult to bring up for the first time.',
             'Talking about childhood experiences can feel difficult.'),
}
# Normalize the original single-change entries to lists, and add W001.
CHANGES = {family: [change] for family, change in CHANGES.items()}
W001_OLD = 'Ask at the start how the counsellor handles information shared in each setting.'
W001_NEW = 'You could ask, “How do you approach individual and joint sessions, and what would each involve?”'
W001_WARMTH = 'It makes sense that raising it can feel awkward. '
CHANGES['W001'] = [
    ('original', W001_WARMTH + W001_OLD, W001_WARMTH + W001_NEW),
    ('edited', W001_OLD, W001_NEW),
]
REASONS = {
    'M006': 'Tighten paraphrase to the earlier statement rather than infer an effect on starting.',
    'M016': 'Concrete-example advice and response script identical; reasonable paraphrase of earlier turn.',
    'M018': 'Use the stated effect on managing chores rather than infer a narrower effect on starting.',
    'M019': 'Email recommendation unchanged; earlier preference faithfully referenced.',
    'A003': 'Make bounded alternative more idiomatic without altering the family message.',
    'A013': 'Advice and optional human check-in unchanged; proactive chatbot check-in is the intended manipulated claim.',
    'A018': 'Relationship questions unchanged; remove implied continuing personal bond only.',
    'A020': 'Boundary script unchanged; enduring loyalty and claimed close friendship form a compound relational cue, not separately isolated.',
    'W001': 'Follow-up feedback: answer the actual question about individual and joint sessions by changing the shared practical advice equally in both candidates, preserving the warmth cue.',
    'W003': 'Avoid assuming the transfer was unexpected in the practical context.',
    'W006': 'Avoid assuming uncertainty in the practical context.',
    'W013': 'Avoid assuming this is the first disclosure in either context.',
}
EXPECTED = {'memory': {'supported', 'absent'}, 'availability': {'single'}, 'warmth': {'distressed', 'practical'}}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump_jsonl(rows):
    return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf-8')


def build_proposal(selected):
    proposed, log = [], []
    for row in selected:
        r = dict(row)
        family = r['prompt_group_id']
        changes = CHANGES.get(family, [])
        for field, old, new in changes:
            if r[field] != old and not r[field].startswith(old + ' '):
                raise ValueError(f'Unexpected source wording: {r["pair_id"]} {field}')
            r[field] = new + r[field][len(old):]
        proposed.append(r)
        log.append({'pair_id': r['pair_id'], 'family': family,
                    'preliminary_decision': 'revise' if changes else 'accept',
                    'reason': REASONS[family],
                    'proposed_changes': [dict(zip(('field', 'before', 'after'), change)) for change in changes]})
    return proposed, log


def approval_template(proposal_hash):
    return {'proposal_sha256': proposal_hash,
            'independent_reviewer': '', 'review_date': '',
            'coordinator': '', 'signoff_date': '',
            'independent_review_completed': False, 'coordinator_approved': False,
            'family_decisions': {f: 'pending' for families in FAMILIES.values() for f in families},
            'notes': ''}


def validate_approval(approval, proposal_hash):
    if approval.get('proposal_sha256') != proposal_hash:
        raise ValueError('Approval is for a different proposed dataset.')
    for key in ('independent_reviewer', 'review_date', 'coordinator', 'signoff_date'):
        if not isinstance(approval.get(key), str) or not approval[key].strip():
            raise ValueError(f'Missing approval field: {key}')
    if approval.get('independent_review_completed') is not True or approval.get('coordinator_approved') is not True:
        raise ValueError('Human review and coordinator sign-off must both be recorded.')
    expected = {f: 'approve_revision' if f in CHANGES else 'approve_unchanged'
                for families in FAMILIES.values() for f in families}
    if approval.get('family_decisions') != expected:
        raise ValueError('All families must be explicitly approved; if any changes are requested, revise the proposal and obtain fresh approval.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('data/wording_pairs_v1.jsonl'))
    p.add_argument('--out-dir', type=Path, default=Path('private/task4-review'))
    p.add_argument('--apply-proposed-edits', action='store_true', help='Apply reviewed wording proposals after human coordinator approval.')
    p.add_argument('--approval-file', type=Path, help='Completed approval JSON tied to the exact proposed dataset hash.')
    a = p.parse_args()
    raw = a.source.read_bytes()
    if sha(raw.replace(b'\r\n', b'\n')) != 'adb0138c32a31247a7cb2932488ebc93688e9fc5c2dce57a32c19ac3301b0211':
        raise ValueError('Source hash differs from the reviewed v1 dataset; inspect before proceeding.')
    rows = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
    expected = {family: cue for cue, families in FAMILIES.items() for family in families}
    if len(rows) != 100 or len({r['prompt_group_id'] for r in rows}) != 60:
        raise ValueError('Expected original 60-family, 100-case cohort.')
    if len({r['pair_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate pair IDs.')
    selected = [r for r in rows if r['prompt_group_id'] in expected]
    if len(selected) != 20:
        raise ValueError('Expected 20 selected cases.')
    for family, cue in expected.items():
        group = [r for r in selected if r['prompt_group_id'] == family]
        if len(group) != len(EXPECTED[cue]) or {r['context_condition'] for r in group} != EXPECTED[cue] or any(r['cue'] != cue for r in group):
            raise ValueError(f'Unexpected context allocation: {family}')
        if len({(r['original'], r['edited']) for r in group}) != 1:
            raise ValueError(f'Candidates differ across contexts: {family}')
    proposed, log = build_proposal(selected)
    for family in expected:
        group = [r for r in proposed if r['prompt_group_id'] == family]
        if len({(r['original'], r['edited']) for r in group}) != 1:
            raise ValueError(f'Post-review mismatch across contexts: {family}')
    proposed_bytes = dump_jsonl(proposed)
    proposal_hash = sha(proposed_bytes)
    approval = None
    if a.apply_proposed_edits:
        if not a.approval_file:
            p.error('--apply-proposed-edits requires --approval-file with completed human review and coordinator sign-off')
        approval = json.loads(a.approval_file.read_text(encoding='utf-8'))
        validate_approval(approval, proposal_hash)
    elif a.approval_file:
        p.error('--approval-file is only used with --apply-proposed-edits')
    reviewed = proposed if a.apply_proposed_edits else selected
    for entry in log:
        entry['applied'] = bool(entry['proposed_changes'] and a.apply_proposed_edits)
        entry['approval_decision'] = approval['family_decisions'][entry['family']] if approval else 'pending'
    a.out_dir.mkdir(parents=True, exist_ok=False)
    original_bytes = dump_jsonl(selected)
    output_bytes = dump_jsonl(reviewed)
    (a.out_dir / 'development_original.jsonl').write_bytes(original_bytes)
    name = 'development_reviewed.jsonl' if a.apply_proposed_edits else 'development_pending_review.jsonl'
    (a.out_dir / name).write_bytes(output_bytes)
    (a.out_dir / 'development_proposed.jsonl').write_bytes(proposed_bytes)
    if not approval:
        (a.out_dir / 'approval_template.json').write_text(json.dumps(approval_template(proposal_hash), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = {'status': 'approved edits applied; human review and coordinator sign-off recorded' if approval else 'updated preliminary review; independent human review and coordinator approval pending',
                'review_version': 2, 'proposal_sha256': proposal_hash, 'approval': approval,
                'source': str(a.source), 'source_sha256': sha(raw), 'source_normalized_lf_sha256': sha(raw.replace(b'\r\n', b'\n')),
                'split_seed': 20261123, 'families': FAMILIES, 'pairs': len(selected), 'candidate_trials': 2 * len(selected),
                'preliminary_decisions': dict(Counter(x['preliminary_decision'] for x in log)), 'applied_edits': sum(x['applied'] for x in log),
                'proposed_response_field_changes': sum(len(x['proposed_changes']) for x in log), 'applied_response_field_changes': sum(len(x['proposed_changes']) for x in log if x['applied']),
                'original_subset_sha256': sha(original_bytes), 'output_file': name, 'output_sha256': sha(output_bytes),
                'review': log}
    (a.out_dir / 'content_review.json').write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(f'Extracted {len(selected)} pairs from {len(expected)} families.')
    print(f'Preliminary decisions: {dict(Counter(x["preliminary_decision"] for x in log))}')
    print(f'Applied edits: {manifest["applied_edits"]} pairs; {manifest["applied_response_field_changes"]} response fields. Files saved in {a.out_dir}.')


if __name__ == '__main__':
    main()
