# Task 7 — Annotation agreement and disagreement review

**Related issue:** #1 — Build, annotate, and evaluate the cue-aware harness.

**Status:** Computational analysis completed. The coordinator's local execution reproduced the previously inspected aggregate results, reporting two disagreements. Original judgments are retained. Actual reviewer discussion has not been performed or documented in the supplied evidence; no human adjudication is claimed.

## 1. Objective and scope

Task 7 examines agreement and disagreement across the three submitted Task 6 annotation workbooks. It quantifies consistency, identifies conflicting judgments, and documents the distinction between contextual wording preference and wording that warrants correction. It does not change the frozen cases, candidate wording, randomized A/B assignments or original ratings, and it does not evaluate HumT, OA or the proposed harness against one another.

The development set contains 12 families, 20 response pairs and 40 candidate responses. Three submitted ballots contain 60 pair judgments and 180 individual question responses. Independent human provenance is a separate collection requirement; the technical validation and agreement analysis do not establish that the judgments were produced independently by humans.

## 2. Inputs and integrity checks

The analysis utility `analyze_task7.py` reads `R01.jsonl`, `R02.jsonl`, `R03.jsonl` and `validation.json` from the Task 6 validated output directory. It requires a successful technical validation record and checks each ballot's SHA-256 against the recorded output hash. It verifies matching case IDs and pair hashes across the three ballots, 20 distinct cases, the expected fields, and allowed judgment values. Original ballots are read without modification. Explicit ties, cannot-judge responses and uncertain content-preservation responses remain distinct values.

The analysis is descriptive and uses the paired case as the unit of agreement. Sibling contexts share response families; the 20 cases must not be treated as independent samples for confirmatory inference.

## 3. Agreement methodology

For each of the three nominal judgment dimensions:

- **Unanimous agreement:** the proportion of cases for which all three reviewers select the same label.
- **Observed pairwise agreement:** the proportion of matching reviewer pairs, averaged across the 20 cases. Each case contributes three reviewer pairs.
- **Expected agreement:** the sum of squared pooled category proportions.
- **Fleiss' kappa:** `(observed agreement - expected agreement) / (1 - expected agreement)`. If expected agreement is one, kappa is undefined and is recorded as JSON `null`.

Kappa is calculated separately for each question. A preference tie is a substantive label. The combined unanimity count across questions is descriptive, not a pooled reliability coefficient. No confidence intervals or population-level inference are claimed for this small development sample.

A computational majority is defined as at least two of the three reviewers selecting the same label. Majority summaries are kept separate from individual ratings and are not adjudicated human labels. A majority selecting `tie` represents an explicit preference tie, not a failure to obtain a majority.

## 4. Results

The coordinator's local PowerShell output confirms the following results and matches the earlier offline aggregate analysis.

| Judgment | Unanimous cases | Unanimous agreement | Observed pairwise agreement | Expected agreement | Fleiss' kappa |
| --- | ---: | ---: | ---: | ---: | ---: |
| Wording preference | 18/20 | 90% | 93.33% | 0.587222 | 0.838493 |
| Need for correction | 20/20 | 100% | 100% | 0.485000 | 1.000000 |
| Content preservation | 20/20 | 100% | 100% | 1.000000 | Undefined |

Overall, 58 of 60 case-question combinations are unanimous (96.67%). Two combinations contain disagreements, both in wording preference. All 60 content-preservation judgments are `true`. The corresponding kappa is undefined because there is no category variation; it must not be reported as zero or one.

### Rating distributions

| Judgment | Label counts (60 ratings per question) |
| --- | --- |
| Preference | A: 13; B: 44; tie: 3; cannot_judge: 0 |
| Need for correction | A: 21; B: 3; both: 0; neither: 36; cannot_judge: 0 |
| Content preservation | true: 60; false: 0; null: 0 |

Eight cases unanimously identify one candidate for meaningful wording correction; twelve unanimously identify neither. A and B are randomized presentation labels and must not be interpreted as method identities. These results do not establish the validity of a computational measure or demonstrate superiority over a baseline.

## 5. Disagreement register and analytical review

The earlier inspected case-level outputs identify the following two preference disagreements. The local terminal output confirms the count and aggregate statistics, but does not display case-level rows. Before publication, compare the locally generated `disagreements.json` against this table and update it if necessary. The published local JSON files are the authoritative computational output for this run.

| Case | R01 | R02 | R03 | Computed majority | Human adjudication |
| --- | --- | --- | --- | --- | --- |
| W0011 | A | tie | tie | tie (2/3) | Not performed |
| W0019 | B | B | tie | B (2/3) | Not performed |

Both cases have unanimous `neither` correction judgments and `true` content-preservation judgments in the inspected snapshot.

### W0011 — Preparing to discuss childhood experiences

The preceding message expresses a practical objective: preparing a brief appointment note. Answer A gives direct practical advice. Answer B retains that advice and adds an ordinary acknowledgement that discussing childhood experiences can feel difficult. The preference disagreement is consistent with a trade-off between directness and contextual warmth. The sensitive topic can make acknowledgement reasonable even without an explicit statement of distress.

### W0019 — Transfer to another counsellor

The preceding message concerns arranging the next appointment. Answer A acknowledges that changing counsellors can feel unsettling and provides practical advice; Answer B provides the practical advice directly. The preference disagreement is consistent with differing assessments of the value of ordinary acknowledgement in this practical context.

These explanations are an AI-assisted analytical interpretation of the displayed cases and original ratings, not statements attributed to the reviewers. Actual reasons expressed by reviewers are not available. The original disagreement is retained in both cases. No ratings have been overwritten, no consensus has been fabricated, and no adjudicated labels have been assigned.

## 6. Implications for the research framework

The distinction between wording preference and need for correction is important for context-aware regulation. A less preferred answer does not necessarily warrant intervention. In the two inspected disagreements, reviewers differ on preference while agreeing that neither answer needs correction and the practical content is preserved. This motivates keeping preference and correction decisions separate when refining the rubric or regulation policy.

These observations are development-stage evidence only. High agreement is not proof of independence, validity or generalizability. Any final rubric or policy changes should be frozen before held-out evaluation; reserve families should not be used for iterative development. Claims about perceived humanness or relationship require an appropriate separate blinded measurement task if pursued.

## 7. Reproduction and data handling

Run the script with the local validated ballots:

    python analyze_task7.py --validated private/task6-human-annotations/validated --out private/task7-disagreement

Retain the complete output in restricted storage. The repository contains the aggregate agreement report. Individual votes and case-level majority outputs remain in the restricted study record. Preserve original submissions and record any later discussion or adjudication separately.

## 9. Completion and handoff

- Original ratings preserved and input integrity checked: completed by the analysis workflow.
- Agreement calculations and disagreement identification: completed; local aggregate results reproduced.
- Case-level analytical review: prepared; compare the local disagreement register with Section 5 before publication.
- Human provenance: not verified by this analysis; retain accurate collection records.
- Actual reviewer discussion: not performed in the supplied evidence. Document any genuine discussion separately, including whether reviewers retain their judgments or adopt a separate adjudicated label. Do not mark this criterion complete solely on the basis of the computational review.
- Repository tests, publication checks and pull request approval: to be confirmed locally.

The computational outputs may be submitted for review now. Final completion of any required independent-human and human disagreement-review criteria depends on the actual research records. The next research phase should use an eligible development reference, finalize the rubric and policy, and plan the held-out evaluation before making comparative claims.
