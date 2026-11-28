# Generated-rewrite results

The controlled follow-up tested 33 previously flagged originals from the [wording-v1 fixed-pair study](WORDING_RESULTS.md). Each draft received one generic and one cue-specific rewrite from the same generator, `gpt-6.2-sol`. Both calls used the same draft, conversation, instructions and settings. The cue-specific call also received the unsupported span and validated evidence saved by the harness. All 66 calls completed and passed replay. All 33 pairs entered blinded review.

Three independent reviewers rated both rewrites on all 33 cases. The coordinator confirmed that the sealed replacement workbooks contained the original ratings, made before reviewers saw the labeled results or one another's ratings. The corrected collection supplies all 99 case ballots. The earlier mistaken submission is archived separately.

## Human-rated outcomes

A reviewer marked a rewrite usable when it corrected the cue, preserved useful advice and appropriate warmth, and earned overall appropriateness (OA) of at least 4 out of 5. Two matching reviewer judgments established the outcome for each rewrite.

| Outcome | Generic rewrite | Cue-specific rewrite |
|---|---:|---:|
| Corrected the cue | 33/33 | 33/33 |
| Preserved useful advice | 33/33 | 33/33 |
| Preserved appropriate warmth | 33/33 | 33/33 |
| Passed OA | 31/33 | 33/33 |
| **Usable on all four checks** | **31/33 (93.9%)** | **33/33 (100.0%)** |

Both rewrites passed on 31 drafts. The cue-specific rewrite alone passed on two. There were zero generic-only passes, joint failures, or unresolved pairs. The two differences came from the whole-answer OA check. Cue correction, advice and warmth passed for both arms on every case.

The paired increase was **6.1 percentage points**, with a descriptive **95% prompt-family bootstrap interval of 0.0 to 15.2 points** from 10,000 draws over 33 families. All flagged drafts had two valid rewrites with resolved ratings, so the all-flagged sensitivity rates match the primary rates. Reviewers agreed on the usable outcome and OA pass decision for all 198 comparable reviewer pairs across the candidate answers. Exact OA scores matched on 174/198 reviewer pairs (87.9%).

## Usage and interpretation

| Arm | Calls | Input tokens | Output tokens | Total tokens | Summed request latency |
|---|---:|---:|---:|---:|---:|
| Generic | 33 | 10,073 | 2,599 | 12,672 | 83.1 s |
| Cue-specific | 33 | 14,596 | 2,772 | 17,368 | 80.0 s |

Cue-specific feedback used 37.1% more tokens. The result suggests a possible improvement in whole-answer quality on these controlled drafts. It rests on two cases and the interval includes zero. The comparison estimates rewrite quality on previously flagged authored drafts. A broader claim about automatic release or fresh model-generated failures needs a separate test.

## Reproduce from the private archive

Use the original freeze, packet and **corrected** collection seals. The command replays the run, verifies the submitted workbooks and computes aggregate results without API calls. Install the pinned dependency in `requirements-rewrite-review.txt` for Excel verification.

```sh
python -m evaluation.rewrite_report \
  --study private/issue26-frozen --run private/issue26-rewrites \
  --packet private/issue26-review-packet --collection private/issue26-corrected-ballots \
  --freeze-sha256 "$freeze" --packet-sha256 "$packet" --collection-sha256 "$collection" \
  --out private/issue26-report
```

Keep original workbooks, per-case decisions and provider outputs in restricted storage.
