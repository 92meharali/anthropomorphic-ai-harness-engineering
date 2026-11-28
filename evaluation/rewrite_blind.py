"""Issue #26 Task 3: offline blinded packet, independent ballot import and replay.

No API calls, no scoring or arm-level analysis. Keep all artifacts under private/.
"""
import argparse
import io
import json
from pathlib import Path
import random
import math
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils.exceptions import InvalidFileException

from . import rewrite_freeze as f, rewrite_generate as g

VERSION = 'generated-rewrite-task3-xlsx-v2'
SOURCE = 'evaluation/rewrite_blind.py'
POSITIONS = ('A', 'B')
FIELDS = ('cue_corrected', 'advice_preserved', 'warmth_preserved', 'oa')
REVIEWERS = ('R01', 'R02', 'R03')
WORKBOOK_PREFIX = 'Generated_Rewrite_Annotation_'
LABELS = ('Cue correction', 'Advice preservation', 'Warmth preservation', 'Overall Appropriateness')


def workbook_name(reviewer):
    return WORKBOOK_PREFIX + reviewer + '.xlsx'


def build(root, study, run, freeze_sha, *, assess=None, build_state=None):
    summary = g.verify(root, study, run, freeze_sha, assess=assess, build_state=build_state)
    config = f.load(study / 'plan.json')['body']['config']
    review = config['review']
    if (review['reviewers'] != len(REVIEWERS) or review['majority'] != 2
            or review['independent'] is not True or review['blinded'] is not True):
        raise ValueError('Unsupported frozen reviewer configuration')
    eligible = [r for r in f.rows(run / 'outcomes.jsonl') if r['pair_eligible']]
    if len(eligible) != summary['eligible_pairs']:
        raise ValueError('Inconsistent eligible pair count')
    rng = random.Random(review['packet_seed'])
    rng.shuffle(eligible)
    orders = [g.ARMS if i % 2 == 0 else g.ARMS[::-1] for i in range(len(eligible))]
    if rng.randrange(2):
        orders = [o[::-1] for o in orders]
    rng.shuffle(orders)
    cases, key = [], []
    for i, (row, order) in enumerate(zip(eligible, orders), 1):
        case = {'review_id': f'RW{i:04d}', 'visible_history': [
            {'role': t['role'], 'content': t['content']} for t in row['visible_history']],
            'current_user_message': row['current_user_message'], 'original': row['original'],
            **{p: row['rewrites'][arm]['response'] for p, arm in zip(POSITIONS, order)}}
        case['case_sha256'] = f.sha(f.canonical(case))
        cases.append(case)
        key.append({'review_id': case['review_id'], 'case_sha256': case['case_sha256'],
                    'draft_id': row['draft_id'], 'prompt_group_id': row['prompt_group_id'],
                    **dict(zip(POSITIONS, order))})
    guide = (root / review['rubric']).read_bytes()
    return summary, cases, key, guide, review


def jsonl_bytes(rows):
    return b''.join(f.canonical(r) + b'\n' for r in rows)


def chunks(text):
    # Preserve every character, including newlines. Split long content over rows
    # so Excel's maximum row height never silently clips a long model response.
    # Excel uses LF inside cells; the private JSONL still binds exact source bytes.
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if not text:
        return ['']
    parts = []
    while text:
        limit = min(600, len(text))
        newlines = [i for i, c in enumerate(text[:limit]) if c == '\n']
        if len(newlines) >= 8:
            limit = newlines[7] + 1
        parts.append(text[:limit])
        text = text[limit:]
    return parts


def layout(cases, reviewer, guide):
    """Canonical visible cell content and rating positions; no arm IDs."""
    rows = [('title', ['Generated rewrite annotation', '', '']),
            ('meta', ['Reviewer ID', reviewer, '']),
            ('note', ['Instructions', 'Read the Rubric sheet first. Rate both answers independently; complete all eight blue cells per case. Return this workbook only.', '']),
            ('note', ['Privacy', 'Do not discuss ratings or try to identify methods. Do not change the text, IDs or layout. Identical answers may receive identical ratings.', ''])]
    slots = {}
    for case in cases:
        rid = case['review_id']
        rows += [('title', [rid, '', '']), ('meta', ['Case SHA-256', case['case_sha256'], ''])]
        for i, turn in enumerate(case['visible_history'], 1):
            for j, piece in enumerate(chunks(turn['content'])):
                rows.append(('text', [f'Earlier {turn["role"]} {i}' if j == 0 else '(continued)', piece, '']))
        if not case['visible_history']:
            rows.append(('text', ['Earlier conversation', '(None)', '']))
        for label, field in [('Current user message','current_user_message'),
                             ('Original draft (reference)','original'), ('Rewrite A','A'), ('Rewrite B','B')]:
            for j, piece in enumerate(chunks(case[field])):
                rows.append(('text', [label if j == 0 else '(continued)', piece, '']))
        rows.append(('header', ['Evaluation dimension','Rewrite A','Rewrite B']))
        for field, label in zip(FIELDS, LABELS):
            rows.append(('rating', [label, '', '']))
            for col, pos in enumerate(POSITIONS, 2):
                slots[(len(rows), col)] = (rid, pos, field)
        rows.append(('spacer', ['', '', '']))
    # Preserve the complete frozen rubric verbatim, including markdown table text.
    rubric = [('title', ['Frozen evaluation rubric', '', ''])]
    for line in guide.decode('utf-8').replace('\r\n','\n').replace('\r','\n').splitlines(keepends=True):
        for piece in chunks(line):
            rubric.append(('text', ['', piece, '']))
    return {'Review': rows, 'Rubric': rubric}, slots


def make_workbook(cases, reviewer, guide):
    spec, slots = layout(cases, reviewer, guide)
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in spec.items():
        ws = wb.create_sheet(name)
        ws.sheet_view.showGridLines = False
        ws.column_dimensions['A'].width = 31 if name == 'Review' else 4
        ws.column_dimensions['B'].width = 49 if name == 'Review' else 65
        ws.column_dimensions['C'].width = 49 if name == 'Review' else 65
        ws.freeze_panes = 'A3' if name == 'Review' else 'A2'
        for rownum, (kind, values) in enumerate(rows, 1):
            for col, value in enumerate(values, 1):
                cell = ws.cell(rownum, col)
                if value != '':
                    cell.value = value
                    cell.data_type = 's'  # treat formula-like chatbot output as literal text
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                cell.font = Font(name='Calibri', size=11, color='172C40')
                if kind in ('title','header'):
                    cell.fill = PatternFill('solid', fgColor='183B56' if kind == 'title' else '245E70')
                    cell.font = Font(name='Calibri', size=12, color='FFFFFF', bold=True)
                elif kind == 'rating' and col > 1:
                    cell.fill = PatternFill('solid', fgColor='DDEFFF')
                    cell.protection = Protection(locked=False)
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                elif col == 1:
                    cell.font = Font(name='Calibri', size=11, color='183B56', bold=True)
                    cell.fill = PatternFill('solid', fgColor='EEF3F7')
            if kind in ('text','note','meta'):
                ws.merge_cells(start_row=rownum,start_column=2,end_row=rownum,end_column=3)
                width = 72 if name == 'Review' else 92
                lines = sum(max(1, math.ceil(len(x)/width)) for x in values[1].split('\n'))
                ws.row_dimensions[rownum].height = min(400, max(28, 16*lines+12))
            elif kind == 'title':
                ws.merge_cells(start_row=rownum,start_column=1,end_row=rownum,end_column=3)
                ws.row_dimensions[rownum].height = 26
            else:
                ws.row_dimensions[rownum].height = 25 if kind != 'spacer' else 10
        ws.protection.sheet = True  # accidental-edit guard, not security
    ws = wb['Review']
    for kind, allowed in [('binary','"Yes,No,Uncertain"'), ('oa','"1,2,3,4,5,Uncertain"')]:
        dv = DataValidation(type='list', formula1=allowed, allow_blank=False, showErrorMessage=True,
                            errorStyle='stop', errorTitle='Invalid rating', error='Choose a listed rating.')
        ws.add_data_validation(dv)
        for (row, col), (_, _, field) in slots.items():
            if (field == 'oa') == (kind == 'oa'):
                dv.add(ws.cell(row,col))
    buf = io.BytesIO(); wb.save(buf); wb.close()
    return buf.getvalue()


def check_workbook(data, cases, reviewer, guide, *, blank=False):
    spec, slots = layout(cases, reviewer, guide)
    try:
        # A reviewer workbook is an ordinary xlsx, not a macro or external-link container.
        with ZipFile(io.BytesIO(data)) as archive:
            if any('vbaproject' in n.lower() or n.startswith('xl/externalLinks/') for n in archive.namelist()):
                raise ValueError('Unexpected macro or external link')
        wb = load_workbook(io.BytesIO(data), data_only=False, keep_links=False)
    except (BadZipFile, InvalidFileException, OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid Excel workbook: ' + reviewer) from exc
    try:
        if wb.sheetnames != list(spec):
            raise ValueError('Unexpected workbook sheets')
        result = {c['review_id']: {'reviewer_id': reviewer, 'review_id': c['review_id'],
                    'case_sha256': c['case_sha256'], 'A': {}, 'B': {}} for c in cases}
        for name, rows in spec.items():
            ws = wb[name]
            if ws.sheet_state != 'visible' or ws.max_row != len(rows) or ws.max_column != 3:
                raise ValueError('Unexpected workbook dimensions or hidden sheet')
            expected_merges = {f'B{i}:C{i}' for i,(kind,_) in enumerate(rows,1) if kind in ('text','note','meta')}
            expected_merges |= {f'A{i}:C{i}' for i,(kind,_) in enumerate(rows,1) if kind == 'title'}
            if {str(r) for r in ws.merged_cells.ranges} != expected_merges:
                raise ValueError('Workbook layout changed')
            if any(d.hidden for d in ws.row_dimensions.values()) or any(d.hidden for d in ws.column_dimensions.values()):
                raise ValueError('Unexpected hidden rows or columns')
            for i, (_, values) in enumerate(rows,1):
                for col, expected in enumerate(values,1):
                    cell = ws.cell(i,col); value = cell.value
                    if cell.data_type == 'f':
                        raise ValueError('Formula cells are not permitted')
                    slot = slots.get((i,col)) if name == 'Review' else None
                    if not slot or blank:
                        if value != (expected if expected != '' else None):
                            raise ValueError(f'Workbook content changed: {reviewer} {name}!{cell.coordinate}')
                        continue
                    rid, pos, field = slot
                    if isinstance(value,str):
                        token = value.strip().casefold()
                    elif type(value) is int or (type(value) is float and value.is_integer()):
                        token = str(int(value))
                    else:
                        token = ''
                    if token == 'uncertain':
                        normalized = None
                    elif field == 'oa' and token in ('1','2','3','4','5'):
                        normalized = int(token)
                    elif field != 'oa' and token in ('yes','no'):
                        normalized = token == 'yes'
                    else:
                        raise ValueError(f'Invalid or blank rating: {reviewer} {rid} {pos} {field}')
                    result[rid][pos][field] = normalized
        return [result[c['review_id']] for c in cases]
    finally:
        wb.close()


def packet_files(cases, key, guide):
    files = {'cases.jsonl': jsonl_bytes(cases), 'key.jsonl': jsonl_bytes(key)}
    for reviewer in REVIEWERS if cases else ():
        name = 'reviewers/' + workbook_name(reviewer)
        files[name] = make_workbook(cases, reviewer, guide)
        check_workbook(files[name], cases, reviewer, guide, blank=True)
    return files


def packet_body(root, run, freeze_sha, summary, cases, review):
    return {'version': VERSION, 'freeze_sha256': freeze_sha,
            'run_status_sha256': f.sha((run / 'status.json').read_bytes()),
            'source_sha256': f.sha((root / SOURCE).read_bytes()),
            'packet_seed': review['packet_seed'], 'screened': summary['screened'],
            'flagged': summary['flagged'], 'eligible_pairs': len(cases),
            'reviewers': list(REVIEWERS) if cases else []}


def prepare(root, study, run, out, freeze_sha, **kwargs):
    summary, cases, key, guide, review = build(root, study, run, freeze_sha, **kwargs)
    files = packet_files(cases, key, guide)
    body = packet_body(root, run, freeze_sha, summary, cases, review)
    body['files_sha256'] = {name: f.sha(data) for name, data in files.items()}
    manifest = {'body': body, 'packet_sha256': f.sha(f.canonical(body))}
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, data in files.items():
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(data)
    f.write(out / 'manifest.json', manifest)
    return manifest


def verify_packet(root, study, run, packet, freeze_sha, packet_sha, **kwargs):
    summary, cases, key, guide, review = build(root, study, run, freeze_sha, **kwargs)
    manifest = f.load(packet / 'manifest.json')
    body = manifest['body']
    if manifest['packet_sha256'] != packet_sha or f.sha(f.canonical(body)) != packet_sha:
        raise ValueError('Packet does not match independently recorded seal')
    metadata = {k:v for k,v in body.items() if k != 'files_sha256'}
    if metadata != packet_body(root, run, freeze_sha, summary, cases, review):
        raise ValueError('Packet does not match verified generation or source')
    exact = {'cases.jsonl': jsonl_bytes(cases), 'key.jsonl': jsonl_bytes(key)}
    expected = set(exact) | {'reviewers/' + workbook_name(r) for r in body['reviewers']}
    if set(body['files_sha256']) != expected:
        raise ValueError('Unexpected packet artifact list')
    # Verify the actual original XLSX bytes against the independent seal, then
    # reconstruct semantic workbook content (ZIP timestamps are not reproducible).
    for name, digest in body['files_sha256'].items():
        data = (packet / name).read_bytes()
        if f.sha(data) != digest or (name in exact and data != exact[name]):
            raise ValueError('Packet artifact changed: ' + name)
    for r in body['reviewers']:
        check_workbook((packet/'reviewers'/workbook_name(r)).read_bytes(),cases,r,guide,blank=True)
    return manifest, cases, key


def parse_ballot(data, cases, reviewer, guide):
    return check_workbook(data, cases, reviewer, guide)


def provenance_check(provenance, reviewers):
    # This is an explicit coordinator attestation, not proof of human independence.
    if not isinstance(provenance, dict) or set(provenance) != {'record_reference','reviewers'} or not f.nonempty(provenance['record_reference']):
        raise ValueError('Missing private provenance record reference')
    entries = provenance['reviewers']
    if not isinstance(entries, dict) or set(entries) != set(reviewers):
        raise ValueError('Expected one provenance entry per reviewer')
    refs = []
    for reviewer in reviewers:
        entry = entries[reviewer]
        if (not isinstance(entry, dict) or set(entry) != {'submission_reference','independent','blinded'}
                or entry['independent'] is not True or entry['blinded'] is not True
                or not f.nonempty(entry['submission_reference'])):
            raise ValueError('Missing independence/blinding attestation: ' + reviewer)
        refs.append(entry['submission_reference'])
    if len(set(refs)) != len(refs):
        raise ValueError('Reviewer submission references must be distinct')


def collection_spec(manifest, cases, raw, provenance, guide):
    reviewers = manifest['body']['reviewers']
    provenance_check(provenance, reviewers)
    if set(raw) != set(reviewers):
        raise ValueError('Expected exactly the assigned reviewer ballots')
    ratings = [r for reviewer in reviewers for r in parse_ballot(raw[reviewer], cases, reviewer, guide)]
    files = {f'ballots/{r}.xlsx': raw[r] for r in reviewers}
    files.update({'ratings.jsonl': jsonl_bytes(ratings), 'provenance.json': f.canonical(provenance) + b'\n'})
    body = {'version': VERSION, 'packet_sha256': manifest['packet_sha256'],
            'reviewers': reviewers, 'cases': len(cases), 'reviewer_case_ratings': len(ratings),
            'state': 'complete' if cases else 'no_eligible_pairs',
            'files_sha256': {name: f.sha(data) for name, data in files.items()}}
    return {'body': body, 'collection_sha256': f.sha(f.canonical(body))}, files, ratings


def collect(root, study, run, packet, out, freeze_sha, packet_sha, ballots, provenance, **kwargs):
    manifest, cases, _ = verify_packet(root, study, run, packet, freeze_sha, packet_sha, **kwargs)
    paths = [p.resolve() for p in ballots]
    if len(paths) != len(manifest['body']['reviewers']) or len(set(paths)) != len(paths):
        raise ValueError('Supply distinct ballot files in R01, R02, R03 order (none for empty packet)')
    if any(p.is_relative_to(packet.resolve()) for p in paths):
        raise ValueError('Use returned ballot copies outside the original packet')
    raw = dict(zip(manifest['body']['reviewers'], (p.read_bytes() for p in paths)))
    guide = (root / f.load(study/'plan.json')['body']['config']['review']['rubric']).read_bytes()
    if any(p.suffix.lower() != '.xlsx' for p in paths):
        raise ValueError('Reviewer submissions must be .xlsx files')
    seal, files, _ = collection_spec(manifest, cases, raw, provenance, guide)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, data in files.items():
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(data)
    f.write(out / 'manifest.json', seal)
    return seal


def verify_collection(root, study, run, packet, collection, freeze_sha, packet_sha, collection_sha, **kwargs):
    manifest, cases, key = verify_packet(root, study, run, packet, freeze_sha, packet_sha, **kwargs)
    raw = {r: (collection / 'ballots' / (r + '.xlsx')).read_bytes() for r in manifest['body']['reviewers']}
    guide = (root / f.load(study/'plan.json')['body']['config']['review']['rubric']).read_bytes()
    seal, files, ratings = collection_spec(manifest, cases, raw, f.load(collection / 'provenance.json'), guide)
    if seal['collection_sha256'] != collection_sha or f.load(collection / 'manifest.json') != seal:
        raise ValueError('Collection does not match independently recorded seal')
    if any((collection / name).read_bytes() != data for name, data in files.items()):
        raise ValueError('Collection artifact changed')
    return seal, cases, key, ratings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify-packet', 'collect', 'verify'):
        sub = commands.add_parser(name)
        for arg in ('study', 'run', 'packet'):
            sub.add_argument('--' + arg, type=Path, required=True)
        sub.add_argument('--freeze-sha256', required=True)
        if name != 'prepare':
            sub.add_argument('--packet-sha256', required=True)
        if name in ('collect','verify'):
            sub.add_argument('--collection', type=Path, required=True)
        if name == 'collect':
            sub.add_argument('--ballots', type=Path, nargs='*', default=[])
            sub.add_argument('--provenance', type=Path, required=True)
        if name == 'verify':
            sub.add_argument('--collection-sha256', required=True)
    args = parser.parse_args()
    try:
        study, run, packet = (f.private_path(getattr(args, name)) for name in ('study','run','packet'))
        base = (f.ROOT, study, run, packet, args.freeze_sha256)
        if args.command == 'prepare':
            result = prepare(*base)
        elif args.command == 'verify-packet':
            result, _, _ = verify_packet(*base, args.packet_sha256)
        elif args.command == 'collect':
            result = collect(f.ROOT, study, run, packet, f.private_path(args.collection), args.freeze_sha256,
                             args.packet_sha256, [f.private_path(p) for p in args.ballots],
                             f.load(f.private_path(args.provenance)))
        else:
            result, _, _, _ = verify_collection(f.ROOT, study, run, packet, f.private_path(args.collection),
                args.freeze_sha256, args.packet_sha256, args.collection_sha256)
        # Aggregate metadata only. Never print cases, mapping or ratings.
        print(json.dumps({k: v for k, v in result.items() if k != 'body'} | {
            k: v for k, v in result['body'].items() if k in ('screened','flagged','eligible_pairs',
                        'reviewers','cases','reviewer_case_ratings','state')}, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
