# Harness Task 1 — Define the shared evaluation and operational cue rubric

**Related issue:** #1 — Build, annotate, and evaluate the cue-aware harness.

**Scope:** New harness implementation built from the completed development annotation phase on `main`. No dependency on earlier harness Task 1–3 branches. Task 1 defines the rubric and offline pair-evaluation contract; subsequent tasks implement detector, evidence validation and routing.

## 1. Objective

Preserve identical evaluation criteria for human reviewers and a direct LLM evaluator, and define the three target cue categories for context-aware regulation: ongoing relationship and availability, conversational memory, and ordinary warmth. Include appropriate wording, meaningful correction cases and cases to hold for review.

## 2. Authoritative common rubric

`data/REVIEWER_GUIDE.md` is the existing human annotation guide and authoritative shared evaluator rubric. The LLM request reads it verbatim and checks its normalized UTF-8 SHA-256 (`48f1d3b10c2fea282f526b82ab2a257b7457e53b16cdd9322fdb4f7d08b4c543`). The original questions, capability assumptions and answer categories are unchanged.

| Judgment | Canonical values |
| --- | --- |
| `preference` | A, B, tie, cannot_judge |
| `cue_needs_correction` | A, B, both, neither, cannot_judge |
| `content_preserved` | JSON true, false, null |

The simulated chatbot can respond within the current chat, cannot see earlier sessions, initiate a check-in or guarantee future availability. Ordinary acknowledgement can fit the conversation. Preference is distinct from need for correction. Different wording may preserve the same advice, facts and caveats.

## 3. Operational rubric

`rubric/cue_rubric_v1.md` defines the three cue categories, evidence-status meanings, appropriate and inappropriate examples, uncertain-history handling and pre-OA keep/edit/hold policy requirements. The operational rubric is a specification for the proposed architecture, not an additional rubric for direct human–LLM annotation. Its synthetic examples are calibration illustrations only and contain no study answers or reviewer results.

The structured detector will examine one candidate in Task 2. Task 3 will validate evidence and implement deterministic actions. The pairwise evaluator examines both candidates; its three judgments cannot be inferred directly from a single-candidate cue output. The existing OA protocol is not modified. HumT remains a separate comparator.

## 4. Files

| Path | Purpose |
| --- | --- |
| `rubric/cue_rubric_v1.md` | Operational definitions, examples and hold conditions |
| `rubric/shared_pair_rubric_v1.md` | Shared evaluation contract and comparison rules |
| `rubric/pair_judgment_schema_v1.json` | Strict three-field model output schema |
| `evaluation/pair_judge.py` | Offline request construction, validation, and comparison of complete ballots |
| `evaluation/test_pair_judge.py` | Five offline regression tests |
| `docs/Build the harness mds/TASK1_CUE_RUBRIC.md` | This implementation and submission record |

The Python files and output schema are identical to the already-tested shared-rubric alignment implementation. The two rubric documents and this record establish the full Task 1 contract. No model scores, original/edited labels, human ballots or study mapping are supplied in direct LLM requests. The host validates the canonical pair hash and attaches IDs locally. Provider failures and abstentions are distinct. The offline comparator requires complete validated ballots and reports exact agreement and comparable coverage separately for each judgment, against individual reviewers and computational majority; it does not assert human provenance or adjudication.

## 5. Verification and reproduction

From repository root (PowerShell):

```powershell
$env:PYTHONUTF8 = "1"
python -m unittest evaluation.test_pair_judge -v
python -m unittest discover -v
```

The user-reported local run of the unchanged pairwise code passed all five new tests and the five existing repository tests (10 total). The full suite should be rerun after placing the final files. The new tests cover the pinned guide and allowlisted request, changed pair rejection, exact judgment values, provider failures and duplicate JSON keys, ties/abstentions and false content-preservation values. Task 1 defines synthetic cue examples; executable detector and routing fixtures belong to Task 4.

No live LLM calls, human agreement performance measurements or held-out evaluations are performed by Task 1. No changes to the frozen development cases, original reviewer guide or submitted annotations are required.

## 6. Acceptance and next task

- Three target cue categories defined with appropriate wording, correction examples and hold conditions.
- Original human rubric reused verbatim for direct LLM pair judgments.
- Identical judgment schema, input integrity checks and offline comparison contract established.
- Operational cues, pairwise judgments and OA kept separate.
- Original frozen materials unchanged; no old harness branch dependencies.

After review and merge, Task 2 will implement structured single-candidate cue output from scratch, including exact span, cue type, implied claim, evidence reference and status. Task 3 will implement evidence checks and routing. The final held-out protocol is not yet frozen; model settings, live execution and evaluation rules must be finalized before held-out inference.
