"""Frozen presentation for the OA comparison on wording-v1."""
from pathlib import Path
import json

from .data import digest
from .run import plan

VERSION = 'oa-visible-history-v1'
MODEL = 'gpt-6.2-sol'
PROTOCOL_SHA256 = '2073a30bf8972d96775b006ae4661f8b73236b98c29b05a731d0356d4bcfd60a'


def prompt_for(record):
    """Return the exact approved rendering of the current visible interaction."""
    current = record['current_user_message']
    history = record['visible_history']
    if not isinstance(current, str) or not current.strip() or not isinstance(history, list):
        raise ValueError('Expected a current user message and visible history list')
    if not history:
        text = current
    elif (len(history) == 1 and isinstance(history[0], dict)
          and history[0].get('role') == 'user'
          and isinstance(history[0].get('content'), str) and history[0]['content'].strip()):
        text = f"Previous user message: {history[0]['content']}\nCurrent user message: {current}"
    else:
        raise ValueError('Wording-v1 supports at most one earlier user turn')
    if record.get('prompt') != text:
        raise ValueError('Rendered OA input differs from approved context')
    return text


def oa_jobs(record, pair, protocol_path):
    """Build the two frozen candidate requests with a common full-context input."""
    payload = Path(protocol_path).read_bytes()
    if digest(payload) != PROTOCOL_SHA256:
        raise ValueError('OA rubric differs from the frozen baseline')
    prompt = prompt_for(record)
    if pair['prompt'] != prompt or sorted((pair['A'], pair['B'])) != sorted((record['original'], record['edited'])):
        raise ValueError('Packet does not match the approved source record')
    inputs = [{'item_id': pair['review_id'] + '-' + label,
               'prompt': prompt, 'response': pair[label]} for label in ('A', 'B')]
    return plan(inputs, json.loads(payload), ('openai',), {'openai': MODEL})
