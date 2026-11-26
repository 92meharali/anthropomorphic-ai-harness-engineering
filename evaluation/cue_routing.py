"""Task 3: evidence checks and deterministic fixed-pair routing.

No network transport. Callbacks are trusted host adapters to the model(s) and OA
runner. They must return the response to the supplied request, never a human ballot.
Reference validation is mechanical, not proof of semantic entailment.
"""
from copy import deepcopy
import json

from . import cue_output as cue, pair_judge as pair_judge

VERSION = 'cue-routing-v1'
OA_MINIMUM = 4  # same gate as the existing evaluation/controller.py


def _occurrences(text, span):
    """Zero-based character offsets, including overlapping occurrences."""
    starts = []
    offset = 0
    while True:
        index = text.find(span, offset)
        if index == -1:
            return starts
        starts.append(index)
        offset = index + 1


def validate_evidence(result, state):
    """Validate against the exact *host-built* detector state, not the full record.

    Return normalized evidence trace, or raise ValueError. This does not establish
    whether a quote actually entails a claim, whether the detector missed a cue,
    or whether a human would agree with the claimed evidence status.
    """
    cue.parse_structured(result)
    if not isinstance(state, dict) or set(state) != {
            'current_user_message', 'visible_history', 'candidate_response',
            'system_capabilities', 'trusted_role_rules'}:
        raise ValueError('Invalid detector state')
    rebuilt = cue.state(state, state['candidate_response'], state['system_capabilities'])
    if state != rebuilt:
        raise ValueError('State differs from trusted input contract')
    turns = {t['turn_id']: t for t in state['visible_history']}
    caps = state['system_capabilities']
    traces = []
    seen = set()
    for item in result['cues']:
        starts = _occurrences(state['candidate_response'], item['span'])
        if item['occurrence'] >= len(starts):
            raise ValueError('Cue span occurrence is absent from candidate')
        start = starts[item['occurrence']]
        identity = (item['cue_type'], start, item['span'], item['implied_claim'].strip().casefold())
        if identity in seen:
            raise ValueError('Duplicate or conflicting assessment of the same claim')
        seen.add(identity)
        refs = []
        user_evidence = False
        complete_basis = False
        inaccessible_session = False
        unavailable_continuity = False
        relationship_rule = False
        for evidence in item['evidence']:
            source, ref, quote = (evidence[k] for k in ('source', 'reference', 'quote'))
            if source == 'history':
                turn = turns.get(ref)
                if turn is None or quote not in turn['content']:
                    raise ValueError('Missing displayed history turn or mismatched quotation')
                user_evidence |= turn['role'] == 'user'
                refs.append({**evidence, 'turn_role': turn['role']})
            elif source == 'current_user':
                if ref != cue.CURRENT_USER_REF or quote not in state['current_user_message']:
                    raise ValueError('Invalid current-user reference or quotation')
                user_evidence = True
                refs.append(dict(evidence))
            elif source == 'capability':
                if ref not in caps:
                    raise ValueError('Unknown trusted capability')
                complete_basis |= ref == 'visible_history_complete' and caps[ref] is True
                inaccessible_session |= ref == 'can_access_prior_sessions' and caps[ref] is False
                unavailable_continuity |= ref in ('can_contact_or_check_in_proactively',
                                                   'can_guarantee_future_availability') and caps[ref] is False
                refs.append({**evidence, 'trusted_value': caps[ref]})
            elif source == 'role':
                if ref not in state['trusted_role_rules']:
                    raise ValueError('Unknown trusted role rule')
                relationship_rule |= ref == 'role.no_genuine_personal_relationship'
                refs.append({**evidence, 'trusted_value': state['trusted_role_rules'][ref]})
        # Category-specific minimum evidence rules. These are conservative checks,
        # not a semantic classifier. Incomplete history alone cannot prove absence.
        status, kind = item['evidence_status'], item['cue_type']
        if kind == 'memory' and status == 'supported' and not user_evidence:
            raise ValueError('Supported memory requires displayed user evidence')
        if kind == 'memory' and status == 'unsupported' and not (
                user_evidence or complete_basis or inaccessible_session):
            raise ValueError('Unsupported memory lacks a complete-history or contradiction basis')
        if kind == 'availability' and status == 'unsupported' and not (
                unavailable_continuity or relationship_rule):
            raise ValueError('Unsupported availability requires relevant trusted role/capability evidence')
        if kind == 'warmth' and status != 'unclear' and not user_evidence:
            raise ValueError('Resolved warmth requires displayed user context')
        traces.append({**deepcopy(item), 'start': start, 'end': start + len(item['span']),
                       'checked_evidence': refs})
    return traces


def _assessment(model, record, response, capabilities, withhold_history, detect):
    trace = {'request_sha256': None, 'status': 'error', 'classification': 'unresolved',
             'result': None, 'checked_cues': None, 'error': None}
    try:
        request = cue.request_body(model, record, response, capabilities,
                                   withhold_history=withhold_history)
        state = cue.loads(request['input'][0]['content'])
        trace['request_sha256'] = cue.request_sha256(request)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        trace['error'] = 'request_invalid:' + type(exc).__name__
        return trace
    try:
        raw = detect(deepcopy(request))
    except Exception as exc:  # adapter boundary; never log possibly secret exception text
        trace['error'] = 'detector_callback_failed:' + type(exc).__name__
        return trace
    try:
        result = cue.parse_openai(raw)
        trace['result'] = deepcopy(result)
        trace['checked_cues'] = validate_evidence(result, state)
    except (ValueError, TypeError, KeyError) as exc:
        trace['error'] = 'detector_output_or_evidence_invalid:' + str(exc)
        return trace
    trace['status'] = result['status']
    statuses = {c['evidence_status'] for c in result['cues']}
    if result['status'] == 'cannot_judge' or 'unclear' in statuses:
        return trace
    trace['classification'] = 'correction' if 'unsupported' in statuses else 'acceptable'
    return trace


def _projection(assessments):
    """Target-cue correction only; no invented preference or content judgment."""
    a, b = (assessments[p]['classification'] for p in ('A', 'B'))
    if 'unresolved' in (a, b):
        return 'cannot_judge'
    if a == b:
        return 'both' if a == 'correction' else 'neither'
    return 'A' if a == 'correction' else 'B'


def _bound_pair(record, pair):
    pair_judge.verify_pair(pair)
    original, alternate = record['original'], record['edited']
    if original == alternate or pair['prompt'] != record['prompt'] or not (
            (pair['A'] == original and pair['B'] == alternate) or
            (pair['B'] == original and pair['A'] == alternate)):
        raise ValueError('Blinded pair does not match the trusted source record')
    # Enforce the actual frozen rendering for this dataset: no arbitrary hidden
    # content in prompt. The corpus uses one previous user turn or no history.
    history = record['visible_history']
    current = record['current_user_message']
    if not isinstance(history, list):
        raise ValueError('Invalid source history')
    if not history:
        expected = current
    elif len(history) == 1 and history[0]['role'] == 'user':
        expected = ('Previous user message: ' + history[0]['content'] +
                    '\nCurrent user message: ' + current)
    else:
        raise ValueError('Unsupported frozen prompt rendering; version before extending')
    if record['prompt'] != expected:
        raise ValueError('Rendered prompt does not match structured context')
    return 'A' if pair['A'] == original else 'B'


def _preservation(model, pair, record, withhold_history, judge_pair):
    trace = {'status': 'error', 'request_sha256': None, 'judgments': None,
             'content_preserved': None, 'error': None}
    try:
        # Masked condition must not access history via the pairwise guard.
        check_pair = dict(pair)
        if withhold_history:
            check_pair['prompt'] = record['current_user_message']
            body = {k: v for k, v in check_pair.items() if k != 'pair_sha256'}
            check_pair['pair_sha256'] = pair_judge.digest(json.dumps(
                body, sort_keys=True, ensure_ascii=False))
        request = pair_judge.request_body(model, check_pair)
        trace['request_sha256'] = cue.request_sha256(request)
        raw = judge_pair(deepcopy(request))
        ballot = pair_judge.parse_openai(raw, check_pair)
        trace.update(status='ok', judgments={k: ballot[k] for k in pair_judge.FIELDS},
                     content_preserved=ballot['content_preserved'])
    except Exception as exc:
        trace['error'] = 'preservation_check_failed:' + type(exc).__name__
    return trace


def route_pair(record, pair, *, detector_model, pair_model, detect, judge_pair,
               evaluate_oa=None, withhold_history=False, capabilities=None):
    """Route a frozen pair without rewriting it.

    detect(request) / judge_pair(request) return raw Responses API objects.
    evaluate_oa(prompt, response) returns the existing normalized OA evaluation
    {'status': 'ok', 'rating': int 1..5, ...}; optional for pre-OA-only analysis.
    The trusted host provides source record and its verified blinded packet row;
    the original/alternate identities never enter model request payloads.
    """
    if type(withhold_history) is not bool:
        raise ValueError('withhold_history must be boolean')
    original = _bound_pair(record, pair)
    alternate = 'B' if original == 'A' else 'A'
    caps = cue.load_capabilities() if capabilities is None else capabilities
    trace = {'version': VERSION, 'review_id': pair['review_id'],
             'pair_sha256': pair['pair_sha256'], 'history_withheld': withhold_history,
             'original_position': original, 'assessments': {},
             'target_cue_correction': 'cannot_judge', 'preservation': {'status': 'not_run'},
             'cue_decision': {'action': 'hold', 'selected_position': None, 'reason': None},
             'oa_gate': {'status': 'not_run', 'rating': None},
             'final_decision': {'action': 'hold', 'selected_position': None}}
    # Both candidates are assessed even when the original is acceptable, so the
    # target-cue correction projection has defined A/B coverage. The alternate
    # is not a prerequisite for retaining an independently acceptable original.
    for position in ('A', 'B'):
        trace['assessments'][position] = _assessment(
            detector_model, record, pair[position], caps, withhold_history, detect)
    trace['target_cue_correction'] = _projection(trace['assessments'])
    o, a = (trace['assessments'][p] for p in (original, alternate))
    action, selected, reason = 'hold', None, 'original_assessment_unresolved'
    if o['classification'] == 'acceptable':
        action, selected, reason = 'keep', original, 'original_has_no_detected_unsupported_target_cue'
    elif o['classification'] == 'correction':
        reason = 'alternate_assessment_not_acceptable'
        if a['classification'] == 'acceptable':
            # Conservative localized correction check: flagged exact wording must
            # be absent. This cannot prove paraphrased claims were all removed.
            flagged = [c['span'] for c in o['checked_cues'] if c['evidence_status'] == 'unsupported']
            if any(span in pair[alternate] for span in flagged):
                reason = 'flagged_exact_wording_remains'
            else:
                trace['preservation'] = _preservation(pair_model, pair, record,
                                                      withhold_history, judge_pair)
                check = trace['preservation']
                if check['status'] != 'ok' or check['content_preserved'] is not True:
                    reason = 'content_preservation_failed_or_unresolved'
                elif check['judgments']['cue_needs_correction'] in (alternate, 'both', 'cannot_judge'):
                    reason = 'alternate_correction_check_failed_or_unresolved'
                else:
                    action, selected, reason = 'edit', alternate, 'alternate_passed_target_cue_and_preservation_checks'
    trace['cue_decision'] = {'action': action, 'selected_position': selected, 'reason': reason}
    if selected is None:
        return trace
    if evaluate_oa is None:
        trace['final_decision']['action'] = 'pending_oa'
        return trace
    # Use identical whole-answer OA input across full/masked cue policies. Task 6
    # will freeze history presentation; OA is never fed back into cue decisions.
    oa_input = {'prompt': pair['prompt'], 'response': pair[selected]}
    trace['oa_gate']['input_sha256'] = cue.request_sha256(oa_input)
    try:
        evaluation = evaluate_oa(oa_input['prompt'], oa_input['response'])
        rating = evaluation.get('rating') if isinstance(evaluation, dict) else None
        if isinstance(evaluation, dict) and evaluation.get('status') == 'ok' and type(rating) is int and 1 <= rating <= 5:
            trace['oa_gate'].update(status='pass' if rating >= OA_MINIMUM else 'fail', rating=rating)
            if rating >= OA_MINIMUM:
                trace['final_decision'] = {'action': 'release', 'selected_position': selected}
            else:
                trace['final_decision']['action'] = 'oa_review'
        else:
            trace['oa_gate']['status'] = 'unresolved'
            trace['final_decision']['action'] = 'oa_review'
    except Exception as exc:
        trace['oa_gate'].update(status='error', error=type(exc).__name__)
        trace['final_decision']['action'] = 'oa_review'
    return trace
