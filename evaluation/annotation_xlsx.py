"""Import blinded, variable-size Excel annotation packets without changing them."""
import argparse
import json
from pathlib import Path
import re

from validate_task6 import MAP, workbook, value
from .data import digest, read_jsonl
from .wording_harness import indexed

HEADERS = ('Case ID', 'Conversation context', 'Answer A', 'Answer B',
           'Wording preference', 'Wording needs correction', 'Content preserved', 'Pair hash')
FIELDS = ('preference', 'cue_needs_correction', 'content_preserved')


def validate_packet(packet):
    checked = indexed(packet, 'review_id')
    if not checked:
        raise ValueError('Empty packet')
    for row in packet:
        if set(row) != {'review_id', 'prompt', 'A', 'B', 'pair_sha256'}:
            raise ValueError('Unexpected reviewer fields')
        payload = {k: v for k, v in row.items() if k != 'pair_sha256'}
        if row['pair_sha256'] != digest(json.dumps(payload, sort_keys=True, ensure_ascii=False)):
            raise ValueError('Invalid packet hash')


def convert(sheet, packet, *, blank=False):
    validate_packet(packet)
    if tuple(value(sheet, f'{col}1', True) for col in 'ABCDEFGH') != HEADERS:
        raise ValueError('Unexpected annotation headings')
    result = []
    for n, pair in enumerate(packet, 2):
        immutable = [value(sheet, f'{c}{n}', True) for c in 'ABCDH']
        if immutable != [pair[k] for k in ('review_id', 'prompt', 'A', 'B', 'pair_sha256')]:
            raise ValueError(f'Changed case text, order or hash on row {n}')
        entries = [value(sheet, f'{c}{n}', True) for c in 'EFG']
        if blank:
            if any(entries):
                raise ValueError(f'Unexpected judgment on blank row {n}')
            continue
        if any(v not in mapping for v, mapping in zip(entries, MAP)):
            raise ValueError(f'Missing or invalid judgment on row {n}')
        result.append({'review_id': pair['review_id'], 'pair_sha256': pair['pair_sha256'],
                       **{key: mapping[v] for key, mapping, v in zip(FIELDS, MAP, entries)}})
    for address, (text, formula) in sheet.items():
        match = re.fullmatch(r'([A-Z]+)(\d+)', address)
        if match and (match[1] not in 'ABCDEFGH' or int(match[2]) > len(packet)+1):
            if text or formula:
                raise ValueError(f'Unexpected extra data at {address}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--verify-blank', action='store_true')
    args = parser.parse_args()
    if args.verify_blank == (args.out is not None):
        parser.error('Use either --verify-blank or --out')
    packet = read_jsonl(args.packet)
    rows = convert(workbook(args.workbook)['Annotation'], packet, blank=args.verify_blank)
    if args.verify_blank:
        print(f'Blank workbook matches all {len(packet)} frozen cases.')
        return
    with args.out.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row) + '\n')
    print(f'Validated {len(rows)} ballots and wrote {args.out}.')


if __name__ == '__main__':
    main()
