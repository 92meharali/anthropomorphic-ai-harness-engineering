# Task 6 — Annotation collection and validation

Related issue: #1 — Build, annotate, and evaluate the cue-aware harness.

**Status:** Three submitted workbooks technically validated and converted. Eligibility for independent-human evaluation is a separate coordinator responsibility; technical validation does not establish provenance. The coordinator describes the replacement submissions as original human annotations, but independent completion without AI assistance has not been verified by this offline review.

## Scope and collection format

The frozen Task 5 study contains 12 development families and 20 pairs (40 candidate responses). Three workbooks labeled R01, R02 and R03 were supplied for this inspection. Each contains the three approved judgments per case: wording preference, need for correction, and preservation of advice, facts and caveats. The Excel interface puts the original context and both answers beside the judgment fields, with dropdown choices and an internal ballot. No additional rating dimensions are introduced. No responses or judgments were generated or modified during conversion.

The submitted workbooks are the replacement originals supplied for review; the earlier file set is superseded for this analysis and must not be mixed into the current set. No AI draft notice is present in the four worksheets of any current submission. Absence of such a notice is not proof of human authorship. The coordinator must retain an accurate provenance record (including any AI involvement, shared assistance or protocol deviations) and confirm independent completion and applicable consent requirements before treating the data as an eligible human reference.

## Validation procedure

`validate_task6.py` is a read-only, standard-library Python utility. It compares the source dataset, review packet and pair key against the relevant manifest hashes, recomputes all canonical pair hashes, and checks source coverage, context and A/B mappings. It reads actual workbook cells rather than trusting the completion display, checks embedded IDs (the R01 layout uses row 3; R02 and R03 use row 4), compares each displayed case with the frozen packet, and checks the ballot metadata and cached judgment values. Visible selections are converted to the approved technical labels, including JSON booleans or null for content preservation. It rejects unexpected sheets, duplicate or missing cases, invalid choices, conflicting IDs and altered displayed cases. Input and output hashes are recorded in a private validation report; output directories must not already exist.

| Check | Result |
| --- | --- |
| Source, review packet and pair key byte hashes | Match frozen manifest |
| Canonical case hashes | 20/20 match |
| Workbook IDs | 3/3 match |
| Displayed cases and answer positions | 60/60 match |
| Completed pair judgments | 60/60 |
| Individual question responses | 180/180 valid |
| Internal ballot cached values | 180/180 match converted selections |
| Unexpected worksheets | None |
| Independent human provenance | Not established by technical checks |

The three JSONL files use `review_id`, `pair_sha256`, `preference`, `cue_needs_correction`, and `content_preserved`, as specified in the supplied reviewer guide. This is a guide-compatible export; the live repository's analysis implementation was not accessible in this offline review, so full end-to-end harness compatibility remains to be checked locally. The original frozen protocol and OA input files were not available for this inspection; their hashes and model scoring are outside this validation's scope.

## Reproduction (PowerShell, repository root)

The blank template is located at `data/annotation/annotator/Development_Annotation_Sheet.xlsx`. Place only the three current completed workbooks in `data/annotation/annotator/completed/` with their original filenames. Retain the original submissions separately and preserve their exact bytes. If publication requires metadata redaction, keep the unmodified originals privately, document the redaction, and revalidate the publication copies. Run:

```powershell
$env:PYTHONUTF8 = "1"
python validate_task6.py --study private/task5-study-v1 --source data/development_reviewed.jsonl --raw data/annotation/annotator/completed --out private/task6-human-annotations/validated
```

Expected: three JSONL ballots and `validation.json` in the new output directory. The conversion does not adjudicate any answer. If the folder already exists, retain the existing snapshot and verify it rather than overwriting it.

## Repository submission and data handling

The Task 6 submission includes the blank annotation template, three completed pseudonymized annotation workbooks, validation utility and this methodology document. Publishing the workbook materials is intended to support transparency and inspection of the submitted judgments. Public release is conditional on confirming that consent and applicable research ethics requirements permit publication of individual ratings, and on checking the workbooks for identifying information (including document properties, comments and hidden content). These checks are the coordinator's responsibility and are not established by the technical validator.

| Repository path | Purpose |
| --- | --- |
| `validate_task6.py` | Workbook validation and JSONL conversion utility. |
| `docs/Prepare and annotate the development set mds/TASK6_ANNOTATION.md` | Task 6 collection and validation documentation. |
| `data/annotation/annotator/Development_Annotation_Sheet.xlsx` | Blank annotation template. |
| `data/annotation/annotator/completed/Development_Annotation_Sheet_R01.xlsx` | First completed workbook. |
| `data/annotation/annotator/completed/Development_Annotation_Sheet_R02.xlsx` | Second completed workbook. |
| `data/annotation/annotator/completed/Development_Annotation_Sheet_R03.xlsx` | Third completed workbook. |

The original submissions are retained privately and unchanged. The internal A/B mapping, coordinator manifest, OA scoring inputs, individual converted JSONL ballots, validation report and personal reviewer records remain outside the public repository. The workbook materials contain the displayed cases and integrity hashes, not the explicit original/edited mapping. Keep any future blinded annotation cohort isolated from these published materials. Publication is not a guarantee against reconstruction of candidate identities from other research materials.

## Completion and handoff

Task 6 technical collection and conversion are complete for the supplied files. The independent-human collection criterion may be marked complete only if the coordinator can substantiate it from actual collection records; do not describe AI-generated or AI-assisted judgments as independent human judgments. If this criterion cannot be substantiated, keep the data as provisional pilot submissions and collect eligible human judgments separately.

Before submitting the pull request, confirm the publication permissions and privacy checks above, run the validator against the completed workbook directory, run the existing repository tests (`python -m unittest discover -q`), and inspect the staged file list. Stage only the six listed deliverables. Do not stage confidential coordinator artifacts or unrelated changes.

Task 7 will analyze agreement and disagreements using the validated JSONL ballots while preserving the original ratings before any discussion. Computed majority summaries are not adjudicated human labels.
