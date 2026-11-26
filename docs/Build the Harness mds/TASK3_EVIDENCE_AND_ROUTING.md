# Build the Harness — Task 3: Evidence validation and deterministic routing

**Roadmap:** Issue #1. **Status:** Development implementation; 10 new offline controller tests and nine Task 2 contract tests passed together. Full repository regression testing and review remain pending. No live inference or held-out evaluation is claimed.

## 1. Objective and scope

Implement the evidence and action policy in `rubric/cue_rubric_v1.md`, consuming the structured output contract in `evaluation/cue_output.py`. The first experiment remains fixed-candidate selection: an edit selects an already prepared alternate; it does not generate a rewrite. The controller never chooses a candidate merely because it has a lower HumT score or is preferred by a reviewer. The frozen whole-answer OA evaluator remains a separate gate. No change is made to the rubric, existing OA evaluator, dataset manifest, development annotations or split.

## 2. Mechanical evidence checks

`validate_evidence(state, result)` first checks the Task 2 output structure. It resolves each cue span and zero-based occurrence against the exact candidate text, counting overlapping substring occurrences. The resulting offsets are zero-based Python Unicode code-point offsets, with the end exclusive. It checks each history reference and exact quotation against the actual visible turn, and each current-user reference and quotation against the current message. It resolves capability keys and role-rule IDs from the host request state, never from candidate text or detector assertions. Unknown references, missing quotes and nonexistent spans are invalid.

For memory, the completeness flag alone cannot establish support. If the history is incomplete, a claim of absence based solely on completeness cannot establish non-support. Supported memory requires conversation evidence. A user disclosure must be assessed against user-origin evidence rather than assumed true because an earlier assistant asserted it; Task 2 prompts this semantic judgment. A valid substring or existing key does **not** establish entailment, relevance, contradiction, correctness of the cue category, or detector recall. These remain empirical questions. The checker is not a semantic theorem prover.

`route` builds the original detector request itself, checks the result against that exact request state, and derives the alternate request from the same state with only the candidate response changed. The history-withheld setting is inherited by all cue and verification stages, including the OA callback's visible state. No hidden prior turns, dataset labels, annotations, source identities or OA/HumT scores are included in the detector payloads. The pair verifier necessarily receives both candidate texts and the flagged claims, but not human reference labels or scores. Task 6 must separately define the final OA presentation and fair baseline inputs.

## 3. Deterministic pre-OA policy

| Condition (in order) | Action |
| --- | --- |
| Detector refusal, failure, abstention, invalid structure or invalid references | `hold` |
| Any material cue is `unclear` | `hold`, even if another cue is unsupported |
| All cues supported, or successful detection with no target cues | `keep` original |
| At least one unsupported cue, no unresolved checks | Assess the fixed alternate |
| Alternate missing/identical, detector failure, invalid evidence, unsupported or unclear alternate cue | `hold` |
| All alternate verification checks pass | `edit` (select alternate) |
| Any verification fails, is unclear, malformed or unavailable | `hold` |

The alternate has its own blinded detector pass. A separate structured verifier request then checks (i) all flagged claims corrected, (ii) no new unsupported target claim, (iii) preservation of practical advice, important facts, safety guidance and caveats, and (iv) localized changes with unrelated content intact. All four statuses must be `pass`. `fail` or `unclear` never permits an edit. This verification is a semantic model assessment, not human ground truth; no model or verifier accuracy is claimed here. The text diff is an audit aid, not proof of preservation. The verifier uses the same model as the detector by default; callers may explicitly specify a different model before freezing study settings. This is an implementation choice, not a frozen experimental configuration.

## 4. Decision trace and independent OA gate

`route` returns a JSON-serializable trace. The caller can persist it as a private JSONL record; there is no automatic public logging. `original_detection` and `alternate_detection` contain request/state hashes, structured judgments and resolved reference checks with offsets. `verification` includes its request hash and check statuses. `text_changes` contains diff offsets. `cue_decision` records the pre-OA action, reason code and selected candidate identity (`original`, `alternate`, or null). `oa` separately records the existing evaluator result and disposition; `final_selected` is null unless the OA gate passes. These are candidate identities, not response strings.

The optional host callback `evaluate_oa(state)` must evaluate exactly the selected candidate under the frozen OA protocol, using the subsequently agreed context presentation. A valid integer OA rating of 4 or 5 passes; 1–3 gives `requires_revision`; an unresolved or failed OA evaluation gives `hold`. If the pre-OA decision is `hold`, the OA callback is not invoked. If no OA callback is supplied, the OA disposition is `not_run` and no final answer is selected. An OA failure cannot overwrite the pre-OA cue decision. For this fixed-candidate experiment, `requires_revision` is a recorded referral to the existing general revision path, not permission to generate another response or silently fall back to the other candidate. The later generation experiment must enforce the existing one-revision budget.

The host controls model transport, private raw request/response logging, cost and latency collection, and research split access. `detect(request)` and `verify(request)` return raw OpenAI Responses API objects. A host transport exception is recorded by error type and produces hold, not a successful empty result. The controller does not perform API calls itself, retry automatically, or select an unverified alternate. Invalid initial host configuration/request construction raises rather than being misreported as a model judgment.

## 5. Offline reproduction

From the repository root, after Task 1 and Task 2 are merged:

```powershell
python -m unittest evaluation.test_cue_controller -v
python -m unittest evaluation.test_cue_controller evaluation.test_cue_output -v
python -m unittest discover -v
```

Expected counts: 10 new Task 3 tests, 19 Task 2+3 tests, 24 total if the original five tests are unchanged. The first two scopes were run successfully in an isolated working directory. The final full-repository command is for local confirmation. Test callbacks are synthetic, not API results or new human judgments.

Example of calling the controller with a synthetic no-cue detector and a synthetic OA pass:

```python
import json
from evaluation.cue_output import load_capabilities
from evaluation.cue_controller import route

record = {'current_user_message': 'How do I begin?', 'visible_history': []}

def detect(request):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps({'status': 'ok',
            'reason': 'No target cue in this synthetic example.', 'cues': []})}]}]}

def verify(request):
    raise AssertionError('No edit should be attempted')

trace = route(record, 'Write down one step.', 'Make a list.', load_capabilities(),
              model='example-model', detect=detect, verify=verify,
              evaluate_oa=lambda state: {'status': 'ok', 'rating': 4})
print(json.dumps(trace, indent=2))
```

The result has `cue_decision.action=keep`, `oa.status=pass`, and `final_selected=original`. This is a simulated behavior check, not model evaluation. Persist traces only in a private/ignored run directory; the trace contains candidate cue text and evidence quotes. Do not commit API credentials, private outputs, reviewer records or held-out material.

## 6. Deliverables and handoff

- `evaluation/cue_controller.py`: reference checks, fixed-pair routing, verification request/parser and separate OA disposition.
- `evaluation/test_cue_controller.py`: ten controller contract tests covering exact occurrences, invalid references, trusted values, keep/edit/hold, uncertainty precedence, alternate verification, errors and OA separation.
- `docs/Build the Harness mds/TASK3_EVIDENCE_AND_ROUTING.md`: this report.

Task 4 expands these unit tests into explicit regression fixtures covering the approved cue examples and damaging edits. Task 5 pins HumT; Task 6 freezes context presentation for OA. Do not tune on reserved families or claim comparative performance based on these offline tests. Semantic verifier requirements and model-call cost (one detector call for a keep; up to two detector calls plus one verifier call for an edit attempt; optional OA call additional) must be included when finalizing the experimental comparison.
