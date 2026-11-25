# Task 4 — Development dataset content review

**Related issue:** #1 — Build, annotate, and evaluate the cue-aware harness  
**Scope:** Content preservation, natural wording, and experimental quality control before blinded annotation.  
**Status:** Independent human review and coordinator sign-off recorded; approved dataset finalized and hash verified. Repository approval pending.

## 1. Objective

Task 4 checks whether the selected development response pairs provide a controlled comparison of the intended anthropomorphic cues. It does not determine which candidate is preferable, validate the proposed computational measure, or establish superiority over HumT/DumT. Those questions belong to subsequent evaluation.

## 2. Dataset and allocation

The source is `data/wording_pairs_v1.jsonl`. Task 3 selected four families per cue category through stratified random sampling without replacement using seed `20261123`, as documented in `data/development_split_v1.json`. All contexts and variants of a family remain together.

| Cue category | Families | Pairs | Candidate trials |
| --- | ---: | ---: | ---: |
| Memory | 4 | 8 | 16 |
| Relationship and availability | 4 | 4 | 8 |
| Ordinary warmth | 4 | 8 | 16 |
| Total | 12 | 20 | 40 |

The remaining 48 families (80 pairs) are reserved, not a finalized held-out evaluation set. No preference judgments or model scores were used to select the development families.

## 3. Review procedure

An AI-assisted preliminary content review identified six family-level wording corrections. Subsequent review added W001 to improve the relevance of shared advice. The resulting proposal was checked against the original subset and reviewed using the following criteria:

| ID | Criterion | Assessment standard |
| --- | --- | --- |
| C1 | Content preservation | Candidates provide equivalent practical advice and information. |
| C2 | Cue isolation | The intended cue is the primary meaningful difference. |
| C3 | Naturalness | Both candidates are fluent and reasonably natural. |
| C4 | Contextual validity | Histories establish the intended conditions without unintended assumptions. |
| C5 | Cross-context consistency | Candidate texts remain identical across sibling contexts; NA for single-context availability cases. |
| C6 | Relevance and completeness | Both candidates adequately address the request. |
| C7 | Safety preservation | Important safety guidance and boundaries are preserved. |

Ratings: P (pass), M (minor issue), F (material failure), CJ (cannot judge), NA (not applicable). Ratings are descriptive and are not averaged into a quality score. Intentional unsupported memory claims and relational promises are experimental stimuli, not verified capabilities or automatic QC failures.

The final content review record documents independent human review and coordinator sign-off, both dated 2026-11-25, with explicit approval of all 12 families against the proposal hash. Named approval records and individual assessments are retained privately; this public summary omits personal identifiers. The research team confirmed that the earlier AI-only label was a recording error.

## 4. Family-level decisions and change rationale

| Family | Decision | Rationale |
| --- | --- | --- |
| M006 | Approve revision | More faithful paraphrase of the visible-checklist preference. |
| M016 | Approve unchanged | Concrete-example advice and memory reference retained. |
| M018 | Approve revision | Reflect the stated benefit for managing chores rather than infer an effect on starting. |
| M019 | Approve unchanged | Email preference and practical recommendation preserved. |
| A003 | Approve revision | Make bounded assistance wording more natural. |
| A013 | Approve unchanged | Future check-in claim contrasted with bounded assistance; practical advice retained. |
| A018 | Approve unchanged | Continuing personal allegiance contrasted with bounded assistance. |
| A020 | Approve unchanged | Enduring loyalty and claimed close friendship contrasted with bounded assistance; no explicit guarantee of future availability. |
| W001 | Approve revision | Both candidates now ask directly about individual and joint counselling sessions. |
| W003 | Approve revision | Avoid assuming the transfer was unexpected. |
| W006 | Approve revision | Avoid assuming uncertainty in the practical context. |
| W013 | Approve revision | Avoid assuming first disclosure of childhood experiences. |

W001 is a documented shared-advice correction, not a cue-only edit. Both candidates use the same practical question: `You could ask, “How do you approach individual and joint sessions, and what would each involve?”` The original warmth acknowledgement remains unchanged. Both candidate texts are identical across the distressed and practical contexts.

All other corrections preserve the shared practical advice. A020 is a compound relational cue, not an isolated manipulation of friendship or loyalty. W013 has a minor shared pronoun ambiguity, retained because it does not materially compromise the comparison. The completed assessment uses NA under C5, not C6, for availability cases; any blank rubric template should use the same placement. No additional response changes are recommended.

## 5. Review outcome

| Metric | Result |
| --- | ---: |
| Families reviewed | 12 |
| Pairs reviewed | 20 |
| Candidate trials reviewed | 40 |
| Revised families | 7 |
| Unchanged families | 5 |
| Revised pairs | 13 |
| Unchanged pairs | 7 |
| Changed response fields | 15 |
| Rejected families | 0 |
| Mandatory further response revisions | 0 |

| Criterion-level rating | Count |
| --- | ---: |
| Pass | 134 |
| Minor issue | 2 |
| Fail | 0 |
| Cannot judge | 0 |
| Not applicable | 4 |
| Total | 140 |

The two minor ratings concern W013 naturalness in its two contexts. The four NA ratings concern C5 for the single-context availability cases. These counts summarize the supplied assessment, not inter-rater agreement or an experimental result.

## 6. Reproducibility and dataset integrity

Expected source SHA-256 (normalized LF line endings):

```text
adb0138c32a31247a7cb2932488ebc93688e9fc5c2dce57a32c19ac3301b0211
```

Reviewed proposal SHA-256 (exact bytes):

```text
e7a131c007c97e1de003f08a61f3744dca9f59c2c92ff4e1bc406c3e382faaa3
```

The supplied original, proposed and finalized JSONL files were checked directly. Replaying the documented changes reproduces the final parsed records exactly. All 20 pair IDs, histories, contexts and family assignments are preserved. There are 13 changed pairs and 15 changed response fields, with no changes to other fields. Both candidate texts remain identical across sibling contexts. The finalized JSONL is byte-for-byte identical to the proposal, and its SHA-256 matches the final review record and recorded approval. The public audit record is `data/development_content_review.json` (personal identifiers and free-text approval notes removed). The recorded approvals establish the audit trail; they are not independently authenticated by this file check.

Preparation script: `prepare_reviewed_dev_v2.py`. Run from the repository root, using a new output directory for each execution:

```powershell
python prepare_reviewed_dev_v2.py --out-dir private/task4-reproduction
```

After genuine reviewer and coordinator approvals have been recorded against the exact proposal hash:

```powershell
python prepare_reviewed_dev_v2.py --apply-proposed-edits --approval-file private/task4-review/approval_completed.json --out-dir private/task4-final-reproduction
Get-FileHash private/task4-final-reproduction/development_reviewed.jsonl -Algorithm SHA256
```

The script checks source integrity, the selected family membership, context consistency and explicit approval of all families. The selected IDs are encoded in the script, so check them against the Task 3 manifest when reproducing the dataset. The resulting reviewed dataset should match the proposal hash above. Keep private approval files outside the public commit. The intended public reviewed dataset is `data/development_reviewed.jsonl`.

## 7. Methodological limitations

- Memory manipulates factual grounding and personalization as well as anthropomorphic wording; preferences cannot be attributed exclusively to anthropomorphism.
- Memory and warmth contain matched contexts and permit exploratory cue-by-context comparisons. Relationship and availability families have only one context each and cannot establish a cue-by-context interaction on their own.
- A020 combines enduring loyalty and claimed close friendship, so their individual effects cannot be separated.
- Practical histories do not explicitly express distress; they do not establish emotional neutrality.
- This small development cohort is not evidence of generalizability, computational measure validity, or superiority over any baseline.

## 8. Handoff to Task 5

After repository review and merge, use the frozen reviewed dataset to prepare blinded, randomized A/B packets. Hide method labels, cue labels, source identifiers, model scores and content-review decisions from annotators. Keep the mapping key and approval records private. Plan three independent annotators for the 20 pairs (60 pair judgments), allowing ties and cannot-judge responses. Preserve original ratings before disagreement discussion. Formal preference annotations are not part of Task 4.

## 9. Pull request acceptance checklist

- [ ] Task 3 allocation is available in the target branch (or the dependency is explicitly recorded).
- [ ] Public reviewed JSONL matches the exact approved proposal hash.
- [ ] Reproducibility script and review documentation are included.
- [ ] A020 documentation reflects enduring loyalty and claimed close friendship.
- [ ] Private approval records are retained and no reviewer identifiers are disclosed without authorization.
- [ ] Repository reviewer approves the Task 4 changes before merge.
