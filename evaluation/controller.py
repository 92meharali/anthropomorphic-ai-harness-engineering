"""Offline routing for a single evaluator-guided revision."""


def _score(evaluation):
    rating = evaluation.get('rating')
    if evaluation.get('status') == 'ok' and type(rating) is int and 1 <= rating <= 5:
        return rating
    return None


def route(prompt, draft, *, evaluate, revise):
    """Callbacks evaluate(prompt, response) and revise(prompt, draft, reason).

    Keep both candidates and evaluations for later human review. A missing
    response or unresolved evaluation produces no selected candidate.
    """
    initial = evaluate(prompt, draft)
    outcome = {'draft': draft, 'initial_evaluation': initial, 'revision': None,
               'revision_evaluation': None, 'selected': None, 'action': 'review'}
    score = _score(initial)
    if score is None:
        return outcome
    if score >= 4:
        return {**outcome, 'selected': draft, 'action': 'keep_original'}

    revision = revise(prompt, draft, initial.get('reason'))
    if not isinstance(revision, str) or not revision.strip():
        return outcome
    final = evaluate(prompt, revision)
    outcome.update(revision=revision, revision_evaluation=final)
    score = _score(final)
    if score is not None and score >= 4:
        outcome.update(selected=revision, action='use_revision')
    return outcome
