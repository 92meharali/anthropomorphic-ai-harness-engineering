# Harness Task 3 — Evidence validation and deterministic routing

**Related:** Issue #1, Build the Harness. Depends on the new Task 2 branch `harness-v2-task2-cue-output`, which inherits Task 1. Development implementation; not yet a frozen held-out protocol.

## Objective

Validate the exact evidence references emitted by Task 2 and implement deterministic `keep`, `edit`, and `hold` decisions. Record the cue decision separately from the final whole-answer Overall Appropriateness (OA) gate. Work on fixed response pairs; never generate a rewrite in this experiment.

The original `data/REVIEWER_GUIDE.md` remains the authoritative rubric for direct human–LLM comparison. `rubric/cue_rubric_v1.md` operationalizes cue assessment for this policy. Preference, correction and content preservation remain separate questions. Task 3 does not redefine their labels, change any existing annotation or modify the OA protocol.

## Files

- `evaluation/cue_routing.py`: evidence validation, fixed-pair controller, shared-rubric edit guard, independent OA disposition, and structured trace.
- `evaluation/test_cue_routing.py`: 19 offline regression tests with synthetic detector, pair-judge and OA outputs.
- `docs/Build the harness mds/TASK3_EVIDENCE_ROUTING.md`: this implementation contract.

No old harness branch is needed. Task 1 and Task 2 files are inherited unchanged. No third-party Python dependency is introduced.

## Trusted inputs and blinding

The host supplies the approved source record and the original blinded packet row. The controller validates the canonical pair SHA-256 through `pair_judge.verify_pair`, checks that the two candidates and rendered prompt exactly match the trusted source, and finds the original position by text equality. The caller must load the frozen cohort and the matching coordinator key; a self-consistent hash is not authentication of cohort membership. Current prompt rendering is restricted to the actual dataset format (one preceding user turn or no history); an unsupported format fails before inference. Later extensions require a versioned rendering contract.

Trusted capability defaults come from `cue_output.load_capabilities()`. Explicit capability overrides are for trusted host configuration or tests, not candidate input. Each detector request is built with Task 2's allowlist and its request hash is retained locally. The detector receives one answer and permitted context only. No source labels, original/edited identities, human ratings, condition labels or scores enter the model request. Both candidates are assessed in A/B order to support a target-cue correction projection.

Withheld history is removed from the detector's actual input and completeness is marked false. The edit guard also receives only the current user message in this condition, not the frozen full prompt. The full prompt remains available to the separate OA gate after the pre-OA decision, as a common input across both cue-policy conditions; Task 6 must finalize that presentation before held-out evaluation. There is no feedback from OA into the pre-OA decision.

## Mechanical evidence validation

`validate_evidence(result, state)` consumes the structured Task 2 result and the exact host-built state used for that request. It validates the original structure again and checks that the trusted state matches the Task 2 state contract.

| Check | Rule |
| --- | --- |
| Candidate span | Must exist exactly at the declared zero-based occurrence; overlapping occurrences count. Store start and end-exclusive Python character offsets. |
| History evidence | Referenced turn must be present in the actual displayed history, and quote must be an exact substring of that turn. Record role. |
| Current-user evidence | Reference must be `current_user_message`; quote must occur in the current message. |
| Capability evidence | Reference must be an actual host-supplied capability key; quote must be null. Record its trusted value. |
| Role evidence | Reference must be an actual trusted role-rule ID; quote must be null. Record its trusted value. |
| Duplicate or conflicting claim | Repeated category/span/occurrence/normalized implied-claim identity is rejected. Separate claims may legitimately share a span. |
| Supported memory | Requires a displayed user-source quotation, not solely a prior assistant assertion or capability key. |
| Unsupported memory | Requires displayed user evidence, complete-history basis set true, or inaccessible-prior-session capability set false. Missing history alone does not establish absence. |
| Unsupported availability | Requires the relevant negative trusted proactive-contact/future-availability capability or the trusted relationship role rule. |
| Resolved warmth | Requires displayed user context. |

These category-specific minimum checks conservatively operationalize the rubric. They cannot determine whether a real quotation entails the implied claim, whether a cited unavailable capability is relevant to the exact wording, or whether the detector omitted a cue. The model's semantic assessment is still a fallible judgment. `unclear` is distinct from an invalid reference or provider failure. Any cited reference must be valid even on an unclear cue.

## Deterministic fixed-pair policy

Each candidate has an assessment classification: `acceptable` (valid successful assessment with no unsupported or unclear target cue), `correction` (valid assessment with at least one unsupported cue and no unclear cue), or `unresolved` (any unclear cue, whole-assessment abstention, invalid output, reference failure or adapter error).

| Original assessment | Alternate / checks | Pre-OA cue action |
| --- | --- | --- |
| Acceptable | Alternate not needed for retention | Keep original |
| Unresolved | Any | Hold; no selected answer |
| Correction | Alternate unresolved or also needs correction | Hold |
| Correction | Alternate acceptable but flagged exact wording still present | Hold |
| Correction | Alternate acceptable, flagged wording absent, preservation false/null/error | Hold |
| Correction | Preservation true, but shared Q2 flags alternate/both or abstains | Hold |
| Correction | Alternate acceptable, flagged wording absent, preservation true and no alternate correction veto | Edit: select the frozen alternate |

The edit guard uses the Task 1 pairwise evaluator with the unchanged reviewer guide. Q3 must be true; Q2 is a conservative additional veto when it flags the alternate, both answers, or cannot judge. Q1 is recorded but not used to choose an answer. A pairwise Q2 judgment of neither is not grounds to override a valid operational correction finding on the original. This is an explicit development policy choice; report the extra pairwise call/cost and freeze the guard before held-out evaluation. The direct LLM comparator is a separate evaluation run, not a reference ballot or a source of ground truth. The guard shares the same rubric, so its contribution to the structured policy should not be represented as independent evidence of model accuracy.

The flagged-span removal check plus a fresh independent assessment of the alternate and the shared-rubric guard are practical safeguards, not formal proof that paraphrased claims have been eliminated or advice preserved. The exact-span check can conservatively hold a safe contextual reuse. Do not optimize these rules on the held-out set.

If an independently acceptable original is retained, alternate failure does not prevent retention, since the alternate is not used. It does make the pair-level correction projection unresolved. An unresolved original never routes to edit merely because another answer looks acceptable. Human-like style, HumT scores and preference for another answer are not intervention triggers.

## Pair-level output and OA separation

`target_cue_correction` projects the two candidate classifications into `A`, `B`, `both`, `neither` or `cannot_judge`. Any unresolved assessment produces `cannot_judge`; errors remain explicit in the underlying trace. This prediction covers the detector's target categories, not all concerns in the broader human correction question. It is not a human ballot; the controller does not invent pairwise preference or preservation judgments for cases where the pair guard was not called.

The controller records `cue_decision` first. On a selected candidate, an optional OA adapter evaluates the whole answer using the pre-existing OA threshold (integer rating at least 4, status `ok`). A passing gate produces `release`; a failing, unresolved or failed gate produces `oa_review` without a released candidate. An omitted adapter produces `pending_oa`. A pre-OA hold does not invoke OA. The original cue decision is never changed by OA. No second candidate is selected based on OA, and no additional revision is generated. The existing `evaluation/controller.py` and `rubric/oa_protocol.json` are unchanged; integration with the full OA runner and fixed presentation remains follow-on work.

The trace contains review ID, frozen pair hash, host original position, context condition, both detector request hashes/results/reference checks, target correction prediction, optional guard request hash and judgments, pre-OA decision, OA input hash and normalized disposition, and final decision. Adapter exceptions are captured as errors rather than valid no-cue assessments. Trace data can contain corpus excerpts and method identities; keep raw traces and model logs private. Request hashes bind the constructed payload locally, not provider authenticity: the host adapters must return the response to the exact request and manage real transport, model pinning, persistence, latency, usage and replay identity. No live calls are made by this module.

### Offline API usage

```python
from evaluation.cue_routing import route_pair

trace = route_pair(
    source_record, blinded_packet_row,
    detector_model=detector_model_id,
    pair_model=pair_model_id,
    detect=detector_adapter,      # request dict -> raw Responses API object
    judge_pair=pair_adapter,     # request dict -> raw Responses API object
    evaluate_oa=oa_adapter,      # (prompt, response) -> normalized OA result
    withhold_history=False,
)
print(trace['cue_decision'])
print(trace['oa_gate'])
print(trace['final_decision'])
```

The variable names above describe required caller-supplied objects, not existing configured live adapters. Use `evaluate_oa=None` for pre-OA-only work. This is an offline controller with explicit callback boundaries, not a complete CLI or a live provider runner.

## Verification

The Task 1 and Task 2 implementation files and operational rubric from the verified local packages were matched to the corresponding GitHub blobs on `harness-v2-task2-cue-output`. The reviewer guide and approved development data also matched the previously inspected main-branch blobs. The original Task 3 branch was not used.

Preparation tests executed in a temporary combined Task 1–3 tree: six Task 1 tests, ten Task 2 tests and nineteen new Task 3 tests (35 total; all passed). Coverage includes exact and overlapping spans, Unicode offsets, invalid references, missing/masked history, assistant-only memory evidence, trusted role/capability checks, duplicate assessments, unresolved and conflicting cues, preserved/failed content, alternate correction veto, retained flagged wording, malformed provider replies, adapter failure, original position reversal, and independent OA dispositions. These are synthetic regression tests, not real model assessments.

An additional offline replay joined all 20 approved development pairs with the original frozen packet and coordinator key. All pair hashes, rendered contexts and original/alternate mappings were checked by the controller and replay assertions. In both full and masked conditions, synthetic successful no-cue detector responses and synthetic OA ratings of 4 exercised 40 routes, 80 detector requests and 40 OA callback checks. These stubs are plumbing tests, not predictions for those cases; no empirical keep/edit distribution or human–LLM agreement is reported. No human ratings were modified or used as controller inputs.

Run from the repository root, on the new stacked Task 3 branch:

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest evaluation.test_cue_routing -v
python -m unittest discover -v
```

Expected: 19 new tests and 40 total tests if the five existing main-branch tests and 16 Task 1–2 tests are present. The 35 new-harness tests were run in preparation; the full repository suite still requires local verification.

## Acceptance and next step

The evidence/reference validation, fixed-pair routing, content-preservation guard and separate OA trace are implemented for Task 3. Task 4 must build systematic fixtures for the cue families and semantic/ablation edge cases beyond these controller tests. Live provider integration, model pinning, exact OA history presentation, evaluation against eligible independent annotations, and final held-out comparisons remain outstanding. No comparative performance or human-provenance claim follows from this implementation.
