"""Response-only HumT baseline following the released scoring script."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import fmean

from .data import digest, read_jsonl, write_json, write_jsonl

UPSTREAM = 'cd677776eff1cc47eadb1d9d4b4be6454a9d52ca'
MODEL = 'openai-community/gpt2'
REVISION = '607a30d783dfa663caf39e06633721c8d4cfcd7e'
CHAR_LIMIT = 300
SAMPLES = 100
SEED = 20261126


def contrast(text, score_group):
    """Subtract mean inanimate group log score from the human group mean."""
    quoted = '"' + text[:CHAR_LIMIT] + '"'
    return score_group([f'He said, {quoted}', f'She said, {quoted}']) - score_group([f'It said, {quoted}'])


def score_inputs(inputs, scorer):
    rows, cache, seen = [], {}, set()
    for row in inputs:
        identifier, text = row['item_id'], row['response']
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise ValueError('Expected unique nonempty item IDs')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Expected a nonempty response')
        seen.add(identifier)
        # HumT sees only the scored prefix. Keep the full answer hash for joins.
        scored = text[:CHAR_LIMIT]
        if scored not in cache:
            value = scorer(scored)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('HumT scorer returned a nonfinite value')
            cache[scored] = value
        rows.append({'item_id': identifier, 'response_sha256': digest(text), 'humt': cache[scored]})
    return rows


def load_scorer(download=False):
    import torch
    import transformers
    from torch.nn.utils.rnn import pad_sequence

    torch.set_num_threads(1)
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        MODEL, revision=REVISION, local_files_only=not download,
    )
    model = transformers.AutoModelForCausalLM.from_pretrained(
        MODEL, revision=REVISION, local_files_only=not download, use_safetensors=True,
        attn_implementation='eager',
    ).to('cpu').train()

    def group(prompts):
        sequences = [tokenizer(p, return_tensors='pt', truncation=True, max_length=1024) for p in prompts]
        ids = pad_sequence([v['input_ids'].squeeze(0) for v in sequences], batch_first=True)
        masks = pad_sequence([v['attention_mask'].squeeze(0) for v in sequences], batch_first=True)
        # Match the released code: one scalar negative batch loss per dropout pass.
        # Input IDs are also the labels, including padding if present.
        with torch.no_grad():
            return fmean(-model(input_ids=ids, attention_mask=masks,
                                labels=ids, use_cache=False).loss.item() for _ in range(SAMPLES))

    def score(text):
        seed = (SEED + int(digest(text)[:8], 16)) % (2**32)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            return contrast(text, group)

    return score, {'torch': torch.__version__, 'transformers': transformers.__version__}


def smoke():
    supplied = []
    def group(prompts):
        supplied.append(prompts)
        return -2 if prompts[0].startswith('He ') else -3
    text = 'A' * 300 + ' unscored suffix'
    other = 'A' * 300 + ' a different suffix'
    rows = score_inputs([{'item_id': 'a', 'response': text}, {'item_id': 'b', 'response': other}],
                        lambda s: contrast(s, group))
    assert len(supplied) == 2 and supplied[0][1] == 'She said, "' + 'A'*300 + '"'
    assert {r['humt'] for r in rows} == {1}
    assert {r['response_sha256'] for r in rows} == {digest(text), digest(other)}
    assert digest(text) != digest(text[:CHAR_LIMIT])
    print('Offline smoke passed: score direction, 300-character truncation, full-text hash, repeated response reuse.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--download', action='store_true', help='Allow download of the pinned GPT-2 checkpoint')
    parser.add_argument('--smoke', action='store_true', help='Check contracts without model weights')
    args = parser.parse_args()
    if args.smoke:
        smoke()
        return
    if args.input is None or args.out_dir is None:
        parser.error('--input and --out-dir are required for scoring')
    if args.out_dir.exists():
        parser.error('Use a new output directory')
    scorer, versions = load_scorer(args.download)
    inputs = read_jsonl(args.input)
    if not inputs:
        parser.error('No input records')
    args.out_dir.mkdir(parents=True, exist_ok=False)
    scores = score_inputs(inputs, scorer)
    result = args.out_dir / 'humt.jsonl'
    write_jsonl(result, scores)
    write_json(args.out_dir / 'manifest.json', {
        'upstream_commit': UPSTREAM, 'model': MODEL, 'revision': REVISION,
        'character_limit': CHAR_LIMIT, 'dropout_samples_per_group': SAMPLES,
        'seed': SEED, 'seed_policy': 'base seed plus 32-bit scored-text digest prefix',
        'device': 'cpu', 'threads': 1, 'versions': versions,
        'input_sha256': digest(args.input.read_bytes()), 'scorer_sha256': digest(Path(__file__).read_bytes()),
        'output_sha256': digest(result.read_bytes()), 'responses': len(scores),
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
    })
    print(f'Saved {len(scores)} HumT scores to {result}')


if __name__ == '__main__':
    main()
